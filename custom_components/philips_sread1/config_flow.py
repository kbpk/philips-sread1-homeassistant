"""Config flow for Philips SREAD1."""

from __future__ import annotations

import logging
from typing import Any, override

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_HOST, CONF_TOKEN
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_AVAILABILITY_GRACE,
    CONF_HANDSHAKE_TIMEOUT,
    CONF_POLL_INTERVAL,
    CONF_REQUEST_ATTEMPTS,
    CONF_REQUEST_TIMEOUT,
    CONF_RETRY_DELAY,
    DOMAIN,
    MIIO_HANDSHAKE_TIMEOUT,
    MIIO_REQUEST_ATTEMPTS,
    MIIO_RETRY_DELAY_SECONDS,
    MIIO_TIMEOUT,
    NAME,
    POLL_FAILURE_GRACE_SECONDS,
    POLL_INTERVAL_SECONDS,
)
from .miio_client import (
    MiIOConnectionError,
    MiIOHandshakeTimeoutError,
    MiIOInvalidTokenError,
    MiIOProtocolError,
    MiIORequestTimeoutError,
    PhilipsSread1MiIOClient,
)

_LOGGER = logging.getLogger(__name__)


class PhilipsSread1ConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Philips SREAD1."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(_config_entry: Any) -> OptionsFlow:
        """Return the optional communication-settings flow."""
        return PhilipsSread1OptionsFlow()

    @override
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect connection details and verify the device."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            token = user_input[CONF_TOKEN].strip()

            if not host:
                errors[CONF_HOST] = "invalid_host"
            else:
                try:
                    client = PhilipsSread1MiIOClient(host, token, timeout=MIIO_TIMEOUT)
                except ValueError:
                    errors[CONF_TOKEN] = "invalid_token"
                else:
                    try:
                        await client.async_get_state()
                    except (MiIOInvalidTokenError, MiIORequestTimeoutError):
                        errors[CONF_TOKEN] = "invalid_token"
                    except (MiIOHandshakeTimeoutError, MiIOConnectionError):
                        errors["base"] = "cannot_connect"
                    except MiIOProtocolError:
                        errors["base"] = "invalid_response"
                    except Exception:
                        _LOGGER.exception(
                            "Unexpected error while connecting to Philips SREAD1 at %s",
                            host,
                        )
                        errors["base"] = "unknown"
                    else:
                        device_id = client.device_id
                        if device_id is None:
                            errors["base"] = "invalid_response"
                        else:
                            await self.async_set_unique_id(device_id)
                            self._abort_if_unique_id_configured()
                            return self.async_create_entry(
                                title=f"{NAME} ({host})",
                                data={CONF_HOST: host, CONF_TOKEN: token.lower()},
                            )

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_HOST,
                    default=user_input.get(CONF_HOST, "") if user_input else "",
                ): str,
                vol.Required(
                    CONF_TOKEN,
                    default=user_input.get(CONF_TOKEN, "") if user_input else "",
                ): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                ),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)


class PhilipsSread1OptionsFlow(OptionsFlowWithReload):
    """Configure transport and polling behavior for an existing lamp."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle communication settings."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_POLL_INTERVAL,
                    default=options.get(CONF_POLL_INTERVAL, POLL_INTERVAL_SECONDS),
                ): vol.All(vol.Coerce(int), vol.Range(min=5, max=300)),
                vol.Required(
                    CONF_REQUEST_TIMEOUT,
                    default=options.get(CONF_REQUEST_TIMEOUT, MIIO_TIMEOUT),
                ): vol.All(vol.Coerce(float), vol.Range(min=1, max=30)),
                vol.Required(
                    CONF_HANDSHAKE_TIMEOUT,
                    default=options.get(CONF_HANDSHAKE_TIMEOUT, MIIO_HANDSHAKE_TIMEOUT),
                ): vol.All(vol.Coerce(float), vol.Range(min=0.2, max=10)),
                vol.Required(
                    CONF_REQUEST_ATTEMPTS,
                    default=options.get(CONF_REQUEST_ATTEMPTS, MIIO_REQUEST_ATTEMPTS),
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=5)),
                vol.Required(
                    CONF_RETRY_DELAY,
                    default=options.get(CONF_RETRY_DELAY, MIIO_RETRY_DELAY_SECONDS),
                ): vol.All(vol.Coerce(float), vol.Range(min=0, max=5)),
                vol.Required(
                    CONF_AVAILABILITY_GRACE,
                    default=options.get(
                        CONF_AVAILABILITY_GRACE, POLL_FAILURE_GRACE_SECONDS
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(min=0, max=600)),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
