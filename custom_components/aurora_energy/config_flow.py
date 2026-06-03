"""Config flow for Aurora Energy integration."""
from __future__ import annotations

import base64
import hashlib
import logging
import secrets
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import AuroraApiClient, AuthenticationError
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_CUSTOMER_ID,
    CONF_REFRESH_COOKIE,
    CONF_REFRESH_TOKEN,
    CONF_SERVICE_AGREEMENT_ID,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

# Azure B2C endpoints and client details for the Aurora+ portal
_B2C_AUTHORIZE = (
    "https://customers.auroraenergy.com.au/"
    "auroracustomers1p.onmicrosoft.com/b2c_1a_sign_in/oauth2/v2.0/authorize"
)
_B2C_TOKEN = (
    "https://customers.auroraenergy.com.au/"
    "auroracustomers1p.onmicrosoft.com/b2c_1a_sign_in/oauth2/v2.0/token"
)
_B2C_CLIENT_ID = "2ff9da64-8629-4a92-a4b6-850a3f02053d"
_B2C_REDIRECT = "https://my.auroraenergy.com.au/login/redirect"

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required("redirect_url"): str,
    }
)


def _generate_pkce_pair() -> tuple[str, str]:
    """Return (code_verifier, code_challenge) for a PKCE exchange."""
    code_verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(code_verifier.encode()).digest()
    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return code_verifier, code_challenge


def _build_auth_url(code_challenge: str) -> str:
    """Build the Azure B2C PKCE authorization URL."""
    params = {
        "client_id": _B2C_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": _B2C_REDIRECT,
        "scope": "openid profile offline_access",
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "nonce": secrets.token_urlsafe(16),
    }
    return f"{_B2C_AUTHORIZE}?{urlencode(params)}"


def _parse_code_from_redirect(redirect_url: str) -> str:
    """Extract the authorization code from the Aurora+ post-login redirect URL.

    Raises ValueError if no 'code' parameter is present.
    """
    parsed = urlparse(redirect_url.strip())
    params = parse_qs(parsed.query)
    codes = params.get("code", [])
    if not codes:
        raise ValueError("No 'code' query parameter found in URL")
    return codes[0]


async def _exchange_code_for_id_token(
    hass: HomeAssistant, code: str, code_verifier: str
) -> str:
    """Exchange a PKCE authorization code for an Azure B2C id_token.

    Raises AuthenticationError if the exchange fails.
    """
    session = async_get_clientsession(hass)
    data = {
        "grant_type": "authorization_code",
        "client_id": _B2C_CLIENT_ID,
        "code": code,
        "code_verifier": code_verifier,
        "redirect_uri": _B2C_REDIRECT,
    }
    try:
        async with session.post(_B2C_TOKEN, data=data) as resp:
            if resp.status != 200:
                _LOGGER.debug("Azure B2C token exchange failed: HTTP %s", resp.status)
                raise AuthenticationError("Azure B2C token exchange failed")
            json_resp = await resp.json(content_type=None)
    except AuthenticationError:
        raise
    except Exception as err:
        raise AuthenticationError(f"Azure B2C token exchange error: {err}") from err

    id_token = json_resp.get("id_token")
    if not id_token:
        raise AuthenticationError("No id_token in Azure B2C response")
    return id_token


async def _validate_token(
    hass: HomeAssistant, id_token: str
) -> tuple[str, str, str | None, str | None, str | None]:
    """Log in and return (service_agreement_id, customer_id, access_token, refresh_token, refresh_cookie)."""
    session = async_get_clientsession(hass)
    client = AuroraApiClient(
        session=session,
        id_token=id_token,
        service_agreement_id="",
        customer_id="",
        hass=hass,
        entry=None,
    )
    sa_id, customer_id = await client.async_validate_and_login(id_token)
    return sa_id, customer_id, client._access_token, client._refresh_token, client._refresh_cookie


class AuroraConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the initial setup config flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Show the PKCE login link, then validate the pasted redirect URL."""
        # Generate PKCE pair once per flow instance.
        if not hasattr(self, "_pkce_verifier"):
            self._pkce_verifier, code_challenge = _generate_pkce_pair()
            self._auth_url = _build_auth_url(code_challenge)

        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                code = _parse_code_from_redirect(user_input["redirect_url"])
            except ValueError:
                errors["base"] = "invalid_redirect_url"
            else:
                try:
                    id_token = await _exchange_code_for_id_token(
                        self.hass, code, self._pkce_verifier
                    )
                    service_agreement_id, customer_id, access_token, refresh_token, refresh_cookie = (
                        await _validate_token(self.hass, id_token)
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
                            CONF_SERVICE_AGREEMENT_ID: service_agreement_id,
                            CONF_CUSTOMER_ID: customer_id,
                            CONF_ACCESS_TOKEN: access_token,
                            CONF_REFRESH_TOKEN: refresh_token,
                            CONF_REFRESH_COOKIE: refresh_cookie,
                        },
                    )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_SCHEMA,
            description_placeholders={"auth_url": self._auth_url},
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
        """Show the reauth PKCE login link and validate the pasted redirect URL."""
        if not hasattr(self, "_pkce_verifier"):
            self._pkce_verifier, code_challenge = _generate_pkce_pair()
            self._auth_url = _build_auth_url(code_challenge)

        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                code = _parse_code_from_redirect(user_input["redirect_url"])
            except ValueError:
                errors["base"] = "invalid_redirect_url"
            else:
                try:
                    id_token = await _exchange_code_for_id_token(
                        self.hass, code, self._pkce_verifier
                    )
                    service_agreement_id, customer_id, access_token, refresh_token, refresh_cookie = (
                        await _validate_token(self.hass, id_token)
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
                            CONF_SERVICE_AGREEMENT_ID: service_agreement_id,
                            CONF_CUSTOMER_ID: customer_id,
                            CONF_ACCESS_TOKEN: access_token,
                            CONF_REFRESH_TOKEN: refresh_token,
                            CONF_REFRESH_COOKIE: refresh_cookie,
                        },
                    )
                    await self.hass.config_entries.async_reload(
                        self._reauth_entry.entry_id
                    )
                    return self.async_abort(reason="reauth_successful")

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=STEP_USER_SCHEMA,
            description_placeholders={"auth_url": self._auth_url},
            errors=errors,
        )
