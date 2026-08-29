"""Small, self-contained MiIO UDP client for philips.light.sread1.

This module intentionally does not import or use python-miio.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import secrets
import socket
import struct
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from .const import (
    DEVICE_BRIGHTNESS_MAX,
    DEVICE_BRIGHTNESS_MIN,
    METHOD_GET_PROPERTIES,
    METHOD_SET_AMBIENT_BRIGHTNESS,
    METHOD_SET_AMBIENT_POWER,
    METHOD_SET_BRIGHTNESS,
    METHOD_SET_EYECARE,
    METHOD_SET_POWER,
    MIIO_HANDSHAKE_TIMEOUT,
    MIIO_PORT,
    MIIO_REQUEST_ATTEMPTS,
    MIIO_RETRY_DELAY_SECONDS,
    MIIO_TIMEOUT,
    SREAD1_STATUS_PROPERTIES,
)

_LOGGER = logging.getLogger(__name__)

_MAGIC = 0x2131
_HEADER_SIZE = 32
_HELLO_PACKET = bytes.fromhex(
    "21310020ffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
)


class MiIOError(Exception):
    """Base exception for MiIO communication errors."""


class MiIOTimeoutError(MiIOError):
    """The device did not reply before the timeout."""


class MiIOHandshakeTimeoutError(MiIOTimeoutError):
    """The device did not reply to the unauthenticated handshake."""


class MiIORequestTimeoutError(MiIOTimeoutError):
    """The device did not reply to an authenticated request."""


class MiIOConnectionError(MiIOError):
    """The UDP connection could not be created or used."""


class MiIOProtocolError(MiIOError):
    """The device returned a malformed or unexpected packet."""


class MiIOChecksumError(MiIOProtocolError):
    """A packet checksum did not match."""


class MiIOInvalidTokenError(MiIOChecksumError):
    """The response checksum indicates that the configured token is invalid."""


class MiIOJsonError(MiIOProtocolError):
    """The decrypted response was not valid MiIO JSON."""


class MiIODeviceError(MiIOError):
    """The device returned a MiIO error object."""

    def __init__(self, code: int | None, message: str) -> None:
        """Initialize a device error without exposing request credentials."""
        self.code = code
        self.message = message
        super().__init__(f"Device error {code}: {message}")


@dataclass(frozen=True, slots=True)
class MiIOHandshake:
    """Data obtained from a MiIO handshake."""

    device_id: bytes
    timestamp: int


@dataclass(frozen=True, slots=True)
class PhilipsSread1State:
    """State of the supported SREAD1 light features."""

    is_on: bool
    brightness: int
    ambient_is_on: bool
    ambient_brightness: int
    automatic_brightness_is_on: bool


def _md5(data: bytes) -> bytes:
    """Return the MD5 required by the MiIO wire protocol."""
    return hashlib.md5(data, usedforsecurity=False).digest()


def _key_and_iv(token: bytes) -> tuple[bytes, bytes]:
    """Derive the MiIO AES key and IV from a raw token."""
    key = _md5(token)
    return key, _md5(key + token)


def _encrypt(plaintext: bytes, token: bytes) -> bytes:
    """Encrypt and PKCS#7-pad a MiIO payload."""
    key, iv = _key_and_iv(token)
    padder = padding.PKCS7(algorithms.AES.block_size).padder()
    padded = padder.update(plaintext) + padder.finalize()
    encryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
    return encryptor.update(padded) + encryptor.finalize()


def _decrypt(ciphertext: bytes, token: bytes) -> bytes:
    """Decrypt and PKCS#7-unpad a MiIO payload."""
    if not ciphertext or len(ciphertext) % 16:
        raise MiIOProtocolError("Encrypted payload has an invalid length")

    key, iv = _key_and_iv(token)
    decryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
    padded = decryptor.update(ciphertext) + decryptor.finalize()
    unpadder = padding.PKCS7(algorithms.AES.block_size).unpadder()
    try:
        return unpadder.update(padded) + unpadder.finalize()
    except ValueError as err:
        raise MiIOProtocolError("Response has invalid PKCS#7 padding") from err


def _build_packet(
    device_id: bytes, timestamp: int, token: bytes, payload: dict[str, Any]
) -> bytes:
    """Build a checksummed and encrypted MiIO request packet."""
    if len(device_id) != 4:
        raise MiIOProtocolError("Device ID must contain four bytes")

    plaintext = (
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        + b"\x00"
    )
    encrypted = _encrypt(plaintext, token)
    packet_length = _HEADER_SIZE + len(encrypted)
    if packet_length > 0xFFFF:
        raise MiIOProtocolError("Request packet is too large")

    header = struct.pack(">HHI4sI", _MAGIC, packet_length, 0, device_id, timestamp)
    checksum = _md5(header + token + encrypted)
    return header + checksum + encrypted


def _parse_header(packet: bytes) -> tuple[bytes, int, bytes, bytes]:
    """Validate a MiIO packet header and return its relevant fields."""
    if len(packet) < _HEADER_SIZE:
        raise MiIOProtocolError(f"MiIO packet is too short ({len(packet)} bytes)")

    magic, declared_length = struct.unpack(">HH", packet[:4])
    if magic != _MAGIC:
        raise MiIOProtocolError(f"Invalid MiIO magic 0x{magic:04x}")
    if declared_length != len(packet):
        raise MiIOProtocolError(
            f"MiIO length mismatch: header={declared_length}, actual={len(packet)}"
        )

    device_id = packet[8:12]
    timestamp = struct.unpack(">I", packet[12:16])[0]
    checksum = packet[16:32]
    encrypted = packet[32:]
    return device_id, timestamp, checksum, encrypted


def _parse_handshake(packet: bytes) -> MiIOHandshake:
    """Parse a handshake without treating its checksum field as a token."""
    device_id, timestamp, _checksum, encrypted = _parse_header(packet)
    if encrypted:
        raise MiIOProtocolError("Handshake response unexpectedly contains a payload")
    if device_id in (b"\x00" * 4, b"\xff" * 4):
        raise MiIOProtocolError("Handshake returned an invalid device ID")
    return MiIOHandshake(device_id=device_id, timestamp=timestamp)


def _parse_response(
    packet: bytes, token: bytes, expected_device_id: bytes
) -> dict[str, Any]:
    """Validate, decrypt, and decode a normal MiIO response."""
    device_id, _timestamp, checksum, encrypted = _parse_header(packet)
    if device_id != expected_device_id:
        raise MiIOProtocolError("Response came from an unexpected MiIO device ID")
    if not encrypted:
        raise MiIOProtocolError("MiIO response does not contain a payload")

    expected_checksum = _md5(packet[:16] + token + encrypted)
    if not hmac.compare_digest(checksum, expected_checksum):
        raise MiIOInvalidTokenError(
            "Response checksum mismatch; the MiIO token is probably invalid"
        )

    plaintext = _decrypt(encrypted, token).rstrip(b"\x00")
    try:
        decoded = plaintext.decode("utf-8")
    except UnicodeDecodeError as err:
        raise MiIOJsonError("MiIO response is not valid UTF-8") from err

    try:
        payload = json.loads(decoded)
    except json.JSONDecodeError as err:
        raise MiIOJsonError("MiIO response is not valid JSON") from err
    if not isinstance(payload, dict):
        raise MiIOJsonError("MiIO response JSON is not an object")
    return payload


class PhilipsSread1MiIOClient:
    """Async facade over the blocking UDP protocol implementation."""

    def __init__(
        self,
        host: str,
        token: str | bytes,
        *,
        port: int = MIIO_PORT,
        timeout: float = MIIO_TIMEOUT,
        handshake_timeout: float = MIIO_HANDSHAKE_TIMEOUT,
        request_attempts: int = MIIO_REQUEST_ATTEMPTS,
        retry_delay: float = MIIO_RETRY_DELAY_SECONDS,
    ) -> None:
        """Initialize the client and validate the token without logging it."""
        self.host = host.strip()
        if not self.host:
            raise ValueError("Host must not be empty")

        if isinstance(token, str):
            token_text = token.strip()
            if len(token_text) != 32:
                raise ValueError(
                    "MiIO token must contain exactly 32 hexadecimal characters"
                )
            try:
                token_bytes = bytes.fromhex(token_text)
            except ValueError as err:
                raise ValueError(
                    "MiIO token must contain only hexadecimal characters"
                ) from err
        else:
            token_bytes = token

        if len(token_bytes) != 16:
            raise ValueError("MiIO token must contain exactly 16 bytes")
        if handshake_timeout <= 0:
            raise ValueError("MiIO handshake timeout must be greater than zero")
        if request_attempts < 1:
            raise ValueError("MiIO request attempts must be at least one")
        if retry_delay < 0:
            raise ValueError("MiIO retry delay must not be negative")

        self._token = token_bytes
        self._port = port
        self._timeout = timeout
        self._handshake_timeout = handshake_timeout
        self._request_attempts = request_attempts
        self._retry_delay = retry_delay
        self._request_id = secrets.randbelow(8999) + 1
        self._request_lock = asyncio.Lock()
        self._device_id: bytes | None = None

    @property
    def device_id(self) -> str | None:
        """Return the device ID learned during the latest handshake."""
        return self._device_id.hex() if self._device_id is not None else None

    async def async_handshake(self) -> MiIOHandshake:
        """Perform only a MiIO handshake."""
        async with self._request_lock:
            handshake = await asyncio.to_thread(self._handshake_sync)
            self._device_id = handshake.device_id
            return handshake

    async def async_request(
        self, method: str, params: Sequence[Any] | dict[str, Any] | None = None
    ) -> Any:
        """Send a MiIO command, retrying only transient transport failures."""
        serialized_params = (
            list(params)
            if isinstance(params, Sequence) and not isinstance(params, str)
            else params
        )
        async with self._request_lock:
            for attempt in range(1, self._request_attempts + 1):
                request_id = self._next_request_id()
                try:
                    return await asyncio.to_thread(
                        self._request_sync,
                        method,
                        serialized_params,
                        request_id,
                    )
                except (MiIOTimeoutError, MiIOConnectionError) as err:
                    if attempt == self._request_attempts:
                        raise

                    delay = self._retry_delay * attempt
                    _LOGGER.debug(
                        "Retrying transient MiIO failure host=%s method=%s "
                        "request_id=%s error=%s next_attempt=%s/%s delay=%.2fs",
                        self.host,
                        method,
                        request_id,
                        type(err).__name__,
                        attempt + 1,
                        self._request_attempts,
                        delay,
                    )
                    await asyncio.sleep(delay)

        raise RuntimeError("MiIO request retry loop exited unexpectedly")

    async def async_get_state(self) -> PhilipsSread1State:
        """Read both light sources and automatic-brightness mode."""
        result = await self.async_request(
            METHOD_GET_PROPERTIES, SREAD1_STATUS_PROPERTIES
        )
        if not isinstance(result, list) or len(result) < 6:
            raise MiIOProtocolError("get_prop returned an unexpected result")

        power = self._validate_power_property(result[0], "Power")
        brightness = self._validate_brightness_property(result[1], "Brightness")
        ambient_power = self._validate_power_property(result[3], "Ambient power")
        ambient_brightness = self._validate_brightness_property(
            result[4], "Ambient brightness"
        )
        eyecare = self._validate_power_property(result[5], "EyeCare")

        return PhilipsSread1State(
            is_on=power == "on",
            brightness=brightness,
            # The firmware reports ambstatus as a remembered request even when
            # primary power is off; the physical ambient output is then dark.
            ambient_is_on=ambient_power == "on" and power == "on",
            ambient_brightness=ambient_brightness,
            automatic_brightness_is_on=eyecare == "on",
        )

    async def async_set_power(self, turn_on: bool) -> None:
        """Set primary light power."""
        result = await self.async_request(
            METHOD_SET_POWER, ["on" if turn_on else "off"]
        )
        self._validate_ok(result, METHOD_SET_POWER)

    async def async_set_brightness(self, brightness: int) -> None:
        """Set primary light brightness in its native 1..100 range."""
        self._validate_brightness_argument(brightness)
        result = await self.async_request(METHOD_SET_BRIGHTNESS, [brightness])
        self._validate_ok(result, METHOD_SET_BRIGHTNESS)

    async def async_set_ambient_power(self, turn_on: bool) -> None:
        """Set ambient/back light power."""
        result = await self.async_request(
            METHOD_SET_AMBIENT_POWER, ["on" if turn_on else "off"]
        )
        self._validate_ok(result, METHOD_SET_AMBIENT_POWER)

    async def async_set_ambient_brightness(self, brightness: int) -> None:
        """Set ambient/back light brightness in its native 1..100 range."""
        self._validate_brightness_argument(brightness)
        result = await self.async_request(METHOD_SET_AMBIENT_BRIGHTNESS, [brightness])
        self._validate_ok(result, METHOD_SET_AMBIENT_BRIGHTNESS)

    async def async_set_automatic_brightness(self, turn_on: bool) -> None:
        """Enable or disable EyeCare automatic brightness."""
        result = await self.async_request(
            METHOD_SET_EYECARE, ["on" if turn_on else "off"]
        )
        self._validate_ok(result, METHOD_SET_EYECARE)

    def _next_request_id(self) -> int:
        """Increment the MiIO request ID, wrapping like established clients."""
        self._request_id += 1
        if self._request_id >= 9999:
            self._request_id = 1
        return self._request_id

    @staticmethod
    def _validate_ok(result: Any, method: str) -> None:
        """Validate the standard response to a setter command."""
        if result not in (["ok"], "ok"):
            raise MiIOProtocolError(f"{method} returned an unexpected result")

    @staticmethod
    def _validate_power_property(value: Any, name: str) -> str:
        """Validate a native on/off property."""
        if value not in ("on", "off"):
            raise MiIOProtocolError(f"{name} property has an unexpected value")
        return value

    @staticmethod
    def _validate_brightness_property(value: Any, name: str) -> int:
        """Validate a native brightness property."""
        if isinstance(value, bool) or not isinstance(value, int):
            raise MiIOProtocolError(f"{name} property is not an integer")
        if not DEVICE_BRIGHTNESS_MIN <= value <= DEVICE_BRIGHTNESS_MAX:
            raise MiIOProtocolError(f"{name} property is outside the supported range")
        return value

    @staticmethod
    def _validate_brightness_argument(brightness: int) -> None:
        """Validate brightness passed to a setter."""
        if isinstance(brightness, bool) or not isinstance(brightness, int):
            raise TypeError("Brightness must be an integer")
        if not DEVICE_BRIGHTNESS_MIN <= brightness <= DEVICE_BRIGHTNESS_MAX:
            raise ValueError(
                f"Brightness must be between {DEVICE_BRIGHTNESS_MIN} and "
                f"{DEVICE_BRIGHTNESS_MAX}"
            )

    def _open_socket(self) -> socket.socket:
        """Create a connected IPv4 UDP socket in the worker thread."""
        udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_socket.settimeout(self._timeout)
        try:
            udp_socket.connect((self.host, self._port))
        except OSError as err:
            udp_socket.close()
            raise MiIOConnectionError(
                f"Could not connect UDP socket to {self.host}:{self._port}"
            ) from err
        return udp_socket

    def _handshake_sync(self) -> MiIOHandshake:
        """Perform a blocking handshake; called only through asyncio.to_thread."""
        udp_socket = self._open_socket()
        try:
            return self._exchange_handshake(udp_socket)
        finally:
            udp_socket.close()

    def _exchange_handshake(self, udp_socket: socket.socket) -> MiIOHandshake:
        """Exchange a handshake on an already connected UDP socket."""
        udp_socket.settimeout(self._handshake_timeout)
        _LOGGER.debug(
            "Sending MiIO handshake host=%s port=%s timeout=%.1fs packet_length=%s",
            self.host,
            self._port,
            self._handshake_timeout,
            len(_HELLO_PACKET),
        )
        try:
            udp_socket.send(_HELLO_PACKET)
            packet = udp_socket.recv(4096)
        except TimeoutError as err:
            _LOGGER.debug("MiIO handshake timeout host=%s", self.host)
            raise MiIOHandshakeTimeoutError(
                f"Handshake timed out for {self.host}"
            ) from err
        except OSError as err:
            raise MiIOConnectionError(f"MiIO handshake failed for {self.host}") from err

        handshake = _parse_handshake(packet)
        _LOGGER.debug(
            "Parsed MiIO handshake host=%s device_id=%s timestamp=%s packet_length=%s",
            self.host,
            handshake.device_id.hex(),
            handshake.timestamp,
            len(packet),
        )
        return handshake

    def _request_sync(self, method: str, params: Any, request_id: int) -> Any:
        """Perform a full blocking handshake/request transaction."""
        udp_socket = self._open_socket()
        try:
            handshake = self._exchange_handshake(udp_socket)
            self._device_id = handshake.device_id
            payload = {
                "id": request_id,
                "method": method,
                "params": params if params is not None else [],
            }
            packet = _build_packet(
                handshake.device_id,
                handshake.timestamp + 1,
                self._token,
                payload,
            )
            _LOGGER.debug(
                "Sending MiIO request host=%s method=%s request_id=%s "
                "timeout=%.1fs packet_length=%s",
                self.host,
                method,
                request_id,
                self._timeout,
                len(packet),
            )
            try:
                udp_socket.send(packet)
            except OSError as err:
                raise MiIOConnectionError(
                    f"Could not send {method} to {self.host}"
                ) from err

            response = self._receive_matching_response(
                udp_socket, handshake.device_id, request_id, method
            )
        finally:
            udp_socket.close()

        if "error" in response:
            error = response["error"]
            if isinstance(error, dict):
                code = error.get("code") if isinstance(error.get("code"), int) else None
                message = str(error.get("message", "Unknown MiIO device error"))
            else:
                code = None
                message = "Unknown MiIO device error"
            raise MiIODeviceError(code, message)
        if "result" not in response:
            raise MiIOProtocolError("MiIO response does not contain a result")

        result = response["result"]
        item_count = len(result) if isinstance(result, (list, dict)) else 1
        _LOGGER.debug(
            "Parsed MiIO result host=%s method=%s request_id=%s "
            "result_type=%s items=%s",
            self.host,
            method,
            request_id,
            type(result).__name__,
            item_count,
        )
        return result

    def _receive_matching_response(
        self,
        udp_socket: socket.socket,
        device_id: bytes,
        request_id: int,
        method: str,
    ) -> dict[str, Any]:
        """Receive datagrams until the matching request ID arrives or time expires."""
        deadline = time.monotonic() + self._timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                _LOGGER.debug(
                    "MiIO request timeout host=%s method=%s request_id=%s",
                    self.host,
                    method,
                    request_id,
                )
                raise MiIORequestTimeoutError(f"{method} timed out for {self.host}")
            udp_socket.settimeout(remaining)
            try:
                packet = udp_socket.recv(4096)
            except TimeoutError as err:
                _LOGGER.debug(
                    "MiIO request timeout host=%s method=%s request_id=%s",
                    self.host,
                    method,
                    request_id,
                )
                raise MiIORequestTimeoutError(
                    f"{method} timed out for {self.host}"
                ) from err
            except OSError as err:
                raise MiIOConnectionError(
                    f"Could not receive {method} response from {self.host}"
                ) from err

            if (
                len(packet) == _HEADER_SIZE
                and packet[:2] == struct.pack(">H", _MAGIC)
                and struct.unpack(">H", packet[2:4])[0] > _HEADER_SIZE
                and packet[8:12] == device_id
            ):
                _LOGGER.debug(
                    "MiIO authenticated request rejected host=%s method=%s "
                    "request_id=%s packet_length=%s declared_length=%s",
                    self.host,
                    method,
                    request_id,
                    len(packet),
                    struct.unpack(">H", packet[2:4])[0],
                )
                raise MiIOInvalidTokenError(
                    "Device returned a header-only rejection; the MiIO token is "
                    "probably invalid"
                )

            response = _parse_response(packet, self._token, device_id)
            response_id = response.get("id")
            if response_id == request_id:
                _LOGGER.debug(
                    "Matched MiIO response host=%s method=%s request_id=%s "
                    "packet_length=%s",
                    self.host,
                    method,
                    request_id,
                    len(packet),
                )
                return response
            _LOGGER.debug(
                "Ignoring unmatched MiIO response host=%s method=%s "
                "request_id=%s response_id=%s packet_length=%s",
                self.host,
                method,
                request_id,
                response_id,
                len(packet),
            )
