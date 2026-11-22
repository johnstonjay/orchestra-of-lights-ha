"""The Gemmy Orchestra of Lights integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError

from .client import normalize_hub_id
from .const import (
    DOMAIN,
    EFFECT_NAME_TO_ID,
    SONG_NAME_TO_ID,
    THEME_NAME_TO_ID,
)
from .coordinator import OrchestraCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.LIGHT,
    Platform.MEDIA_PLAYER,
    Platform.SELECT,
    Platform.NUMBER,
    Platform.SWITCH,
    Platform.BUTTON,
    Platform.SENSOR,
]

SERVICE_SET_THEME = "set_theme"
SERVICE_PLAY_SONG = "play_song"
SERVICE_SET_PLAYLIST = "set_playlist"
SERVICE_SET_TIMER = "set_timer"
SERVICE_REFRESH = "refresh"

_SERVICE_REGISTERED_KEY = "_services_registered"


def _resolve_theme_id(value: str | int) -> int:
    if isinstance(value, int) or str(value).strip().isdigit():
        return int(value)
    low = str(value).strip().lower()
    for name, tid in THEME_NAME_TO_ID.items():
        if name.lower() == low:
            return tid
    for name, tid in THEME_NAME_TO_ID.items():
        if low in name.lower():
            return tid
    raise HomeAssistantError(f"Unknown Orchestra of Lights theme: {value}")


def _resolve_effect_id(value: str | int | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, int) or str(value).strip().isdigit():
        return int(value)
    low = str(value).strip().lower()
    for name, eid in EFFECT_NAME_TO_ID.items():
        if name.lower() == low or low in name.lower():
            return eid
    raise HomeAssistantError(f"Unknown Orchestra of Lights effect: {value}")


def _resolve_song_id(value: str | int) -> int:
    if isinstance(value, int) or str(value).strip().isdigit():
        idx = int(value)
        if 0 <= idx <= 11:
            return idx
        raise HomeAssistantError(f"Song index out of range (0-11): {idx}")
    low = str(value).strip().lower()
    for name, sid in SONG_NAME_TO_ID.items():
        if name.lower() == low:
            return sid
    for name, sid in SONG_NAME_TO_ID.items():
        if low in name.lower():
            return sid
    raise HomeAssistantError(f"Unknown Orchestra of Lights song: {value}")


def _target_coordinators(
    hass: HomeAssistant, hub_id: str | None
) -> list[OrchestraCoordinator]:
    domain_data: dict[str, Any] = hass.data.get(DOMAIN, {})
    coordinators = [
        v for k, v in domain_data.items() if isinstance(v, OrchestraCoordinator)
    ]
    if not coordinators:
        raise HomeAssistantError("No Orchestra of Lights hubs are configured")
    if hub_id:
        norm = normalize_hub_id(hub_id)
        matched = [c for c in coordinators if c.hub_id == norm]
        if not matched:
            raise HomeAssistantError(f"Orchestra of Lights hub not found: {hub_id}")
        return matched
    return coordinators


def _register_services(hass: HomeAssistant) -> None:
    domain_data = hass.data.setdefault(DOMAIN, {})
    if domain_data.get(_SERVICE_REGISTERED_KEY):
        return

    async def handle_set_theme(call: ServiceCall) -> None:
        theme_id = _resolve_theme_id(call.data["theme"])
        effect_id = _resolve_effect_id(call.data.get("effect"))
        for coord in _target_coordinators(hass, call.data.get("hub_id")):
            await coord.client.set_theme(theme_id, effect_id)

    async def handle_play_song(call: ServiceCall) -> None:
        song_id = _resolve_song_id(call.data["song"])
        volume = call.data.get("volume")
        for coord in _target_coordinators(hass, call.data.get("hub_id")):
            if volume is not None:
                await coord.client.set_volume(int(volume))
            await coord.client.play_song(song_id)

    async def handle_set_playlist(call: ServiceCall) -> None:
        raw_songs = call.data["songs"]
        if not isinstance(raw_songs, list) or not raw_songs:
            raise HomeAssistantError("songs must be a non-empty list")
        indices = [_resolve_song_id(s) for s in raw_songs]
        for coord in _target_coordinators(hass, call.data.get("hub_id")):
            await coord.client.set_playlist(indices)

    async def handle_set_timer(call: ServiceCall) -> None:
        enabled = bool(call.data["enabled"])
        sh = sm = eh = em = None
        if call.data.get("start_time"):
            sh, sm = (int(x) for x in str(call.data["start_time"]).split(":"))
        if call.data.get("stop_time"):
            eh, em = (int(x) for x in str(call.data["stop_time"]).split(":"))
        for coord in _target_coordinators(hass, call.data.get("hub_id")):
            await coord.client.set_timer(enabled, sh, sm, eh, em)

    async def handle_refresh(call: ServiceCall) -> None:
        for coord in _target_coordinators(hass, call.data.get("hub_id")):
            await coord.client.refresh_all(timeout=6.0)
            coord.async_set_updated_data(coord.client.state)

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_THEME,
        handle_set_theme,
        schema=vol.Schema(
            {
                vol.Optional("hub_id"): str,
                vol.Required("theme"): vol.Any(str, int),
                vol.Optional("effect"): vol.Any(str, int),
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_PLAY_SONG,
        handle_play_song,
        schema=vol.Schema(
            {
                vol.Optional("hub_id"): str,
                vol.Required("song"): vol.Any(str, int),
                vol.Optional("volume"): vol.All(vol.Coerce(int), vol.Range(min=0, max=100)),
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_PLAYLIST,
        handle_set_playlist,
        schema=vol.Schema(
            {
                vol.Optional("hub_id"): str,
                vol.Required("songs"): list,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_TIMER,
        handle_set_timer,
        schema=vol.Schema(
            {
                vol.Optional("hub_id"): str,
                vol.Required("enabled"): bool,
                vol.Optional("start_time"): str,
                vol.Optional("stop_time"): str,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_REFRESH,
        handle_refresh,
        schema=vol.Schema({vol.Optional("hub_id"): str}),
    )

    domain_data[_SERVICE_REGISTERED_KEY] = True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Gemmy Orchestra of Lights from a config entry."""
    coordinator = OrchestraCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    _register_services(hass)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload entry when options are updated."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator: OrchestraCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_shutdown()

        # Unregister services if no entries remain
        remaining = [
            v
            for v in hass.data.get(DOMAIN, {}).values()
            if isinstance(v, OrchestraCoordinator)
        ]
        if not remaining and hass.data.get(DOMAIN, {}).get(_SERVICE_REGISTERED_KEY):
            for svc in (
                SERVICE_SET_THEME,
                SERVICE_PLAY_SONG,
                SERVICE_SET_PLAYLIST,
                SERVICE_SET_TIMER,
                SERVICE_REFRESH,
            ):
                hass.services.async_remove(DOMAIN, svc)
            hass.data[DOMAIN][_SERVICE_REGISTERED_KEY] = False

    return unload_ok
