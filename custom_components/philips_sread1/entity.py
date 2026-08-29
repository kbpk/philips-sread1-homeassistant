"""Shared entity base for Philips SREAD1."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MODEL, NAME
from .coordinator import PhilipsSread1ConfigEntry, PhilipsSread1Coordinator


class PhilipsSread1Entity(CoordinatorEntity[PhilipsSread1Coordinator]):
    """Base entity linked to the physical SREAD1 device."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: PhilipsSread1Coordinator,
        entry: PhilipsSread1ConfigEntry,
        unique_id_suffix: str,
    ) -> None:
        """Initialize shared device and unique-ID attributes."""
        super().__init__(coordinator)
        device_unique_id = (
            entry.unique_id or coordinator.client.device_id or entry.entry_id
        )
        self._attr_unique_id = f"{device_unique_id}_{unique_id_suffix}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_unique_id)},
            manufacturer="Philips",
            model=MODEL,
            name=NAME,
        )
