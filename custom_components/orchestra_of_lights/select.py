"""Select platform for Gemmy Orchestra of Lights (Theme, Effect, Song)."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    EFFECT_NAME_TO_ID,
    EFFECTS,
    SONG_NAME_TO_ID,
    SONGS,
    THEME_NAME_TO_ID,
    THEMES,
)
from .coordinator import OrchestraCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Orchestra of Lights select entities."""
    coordinator: OrchestraCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            OrchestraThemeSelect(coordinator),
            OrchestraEffectSelect(coordinator),
            OrchestraSongSelect(coordinator),
        ]
    )


class OrchestraThemeSelect(CoordinatorEntity[OrchestraCoordinator], SelectEntity):
    """Select active lightshow/holiday/color theme."""

    _attr_has_entity_name = True
    _attr_name = "Theme"
    _attr_icon = "mdi:palette"
    _attr_options = list(THEMES.values())

    def __init__(self, coordinator: OrchestraCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.hub_id}_theme"
        self._attr_device_info = coordinator.device_info

    @property
    def current_option(self) -> str | None:
        name = self.coordinator.data.theme_name
        return name if name in self._attr_options else None

    async def async_select_option(self, option: str) -> None:
        theme_id = THEME_NAME_TO_ID.get(option)
        if theme_id is not None:
            await self.coordinator.client.set_theme(theme_id)


class OrchestraEffectSelect(CoordinatorEntity[OrchestraCoordinator], SelectEntity):
    """Select active animation effect (Steady, Glimmer, Sparkle, Starry Night, Lightshow)."""

    _attr_has_entity_name = True
    _attr_name = "Effect"
    _attr_icon = "mdi:sparkles"
    _attr_options = list(EFFECTS.values())

    def __init__(self, coordinator: OrchestraCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.hub_id}_effect"
        self._attr_device_info = coordinator.device_info

    @property
    def current_option(self) -> str | None:
        name = self.coordinator.data.effect_name
        return name if name in self._attr_options else None

    async def async_select_option(self, option: str) -> None:
        effect_id = EFFECT_NAME_TO_ID.get(option)
        if effect_id is not None:
            await self.coordinator.client.set_theme(
                self.coordinator.data.theme, effect_id
            )


class OrchestraSongSelect(CoordinatorEntity[OrchestraCoordinator], SelectEntity):
    """Select and play any of the 12 built-in musical lightshow songs."""

    _attr_has_entity_name = True
    _attr_name = "Song"
    _attr_icon = "mdi:music-note"
    _attr_options = list(SONGS.values())

    def __init__(self, coordinator: OrchestraCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.hub_id}_song"
        self._attr_device_info = coordinator.device_info

    @property
    def current_option(self) -> str | None:
        name = self.coordinator.data.song_name
        return name if name in self._attr_options else None

    async def async_select_option(self, option: str) -> None:
        song_id = SONG_NAME_TO_ID.get(option)
        if song_id is not None:
            await self.coordinator.client.play_song(song_id)
