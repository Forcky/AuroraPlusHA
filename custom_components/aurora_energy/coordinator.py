"""Data coordinator for Aurora Energy integration.

Fetches billing and usage data from the Aurora+ API on a schedule, parses
it into a flat dict for sensor consumption, and injects historical hourly
statistics into the HA recorder for the Energy Dashboard.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.recorder.statistics import async_add_external_statistics
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import AuroraApiClient, TokenRefreshError
from .const import (
    BACKFILL_DAYS,
    DOMAIN,
    POLL_INTERVAL,
    STAT_ID_SOLAR_DOLLARS,
    STAT_ID_SOLAR_KWH,
    STAT_ID_T31_KWH,
    STAT_ID_T41_KWH,
    STAT_ID_TOTAL_DOLLARS,
    STAT_ID_TOTAL_KWH,
    TARIFF_OTHER,
    TARIFF_T31,
    TARIFF_T41,
    TARIFF_T140,
    TARIFF_TOTAL,
)

_LOGGER = logging.getLogger(__name__)

# StatisticMetaData for each external statistic registered with the recorder.
# source must equal DOMAIN for external statistics.
_STAT_METADATA: dict[str, StatisticMetaData] = {
    STAT_ID_TOTAL_KWH: StatisticMetaData(
        has_mean=False,
        has_sum=True,
        name="Aurora Total Energy",
        source=DOMAIN,
        statistic_id=STAT_ID_TOTAL_KWH,
        unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
    ),
    STAT_ID_T41_KWH: StatisticMetaData(
        has_mean=False,
        has_sum=True,
        name="Aurora T41 Heating Energy",
        source=DOMAIN,
        statistic_id=STAT_ID_T41_KWH,
        unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
    ),
    STAT_ID_T31_KWH: StatisticMetaData(
        has_mean=False,
        has_sum=True,
        name="Aurora T31 General Energy",
        source=DOMAIN,
        statistic_id=STAT_ID_T31_KWH,
        unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
    ),
    STAT_ID_SOLAR_KWH: StatisticMetaData(
        has_mean=False,
        has_sum=True,
        name="Aurora Solar Feed-in Energy",
        source=DOMAIN,
        statistic_id=STAT_ID_SOLAR_KWH,
        unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
    ),
    STAT_ID_TOTAL_DOLLARS: StatisticMetaData(
        has_mean=False,
        has_sum=True,
        name="Aurora Total Cost",
        source=DOMAIN,
        statistic_id=STAT_ID_TOTAL_DOLLARS,
        unit_of_measurement="AUD",
    ),
    STAT_ID_SOLAR_DOLLARS: StatisticMetaData(
        has_mean=False,
        has_sum=True,
        name="Aurora Solar Feed-in Earnings",
        source=DOMAIN,
        statistic_id=STAT_ID_SOLAR_DOLLARS,
        unit_of_measurement="AUD",
    ),
}


class AuroraCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator that polls the Aurora+ API and manages statistics injection."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: AuroraApiClient,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=POLL_INTERVAL,
        )
        self.client = client
        self.entry = entry
        # Persistent store for tracking which dates have been injected into recorder
        self._store: Store = Store(
            hass, version=1, key=f"{DOMAIN}_{entry.entry_id}_backfill"
        )
        self._injected_dates: set[str] = set()
        self._store_loaded = False
        self._nmi: Optional[str] = None

    # ------------------------------------------------------------------
    # Core update method
    # ------------------------------------------------------------------

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch fresh data from the Aurora+ API."""
        # Load backfill state from storage on first call
        if not self._store_loaded:
            stored = await self._store.async_load() or {}
            self._injected_dates = set(stored.get("injected_dates", []))
            self._store_loaded = True

        try:
            customer_data = await self.client.async_get_customer_data()
            # Extract active premise for correct service agreement ID and NMI
            _customer = customer_data[0] if isinstance(customer_data, list) else customer_data
            _premises = _customer.get("Premises") or []
            _active = next((p for p in _premises if p.get("IsActive")), _premises[0] if _premises else {})
            _sa_id = _active.get("ServiceAgreementID") or self.client._service_agreement_id
            _meters = _active.get("Meters") or []
            _nmi = _meters[0].get("NMI") if _meters else None
            # Update client with correct service agreement ID (fixes stale config entries)
            self.client._service_agreement_id = _sa_id
            usage_data = await self.client.async_get_usage(timespan="day", index=-1, nmi=_nmi)
        except TokenRefreshError as err:
            raise ConfigEntryAuthFailed(
                "Aurora+ authentication tokens expired — please re-authenticate"
            ) from err
        except Exception as err:
            raise UpdateFailed(f"Error communicating with Aurora+ API: {err}") from err

        parsed = self._parse(customer_data, usage_data)
        self._nmi = parsed.get("nmi")

        # Inject statistics: backfill all available days on first run
        if not self._injected_dates:
            await self._backfill_history()

        # Inject the fetched day's records if not already done
        date_key = parsed.get("start_date")
        if date_key and date_key not in self._injected_dates:
            records = parsed.get("metered_records", [])
            if records and not parsed.get("no_data_flag"):
                await self._inject_statistics(records, date_key)

        return parsed

    # ------------------------------------------------------------------
    # Data parsing
    # ------------------------------------------------------------------

    def _parse(
        self, customer: Any, usage: dict[str, Any]
    ) -> dict[str, Any]:
        """Normalise raw API responses into a flat dict for sensors."""
        if isinstance(customer, list):
            customer = customer[0] if customer else {}
        premises = customer.get("Premises") or []
        # Use the active premise; fall back to first if none found
        premise = next(
            (p for p in premises if p.get("IsActive")),
            premises[0] if premises else {},
        )
        meters = premise.get("Meters") or []
        data: dict[str, Any] = {}
        data["nmi"] = meters[0].get("NMI") if meters else None

        # Billing fields — nested inside first Premise
        data["estimated_balance"] = premise.get("EstimatedBalance")
        data["amount_owed"] = premise.get("AmountOwed")
        data["unbilled_amount"] = premise.get("UnbilledAmount")
        data["average_daily_usage"] = premise.get("AverageDailyUsage")
        data["usage_days_remaining"] = premise.get("UsageDaysRemaining")
        data["bill_total_amount"] = premise.get("BillTotalAmount")

        # Usage summary totals
        summary = usage.get("SummaryTotals", {})
        kwh_summary: dict[str, Any] = summary.get("KilowattHourUsage") or {}
        dollar_summary: dict[str, Any] = summary.get("DollarValueUsage") or {}

        data["total_kwh"] = kwh_summary.get(TARIFF_TOTAL)
        data["total_dollars"] = dollar_summary.get(TARIFF_TOTAL)
        data["t41_kwh"] = kwh_summary.get(TARIFF_T41)
        data["t41_dollars"] = dollar_summary.get(TARIFF_T41)
        data["t31_kwh"] = kwh_summary.get(TARIFF_T31)
        data["t31_dollars"] = dollar_summary.get(TARIFF_T31)

        # Solar feed-in — T140 tariff (negative dollars = earnings from export)
        t140_kwh = kwh_summary.get(TARIFF_T140)
        t140_dollars = dollar_summary.get(TARIFF_T140)
        data["solar_feedin_kwh"] = t140_kwh
        data["solar_feedin_dollars"] = abs(t140_dollars) if t140_dollars is not None else None

        # Raw records + metadata for statistics injection
        data["metered_records"] = usage.get("MeteredUsageRecords", [])
        data["no_data_flag"] = usage.get("NoDataFlag", False)
        data["start_date"] = usage.get("StartDate")

        return data

    # ------------------------------------------------------------------
    # Statistics injection
    # ------------------------------------------------------------------

    async def _backfill_history(self) -> None:
        """Fetch and inject statistics for the last BACKFILL_DAYS days."""
        _LOGGER.info("Aurora+: starting historical data backfill (%d days)", BACKFILL_DAYS)
        for idx in range(-1, -(BACKFILL_DAYS + 1), -1):
            try:
                usage = await self.client.async_get_usage(timespan="day", index=idx, nmi=getattr(self, "_nmi", None))
                date_key = usage.get("StartDate")
                records = usage.get("MeteredUsageRecords", [])
                no_data = usage.get("NoDataFlag", False)
                if records and not no_data and date_key:
                    if date_key not in self._injected_dates:
                        await self._inject_statistics(records, date_key)
            except Exception as err:
                _LOGGER.warning(
                    "Aurora+: could not backfill index %d: %s", idx, err
                )

    async def _inject_statistics(
        self, records: list[dict[str, Any]], date_key: str
    ) -> None:
        """Inject hourly metered records as external statistics into the recorder.

        StatisticData.sum must be a monotonically increasing cumulative total.
        StatisticData.state holds the per-period (hourly) value.
        """
        # Accumulate running sums across the day
        sums: dict[str, float] = {
            STAT_ID_TOTAL_KWH: 0.0,
            STAT_ID_T41_KWH: 0.0,
            STAT_ID_T31_KWH: 0.0,
            STAT_ID_SOLAR_KWH: 0.0,
            STAT_ID_TOTAL_DOLLARS: 0.0,
            STAT_ID_SOLAR_DOLLARS: 0.0,
        }
        stats: dict[str, list[StatisticData]] = {k: [] for k in sums}

        for record in sorted(records, key=lambda r: r.get("StartTime", "")):
            start_str = record.get("StartTime")
            if not start_str:
                continue
            start_dt = dt_util.parse_datetime(start_str)
            if start_dt is None:
                continue
            start_dt = dt_util.as_utc(start_dt)

            kwh_by_tariff: dict[str, Any] = record.get("KilowattHourUsage") or {}
            dollar_by_tariff: dict[str, Any] = record.get("DollarValueUsage") or {}

            t41_kwh = float(kwh_by_tariff.get(TARIFF_T41) or 0.0)
            t31_kwh = float(kwh_by_tariff.get(TARIFF_T31) or 0.0)
            solar_kwh = abs(float(kwh_by_tariff.get(TARIFF_T140) or 0.0))
            solar_dollars = abs(float(dollar_by_tariff.get(TARIFF_T140) or 0.0))
            # Total consumption = all kWh except solar (T140)
            total_kwh = float(
                sum(
                    float(v or 0.0)
                    for k, v in kwh_by_tariff.items()
                    if k not in (TARIFF_T140, TARIFF_TOTAL)
                )
            )
            # Total cost = all dollar charges except solar credit and supply charge
            total_dollars = float(
                sum(
                    float(v or 0.0)
                    for k, v in dollar_by_tariff.items()
                    if k not in (TARIFF_T140, TARIFF_OTHER, TARIFF_TOTAL)
                )
            )

            for stat_id, period_val in [
                (STAT_ID_TOTAL_KWH, total_kwh),
                (STAT_ID_T41_KWH, t41_kwh),
                (STAT_ID_T31_KWH, t31_kwh),
                (STAT_ID_SOLAR_KWH, solar_kwh),
                (STAT_ID_TOTAL_DOLLARS, total_dollars),
                (STAT_ID_SOLAR_DOLLARS, solar_dollars),
            ]:
                sums[stat_id] += period_val
                stats[stat_id].append(
                    StatisticData(
                        start=start_dt,
                        state=period_val,
                        sum=sums[stat_id],
                    )
                )

        # Submit to recorder — async_add_external_statistics is idempotent per (id, start)
        for stat_id, data_points in stats.items():
            if data_points:
                async_add_external_statistics(
                    self.hass, _STAT_METADATA[stat_id], data_points
                )

        self._injected_dates.add(date_key)
        await self._store.async_save(
            {"injected_dates": list(self._injected_dates)}
        )
        _LOGGER.debug("Aurora+: injected statistics for %s", date_key)
