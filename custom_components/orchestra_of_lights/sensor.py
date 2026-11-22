"""Sensor platform for Gemmy Orchestra of Lights diagnostics and paired devices."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import SIGNAL_STRENGTH_DECIBELS_MILLIWATT, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import OrchestraCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Orchestra of Lights sensor entities."""
    coordinator: OrchestraCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            OrchestraRssiSensor(coordinator),
            OrchestraDevicesSensor(coordinator),
            OrchestraTransportSensor(coordinator),
        ]
    )


class OrchestraRssiSensor(CoordinatorEntity[OrchestraCoordinator], SensorEntity):
    """Hub Wi-Fi RSSI diagnostic sensor."""

    _attr_has_entity_name = True
    _attr_name = "Wi-Fi Signal"
    _attr_device_class = SensorDeviceClass.SIGNAL_STRENGTH
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = SIGNAL_STRENGTH_DECIBELS_MILLIWATT
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: OrchestraCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.hub_id}_rssi"
        self._attr_device_info = coordinator.device_info

    @property
    def native_value(self) -> int | None:
        return self.coordinator.data.rssi


class OrchestraDevicesSensor(CoordinatorEntity[OrchestraCoordinator], SensorEntity):
    """Count and details of 2.4 GHz Orchestra of Lights products paired to the hub."""

    _attr_has_entity_name = True
    _attr_name = "Paired Products"
    _attr_icon = "mdi:string-lights"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: OrchestraCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.hub_id}_devices"
        self._attr_device_info = coordinator.device_info

    @property
    def native_value(self) -> int:
        return len(self.coordinator.data.devices)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        st = self.coordinator.data
        return {
            "group_id": st.group_id,
            "rf_version": st.rf_ver,
            "has_op2_speaker": st.has_op2_speaker,
            "products": [
                {
                    "name": d.name,
                    "type_id": d.device_id,
                    "mac": d.mac,
                    "bound": d.bound,
                    "slot": d.slot,
                }
                for d in st.devices
            ],
        }


class OrchestraTransportSensor(CoordinatorEntity[OrchestraCoordinator], SensorEntity):
    """Active communication transport (local TCP 8087 vs cloud AWS IoT MQTT)."""

    _attr_has_entity_name = True
    _attr_name = "Connection Transport"
    _attr_icon = "mdi:lan-connect"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: OrchestraCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.hub_id}_transport"
        self._attr_device_info = coordinator.device_info

    @property
    def native_value(self) -> str:
        st = self.coordinator.data
        if not st.connected:
            return "disconnected"
        return st.transport or "unknown"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        st = self.coordinator.data
        return {
            "hub_version": st.hub_ver,
            "ssid": st.ssid,
            "local_host": self.coordinator.host or "",
        }
