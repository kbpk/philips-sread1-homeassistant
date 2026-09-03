"""Constants for the Philips SREAD1 integration."""

from enum import StrEnum
from typing import Final

DOMAIN: Final = "philips_sread1"
MODEL: Final = "philips.light.sread1"
NAME: Final = "Philips EyeCare Smart Lamp 2"

MIIO_PORT: Final = 54321
MIIO_TIMEOUT: Final = 5.0
MIIO_HANDSHAKE_TIMEOUT: Final = 1.0
MIIO_REQUEST_ATTEMPTS: Final = 3
MIIO_RETRY_DELAY_SECONDS: Final = 0.35
POLL_INTERVAL_SECONDS: Final = 5
POLL_BACKOFF_INTERVAL_SECONDS: Final = 15
POLL_FAILURE_GRACE_SECONDS: Final = 60

CONF_POLL_INTERVAL: Final = "poll_interval"
CONF_REQUEST_TIMEOUT: Final = "request_timeout"
CONF_HANDSHAKE_TIMEOUT: Final = "handshake_timeout"
CONF_REQUEST_ATTEMPTS: Final = "request_attempts"
CONF_RETRY_DELAY: Final = "retry_delay"
CONF_AVAILABILITY_GRACE: Final = "availability_grace"


class MiIOPowerState(StrEnum):
    """Power values used by the SREAD1 MiIO protocol."""

    OFF = "off"
    ON = "on"


class Sread1Method(StrEnum):
    """Supported SREAD1 MiIO methods."""

    GET_PROPERTIES = "get_prop"
    SET_POWER = "set_power"
    SET_BRIGHTNESS = "set_bright"
    SET_AMBIENT_POWER = "enable_amb"
    SET_AMBIENT_BRIGHTNESS = "set_amb_bright"
    SET_EYECARE = "set_eyecare"
    SET_SMART_NIGHT_LIGHT = "enable_bl"


class Sread1Property(StrEnum):
    """Properties requested from the SREAD1 firmware."""

    POWER = "power"
    BRIGHTNESS = "bright"
    NOTIFY_STATUS = "notifystatus"
    AMBIENT_POWER = "ambstatus"
    AMBIENT_BRIGHTNESS = "ambvalue"
    EYECARE = "eyecare"
    SCENE_NUMBER = "scene_num"
    SMART_NIGHT_LIGHT = "bls"
    DVALUE = "dvalue"


# MiIO returns get_prop values positionally, so keep this tuple explicit and in
# exactly the same order expected by PhilipsSread1Properties.from_result().
SREAD1_STATUS_PROPERTIES: Final[tuple[Sread1Property, ...]] = (
    Sread1Property.POWER,
    Sread1Property.BRIGHTNESS,
    Sread1Property.NOTIFY_STATUS,
    Sread1Property.AMBIENT_POWER,
    Sread1Property.AMBIENT_BRIGHTNESS,
    Sread1Property.EYECARE,
    Sread1Property.SCENE_NUMBER,
    Sread1Property.SMART_NIGHT_LIGHT,
    Sread1Property.DVALUE,
)

DEVICE_BRIGHTNESS_MIN: Final = 1
DEVICE_BRIGHTNESS_MAX: Final = 100
DEVICE_BRIGHTNESS_SCALE: Final = (
    DEVICE_BRIGHTNESS_MIN,
    DEVICE_BRIGHTNESS_MAX,
)
