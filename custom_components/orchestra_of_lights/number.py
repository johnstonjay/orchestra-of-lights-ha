"""Number platform for Gemmy Orchestra of Lights (Speaker Volume slider)."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
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
    """Set up Orchestra of Lights number entities."""
    coordinator: OrchestraCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([OrchestraVolumeNumber(coordinator)])


class OrchestraVolumeNumber(CoordinatorEntity[OrchestraCoordinator], NumberEntity):
    """Direct 0-100% speaker volume slider for easy dashboards and automations."""

    _attr_has_entity_name = True
    _attr_name = "Speaker Volume"
    _attr_icon = "mdi:volume-high"
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 5
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator: OrchestraCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.hub_id}_volume"
        self._attr_device_info = coordinator.device_info

    @property
    def native_value(self) -> float:
        return float(self.coordinator.data.volume)

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.client.set_volume(int(round(value)))
