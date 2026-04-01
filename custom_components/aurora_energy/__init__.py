"""Aurora Energy (Aurora+) Home Assistant integration.

Connects to the Aurora+ cloud API to expose billing, energy usage,
and solar feed-in data as Home Assistant sensors.
"""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import AuroraApiClient
from .const import (
    CONF_CUSTOMER_ID,
    CONF_ID_TOKEN,
    CONF_SERVICE_AGREEMENT_ID,
    DOMAIN,
)
from .coordinator import AuroraCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Aurora Energy from a config entry."""
    session = async_get_clientsession(hass)

    client = AuroraApiClient(
        session=session,
        id_token=entry.data[CONF_ID_TOKEN],
        service_agreement_id=entry.data[CONF_SERVICE_AGREEMENT_ID],
        customer_id=entry.data[CONF_CUSTOMER_ID],
        hass=hass,
        entry=entry,
    )

    coordinator = AuroraCoordinator(hass, client, entry)

    # This performs the first data fetch and raises ConfigEntryNotReady if it fails.
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "coordinator": coordinator,
        "client": client,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
