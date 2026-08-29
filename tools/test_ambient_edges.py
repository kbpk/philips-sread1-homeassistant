#!/usr/bin/env python3
"""Exercise SREAD1 remembered-ambient edge cases and restore lamp state."""

from __future__ import annotations

import argparse
import getpass
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from provision_and_test import MiIOError, MiIOTimeout, request, response_result

STATUS_PROPERTIES = (
    "power",
    "bright",
    "notifystatus",
    "ambstatus",
    "ambvalue",
    "eyecare",
    "scene_num",
    "bls",
    "dvalue",
)
DEFAULT_TOKEN_FILE = Path(__file__).resolve().parents[1] / ".philips_sread1_token"
COMMAND_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 0.4
COMMAND_SETTLE_SECONDS = 0.4


class EdgeTestFailure(Exception):
    """A tested firmware transition did not produce the expected state."""


@dataclass(frozen=True, slots=True)
class LampState:
    """Relevant raw SREAD1 properties."""

    power: str
    brightness: int
    ambient_power: str
    ambient_brightness: int
    eyecare: str

    @classmethod
    def from_result(cls, result: Any) -> LampState:
        """Validate and map a positional get_prop response."""
        if not isinstance(result, list) or len(result) < 6:
            raise MiIOError(f"unexpected get_prop result: {result!r}")

        power, brightness, _notify, ambient_power, ambient_brightness, eyecare = result[
            :6
        ]
        for name, value in (
            ("power", power),
            ("ambstatus", ambient_power),
            ("eyecare", eyecare),
        ):
            if value not in ("on", "off"):
                raise MiIOError(f"unexpected {name} value: {value!r}")
        for name, value in (
            ("bright", brightness),
            ("ambvalue", ambient_brightness),
        ):
            if isinstance(value, bool) or not isinstance(value, int):
                raise MiIOError(f"unexpected {name} value: {value!r}")

        return cls(power, brightness, ambient_power, ambient_brightness, eyecare)

    def summary(self) -> str:
        """Return a safe, concise representation for console output."""
        return (
            f"power={self.power} bright={self.brightness} "
            f"ambstatus={self.ambient_power} ambvalue={self.ambient_brightness} "
            f"eyecare={self.eyecare}"
        )


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Test remembered ambient behavior on philips.light.sread1. The test "
            "temporarily toggles both outputs and attempts to restore the complete "
            "initial state even after a failure."
        )
    )
    parser.add_argument("host", help="Lamp IPv4 address or hostname")
    parser.add_argument(
        "--token-file",
        type=Path,
        default=DEFAULT_TOKEN_FILE,
        help=(
            "File containing the 32-character MiIO token. If it does not exist, "
            "the token is requested using a hidden prompt."
        ),
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Run without the interactive state-change confirmation",
    )
    return parser.parse_args()


def load_token(token_file: Path) -> bytes:
    """Read and validate a token without displaying it."""
    if token_file.is_file():
        token_text = token_file.read_text(encoding="ascii").strip()
        print(f"Using token file: {token_file}")
    else:
        token_text = getpass.getpass("MiIO token (32 hex characters, hidden): ").strip()

    if len(token_text) != 32:
        raise MiIOError("token must contain exactly 32 hexadecimal characters")
    try:
        token = bytes.fromhex(token_text)
    except ValueError as err:
        raise MiIOError("token contains non-hexadecimal characters") from err
    if len(token) != 16:
        raise MiIOError("token must contain exactly 16 bytes")
    return token


def call(host: str, token: bytes, method: str, params: Any) -> Any:
    """Send a request with bounded retries for transient timeouts."""
    for attempt in range(1, COMMAND_ATTEMPTS + 1):
        try:
            return response_result(request(host, token, method, params))
        except MiIOTimeout:
            if attempt == COMMAND_ATTEMPTS:
                raise
            print(f"  {method}: timeout, retrying ({attempt + 1}/{COMMAND_ATTEMPTS})")
            time.sleep(RETRY_DELAY_SECONDS * attempt)
    raise RuntimeError("request retry loop exited unexpectedly")


def get_state(host: str, token: bytes) -> LampState:
    """Fetch all properties used by the edge tests."""
    return LampState.from_result(call(host, token, "get_prop", STATUS_PROPERTIES))


def set_value(
    host: str, token: bytes, method: str, value: str | int, description: str
) -> None:
    """Send a setter, validate its acknowledgement, and let state settle."""
    result = call(host, token, method, [value])
    if result not in (0, "ok", "OK", ["ok"], ["OK"]):
        raise MiIOError(f"{method} returned an unexpected result: {result!r}")
    print(f"  {description}: accepted")
    time.sleep(COMMAND_SETTLE_SECONDS)


def prepare_remembered_ambient(host: str, token: bytes) -> LampState:
    """Create power=off, ambstatus=on, eyecare=off for both tests."""
    state = get_state(host, token)
    if state.power == "off":
        set_value(host, token, "set_power", "on", "wake primary light")
        state = get_state(host, token)
    if state.eyecare == "on":
        set_value(host, token, "set_eyecare", "off", "disable EyeCare")
    set_value(host, token, "enable_amb", "on", "remember ambient ON")
    set_value(host, token, "set_power", "off", "turn primary power OFF")

    state = get_state(host, token)
    print(f"  prepared: {state.summary()}")
    if state.power != "off" or state.ambient_power != "on":
        raise EdgeTestFailure(
            "could not prepare power=off with remembered ambstatus=on"
        )
    if state.eyecare != "off":
        raise EdgeTestFailure("EyeCare remained enabled during manual ambient test")
    return state


def test_turn_on_with_brightness(host: str, token: bytes) -> None:
    """Verify the fixed brightness-plus-enable sequence from an effective OFF state."""
    print("\n[1/2] Ambient turn_on with brightness from remembered OFF state")
    prepared = prepare_remembered_ambient(host, token)
    probe_brightness = 18 if prepared.ambient_brightness == 17 else 17

    set_value(
        host,
        token,
        "set_amb_bright",
        probe_brightness,
        f"set ambient brightness to {probe_brightness}",
    )
    after_brightness = get_state(host, token)
    print(f"  after set_amb_bright: {after_brightness.summary()}")
    if after_brightness.power == "on":
        print("  observation: set_amb_bright wakes primary power on this firmware")
    else:
        print("  observation: set_amb_bright does not wake primary power")

    # This is the enable_amb call which the fixed LightEntity now performs when
    # effective ambient state is OFF, even if raw ambstatus is remembered as ON.
    set_value(host, token, "enable_amb", "on", "enable effective ambient output")
    final_state = get_state(host, token)
    print(f"  result: {final_state.summary()}")
    if (
        final_state.power != "on"
        or final_state.ambient_power != "on"
        or final_state.ambient_brightness != probe_brightness
    ):
        raise EdgeTestFailure(
            "ambient turn_on with brightness did not leave power and ambient ON"
        )
    print("  PASS")


def test_clear_remembered_ambient(host: str, token: bytes) -> None:
    """Verify ambient OFF clears ambstatus while primary power is already OFF."""
    print("\n[2/2] Clear remembered ambient while primary power is OFF")
    prepare_remembered_ambient(host, token)

    set_value(host, token, "enable_amb", "off", "clear remembered ambient")
    after_disable = get_state(host, token)
    print(f"  after enable_amb OFF: {after_disable.summary()}")
    if after_disable.ambient_power != "off":
        raise EdgeTestFailure("enable_amb OFF did not clear remembered ambstatus")
    if after_disable.power != "off":
        raise EdgeTestFailure("enable_amb OFF unexpectedly left primary power ON")

    set_value(host, token, "set_power", "on", "turn primary power ON")
    final_state = get_state(host, token)
    print(f"  result: {final_state.summary()}")
    if final_state.power != "on" or final_state.ambient_power != "off":
        raise EdgeTestFailure("ambient returned after the primary light was enabled")
    print("  PASS")


def restore_state(host: str, token: bytes, initial: LampState) -> LampState:
    """Best-effort restoration of all state modified by the tests."""
    print("\n[restore] Restoring initial lamp state")
    set_value(host, token, "set_power", "on", "wake primary light")
    set_value(host, token, "set_eyecare", "off", "disable EyeCare temporarily")
    set_value(
        host, token, "set_bright", initial.brightness, "restore primary brightness"
    )
    set_value(
        host,
        token,
        "set_amb_bright",
        initial.ambient_brightness,
        "restore ambient brightness",
    )
    set_value(host, token, "set_eyecare", initial.eyecare, "restore EyeCare")
    set_value(host, token, "enable_amb", initial.ambient_power, "restore ambient mode")
    set_value(host, token, "set_power", initial.power, "restore primary power")
    restored = get_state(host, token)
    print(f"  restored: {restored.summary()}")
    return restored


def main() -> int:
    """Run both hardware edge tests and always attempt state restoration."""
    args = parse_args()
    try:
        token = load_token(args.token_file)
    except (MiIOError, OSError) as err:
        print(f"TOKEN ERROR: {err}")
        return 1

    if not args.yes:
        answer = input(
            "This test will briefly toggle the main and ambient lights, then "
            "restore their initial state. Continue? [y/N]: "
        )
        if answer.strip().lower() not in {"y", "yes"}:
            print("Cancelled; lamp state was not changed.")
            return 0

    initial: LampState | None = None
    test_error: Exception | None = None
    restore_error: Exception | None = None
    restored: LampState | None = None

    try:
        initial = get_state(args.host, token)
        print(f"Initial state: {initial.summary()}")
        test_turn_on_with_brightness(args.host, token)
        test_clear_remembered_ambient(args.host, token)
    except (EdgeTestFailure, MiIOError, OSError) as err:
        test_error = err
        print(f"\nTEST FAILED: {type(err).__name__}: {err}")
    finally:
        if initial is not None:
            try:
                restored = restore_state(args.host, token, initial)
            except (MiIOError, OSError) as err:
                restore_error = err
                print(f"RESTORE FAILED: {type(err).__name__}: {err}")

    if restore_error is not None:
        return 4
    if restored is not None and restored != initial:
        print("WARNING: final state differs from the initial state")
        return 5
    if test_error is not None:
        return 3

    print("\nSUCCESS: both ambient edge cases passed and initial state was restored")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
