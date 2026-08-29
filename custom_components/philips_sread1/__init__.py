"""Philips SREAD1 custom integration."""

from homeassistant.const import CONF_HOST, CONF_TOKEN, Platform
from homeassistant.core import HomeAssistant

from .const import (
    CONF_AVAILABILITY_GRACE,
    CONF_HANDSHAKE_TIMEOUT,
    CONF_POLL_INTERVAL,
    CONF_REQUEST_ATTEMPTS,
    CONF_REQUEST_TIMEOUT,
    CONF_RETRY_DELAY,
    MIIO_HANDSHAKE_TIMEOUT,
    MIIO_REQUEST_ATTEMPTS,
    MIIO_RETRY_DELAY_SECONDS,
    MIIO_TIMEOUT,
    NAME,
    POLL_FAILURE_GRACE_SECONDS,
    POLL_INTERVAL_SECONDS,
)
from .coordinator import PhilipsSread1ConfigEntry, PhilipsSread1Coordinator
from .miio_client import PhilipsSread1MiIOClient

PLATFORMS: list[Platform] = [Platform.LIGHT, Platform.SWITCH]


async def async_setup_entry(
    hass: HomeAssistant, entry: PhilipsSread1ConfigEntry
) -> bool:
    """Set up Philips SREAD1 from a config entry."""
    options = entry.options
    client = PhilipsSread1MiIOClient(
        entry.data[CONF_HOST],
        entry.data[CONF_TOKEN],
        timeout=options.get(CONF_REQUEST_TIMEOUT, MIIO_TIMEOUT),
        handshake_timeout=options.get(CONF_HANDSHAKE_TIMEOUT, MIIO_HANDSHAKE_TIMEOUT),
        request_attempts=options.get(CONF_REQUEST_ATTEMPTS, MIIO_REQUEST_ATTEMPTS),
        retry_delay=options.get(CONF_RETRY_DELAY, MIIO_RETRY_DELAY_SECONDS),
    )
    legacy_title = f"Philips SREAD1 ({entry.data[CONF_HOST]})"
    if entry.title == legacy_title:
        hass.config_entries.async_update_entry(
            entry, title=f"{NAME} ({entry.data[CONF_HOST]})"
        )
    coordinator = PhilipsSread1Coordinator(
        hass,
        entry,
        client,
        poll_interval=options.get(CONF_POLL_INTERVAL, POLL_INTERVAL_SECONDS),
        availability_grace=options.get(
            CONF_AVAILABILITY_GRACE, POLL_FAILURE_GRACE_SECONDS
        ),
    )
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: PhilipsSread1ConfigEntry
) -> bool:
    """Unload a Philips SREAD1 config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
