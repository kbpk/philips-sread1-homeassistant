#!/usr/bin/env python3
"""Test routed UDP access to a MiIO device without using its token."""

from __future__ import annotations

import argparse
import socket
import struct

HELLO_PACKET = bytes.fromhex(
    "21310020ffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
)
MIIO_MAGIC = 0x2131
MIIO_PORT = 54321
MIIO_HEADER_SIZE = 32


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Send an unauthenticated MiIO handshake and validate the response. "
            "No token is required or displayed."
        )
    )
    parser.add_argument("host", help="Lamp IPv4 address or hostname")
    parser.add_argument(
        "--port",
        type=int,
        default=MIIO_PORT,
        help=f"MiIO UDP port (default: {MIIO_PORT})",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=3.0,
        help="Response timeout in seconds (default: 3.0)",
    )
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    if args.timeout <= 0:
        parser.error("--timeout must be greater than zero")
    return args


def parse_handshake(packet: bytes) -> tuple[str, int]:
    """Validate a MiIO handshake response and return device ID and timestamp."""
    if len(packet) < MIIO_HEADER_SIZE:
        raise ValueError(f"response is too short ({len(packet)} bytes)")

    magic, declared_length, _reserved, device_id, timestamp = struct.unpack(
        ">HHI4sI", packet[:16]
    )
    if magic != MIIO_MAGIC:
        raise ValueError(f"unexpected MiIO magic 0x{magic:04x}")
    if declared_length != len(packet):
        raise ValueError(
            f"length mismatch: header={declared_length}, actual={len(packet)}"
        )
    if len(packet) != MIIO_HEADER_SIZE:
        raise ValueError(
            f"handshake unexpectedly contains a payload ({len(packet)} bytes)"
        )
    if device_id in (bytes(4), bytes([0xFF]) * 4):
        raise ValueError("handshake returned an invalid device ID")

    return device_id.hex(), timestamp


def main() -> int:
    """Send the handshake and print a concise diagnostic result."""
    args = parse_args()
    target = (args.host, args.port)

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp_socket:
        udp_socket.settimeout(args.timeout)
        try:
            udp_socket.connect(target)
            remote_address, remote_port = udp_socket.getpeername()
            udp_socket.send(HELLO_PACKET)
            response = udp_socket.recv(4096)
        except TimeoutError:
            print(
                f"TIMEOUT: no MiIO handshake response from "
                f"{args.host}:{args.port} after {args.timeout:g}s"
            )
            print(
                "Check VPN/firewall access to UDP destination port 54321 and "
                "automatic return traffic."
            )
            return 2
        except OSError as err:
            print(f"NETWORK ERROR: {type(err).__name__}: {err}")
            return 1

    try:
        device_id, timestamp = parse_handshake(response)
    except ValueError as err:
        print(f"INVALID RESPONSE: {err}")
        return 3

    print("MiIO handshake succeeded")
    print(f"Remote:    {remote_address}:{remote_port}")
    print(f"Packet:    {len(response)} bytes")
    print(f"Device ID: {device_id}")
    print(f"Timestamp: {timestamp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
