"""Aurora Energy API client.

Handles authentication (Azure B2C id_token exchange) and all API calls.
Uses aiohttp (already part of Home Assistant) — no external dependencies.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

import aiohttp

from .const import (
    BASE_URL,
    CONF_ACCESS_TOKEN,
    CONF_REFRESH_COOKIE,
    CONF_REFRESH_TOKEN,
    ENDPOINT_CUSTOMERS,
    ENDPOINT_LOGIN,
    ENDPOINT_POWERHOUR_ALL,
    ENDPOINT_POWERHOUR_UPCOMING,
    ENDPOINT_REFRESH,
    ENDPOINT_USAGE,
)

_LOGGER = logging.getLogger(__name__)


class AuthenticationError(Exception):
    """Raised when the id_token is rejected by the Aurora API."""


class TokenRefreshError(Exception):
    """Raised when the refresh token is also expired — reauth required."""


class AuroraApiClient:
    """Client for the Aurora Energy (Aurora+) REST API."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        id_token: str,
        service_agreement_id: str,
        customer_id: str,
        hass: Any = None,
        entry: Any = None,
    ) -> None:
        self._session = session
        self._id_token = id_token
        self._service_agreement_id = service_agreement_id
        self._customer_id = customer_id
        self._hass = hass
        self._entry = entry

        self._access_token: Optional[str] = None
        self._refresh_token: Optional[str] = None
        self._refresh_cookie: Optional[str] = None

        # Restore persisted tokens from config entry if available
        if entry is not None:
            self._access_token = entry.data.get(CONF_ACCESS_TOKEN)
            self._refresh_token = entry.data.get(CONF_REFRESH_TOKEN)
            self._refresh_cookie = entry.data.get(CONF_REFRESH_COOKIE)

        self._refresh_lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Public auth methods
    # ------------------------------------------------------------------

    async def async_login(self, id_token: str) -> None:
        """Exchange an id_token for an access_token via /identity/LoginToken."""
        url = BASE_URL + ENDPOINT_LOGIN
        try:
            async with self._session.post(url, json={"token": id_token}, headers={"Accept": "application/json", "User-Agent": "python/auroraplus"}) as resp:
                if resp.status in (401, 403):
                    _LOGGER.warning(
                        "Aurora login rejected (HTTP %s) — id_token likely expired",
                        resp.status,
                    )
                    raise AuthenticationError(
                        f"id_token rejected by Aurora API (HTTP {resp.status})"
                    )
                resp.raise_for_status()
                data = await resp.json(content_type=None)

            self._id_token = id_token
            raw_token = (
                data.get("accessToken")
                or data.get("access_token")
                or data.get("AccessToken")
            )
            self._access_token = (
                raw_token.removeprefix("bearer ").removeprefix("Bearer ")
                if raw_token
                else None
            )
            self._refresh_token = (
                data.get("refreshToken")
                or data.get("refresh_token")
                or data.get("RefreshToken")
            )
            self._refresh_cookie = self._extract_refresh_cookie(resp.cookies)

            if not self._access_token:
                raise AuthenticationError(
                    "Login succeeded but no access_token found in response"
                )

            _LOGGER.debug("Aurora login successful, access_token obtained")
            await self._persist_tokens()

        except AuthenticationError:
            raise
        except aiohttp.ClientError as err:
            raise AuthenticationError(f"Network error during login: {err}") from err

    async def async_refresh_token(self) -> None:
        """Refresh the access token using the refresh token / cookie.

        Protected by a lock so concurrent 401 responses only trigger one refresh.
        Raises TokenRefreshError if the refresh token is also expired.
        """
        async with self._refresh_lock:
            url = BASE_URL + ENDPOINT_REFRESH
            cookies: dict[str, str] = {}
            if self._refresh_cookie:
                cookies["RefreshToken"] = self._refresh_cookie

            try:
                async with self._session.post(
                    url,
                    json={"token": self._refresh_token},
                    cookies=cookies,
                    headers={"Accept": "application/json", "User-Agent": "python/auroraplus"},
                ) as resp:
                    if resp.status in (401, 403):
                        raise TokenRefreshError(
                            "Refresh token expired — re-authentication required"
                        )
                    resp.raise_for_status()
                    data = await resp.json(content_type=None)

                raw_token = (
                    data.get("accessToken")
                    or data.get("access_token")
                    or data.get("AccessToken")
                )
                self._access_token = (
                    raw_token.removeprefix("bearer ").removeprefix("Bearer ")
                    if raw_token
                    else None
                )
                self._refresh_token = (
                    data.get("refreshToken")
                    or data.get("refresh_token")
                    or data.get("RefreshToken")
                    or self._refresh_token
                )
                new_cookie = self._extract_refresh_cookie(resp.cookies)
                if new_cookie:
                    self._refresh_cookie = new_cookie

                _LOGGER.debug("Aurora token refresh successful")
                await self._persist_tokens()

            except TokenRefreshError:
                raise
            except aiohttp.ClientError as err:
                raise TokenRefreshError(
                    f"Network error during token refresh: {err}"
                ) from err

    async def async_validate_and_login(self, id_token: str) -> tuple[str, str]:
        """Validate an id_token and return (service_agreement_id, customer_id).

        Used by the config flow to verify credentials before creating the entry.
        """
        await self.async_login(id_token)
        raw = await self.async_get_customer_data()
        data = raw[0] if isinstance(raw, list) else raw
        customer_id = data.get("CustomerID", "")
        # ServiceAgreementID is nested inside Premises
        premises = data.get("Premises") or []
        active_premise = next(
            (p for p in premises if p.get("IsActive")),
            premises[0] if premises else {},
        )
        service_agreement_id = (
            active_premise.get("ServiceAgreementID")
            or active_premise.get("serviceAgreementId")
            or ""
        )
        if not service_agreement_id or not customer_id:
            raise AuthenticationError(
                "Could not retrieve ServiceAgreementID or CustomerID from API"
            )
        return service_agreement_id, customer_id

    # ------------------------------------------------------------------
    # Public data methods
    # ------------------------------------------------------------------

    async def async_get_customer_data(self) -> dict[str, Any]:
        """GET /customers/current — billing and account info."""
        if not self._access_token:
            await self.async_login(self._id_token)
        url = BASE_URL + ENDPOINT_CUSTOMERS
        return await self._get_with_retry(url)

    async def async_get_usage(
        self, timespan: str = "day", index: int = -1, nmi: Optional[str] = None
    ) -> dict[str, Any]:
        """GET /usage/{timespan} — metered usage records.

        Args:
            timespan: "day", "week", "month", "quarter", or "year"
            index: -1 = most recent, -9 = oldest available
            nmi: National Metering Identifier (unlocks per-interval data)
        """
        if not self._access_token:
            await self.async_login(self._id_token)
        url = BASE_URL + ENDPOINT_USAGE.format(timespan=timespan)
        params: dict[str, str] = {
            "serviceAgreementID": self._service_agreement_id,
            "customerId": self._customer_id,
            "index": str(index),
        }
        if nmi:
            params["nmi"] = nmi
        return await self._get_with_retry(url, params)

    async def async_get_powerhour_upcoming(self) -> list[dict[str, Any]]:
        """GET /powerhour/upcoming-active — current and upcoming Power Hour events."""
        if not self._access_token:
            await self.async_login(self._id_token)
        url = BASE_URL + ENDPOINT_POWERHOUR_UPCOMING
        result = await self._get_with_retry(url)
        if isinstance(result, list):
            return result
        return result.get("value") or result.get("items") or []

    async def async_get_powerhour_all(self) -> list[dict[str, Any]]:
        """GET /powerhour/all — all Power Hour events including historical (for savings)."""
        if not self._access_token:
            await self.async_login(self._id_token)
        url = BASE_URL + ENDPOINT_POWERHOUR_ALL
        result = await self._get_with_retry(url)
        if isinstance(result, list):
            return result
        return result.get("value") or result.get("items") or []

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _get_with_retry(
        self, url: str, params: Optional[dict] = None
    ) -> dict[str, Any]:
        """GET with a single automatic token-refresh retry on 401."""
        for attempt in range(2):
            async with self._session.get(
                url,
                headers={
                    "Authorization": f"Bearer {self._access_token}",
                    "Accept": "application/json",
                    "User-Agent": "python/auroraplus",
                },
                params=params,
            ) as resp:
                if resp.status == 401:
                    if attempt == 0:
                        _LOGGER.warning(
                            "Aurora 401 from %s (token prefix: %s...)",
                            url,
                            (self._access_token or "")[:20],
                        )
                        await self.async_refresh_token()
                        continue
                    raise AuthenticationError(
                        f"Access token rejected by {url} after refresh (401)"
                    )
                resp.raise_for_status()
                return await resp.json(content_type=None)

        raise RuntimeError("Unexpected state after retry loop")

    def _extract_refresh_cookie(self, cookies: Any) -> Optional[str]:
        """Extract the RefreshToken cookie value from a response."""
        for name in cookies:
            if name.lower() == "refreshtoken":
                morsel = cookies[name]
                return morsel.value if hasattr(morsel, "value") else str(morsel)
        return None

    async def _persist_tokens(self) -> None:
        """Write updated tokens back to the config entry for persistence across restarts."""
        if self._entry is None or self._hass is None:
            return
        new_data = {
            **self._entry.data,
            CONF_ACCESS_TOKEN: self._access_token,
            CONF_REFRESH_TOKEN: self._refresh_token,
            CONF_REFRESH_COOKIE: self._refresh_cookie,
        }
        self._hass.config_entries.async_update_entry(self._entry, data=new_data)
