"""Sensor platform for Aurora Energy integration."""
from __future__ import annotations

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
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    SENSOR_AMOUNT_OWED,
    SENSOR_AVG_DAILY_USAGE,
    SENSOR_BILL_TOTAL,
    SENSOR_DAYS_REMAINING,
    SENSOR_ESTIMATED_BALANCE,
    SENSOR_SOLAR_DOLLARS,
    SENSOR_SOLAR_KWH,
    SENSOR_T31_DOLLARS,
    SENSOR_T31_KWH,
    SENSOR_T41_DOLLARS,
    SENSOR_T41_KWH,
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
    async_add_entities(
        AuroraSensor(coordinator, description, entry)
        for description in SENSOR_DESCRIPTIONS
    )


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
