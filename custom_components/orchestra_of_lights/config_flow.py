"""Config flow for Gemmy Orchestra of Lights."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .client import OrchestraOfLightsClient, normalize_hub_id
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
    TRANSPORT_CLOUD,
    TRANSPORT_LOCAL,
)

_LOGGER = logging.getLogger(__name__)

TRANSPORT_OPTIONS = [TRANSPORT_AUTO, TRANSPORT_LOCAL, TRANSPORT_CLOUD]


async def _validate_hub(data: dict[str, Any]) -> dict[str, Any]:
    """Verify we can connect to the hub and read its state."""
    hub_id = normalize_hub_id(data[CONF_HUB_ID])
    host = (data.get(CONF_HOST) or "").strip() or None
    port = int(data.get(CONF_PORT, DEFAULT_PORT))
    password = data.get(CONF_PASSWORD, "")
    transport = data.get(CONF_TRANSPORT, TRANSPORT_AUTO)

    client = OrchestraOfLightsClient(
        hub_id=hub_id,
        host=host,
        port=port,
        password=password,
        transport=transport,
    )
    try:
        await client.connect()
        await client.refresh_all(timeout=6.0)
        title = (
            f"{DEFAULT_NAME} ({client.state.group_name})"
            if client.state.group_name
            else f"{DEFAULT_NAME} ({hub_id[-4:].upper()})"
        )
        return {
            "hub_id": hub_id,
            "host": host or "",
            "port": port,
            "password": password,
            "transport": transport,
            "title": title,
        }
    finally:
        await client.disconnect()


class OrchestraOfLightsConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Gemmy Orchestra of Lights."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial setup step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                validated = await _validate_hub(user_input)
            except ValueError:
                errors["hub_id"] = "invalid_hub_id"
            except Exception as err:
                _LOGGER.warning("Cannot connect to Orchestra of Lights hub: %s", err)
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(validated["hub_id"])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=validated["title"],
                    data={
                        CONF_HUB_ID: validated["hub_id"],
                        CONF_HOST: validated["host"],
                        CONF_PORT: validated["port"],
                        CONF_PASSWORD: validated["password"],
                        CONF_TRANSPORT: validated["transport"],
                    },
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_HUB_ID): str,
                vol.Optional(CONF_HOST, default=""): str,
                vol.Optional(CONF_TRANSPORT, default=TRANSPORT_AUTO): vol.In(
                    TRANSPORT_OPTIONS
                ),
                vol.Optional(CONF_PASSWORD, default=""): str,
                vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> OrchestraOfLightsOptionsFlow:
        return OrchestraOfLightsOptionsFlow(config_entry)


class OrchestraOfLightsOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for updating IP / transport / password."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = {**self._config_entry.data, **self._config_entry.options}
        schema = vol.Schema(
            {
                vol.Optional(CONF_HOST, default=current.get(CONF_HOST, "")): str,
                vol.Optional(
                    CONF_TRANSPORT,
                    default=current.get(CONF_TRANSPORT, TRANSPORT_AUTO),
                ): vol.In(TRANSPORT_OPTIONS),
                vol.Optional(
                    CONF_PASSWORD, default=current.get(CONF_PASSWORD, "")
                ): str,
                vol.Optional(
                    CONF_PORT, default=current.get(CONF_PORT, DEFAULT_PORT)
                ): int,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
