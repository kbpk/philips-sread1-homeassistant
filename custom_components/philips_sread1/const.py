"""Constants for the Philips SREAD1 integration."""

from typing import Final

DOMAIN: Final = "philips_sread1"
MODEL: Final = "philips.light.sread1"
NAME: Final = "Philips SREAD1"

MIIO_PORT: Final = 54321
MIIO_TIMEOUT: Final = 5.0
MIIO_HANDSHAKE_TIMEOUT: Final = 1.0
MIIO_REQUEST_ATTEMPTS: Final = 3
MIIO_RETRY_DELAY_SECONDS: Final = 0.35
POLL_INTERVAL_SECONDS: Final = 15

PROPERTY_POWER: Final = "power"
PROPERTY_BRIGHTNESS: Final = "bright"
PROPERTY_AMBIENT_POWER: Final = "ambstatus"
PROPERTY_AMBIENT_BRIGHTNESS: Final = "ambvalue"
PROPERTY_EYECARE: Final = "eyecare"
SREAD1_STATUS_PROPERTIES: Final = (
    PROPERTY_POWER,
    PROPERTY_BRIGHTNESS,
    "notifystatus",
    PROPERTY_AMBIENT_POWER,
    PROPERTY_AMBIENT_BRIGHTNESS,
    PROPERTY_EYECARE,
    "scene_num",
    "bls",
    "dvalue",
)

METHOD_GET_PROPERTIES: Final = "get_prop"
METHOD_SET_POWER: Final = "set_power"
METHOD_SET_BRIGHTNESS: Final = "set_bright"
METHOD_SET_AMBIENT_POWER: Final = "enable_amb"
METHOD_SET_AMBIENT_BRIGHTNESS: Final = "set_amb_bright"
METHOD_SET_EYECARE: Final = "set_eyecare"

DEVICE_BRIGHTNESS_MIN: Final = 1
DEVICE_BRIGHTNESS_MAX: Final = 100
DEVICE_BRIGHTNESS_SCALE: Final = (
    DEVICE_BRIGHTNESS_MIN,
    DEVICE_BRIGHTNESS_MAX,
)
