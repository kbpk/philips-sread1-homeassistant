"""Data update coordinator for Philips SREAD1."""

import logging
from datetime import timedelta
from typing import override

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, POLL_INTERVAL_SECONDS
from .miio_client import MiIOError, PhilipsSread1MiIOClient, PhilipsSread1State

_LOGGER = logging.getLogger(__name__)

type PhilipsSread1ConfigEntry = ConfigEntry[PhilipsSread1Coordinator]


class PhilipsSread1Coordinator(DataUpdateCoordinator[PhilipsSread1State]):
    """Coordinate polling and commands for a single SREAD1 lamp."""

    config_entry: PhilipsSread1ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: PhilipsSread1ConfigEntry,
        client: PhilipsSread1MiIOClient,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=POLL_INTERVAL_SECONDS),
            always_update=False,
        )
        self.client = client

    @override
    async def _async_update_data(self) -> PhilipsSread1State:
        """Fetch the current state of all supported lamp features."""
        try:
            return await self.client.async_get_state()
        except MiIOError as err:
            raise UpdateFailed(f"Unable to update Philips SREAD1: {err}") from err

    async def async_set_power(self, turn_on: bool) -> None:
        """Set power and immediately request authoritative state."""
        try:
            await self.client.async_set_power(turn_on)
        except MiIOError as err:
            raise HomeAssistantError(
                f"Unable to set Philips SREAD1 power: {err}"
            ) from err
        await self.async_request_refresh()

    async def async_set_brightness(self, brightness: int) -> None:
        """Set brightness and immediately request authoritative state."""
        try:
            await self.client.async_set_brightness(brightness)
        except (MiIOError, TypeError, ValueError) as err:
            raise HomeAssistantError(
                f"Unable to set Philips SREAD1 brightness: {err}"
            ) from err
        await self.async_request_refresh()

    async def async_set_ambient_power(self, turn_on: bool) -> None:
        """Set ambient/back light power and refresh authoritative state."""
        try:
            await self.client.async_set_ambient_power(turn_on)
        except MiIOError as err:
            raise HomeAssistantError(
                f"Unable to set Philips SREAD1 ambient power: {err}"
            ) from err
        await self.async_request_refresh()

    async def async_set_ambient_brightness(self, brightness: int) -> None:
        """Set ambient/back light brightness and refresh authoritative state."""
        try:
            await self.client.async_set_ambient_brightness(brightness)
        except (MiIOError, TypeError, ValueError) as err:
            raise HomeAssistantError(
                f"Unable to set Philips SREAD1 ambient brightness: {err}"
            ) from err
        await self.async_request_refresh()

    async def async_set_automatic_brightness(self, turn_on: bool) -> None:
        """Set EyeCare automatic brightness and refresh authoritative state."""
        try:
            await self.client.async_set_automatic_brightness(turn_on)
        except MiIOError as err:
            raise HomeAssistantError(
                f"Unable to set Philips SREAD1 automatic brightness: {err}"
            ) from err
        await self.async_request_refresh()
