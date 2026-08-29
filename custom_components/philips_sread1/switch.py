"""Switch platform for Philips SREAD1."""

from __future__ import annotations

from typing import Any, override

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import PhilipsSread1ConfigEntry, PhilipsSread1Coordinator
from .entity import PhilipsSread1Entity


async def async_setup_entry(
    _hass: HomeAssistant,
    entry: PhilipsSread1ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Philips SREAD1 automatic-brightness switch."""
    async_add_entities(
        [PhilipsSread1AutomaticBrightnessSwitch(entry.runtime_data, entry)]
    )


class PhilipsSread1AutomaticBrightnessSwitch(PhilipsSread1Entity, SwitchEntity):
    """Control the EyeCare automatic-brightness mode."""

    _attr_translation_key = "automatic_brightness"

    def __init__(
        self,
        coordinator: PhilipsSread1Coordinator,
        entry: PhilipsSread1ConfigEntry,
    ) -> None:
        """Initialize the automatic-brightness switch."""
        super().__init__(coordinator, entry, "automatic_brightness")

    @property
    @override
    def is_on(self) -> bool:
        """Return whether EyeCare automatic brightness is enabled."""
        return self.coordinator.data.automatic_brightness_is_on

    @override
    async def async_turn_on(self, **_kwargs: Any) -> None:
        """Enable EyeCare automatic brightness."""
        await self.coordinator.async_set_automatic_brightness(True)

    @override
    async def async_turn_off(self, **_kwargs: Any) -> None:
        """Disable EyeCare automatic brightness."""
        await self.coordinator.async_set_automatic_brightness(False)
