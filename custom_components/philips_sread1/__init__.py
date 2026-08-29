"""Philips SREAD1 custom integration."""

from homeassistant.const import CONF_HOST, CONF_TOKEN, Platform
from homeassistant.core import HomeAssistant

from .const import MIIO_TIMEOUT
from .coordinator import PhilipsSread1ConfigEntry, PhilipsSread1Coordinator
from .miio_client import PhilipsSread1MiIOClient

PLATFORMS: list[Platform] = [Platform.LIGHT]


async def async_setup_entry(
    hass: HomeAssistant, entry: PhilipsSread1ConfigEntry
) -> bool:
    """Set up Philips SREAD1 from a config entry."""
    client = PhilipsSread1MiIOClient(
        entry.data[CONF_HOST], entry.data[CONF_TOKEN], timeout=MIIO_TIMEOUT
    )
    coordinator = PhilipsSread1Coordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: PhilipsSread1ConfigEntry
) -> bool:
    """Unload a Philips SREAD1 config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
