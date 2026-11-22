"""Button platform for Gemmy Orchestra of Lights (Random Show, Next Song, Refresh)."""

from __future__ import annotations

import random

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, SOLID_COLOR_THEMES, THEMES
from .coordinator import OrchestraCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Orchestra of Lights button entities."""
    coordinator: OrchestraCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            OrchestraRandomShowButton(coordinator),
            OrchestraNextSongButton(coordinator),
            OrchestraRefreshButton(coordinator),
        ]
    )


class OrchestraRandomShowButton(CoordinatorEntity[OrchestraCoordinator], ButtonEntity):
    """Trigger a random theme + effect (replicates the mobile app's Shake feature)."""

    _attr_has_entity_name = True
    _attr_name = "Random Show"
    _attr_icon = "mdi:dice-multiple"

    def __init__(self, coordinator: OrchestraCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.hub_id}_random_show"
        self._attr_device_info = coordinator.device_info

    async def async_press(self) -> None:
        theme_id = random.choice(list(THEMES.keys()))
        max_effect = 3 if theme_id in SOLID_COLOR_THEMES else 4
        effect_id = random.randint(0, max_effect)
        await self.coordinator.client.set_theme(theme_id, effect_id)


class OrchestraNextSongButton(CoordinatorEntity[OrchestraCoordinator], ButtonEntity):
    """Skip to the next song in the hub's active playlist."""

    _attr_has_entity_name = True
    _attr_name = "Next Song"
    _attr_icon = "mdi:skip-next"

    def __init__(self, coordinator: OrchestraCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.hub_id}_next_song"
        self._attr_device_info = coordinator.device_info

    async def async_press(self) -> None:
        st = self.coordinator.data
        playlist = st.music_playlist or list(range(6))
        if st.music_song in playlist:
            next_song = playlist[(playlist.index(st.music_song) + 1) % len(playlist)]
        else:
            next_song = playlist[0]
        await self.coordinator.client.play_song(next_song)


class OrchestraRefreshButton(CoordinatorEntity[OrchestraCoordinator], ButtonEntity):
    """Force an immediate refresh of hub state, RSSI, and paired products."""

    _attr_has_entity_name = True
    _attr_name = "Refresh Status"
    _attr_icon = "mdi:refresh"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: OrchestraCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.hub_id}_refresh"
        self._attr_device_info = coordinator.device_info

    async def async_press(self) -> None:
        await self.coordinator.client.refresh_all(timeout=6.0)
        self.coordinator.async_set_updated_data(self.coordinator.client.state)
