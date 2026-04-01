"""Config flow for Aurora Energy integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import AuroraApiClient, AuthenticationError
from .const import (
    CONF_CUSTOMER_ID,
    CONF_ID_TOKEN,
    CONF_SERVICE_AGREEMENT_ID,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_ID_TOKEN): str,
    }
)


async def _validate_token(hass: HomeAssistant, id_token: str) -> tuple[str, str]:
    """Try to log in and return (service_agreement_id, customer_id)."""
    session = async_get_clientsession(hass)
    client = AuroraApiClient(
        session=session,
        id_token=id_token,
        service_agreement_id="",
        customer_id="",
        hass=hass,
        entry=None,
    )
    return await client.async_validate_and_login(id_token)


class AuroraConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the initial setup config flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Show the token input form and validate on submit."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                service_agreement_id, customer_id = await _validate_token(
                    self.hass, user_input[CONF_ID_TOKEN]
                )
            except AuthenticationError:
                errors["base"] = "invalid_token"
            except Exception:
                _LOGGER.exception("Unexpected error during Aurora+ config flow")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(service_agreement_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title="Aurora Energy Tasmania",
                    data={
                        CONF_ID_TOKEN: user_input[CONF_ID_TOKEN],
                        CONF_SERVICE_AGREEMENT_ID: service_agreement_id,
                        CONF_CUSTOMER_ID: customer_id,
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_SCHEMA,
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> config_entries.FlowResult:
        """Triggered by HA when ConfigEntryAuthFailed is raised in the coordinator."""
        self._reauth_entry: ConfigEntry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Show the reauth token form."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                service_agreement_id, customer_id = await _validate_token(
                    self.hass, user_input[CONF_ID_TOKEN]
                )
            except AuthenticationError:
                errors["base"] = "invalid_token"
            except Exception:
                _LOGGER.exception("Unexpected error during Aurora+ re-authentication")
                errors["base"] = "unknown"
            else:
                self.hass.config_entries.async_update_entry(
                    self._reauth_entry,
                    data={
                        **self._reauth_entry.data,
                        CONF_ID_TOKEN: user_input[CONF_ID_TOKEN],
                        CONF_SERVICE_AGREEMENT_ID: service_agreement_id,
                        CONF_CUSTOMER_ID: customer_id,
                    },
                )
                await self.hass.config_entries.async_reload(
                    self._reauth_entry.entry_id
                )
                return self.async_abort(reason="reauth_successful")

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=STEP_USER_SCHEMA,
            errors=errors,
        )
