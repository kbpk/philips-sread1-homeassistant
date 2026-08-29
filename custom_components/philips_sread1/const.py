"""Constants for the Philips SREAD1 integration."""

from typing import Final

DOMAIN: Final = "philips_sread1"
MODEL: Final = "philips.light.sread1"
NAME: Final = "Philips SREAD1"

MIIO_PORT: Final = 54321
MIIO_TIMEOUT: Final = 5.0
POLL_INTERVAL_SECONDS: Final = 15

PROPERTY_POWER: Final = "power"
PROPERTY_BRIGHTNESS: Final = "bright"
SREAD1_STATUS_PROPERTIES: Final = (
    PROPERTY_POWER,
    PROPERTY_BRIGHTNESS,
    "notifystatus",
    "ambstatus",
    "ambvalue",
    "eyecare",
    "scene_num",
    "bls",
    "dvalue",
)

METHOD_GET_PROPERTIES: Final = "get_prop"
METHOD_SET_POWER: Final = "set_power"
METHOD_SET_BRIGHTNESS: Final = "set_bright"

DEVICE_BRIGHTNESS_MIN: Final = 1
DEVICE_BRIGHTNESS_MAX: Final = 100
DEVICE_BRIGHTNESS_SCALE: Final = (
    DEVICE_BRIGHTNESS_MIN,
    DEVICE_BRIGHTNESS_MAX,
)
