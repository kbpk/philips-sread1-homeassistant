"""Light platform for Philips SREAD1."""

from __future__ import annotations

from typing import Any, ClassVar, override

from homeassistant.components.light import ATTR_BRIGHTNESS, ColorMode, LightEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util.color import brightness_to_value, value_to_brightness

from .const import (
    DEVICE_BRIGHTNESS_MAX,
    DEVICE_BRIGHTNESS_MIN,
    DEVICE_BRIGHTNESS_SCALE,
)
from .coordinator import PhilipsSread1ConfigEntry, PhilipsSread1Coordinator
from .entity import PhilipsSread1Entity


async def async_setup_entry(
    _hass: HomeAssistant,
    entry: PhilipsSread1ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Philips SREAD1 primary and ambient light entities."""
    coordinator = entry.runtime_data
    async_add_entities(
        [
            PhilipsSread1Light(coordinator, entry),
            PhilipsSread1AmbientLight(coordinator, entry),
        ]
    )


def _native_brightness(kwargs: dict[str, Any]) -> int:
    """Convert Home Assistant brightness to the lamp's native scale."""
    brightness = round(
        brightness_to_value(DEVICE_BRIGHTNESS_SCALE, kwargs[ATTR_BRIGHTNESS])
    )
    return max(DEVICE_BRIGHTNESS_MIN, min(DEVICE_BRIGHTNESS_MAX, brightness))


class PhilipsSread1Light(PhilipsSread1Entity, LightEntity):
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
        super().__init__(coordinator, entry, "main")

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
            await self.coordinator.async_set_brightness(_native_brightness(kwargs))
            if not self.coordinator.data.is_on:
                await self.coordinator.async_set_power(True)
            return
        await self.coordinator.async_set_power(True)

    @override
    async def async_turn_off(self, **_kwargs: Any) -> None:
        """Turn off the primary light."""
        await self.coordinator.async_set_power(False)


class PhilipsSread1AmbientLight(PhilipsSread1Entity, LightEntity):
    """Representation of the SREAD1 ambient/back light."""

    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_supported_color_modes: ClassVar[set[ColorMode]] = {ColorMode.BRIGHTNESS}
    _attr_translation_key = "ambient_light"

    def __init__(
        self,
        coordinator: PhilipsSread1Coordinator,
        entry: PhilipsSread1ConfigEntry,
    ) -> None:
        """Initialize the ambient-light entity."""
        super().__init__(coordinator, entry, "ambient")

    @property
    @override
    def is_on(self) -> bool:
        """Return whether the ambient/back light is on."""
        return self.coordinator.data.ambient_is_on

    @property
    @override
    def brightness(self) -> int:
        """Return ambient brightness converted to Home Assistant's 0..255."""
        return value_to_brightness(
            DEVICE_BRIGHTNESS_SCALE, self.coordinator.data.ambient_brightness
        )

    @override
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the ambient light, optionally setting brightness."""
        if ATTR_BRIGHTNESS in kwargs:
            await self.coordinator.async_set_ambient_brightness(
                _native_brightness(kwargs)
            )
            if not self.coordinator.data.ambient_is_on:
                await self.coordinator.async_set_ambient_power(True)
            return
        await self.coordinator.async_set_ambient_power(True)

    @override
    async def async_turn_off(self, **_kwargs: Any) -> None:
        """Turn off the ambient/back light."""
        await self.coordinator.async_set_ambient_power(False)
