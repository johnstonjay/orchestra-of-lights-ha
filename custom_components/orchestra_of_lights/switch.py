"""Switch platform for Gemmy Orchestra of Lights (Bluetooth Speaker, Built-in Timer)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
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
    """Set up Orchestra of Lights switches."""
    coordinator: OrchestraCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            OrchestraBluetoothSwitch(coordinator),
            OrchestraTimerSwitch(coordinator),
        ]
    )


class OrchestraBluetoothSwitch(CoordinatorEntity[OrchestraCoordinator], SwitchEntity):
    """Toggle Bluetooth speaker streaming mode on the hub/speaker."""

    _attr_has_entity_name = True
    _attr_name = "Bluetooth Speaker"
    _attr_icon = "mdi:bluetooth-audio"

    def __init__(self, coordinator: OrchestraCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.hub_id}_bt_speaker"
        self._attr_device_info = coordinator.device_info

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.bt_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.client.set_bluetooth(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.client.set_bluetooth(False)


class OrchestraTimerSwitch(CoordinatorEntity[OrchestraCoordinator], SwitchEntity):
    """Toggle the hub's built-in daily timer (turn off to schedule via Home Assistant)."""

    _attr_has_entity_name = True
    _attr_name = "Hub Built-in Timer"
    _attr_icon = "mdi:timer-outline"

    def __init__(self, coordinator: OrchestraCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.hub_id}_timer"
        self._attr_device_info = coordinator.device_info

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.timer_on

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        st = self.coordinator.data
        return {
            "timer_start": st.timer_start,
            "timer_stop": st.timer_stop,
            "timer_zone": st.timer_zone,
        }

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.client.set_timer(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.client.set_timer(False)
