"""Light platform for Philips SREAD1."""

from __future__ import annotations

import math
from typing import Any, ClassVar, override

from homeassistant.components.light import ATTR_BRIGHTNESS, ColorMode, LightEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util.color import brightness_to_value, value_to_brightness

from .const import DEVICE_BRIGHTNESS_SCALE, DOMAIN, MODEL, NAME
from .coordinator import PhilipsSread1ConfigEntry, PhilipsSread1Coordinator


async def async_setup_entry(
    _hass: HomeAssistant,
    entry: PhilipsSread1ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Philips SREAD1 primary light entity."""
    async_add_entities([PhilipsSread1Light(entry.runtime_data, entry)])


class PhilipsSread1Light(CoordinatorEntity[PhilipsSread1Coordinator], LightEntity):
    """Representation of the SREAD1 primary light."""

    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_has_entity_name = True
    _attr_name = None
    _attr_supported_color_modes: ClassVar[set[ColorMode]] = {ColorMode.BRIGHTNESS}

    def __init__(
        self,
        coordinator: PhilipsSread1Coordinator,
        entry: PhilipsSread1ConfigEntry,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        unique_id = entry.unique_id or coordinator.client.device_id or entry.entry_id
        self._attr_unique_id = f"{unique_id}_main"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, unique_id)},
            manufacturer="Philips",
            model=MODEL,
            name=NAME,
        )

    @property
    @override
    def is_on(self) -> bool:
        """Return whether the primary light is on."""
        return self.coordinator.data.is_on

    @property
    @override
    def brightness(self) -> int:
        """Return brightness converted from 1..100 to Home Assistant's 0..255."""
        return value_to_brightness(
            DEVICE_BRIGHTNESS_SCALE, self.coordinator.data.brightness
        )

    @override
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the primary light, optionally setting brightness."""
        if ATTR_BRIGHTNESS in kwargs:
            native_brightness = math.ceil(
                brightness_to_value(
                    DEVICE_BRIGHTNESS_SCALE,
                    kwargs[ATTR_BRIGHTNESS],
                )
            )
            await self.coordinator.async_set_brightness(native_brightness)
            return
        await self.coordinator.async_set_power(True)

    @override
    async def async_turn_off(self, **_kwargs: Any) -> None:
        """Turn off the primary light."""
        await self.coordinator.async_set_power(False)
