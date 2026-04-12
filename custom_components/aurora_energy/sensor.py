"""Sensor platform for Aurora Energy integration."""
from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Any, Optional

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_utc_time_change
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    SENSOR_AMOUNT_OWED,
    SENSOR_AVG_DAILY_USAGE,
    SENSOR_BILL_TOTAL,
    SENSOR_DAYS_REMAINING,
    SENSOR_ESTIMATED_BALANCE,
    SENSOR_PH_END,
    SENSOR_PH_EVENT_NAME,
    SENSOR_PH_SELECTION_DEADLINE,
    SENSOR_PH_START,
    SENSOR_PH_STATUS,
    SENSOR_PH_TOTAL_SAVINGS,
    SENSOR_SOLAR_DOLLARS,
    SENSOR_SOLAR_KWH,
    SENSOR_T31_DOLLARS,
    SENSOR_T31_KWH,
    SENSOR_T41_DOLLARS,
    SENSOR_T41_KWH,
    SENSOR_T93OFFPEAK_DOLLARS,
    SENSOR_T93OFFPEAK_KWH,
    SENSOR_T93PEAK_DOLLARS,
    SENSOR_T93PEAK_KWH,
    SENSOR_TOTAL_DOLLARS,
    SENSOR_TOTAL_KWH,
    SENSOR_UNBILLED_AMOUNT,
)
from .coordinator import AuroraCoordinator


@dataclass(frozen=True, kw_only=True)
class AuroraSensorEntityDescription(SensorEntityDescription):
    """Sensor description extended with a coordinator data key."""

    data_key: str = ""


SENSOR_DESCRIPTIONS: tuple[AuroraSensorEntityDescription, ...] = (
    # --- Billing ---
    AuroraSensorEntityDescription(
        key=SENSOR_ESTIMATED_BALANCE,
        name="Estimated Balance",
        data_key="estimated_balance",
        native_unit_of_measurement="AUD",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        icon="mdi:currency-usd",
    ),
    AuroraSensorEntityDescription(
        key=SENSOR_AMOUNT_OWED,
        name="Amount Owed",
        data_key="amount_owed",
        native_unit_of_measurement="AUD",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        icon="mdi:cash-clock",
    ),
    AuroraSensorEntityDescription(
        key=SENSOR_UNBILLED_AMOUNT,
        name="Unbilled Amount",
        data_key="unbilled_amount",
        native_unit_of_measurement="AUD",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        icon="mdi:receipt-text-clock",
    ),
    AuroraSensorEntityDescription(
        key=SENSOR_AVG_DAILY_USAGE,
        name="Average Daily Usage",
        data_key="average_daily_usage",
        native_unit_of_measurement="AUD",
        device_class=SensorDeviceClass.MONETARY,
        state_class=None,
        icon="mdi:currency-usd",
        suggested_display_precision=2,
    ),
    AuroraSensorEntityDescription(
        key=SENSOR_DAYS_REMAINING,
        name="Usage Days Remaining",
        data_key="usage_days_remaining",
        native_unit_of_measurement="d",
        device_class=None,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:calendar-clock",
    ),
    AuroraSensorEntityDescription(
        key=SENSOR_BILL_TOTAL,
        name="Bill Total Amount",
        data_key="bill_total_amount",
        native_unit_of_measurement="AUD",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        icon="mdi:file-document-outline",
    ),
    # --- Daily usage totals ---
    AuroraSensorEntityDescription(
        key=SENSOR_TOTAL_KWH,
        name="Daily Total Usage",
        data_key="total_kwh",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:meter-electric",
        suggested_display_precision=3,
    ),
    AuroraSensorEntityDescription(
        key=SENSOR_TOTAL_DOLLARS,
        name="Daily Total Cost",
        data_key="total_dollars",
        native_unit_of_measurement="AUD",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        icon="mdi:currency-usd",
        suggested_display_precision=2,
    ),
    # --- T41 Heating tariff ---
    AuroraSensorEntityDescription(
        key=SENSOR_T41_KWH,
        name="T41 Heating Usage",
        data_key="t41_kwh",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:radiator",
        suggested_display_precision=3,
        entity_registry_enabled_default=False,
    ),
    AuroraSensorEntityDescription(
        key=SENSOR_T41_DOLLARS,
        name="T41 Heating Cost",
        data_key="t41_dollars",
        native_unit_of_measurement="AUD",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        icon="mdi:radiator",
        suggested_display_precision=2,
        entity_registry_enabled_default=False,
    ),
    # --- T31 General Power tariff ---
    AuroraSensorEntityDescription(
        key=SENSOR_T31_KWH,
        name="T31 General Usage",
        data_key="t31_kwh",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:power-plug",
        suggested_display_precision=3,
        entity_registry_enabled_default=False,
    ),
    AuroraSensorEntityDescription(
        key=SENSOR_T31_DOLLARS,
        name="T31 General Cost",
        data_key="t31_dollars",
        native_unit_of_measurement="AUD",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        icon="mdi:power-plug",
        suggested_display_precision=2,
        entity_registry_enabled_default=False,
    ),
    # --- T93 Time-of-Use tariff (disabled by default — account-type-dependent) ---
    AuroraSensorEntityDescription(
        key=SENSOR_T93PEAK_KWH,
        name="T93 Peak Usage",
        data_key="t93peak_kwh",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:lightning-bolt",
        suggested_display_precision=3,
        entity_registry_enabled_default=False,
    ),
    AuroraSensorEntityDescription(
        key=SENSOR_T93PEAK_DOLLARS,
        name="T93 Peak Cost",
        data_key="t93peak_dollars",
        native_unit_of_measurement="AUD",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        icon="mdi:lightning-bolt",
        suggested_display_precision=2,
        entity_registry_enabled_default=False,
    ),
    AuroraSensorEntityDescription(
        key=SENSOR_T93OFFPEAK_KWH,
        name="T93 Off-Peak Usage",
        data_key="t93offpeak_kwh",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:lightning-bolt-outline",
        suggested_display_precision=3,
        entity_registry_enabled_default=False,
    ),
    AuroraSensorEntityDescription(
        key=SENSOR_T93OFFPEAK_DOLLARS,
        name="T93 Off-Peak Cost",
        data_key="t93offpeak_dollars",
        native_unit_of_measurement="AUD",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        icon="mdi:lightning-bolt-outline",
        suggested_display_precision=2,
        entity_registry_enabled_default=False,
    ),
    # --- Power Hours demand-response program ---
    AuroraSensorEntityDescription(
        key=SENSOR_PH_STATUS,
        name="Power Hour Status",
        data_key="powerhour_status",
        native_unit_of_measurement=None,
        device_class=None,
        state_class=None,
        icon="mdi:clock-star-four-points",
    ),
    AuroraSensorEntityDescription(
        key=SENSOR_PH_EVENT_NAME,
        name="Power Hour Event",
        data_key="powerhour_event_name",
        native_unit_of_measurement=None,
        device_class=None,
        state_class=None,
        icon="mdi:calendar-star",
    ),
    AuroraSensorEntityDescription(
        key=SENSOR_PH_START,
        name="Power Hour Start",
        data_key="powerhour_start",
        native_unit_of_measurement=None,
        device_class=SensorDeviceClass.TIMESTAMP,
        state_class=None,
        icon="mdi:clock-start",
    ),
    AuroraSensorEntityDescription(
        key=SENSOR_PH_END,
        name="Power Hour End",
        data_key="powerhour_end",
        native_unit_of_measurement=None,
        device_class=SensorDeviceClass.TIMESTAMP,
        state_class=None,
        icon="mdi:clock-end",
    ),
    AuroraSensorEntityDescription(
        key=SENSOR_PH_SELECTION_DEADLINE,
        name="Power Hour Selection Deadline",
        data_key="powerhour_selection_deadline",
        native_unit_of_measurement=None,
        device_class=SensorDeviceClass.TIMESTAMP,
        state_class=None,
        icon="mdi:timer-sand",
    ),
    AuroraSensorEntityDescription(
        key=SENSOR_PH_TOTAL_SAVINGS,
        name="Power Hour Total Savings",
        data_key="powerhour_total_savings",
        native_unit_of_measurement="AUD",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:piggy-bank",
        suggested_display_precision=2,
    ),
    # --- Solar feed-in ---
    AuroraSensorEntityDescription(
        key=SENSOR_SOLAR_KWH,
        name="Solar Feed-in",
        data_key="solar_feedin_kwh",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:solar-panel",
        suggested_display_precision=3,
    ),
    AuroraSensorEntityDescription(
        key=SENSOR_SOLAR_DOLLARS,
        name="Solar Feed-in Earnings",
        data_key="solar_feedin_dollars",
        native_unit_of_measurement="AUD",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        icon="mdi:solar-panel-large",
        suggested_display_precision=2,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Aurora Energy sensors from a config entry."""
    coordinator: AuroraCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    entities: list[SensorEntity] = [
        AuroraSensor(coordinator, description, entry)
        for description in SENSOR_DESCRIPTIONS
    ]
    entities.append(TariffPeriodSensor(entry))
    async_add_entities(entities)


class AuroraSensor(CoordinatorEntity[AuroraCoordinator], SensorEntity):
    """Sensor entity that reads from the AuroraCoordinator."""

    entity_description: AuroraSensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: AuroraCoordinator,
        description: AuroraSensorEntityDescription,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Aurora Energy",
            manufacturer="Aurora Energy Tasmania",
            model="Aurora+",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def native_value(self) -> Optional[Any]:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(self.entity_description.data_key)

    @property
    def available(self) -> bool:
        return (
            self.coordinator.last_update_success
            and self.coordinator.data is not None
        )


class TariffPeriodSensor(SensorEntity):
    """Sensor showing the current T93 tariff period: 'peak' or 'off_peak'.

    Value is computed from wall-clock time in Australia/Hobart timezone.
    Updates are triggered by time-change listeners at exact transition
    boundaries (07:00, 22:00, and 00:00 for weekday transitions) rather
    than polling, so the state flips at the correct second.

    Aurora T93 schedule (NEM clock, AEST UTC+10 — does NOT observe daylight saving):
      Peak:     07:00–22:00 AEST, Monday–Friday
      Off-peak: all other times

    During AEDT (Tasmania daylight saving, UTC+11) peak appears as 08:00–23:00
    local time, but the underlying NEM boundary is still 07:00–22:00 AEST.
    This sensor always computes against fixed UTC+10, never local Hobart time.

    Note: public holidays are treated as weekdays by this implementation.
    """

    _attr_has_entity_name = True
    _attr_name = "T93 Tariff Period"
    _attr_icon = "mdi:clock-time-eight"
    _attr_should_poll = False

    # Fixed AEST offset — UTC+10 with no DST adjustment, matching the NEM clock
    _AEST = datetime.timezone(datetime.timedelta(hours=10))

    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_t93_tariff_period"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Aurora Energy",
            manufacturer="Aurora Energy Tasmania",
            model="Aurora+",
            entry_type=DeviceEntryType.SERVICE,
        )
        self._unsub_listeners: list = []

    @property
    def native_value(self) -> str:
        # Always compute against AEST (UTC+10). The NEM tariff clock does not
        # observe daylight saving, so during AEDT the peak window shifts to
        # 08:00–23:00 local time but remains 07:00–22:00 AEST.
        now_aest = dt_util.utcnow().astimezone(self._AEST)
        if now_aest.weekday() < 5 and 7 <= now_aest.hour < 22:
            return "peak"
        return "off_peak"

    async def async_added_to_hass(self) -> None:
        """Register UTC time-change listeners for exact AEST tariff transitions.

        Listeners fire at the fixed UTC times that correspond to the AEST
        boundaries, so they remain correct regardless of DST:
          21:00 UTC = 07:00 AEST (peak start on weekdays)
          12:00 UTC = 22:00 AEST (peak end on weekdays)
          14:00 UTC = 00:00 AEST (weekday/weekend boundary)
        """
        for hr in (12, 14, 21):
            self._unsub_listeners.append(
                async_track_utc_time_change(
                    self.hass,
                    self._handle_time_change,
                    hour=hr,
                    minute=0,
                    second=0,
                )
            )

    async def async_will_remove_from_hass(self) -> None:
        """Cancel time-change listeners on removal."""
        for unsub in self._unsub_listeners:
            unsub()
        self._unsub_listeners.clear()

    async def _handle_time_change(self, now: Any) -> None:
        """Recompute and push state at tariff transition times."""
        self.async_write_ha_state()
