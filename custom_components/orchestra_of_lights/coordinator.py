"""DataUpdateCoordinator for Gemmy Orchestra of Lights."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import OrchestraOfLightsClient, OrchestraState
from .const import (
    CONF_HOST,
    CONF_HUB_ID,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_TRANSPORT,
    DEFAULT_NAME,
    DEFAULT_PORT,
    DOMAIN,
    TRANSPORT_AUTO,
)

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(seconds=60)


class OrchestraCoordinator(DataUpdateCoordinator[OrchestraState]):
    """Coordinator managing push + poll updates for an Orchestra of Lights Hub."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.config_entry = entry
        data = {**entry.data, **entry.options}
        self.hub_id: str = data[CONF_HUB_ID]
        self.host: str | None = data.get(CONF_HOST) or None
        self.port: int = int(data.get(CONF_PORT, DEFAULT_PORT))
        self.password: str = data.get(CONF_PASSWORD, "")
        self.transport: str = data.get(CONF_TRANSPORT, TRANSPORT_AUTO)

        self.client = OrchestraOfLightsClient(
            hub_id=self.hub_id,
            host=self.host,
            port=self.port,
            password=self.password,
            transport=self.transport,
            on_state_update=self._handle_push_update,
        )
        self._info_counter = 0

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{self.hub_id}",
            update_interval=SCAN_INTERVAL,
        )

    def _handle_push_update(self, state: OrchestraState) -> None:
        """Push live updates from TCP/MQTT directly into Home Assistant."""
        self.hass.loop.call_soon_threadsafe(self.async_set_updated_data, state)

    @property
    def device_info(self) -> DeviceInfo:
        """Return Home Assistant DeviceInfo for the hub."""
        mac_formatted = ":".join(
            self.hub_id[i : i + 2] for i in range(0, 12, 2)
        )
        group_name = self.client.state.group_name
        name = f"{DEFAULT_NAME} ({group_name})" if group_name else DEFAULT_NAME
        return DeviceInfo(
            identifiers={(DOMAIN, self.hub_id)},
            connections={(CONNECTION_NETWORK_MAC, mac_formatted)},
            manufacturer="Gemmy Industries",
            model="Orchestra of Lights WiFi Hub",
            name=name,
            sw_version=self.client.state.hub_ver or None,
        )

    async def _async_update_data(self) -> OrchestraState:
        """Refresh state from the hub (and reconnect if needed)."""
        try:
            if not self.client.state.connected:
                await self.client.connect()
                await self.client.refresh_all(timeout=6.0)
            else:
                await self.client.refresh_state(timeout=5.0)
                self._info_counter += 1
                if self._info_counter % 5 == 0 or not self.client.state.hub_ver:
                    await self.client.refresh_info(timeout=5.0)
            return self.client.state
        except (TimeoutError, ConnectionError, OSError) as err:
            # Force clean reconnect on next cycle
            try:
                await self.client.disconnect()
            except Exception:
                pass
            raise UpdateFailed(f"Error communicating with Orchestra of Lights hub {self.hub_id}: {err}") from err

    async def async_shutdown(self) -> None:
        """Disconnect cleanly when unloading the entry."""
        await self.client.disconnect()
        await super().async_shutdown()
