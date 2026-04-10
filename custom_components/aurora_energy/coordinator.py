"""Data coordinator for Aurora Energy integration.

Fetches billing and usage data from the Aurora+ API on a schedule, parses
it into a flat dict for sensor consumption, and injects historical hourly
statistics into the HA recorder for the Energy Dashboard.
"""
from __future__ import annotations

import datetime
import logging
import zoneinfo
from typing import Any, Optional

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    get_last_statistics,
)
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
    SENSOR_PH_END,
    SENSOR_PH_EVENT_NAME,
    SENSOR_PH_SELECTION_DEADLINE,
    SENSOR_PH_START,
    SENSOR_PH_STATUS,
    SENSOR_PH_TOTAL_SAVINGS,
    STAT_ID_SOLAR_DOLLARS,
    STAT_ID_SOLAR_KWH,
    STAT_ID_T31_KWH,
    STAT_ID_T41_KWH,
    STAT_ID_T93OFFPEAK_KWH,
    STAT_ID_T93PEAK_KWH,
    STAT_ID_TOTAL_DOLLARS,
    STAT_ID_TOTAL_KWH,
    TARIFF_OTHER,
    TARIFF_T31,
    TARIFF_T41,
    TARIFF_T140,
    TARIFF_T93OFFPEAK,
    TARIFF_T93PEAK,
    TARIFF_TOTAL,
    TZ_HOBART,
)

_LOGGER = logging.getLogger(__name__)


def _parse_hobart_naive(
    dt_str: Optional[str], tz: zoneinfo.ZoneInfo
) -> Optional[datetime.datetime]:
    """Parse a naive ISO datetime string as Australia/Hobart and return a UTC-aware datetime.

    Aurora Power Hours datetimes have no timezone suffix (e.g. "2026-04-24T16:00:00").
    """
    if not dt_str:
        return None
    naive = dt_util.parse_datetime(dt_str)
    if naive is None:
        return None
    return dt_util.as_utc(naive.replace(tzinfo=tz))


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
    STAT_ID_T93PEAK_KWH: StatisticMetaData(
        has_mean=False,
        has_sum=True,
        name="Aurora T93 Peak Energy",
        source=DOMAIN,
        statistic_id=STAT_ID_T93PEAK_KWH,
        unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
    ),
    STAT_ID_T93OFFPEAK_KWH: StatisticMetaData(
        has_mean=False,
        has_sum=True,
        name="Aurora T93 Off-Peak Energy",
        source=DOMAIN,
        statistic_id=STAT_ID_T93OFFPEAK_KWH,
        unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
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
        self._last_powerhour_all_date: Optional[datetime.date] = None
        self._powerhour_savings_cache: Optional[float] = None

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

        # Fetch Power Hours data — isolated try/except so failures don't break main update
        powerhour_upcoming: list[dict] = []
        try:
            powerhour_upcoming = await self.client.async_get_powerhour_upcoming()
            today = dt_util.now().date()
            if self._last_powerhour_all_date != today:
                ph_all = await self.client.async_get_powerhour_all()
                self._last_powerhour_all_date = today
                self._powerhour_savings_cache = self._calculate_total_savings(ph_all)
        except Exception as err:
            _LOGGER.warning("Aurora+: Power Hours fetch failed: %s", err)

        parsed = self._parse(customer_data, usage_data, powerhour_upcoming)
        parsed[SENSOR_PH_TOTAL_SAVINGS] = self._powerhour_savings_cache
        self._nmi = parsed.get("nmi")

        # Inject statistics: backfill all available days on first run
        if not self._injected_dates:
            await self._backfill_history()

        # Inject the fetched day's records if not already done
        date_key = parsed.get("start_date")
        if date_key and date_key not in self._injected_dates:
            records = parsed.get("metered_records", [])
            if self._has_real_kwh_data(records):
                await self._inject_statistics(records, date_key)

        return parsed

    # ------------------------------------------------------------------
    # Data parsing
    # ------------------------------------------------------------------

    def _parse(
        self,
        customer: Any,
        usage: dict[str, Any],
        powerhour_upcoming: Optional[list] = None,
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

        # T93 Time-of-Use tariff (peak / off-peak) — None for non-T93 accounts
        data["t93peak_kwh"]        = kwh_summary.get(TARIFF_T93PEAK)
        data["t93peak_dollars"]    = dollar_summary.get(TARIFF_T93PEAK)
        data["t93offpeak_kwh"]     = kwh_summary.get(TARIFF_T93OFFPEAK)
        data["t93offpeak_dollars"] = dollar_summary.get(TARIFF_T93OFFPEAK)

        # Solar feed-in — T140 tariff (negative dollars = earnings from export)
        t140_kwh = kwh_summary.get(TARIFF_T140)
        t140_dollars = dollar_summary.get(TARIFF_T140)
        data["solar_feedin_kwh"] = t140_kwh
        data["solar_feedin_dollars"] = abs(t140_dollars) if t140_dollars is not None else None

        # Raw records + metadata for statistics injection
        data["metered_records"] = usage.get("MeteredUsageRecords", [])
        data["no_data_flag"] = usage.get("NoDataFlag", False)
        data["start_date"] = usage.get("StartDate")

        # Power Hours
        _tz = zoneinfo.ZoneInfo(TZ_HOBART)
        if powerhour_upcoming:
            event = powerhour_upcoming[0]
            data[SENSOR_PH_EVENT_NAME] = event.get("EventName")
            expiry_dt = _parse_hobart_naive(event.get("OfferExpiryDateTime"), _tz)
            data[SENSOR_PH_SELECTION_DEADLINE] = expiry_dt
            slot = event.get("TimeslotAccepted")
            if slot:
                start_dt = _parse_hobart_naive(slot.get("StartDateTime"), _tz)
                end_dt   = _parse_hobart_naive(slot.get("EndDateTime"), _tz)
                data[SENSOR_PH_START] = start_dt
                data[SENSOR_PH_END]   = end_dt
                now_utc = dt_util.utcnow()
                if start_dt and end_dt and start_dt <= now_utc <= end_dt:
                    data[SENSOR_PH_STATUS] = "active"
                else:
                    data[SENSOR_PH_STATUS] = "confirmed"
            else:
                data[SENSOR_PH_START] = None
                data[SENSOR_PH_END]   = None
                now_utc = dt_util.utcnow()
                data[SENSOR_PH_STATUS] = (
                    "selection_pending"
                    if expiry_dt and now_utc < expiry_dt
                    else "no_event"
                )
        else:
            data[SENSOR_PH_STATUS]             = "no_event"
            data[SENSOR_PH_EVENT_NAME]         = None
            data[SENSOR_PH_START]              = None
            data[SENSOR_PH_END]                = None
            data[SENSOR_PH_SELECTION_DEADLINE] = None

        return data

    # ------------------------------------------------------------------
    # Statistics injection
    # ------------------------------------------------------------------

    @staticmethod
    def _has_real_kwh_data(records: list[dict[str, Any]]) -> bool:
        """Return True if any hourly record contains non-zero kWh consumption.

        NoDataFlag from the API is unreliable — records can contain valid data
        even when the flag is True. This check uses the actual record values
        so that days with real usage are never skipped.
        """
        for record in records:
            if record.get("TimeMeasureUnit") != "Hour":
                continue
            kwh = record.get("KilowattHourUsage") or {}
            if any(float(v or 0) > 0 for v in kwh.values()):
                return True
        return False

    async def _backfill_history(self) -> None:
        """Fetch and inject statistics for the last BACKFILL_DAYS days."""
        _LOGGER.info("Aurora+: starting historical data backfill (%d days)", BACKFILL_DAYS)
        # Carry running sums across days in memory so we don't depend on
        # async_add_external_statistics committing before the next read.
        sums = await self._get_last_sums()
        for idx in range(-BACKFILL_DAYS, 0):
            try:
                usage = await self.client.async_get_usage(timespan="day", index=idx, nmi=getattr(self, "_nmi", None))
                date_key = usage.get("StartDate")
                records = usage.get("MeteredUsageRecords", [])
                # NoDataFlag is unreliable — check for actual kWh data in hourly records instead
                if date_key and date_key not in self._injected_dates and self._has_real_kwh_data(records):
                    sums = await self._inject_statistics(records, date_key, sums)
            except Exception as err:
                _LOGGER.warning(
                    "Aurora+: could not backfill index %d: %s", idx, err
                )

    async def _get_last_sums(self) -> dict[str, float]:
        """Retrieve the last cumulative sum for each statistic from the recorder."""
        sums: dict[str, float] = {}
        for stat_id in _STAT_METADATA:
            last = await get_instance(self.hass).async_add_executor_job(
                get_last_statistics, self.hass, 1, stat_id, True, set()
            )
            if last and stat_id in last:
                sums[stat_id] = last[stat_id][0].get("sum", 0.0) or 0.0
            else:
                sums[stat_id] = 0.0
        return sums

    async def _inject_statistics(
        self,
        records: list[dict[str, Any]],
        date_key: str,
        sums: dict[str, float] | None = None,
    ) -> dict[str, float]:
        """Inject hourly metered records as external statistics into the recorder.

        StatisticData.sum must be a monotonically increasing cumulative total.
        StatisticData.state holds the per-period (hourly) value.

        Args:
            sums: Starting cumulative sums. If None, reads them from the recorder.

        Returns:
            The updated cumulative sums after all records have been processed.
        """
        if sums is None:
            sums = await self._get_last_sums()
        stats: dict[str, list[StatisticData]] = {k: [] for k in sums}

        # Process only hourly records — the Day-level record has null KilowattHourUsage
        hourly = [r for r in records if r.get("TimeMeasureUnit") == "Hour"]
        for record in sorted(hourly, key=lambda r: r.get("StartTime", "")):
            start_str = record.get("StartTime")
            if not start_str:
                continue
            start_dt = dt_util.parse_datetime(start_str)
            if start_dt is None:
                continue
            start_dt = dt_util.as_utc(start_dt)

            kwh_by_tariff: dict[str, Any] = record.get("KilowattHourUsage") or {}
            dollar_by_tariff: dict[str, Any] = record.get("DollarValueUsage") or {}

            t41_kwh        = float(kwh_by_tariff.get(TARIFF_T41)      or 0.0)
            t31_kwh        = float(kwh_by_tariff.get(TARIFF_T31)      or 0.0)
            t93peak_kwh    = float(kwh_by_tariff.get(TARIFF_T93PEAK)    or 0.0)
            t93offpeak_kwh = float(kwh_by_tariff.get(TARIFF_T93OFFPEAK) or 0.0)
            solar_kwh      = abs(float(kwh_by_tariff.get(TARIFF_T140) or 0.0))
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
                (STAT_ID_TOTAL_KWH,      total_kwh),
                (STAT_ID_T41_KWH,        t41_kwh),
                (STAT_ID_T31_KWH,        t31_kwh),
                (STAT_ID_T93PEAK_KWH,    t93peak_kwh),
                (STAT_ID_T93OFFPEAK_KWH, t93offpeak_kwh),
                (STAT_ID_SOLAR_KWH,      solar_kwh),
                (STAT_ID_TOTAL_DOLLARS,  total_dollars),
                (STAT_ID_SOLAR_DOLLARS,  solar_dollars),
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
        return sums

    def _calculate_total_savings(self, events: list[dict]) -> Optional[float]:
        """Sum abs(Customer.Cost) for all completed Power Hour events.

        Returns None if no completed events exist yet (avoids showing misleading 0.00).
        """
        total = 0.0
        found_any = False
        for event in events:
            cost = (event.get("Customer") or {}).get("Cost")
            if cost is not None:
                total += abs(float(cost))
                found_any = True
        return round(total, 2) if found_any else None
