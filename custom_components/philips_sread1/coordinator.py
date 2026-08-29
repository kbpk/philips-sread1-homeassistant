"""Data update coordinator for Philips SREAD1."""

import logging
import time
from dataclasses import replace
from datetime import timedelta
from typing import override

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    DOMAIN,
    NAME,
    POLL_FAILURE_GRACE_SECONDS,
    POLL_INTERVAL_SECONDS,
)
from .miio_client import (
    MiIOError,
    MiIOInvalidTokenError,
    PhilipsSread1MiIOClient,
    PhilipsSread1State,
)

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
        *,
        poll_interval: float = POLL_INTERVAL_SECONDS,
        availability_grace: float = POLL_FAILURE_GRACE_SECONDS,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=poll_interval),
            always_update=False,
        )
        self.client = client
        self._availability_grace = availability_grace
        self._last_device_update_monotonic: float | None = None
        self._consecutive_update_failures = 0

    @override
    async def _async_update_data(self) -> PhilipsSread1State:
        """Fetch the current state of all supported lamp features."""
        try:
            state = await self.client.async_get_state()
        except MiIOInvalidTokenError as err:
            # Authentication failures are not transient connectivity problems and
            # must never be hidden behind cached state.
            raise UpdateFailed(f"Unable to update {NAME}: {err}") from err
        except MiIOError as err:
            self._consecutive_update_failures += 1
            last_update = self._last_device_update_monotonic
            stale_age = (
                time.monotonic() - last_update if last_update is not None else None
            )

            if (
                self.data is not None
                and stale_age is not None
                and stale_age <= self._availability_grace
            ):
                log = (
                    _LOGGER.warning
                    if self._consecutive_update_failures == 1
                    else _LOGGER.debug
                )
                log(
                    "Keeping the last confirmed %s state after polling failure "
                    "host=%s failures=%s stale_age=%.1fs grace=%ss error=%s",
                    NAME,
                    self.client.host,
                    self._consecutive_update_failures,
                    stale_age,
                    self._availability_grace,
                    type(err).__name__,
                )
                return self.data

            stale_context = (
                "no previous successful update"
                if stale_age is None
                else f"last successful update was {stale_age:.1f}s ago"
            )
            raise UpdateFailed(
                f"Unable to update {NAME}: {err} ({stale_context}; "
                f"consecutive failures={self._consecutive_update_failures})"
            ) from err

        self._record_successful_communication()
        return state

    def _record_successful_communication(self) -> None:
        """Record an authenticated response from the lamp."""
        if self._consecutive_update_failures:
            _LOGGER.info(
                "Recovered %s communication host=%s after_poll_failures=%s",
                NAME,
                self.client.host,
                self._consecutive_update_failures,
            )
        self._consecutive_update_failures = 0
        self._last_device_update_monotonic = time.monotonic()

    async def async_set_power(self, turn_on: bool) -> None:
        """Set power and publish the acknowledged state without another request."""
        try:
            await self.client.async_set_power(turn_on)
        except MiIOError as err:
            raise HomeAssistantError(f"Unable to set {NAME} power: {err}") from err
        self._record_successful_communication()
        self.async_set_updated_data(
            replace(
                self.data,
                is_on=turn_on,
            )
        )

    async def async_set_brightness(self, brightness: int) -> None:
        """Set manual brightness and publish the resulting EyeCare state."""
        try:
            await self.client.async_set_brightness(brightness)
        except (MiIOError, TypeError, ValueError) as err:
            raise HomeAssistantError(f"Unable to set {NAME} brightness: {err}") from err
        self._record_successful_communication()
        # Firmware 1.3.0 leaves automatic mode whenever a manual primary
        # brightness is accepted.
        self.async_set_updated_data(
            replace(
                self.data,
                brightness=brightness,
                automatic_brightness_is_on=False,
            )
        )

    async def async_set_ambient_power(self, turn_on: bool) -> None:
        """Set ambient power while respecting the primary-light coupling."""
        ambient_is_effectively_on = self.data.is_on and self.data.ambient_is_on
        if turn_on and ambient_is_effectively_on:
            return
        # OFF must clear the firmware's remembered ambstatus even when the
        # primary supply already makes the physical ambient output dark.
        if not turn_on and not self.data.ambient_is_on:
            return

        main_was_on = self.data.is_on
        try:
            await self.client.async_set_ambient_power(turn_on)
        except MiIOError as err:
            raise HomeAssistantError(
                f"Unable to set {NAME} ambient power: {err}"
            ) from err

        self._record_successful_communication()
        self.async_set_updated_data(
            replace(
                self.data,
                ambient_is_on=turn_on,
                # enable_amb("on") wakes primary power. There is no physical
                # ambient-only state on the tested SREAD1 firmware.
                is_on=main_was_on or turn_on,
            )
        )

    async def async_set_ambient_brightness(self, brightness: int) -> None:
        """Set ambient/back light brightness and publish acknowledged state."""
        try:
            await self.client.async_set_ambient_brightness(brightness)
        except (MiIOError, TypeError, ValueError) as err:
            raise HomeAssistantError(
                f"Unable to set {NAME} ambient brightness: {err}"
            ) from err
        self._record_successful_communication()
        self.async_set_updated_data(replace(self.data, ambient_brightness=brightness))

    async def async_set_automatic_brightness(self, turn_on: bool) -> None:
        """Set EyeCare while preserving the primary-light power state."""
        if turn_on == self.data.automatic_brightness_is_on:
            return

        main_was_on = self.data.is_on

        # set_eyecare("off") cannot disable the mode while primary power is
        # off: the first call merely wakes the primary output. Wake explicitly
        # so the following mode command has its documented effect.
        if not turn_on and not main_was_on:
            try:
                await self.client.async_set_power(True)
            except MiIOError as err:
                raise HomeAssistantError(
                    f"Unable to wake {NAME} before disabling automatic "
                    f"brightness: {err}"
                ) from err

        try:
            await self.client.async_set_automatic_brightness(turn_on)
        except MiIOError as err:
            if not turn_on and not main_was_on:
                self._record_successful_communication()
                self.async_set_updated_data(replace(self.data, is_on=True))
            raise HomeAssistantError(
                f"Unable to set {NAME} automatic brightness: {err}"
            ) from err

        # Enabling EyeCare wakes primary power. Keep it on because turning
        # primary power off also extinguishes the ambient output physically.
        # Disabling EyeCare is different: after the explicit wake above, turn
        # primary power back off to preserve an originally dark lamp.
        if turn_on and not main_was_on:
            final_main_state = True
        elif not turn_on and not main_was_on:
            try:
                await self.client.async_set_power(False)
            except MiIOError as err:
                self._record_successful_communication()
                self.async_set_updated_data(
                    replace(
                        self.data,
                        automatic_brightness_is_on=turn_on,
                        is_on=True,
                    )
                )
                raise HomeAssistantError(
                    f"{NAME} changed automatic brightness but could not restore "
                    f"the primary light state: {err}"
                ) from err
            final_main_state = False
        else:
            final_main_state = main_was_on

        self._record_successful_communication()
        self.async_set_updated_data(
            replace(
                self.data,
                automatic_brightness_is_on=turn_on,
                is_on=final_main_state,
            )
        )
