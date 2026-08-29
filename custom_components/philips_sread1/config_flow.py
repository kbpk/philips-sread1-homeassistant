"""Config flow for Philips SREAD1."""

from __future__ import annotations

import logging
from typing import Any, override

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_TOKEN
from homeassistant.helpers import selector

from .const import DOMAIN, MIIO_TIMEOUT, NAME
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
