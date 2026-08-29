#!/usr/bin/env python3
"""Provision and verify a Philips SREAD1 without requiring Internet access.

Run this while connected to the lamp's setup access point. The program validates
the setup token, sends Wi-Fi credentials, waits for the computer and lamp to
return to the normal LAN, and then validates local control using the same token.
"""

from __future__ import annotations

import getpass
import hashlib
import hmac
import json
import os
import secrets
import socket
import struct
import time
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

AP_HOST = "192.168.4.1"
PORT = 54321
SOCKET_TIMEOUT = 3.0
LAN_WAIT_SECONDS = 240
TOKEN_FILE = Path(__file__).resolve().parents[1] / ".philips_sread1_token"

HELLO_PACKET = bytes.fromhex(
    "21310020ffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
)
MAGIC = 0x2131
HEADER_SIZE = 32


class MiIOError(Exception):
    """Base diagnostic protocol error."""


class MiIOTimeout(MiIOError):
    """The device did not answer in time."""


class MiIOInvalidToken(MiIOError):
    """The device rejected the authenticated packet."""


def md5(data: bytes) -> bytes:
    """Return the MD5 digest required by MiIO."""
    return hashlib.md5(data, usedforsecurity=False).digest()


def key_and_iv(token: bytes) -> tuple[bytes, bytes]:
    """Derive the AES key and IV from a MiIO token."""
    key = md5(token)
    return key, md5(key + token)


def encrypt(plaintext: bytes, token: bytes) -> bytes:
    """Encrypt and pad a MiIO JSON payload."""
    key, iv = key_and_iv(token)
    padder = padding.PKCS7(128).padder()
    padded = padder.update(plaintext) + padder.finalize()
    encryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
    return encryptor.update(padded) + encryptor.finalize()


def decrypt(ciphertext: bytes, token: bytes) -> bytes:
    """Decrypt and unpad a MiIO JSON payload."""
    if not ciphertext or len(ciphertext) % 16:
        raise MiIOError("invalid encrypted payload length")
    key, iv = key_and_iv(token)
    decryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
    padded = decryptor.update(ciphertext) + decryptor.finalize()
    unpadder = padding.PKCS7(128).unpadder()
    try:
        return unpadder.update(padded) + unpadder.finalize()
    except ValueError as err:
        raise MiIOInvalidToken("invalid PKCS#7 padding") from err


def parse_header(
    packet: bytes, *, allow_truncated_rejection: bool = False
) -> tuple[bytes, int, bytes, bytes]:
    """Parse a MiIO packet header."""
    if len(packet) < HEADER_SIZE:
        raise MiIOError(f"packet too short: {len(packet)} bytes")
    magic, declared_length = struct.unpack(">HH", packet[:4])
    if magic != MAGIC:
        raise MiIOError(f"invalid magic: 0x{magic:04x}")
    if declared_length != len(packet):
        if allow_truncated_rejection and len(packet) == HEADER_SIZE:
            raise MiIOInvalidToken(
                f"header-only rejection (declared {declared_length} bytes)"
            )
        raise MiIOError(
            f"packet length mismatch: header={declared_length}, actual={len(packet)}"
        )
    return (
        packet[8:12],
        struct.unpack(">I", packet[12:16])[0],
        packet[16:32],
        packet[32:],
    )


def handshake(
    sock: socket.socket, *, reveal_token: bool
) -> tuple[bytes, int, bytes | None]:
    """Perform a handshake and optionally read an unprovisioned token."""
    try:
        sock.send(HELLO_PACKET)
        packet = sock.recv(4096)
    except TimeoutError as err:
        raise MiIOTimeout("handshake timeout") from err

    device_id, timestamp, checksum_or_token, encrypted = parse_header(packet)
    if encrypted:
        raise MiIOError("handshake unexpectedly contains a payload")
    if device_id in (bytes(4), bytes([255]) * 4):
        raise MiIOError("invalid device ID")

    token: bytes | None = None
    if reveal_token:
        if checksum_or_token in (bytes(16), bytes([255]) * 16):
            raise MiIOError("the setup handshake did not reveal a token")
        token = checksum_or_token
    return device_id, timestamp, token


def build_packet(
    device_id: bytes,
    timestamp: int,
    token: bytes,
    request_id: int,
    method: str,
    params: Any,
) -> bytes:
    """Build one authenticated MiIO request."""
    payload = {
        "id": request_id,
        "method": method,
        "params": params,
    }
    plaintext = (
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
        + b"\x00"
    )
    encrypted = encrypt(plaintext, token)
    header = struct.pack(
        ">HHI4sI",
        MAGIC,
        HEADER_SIZE + len(encrypted),
        0,
        device_id,
        timestamp,
    )
    return header + md5(header + token + encrypted) + encrypted


def parse_response(
    packet: bytes, token: bytes, device_id: bytes, request_id: int
) -> dict[str, Any]:
    """Authenticate, decrypt, and decode a matching response."""
    response_device_id, _timestamp, checksum, encrypted = parse_header(
        packet, allow_truncated_rejection=True
    )
    if response_device_id != device_id:
        raise MiIOError("response device ID does not match")
    if not encrypted:
        raise MiIOInvalidToken("response does not contain a payload")
    expected = md5(packet[:16] + token + encrypted)
    if not hmac.compare_digest(checksum, expected):
        raise MiIOInvalidToken("response checksum does not match")

    plaintext = decrypt(encrypted, token).rstrip(b"\x00")
    try:
        response = json.loads(plaintext.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as err:
        raise MiIOError("response is not valid JSON") from err
    if not isinstance(response, dict):
        raise MiIOError("response JSON is not an object")
    if response.get("id") != request_id:
        raise MiIOError(
            f"response ID mismatch: expected={request_id}, got={response.get('id')}"
        )
    return response


def request(
    host: str,
    token: bytes,
    method: str,
    params: Any,
    *,
    timestamp_offset: int = 1,
    timeout: float = SOCKET_TIMEOUT,
) -> dict[str, Any]:
    """Perform a fresh handshake followed by one authenticated request."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout)
        try:
            sock.connect((host, PORT))
        except OSError as err:
            raise MiIOError(f"could not open UDP connection to {host}:{PORT}") from err

        device_id, timestamp, _hidden_token = handshake(sock, reveal_token=False)
        request_id = secrets.randbelow(2_000_000_000) + 1
        packet = build_packet(
            device_id,
            timestamp + timestamp_offset,
            token,
            request_id,
            method,
            params,
        )
        try:
            sock.send(packet)
            response_packet = sock.recv(4096)
        except TimeoutError as err:
            raise MiIOTimeout(f"{method} timeout") from err
        return parse_response(response_packet, token, device_id, request_id)


def discover_setup_device() -> tuple[str, bytes, bytes]:
    """Read device ID and token from the lamp's setup access point."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(SOCKET_TIMEOUT)
        sock.connect((AP_HOST, PORT))
        device_id, _timestamp, token = handshake(sock, reveal_token=True)
    assert token is not None
    return device_id.hex(), device_id, token


def response_result(response: dict[str, Any]) -> Any:
    """Return a result or raise a readable device error."""
    if "error" in response:
        raise MiIOError(f"device error: {response['error']!r}")
    if "result" not in response:
        raise MiIOError("response has no result")
    return response["result"]


def save_token(token: bytes) -> None:
    """Save the token with owner-only permissions and never print its value."""
    TOKEN_FILE.write_text(token.hex() + "\n", encoding="ascii")
    os.chmod(TOKEN_FILE, 0o600)


def prompt() -> tuple[str, str, str, int | None, bool]:
    """Collect configuration without echoing the Wi-Fi password."""
    print("Philips SREAD1 offline provisioning + LAN validation")
    print(f"Connect this computer to the lamp AP before continuing ({AP_HOST}).")
    input("Press Enter when connected... ")
    ssid = input("Target Wi-Fi SSID: ").strip()
    if not ssid:
        raise SystemExit("SSID must not be empty")
    password = getpass.getpass("Target Wi-Fi password (hidden): ")
    lan_host = input("Expected lamp LAN IP or hostname (required): ").strip()
    if not lan_host:
        raise SystemExit("Lamp LAN IP or hostname must not be empty")
    uid_text = input("Mi Home numeric UID [auto/0]: ").strip()
    if uid_text and (not uid_text.isdecimal() or int(uid_text) < 0):
        raise SystemExit("UID must be a non-negative decimal number")
    uid_override = int(uid_text) if uid_text else None
    turn_off_answer = input("Turn the lamp OFF after successful LAN test? [Y/n]: ")
    turn_off = turn_off_answer.strip().lower() not in {"n", "no"}
    return ssid, password, lan_host, uid_override, turn_off


def main() -> int:
    """Run the complete offline-capable diagnostic flow."""
    ssid, password, lan_host, uid_override, turn_off = prompt()

    print("\n[1/4] Reading setup handshake...")
    try:
        device_id_hex, _device_id, token = discover_setup_device()
    except MiIOError as err:
        print(f"FAILED: {err}")
        return 2
    print(f"OK: device_id={device_id_hex}; setup token captured (not displayed)")
    save_token(token)
    print(f"Token saved with mode 0600: {TOKEN_FILE}")

    print("\n[2/4] Validating token with get_prop while still on the lamp AP...")
    try:
        ap_state = response_result(
            request(AP_HOST, token, "get_prop", ["power", "bright"])
        )
    except MiIOError as err:
        print(f"FAILED: setup token cannot control the lamp in AP mode: {err}")
        return 3
    print(f"OK: AP state={ap_state!r}")

    discovered_uid = 0
    try:
        info = response_result(request(AP_HOST, token, "miIO.info", []))
        if isinstance(info, dict):
            discovered_uid_value = info.get("uid")
            if isinstance(discovered_uid_value, int) and discovered_uid_value >= 0:
                discovered_uid = discovered_uid_value
            safe_info = {
                key: info[key]
                for key in ("model", "fw_ver", "hw_ver", "mac")
                if key in info
            }
            safe_info["has_nonzero_uid"] = discovered_uid > 0
            print(f"OK: miIO.info={safe_info!r}")
        else:
            print(f"WARNING: miIO.info returned {type(info).__name__}, continuing")
    except MiIOError as err:
        print(f"WARNING: miIO.info failed ({err}); continuing")

    config_uid = uid_override if uid_override is not None else discovered_uid
    uid_source = "entered value" if uid_override is not None else "miIO.info/default"
    print(f"Config UID source: {uid_source}; nonzero={config_uid > 0}")

    print("\n[3/4] Sending miIO.config_router...")
    input(
        "Ensure the lamp is blocked from WAN and from gateway DNS on TCP/UDP 53 "
        "while DHCP, LAN, and UDP 54321 remain allowed. Alternatively disconnect "
        "the target router's WAN now. Press Enter to provision... "
    )
    try:
        config_result = response_result(
            request(
                AP_HOST,
                token,
                "miIO.config_router",
                {"ssid": ssid, "passwd": password, "uid": config_uid},
                timestamp_offset=0,
                timeout=5.0,
            )
        )
    except MiIOError as err:
        print(f"FAILED: provisioning request failed: {err}")
        return 4
    finally:
        password = ""

    if config_result not in (0, "ok", "OK", ["ok"], ["OK"]):
        print(f"FAILED: unexpected config_router result={config_result!r}")
        return 5
    print(f"OK: config_router accepted with result={config_result!r}")

    print("\n[4/4] Waiting for LAN control...")
    print(
        "The lamp AP will disappear. Reconnect this computer to the target Wi-Fi "
        "if it does not reconnect automatically. This program keeps running offline."
    )
    deadline = time.monotonic() + LAN_WAIT_SECONDS
    attempt = 0
    invalid_token_rejections = 0
    last_error = ""
    while time.monotonic() < deadline:
        attempt += 1
        try:
            lan_state = response_result(
                request(lan_host, token, "get_prop", ["power", "bright"])
            )
            print(f"OK: LAN token accepted; state={lan_state!r}")
            break
        except MiIOInvalidToken as err:
            invalid_token_rejections += 1
            print(f"LAN rejected the setup token ({invalid_token_rejections}/3): {err}")
            if invalid_token_rejections >= 3:
                print("FAILED: three authenticated LAN requests were rejected")
                print(
                    "The token works in AP mode but changes during the Wi-Fi "
                    "transition."
                )
                return 6
            time.sleep(2)
        except MiIOError as err:
            error_text = f"{type(err).__name__}: {err}"
            if error_text != last_error or attempt % 5 == 0:
                remaining = max(0, int(deadline - time.monotonic()))
                print(f"Waiting ({remaining}s left): {error_text}")
                last_error = error_text
            time.sleep(3)
    else:
        print("FAILED: the setup token was not accepted on LAN within the time limit")
        print("The token is valid in AP mode but changes during the Wi-Fi transition.")
        return 6

    print(
        "IMPORTANT: keep this lamp blocked from WAN and gateway DNS (TCP/UDP 53) "
        "while allowing DHCP, LAN, and UDP 54321. On the tested firmware, DNS/cloud "
        "access changes the AP-derived token."
    )

    if not turn_off:
        print("LAN validation succeeded; leaving lamp state unchanged.")
        return 0

    print("Sending set_power OFF...")
    try:
        off_result = response_result(request(lan_host, token, "set_power", ["off"]))
        if off_result not in (0, "ok", "OK", ["ok"], ["OK"]):
            raise MiIOError(f"unexpected set_power result={off_result!r}")
        time.sleep(0.5)
        final_state = response_result(
            request(lan_host, token, "get_prop", ["power", "bright"])
        )
    except MiIOError as err:
        print(f"FAILED: LAN worked, but OFF verification failed: {err}")
        return 7

    print(f"SUCCESS: OFF accepted; final state={final_state!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
