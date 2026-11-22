"""Media player platform for Gemmy Orchestra of Lights synchronized music shows."""

from __future__ import annotations

from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, SONG_NAME_TO_ID, SONGS
from .coordinator import OrchestraCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Orchestra of Lights media player."""
    coordinator: OrchestraCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([OrchestraMediaPlayer(coordinator)])


class OrchestraMediaPlayer(CoordinatorEntity[OrchestraCoordinator], MediaPlayerEntity):
    """Media player for built-in Orchestra of Lights musical lightshows."""

    _attr_has_entity_name = True
    _attr_name = "Music Show"
    _attr_supported_features = (
        MediaPlayerEntityFeature.PLAY
        | MediaPlayerEntityFeature.PAUSE
        | MediaPlayerEntityFeature.STOP
        | MediaPlayerEntityFeature.VOLUME_SET
        | MediaPlayerEntityFeature.NEXT_TRACK
        | MediaPlayerEntityFeature.PREVIOUS_TRACK
        | MediaPlayerEntityFeature.SHUFFLE_SET
        | MediaPlayerEntityFeature.SELECT_SOURCE
        | MediaPlayerEntityFeature.TURN_ON
        | MediaPlayerEntityFeature.TURN_OFF
    )

    def __init__(self, coordinator: OrchestraCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.hub_id}_media_player"
        self._attr_device_info = coordinator.device_info

    @property
    def state(self) -> MediaPlayerState:
        st = self.coordinator.data
        if not st.power:
            return MediaPlayerState.OFF
        if st.music_status == 1:
            return MediaPlayerState.PLAYING
        if st.music_status == 2:
            return MediaPlayerState.PAUSED
        return MediaPlayerState.IDLE

    @property
    def volume_level(self) -> float:
        return max(0.0, min(1.0, self.coordinator.data.volume / 100.0))

    @property
    def shuffle(self) -> bool:
        return self.coordinator.data.music_mode == 1

    @property
    def media_title(self) -> str | None:
        if self.coordinator.data.music_status in (1, 2):
            return self.coordinator.data.song_name
        return None

    @property
    def source(self) -> str | None:
        return self.coordinator.data.song_name

    @property
    def source_list(self) -> list[str]:
        if self.coordinator.data.devices and not self.coordinator.data.has_op2_speaker:
            return [SONGS[i] for i in range(6)]
        return [SONGS[i] for i in range(12)]

    async def async_media_play(self) -> None:
        st = self.coordinator.data
        if st.music_status == 2:
            await self.coordinator.client.resume_music()
        else:
            song = st.music_song if 0 <= st.music_song <= 11 else 0
            await self.coordinator.client.play_song(song)

    async def async_media_pause(self) -> None:
        await self.coordinator.client.pause_music()

    async def async_media_stop(self) -> None:
        await self.coordinator.client.pause_music()

    async def async_set_volume_level(self, volume: float) -> None:
        await self.coordinator.client.set_volume(round(volume * 100))

    async def async_set_shuffle(self, shuffle: bool) -> None:
        await self.coordinator.client.set_music_mode(shuffle)

    async def async_select_source(self, source: str) -> None:
        song_id = SONG_NAME_TO_ID.get(source)
        if song_id is not None:
            await self.coordinator.client.play_song(song_id)

    async def async_media_next_track(self) -> None:
        st = self.coordinator.data
        playlist = st.music_playlist or list(range(6))
        if st.music_song in playlist:
            idx = (playlist.index(st.music_song) + 1) % len(playlist)
            next_song = playlist[idx]
        else:
            next_song = playlist[0]
        await self.coordinator.client.play_song(next_song)

    async def async_media_previous_track(self) -> None:
        st = self.coordinator.data
        playlist = st.music_playlist or list(range(6))
        if st.music_song in playlist:
            idx = (playlist.index(st.music_song) - 1) % len(playlist)
            prev_song = playlist[idx]
        else:
            prev_song = playlist[0]
        await self.coordinator.client.play_song(prev_song)

    async def async_turn_on(self) -> None:
        await self.async_media_play()

    async def async_turn_off(self) -> None:
        await self.coordinator.client.set_power(False)
