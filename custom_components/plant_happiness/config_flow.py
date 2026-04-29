"""Config flow for Plant Happiness."""

from __future__ import annotations

import re
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import (
    CONF_HUMIDITY_ENTITY,
    CONF_LIGHT_ENTITY,
    CONF_MOISTURE_ENTITY,
    CONF_PLANT_NAME,
    CONF_TEMPERATURE_ENTITY,
    DOMAIN,
)


def _build_schema(
    defaults: dict[str, Any] | None = None,
    show_name: bool = True,
) -> vol.Schema:
    """Build the config / options schema with optional defaults."""
    d = defaults or {}
    fields: dict[vol.Marker, Any] = {}

    if show_name:
        fields[vol.Required(CONF_PLANT_NAME, default=d.get(CONF_PLANT_NAME, ""))] = str

    fields[vol.Required(CONF_MOISTURE_ENTITY, default=d.get(CONF_MOISTURE_ENTITY, ""))] = (
        selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor"))
    )
    fields[vol.Required(CONF_LIGHT_ENTITY, default=d.get(CONF_LIGHT_ENTITY, ""))] = (
        selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor"))
    )
    fields[vol.Optional(CONF_TEMPERATURE_ENTITY, default=d.get(CONF_TEMPERATURE_ENTITY, ""))] = (
        selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor"))
    )
    fields[vol.Optional(CONF_HUMIDITY_ENTITY, default=d.get(CONF_HUMIDITY_ENTITY, ""))] = (
        selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor"))
    )

    return vol.Schema(fields)


def _slugify(name: str) -> str:
    """Convert a plant name to a safe slug for unique_id comparison."""
    return re.sub(r"[^a-z0-9_]+", "_", name.lower()).strip("_")


class PlantHappinessConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the initial setup flow for a plant."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Show the add-plant form and validate input."""
        errors: dict[str, str] = {}

        if user_input is not None:
            plant_name = user_input.get(CONF_PLANT_NAME, "").strip()

            # Prevent duplicate plant names
            await self.async_set_unique_id(_slugify(plant_name))
            self._abort_if_unique_id_configured()

            # Basic validation
            if not user_input.get(CONF_MOISTURE_ENTITY):
                errors[CONF_MOISTURE_ENTITY] = "moisture_required"
            elif not user_input.get(CONF_LIGHT_ENTITY):
                errors[CONF_LIGHT_ENTITY] = "light_required"
            else:
                # Strip empty optional fields so they're cleanly absent
                data = {k: v for k, v in user_input.items() if v != ""}
                return self.async_create_entry(title=plant_name, data=data)

        return self.async_show_form(
            step_id="user",
            data_schema=_build_schema(user_input),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> PlantHappinessOptionsFlow:
        """Return the options flow so users can edit sensor assignments later."""
        return PlantHappinessOptionsFlow(config_entry)


class PlantHappinessOptionsFlow(OptionsFlow):
    """Allow editing sensor entity assignments after initial setup."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Show the edit form pre-filled with existing values."""
        errors: dict[str, str] = {}

        # Merge config + existing options as defaults
        current: dict[str, Any] = {
            **self._config_entry.data,
            **self._config_entry.options,
        }

        if user_input is not None:
            if not user_input.get(CONF_MOISTURE_ENTITY):
                errors[CONF_MOISTURE_ENTITY] = "moisture_required"
            elif not user_input.get(CONF_LIGHT_ENTITY):
                errors[CONF_LIGHT_ENTITY] = "light_required"
            else:
                cleaned = {k: v for k, v in user_input.items() if v != ""}
                return self.async_create_entry(title="", data=cleaned)

        return self.async_show_form(
            step_id="init",
            data_schema=_build_schema(defaults=current, show_name=False),
            errors=errors,
        )
