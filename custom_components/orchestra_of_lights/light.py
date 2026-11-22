"""Light platform for Gemmy Orchestra of Lights."""

from __future__ import annotations

from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_EFFECT,
    ATTR_RGB_COLOR,
    ColorMode,
    LightEntity,
    LightEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, THEME_NAME_TO_ID, THEMES
from .coordinator import OrchestraCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Orchestra of Lights light entity."""
    coordinator: OrchestraCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([OrchestraLight(coordinator)])


class OrchestraLight(CoordinatorEntity[OrchestraCoordinator], LightEntity):
    """Main light entity controlling the Orchestra of Lights Hub."""

    _attr_has_entity_name = True
    _attr_name = "Lights"
    _attr_supported_color_modes = {ColorMode.RGB}
    _attr_color_mode = ColorMode.RGB
    _attr_supported_features = LightEntityFeature.EFFECT
    _attr_effect_list = list(THEMES.values())

    def __init__(self, coordinator: OrchestraCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.hub_id}_light"
        self._attr_device_info = coordinator.device_info

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.power

    @property
    def brightness(self) -> int:
        # Hub brightness is 0..100, HA uses 0..255
        return round(self.coordinator.data.brightness * 255 / 100)

    @property
    def rgb_color(self) -> tuple[int, int, int]:
        return self.coordinator.data.rgb

    @property
    def effect(self) -> str | None:
        if self.coordinator.data.color_mode == "theme":
            return self.coordinator.data.theme_name
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        st = self.coordinator.data
        return {
            "theme_id": st.theme,
            "theme_name": st.theme_name,
            "effect_id": st.effect,
            "effect_name": st.effect_name,
            "color_mode_raw": st.color_mode,
        }

    async def async_turn_on(self, **kwargs: Any) -> None:
        client = self.coordinator.client

        if ATTR_EFFECT in kwargs:
            effect_name = kwargs[ATTR_EFFECT]
            theme_id = THEME_NAME_TO_ID.get(effect_name)
            if theme_id is not None:
                await client.set_theme(theme_id)
                return

        if ATTR_RGB_COLOR in kwargs or ATTR_BRIGHTNESS in kwargs:
            r, g, b = kwargs.get(ATTR_RGB_COLOR, self.coordinator.data.rgb)
            bri_pct = (
                max(1, round(kwargs[ATTR_BRIGHTNESS] * 100 / 255))
                if ATTR_BRIGHTNESS in kwargs
                else self.coordinator.data.brightness
            )
            await client.set_rgb(r, g, b, bri_pct)
            return

        await client.set_power(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.client.set_power(False)
