"""Config flow for Plant Happiness.

Setup is split into two steps:

  Step 1 – "user"      : plant name + HA sensor entity assignments
  Step 2 – "plantbook" : optional Open PlantBook credentials + species name

The PlantBook step is always presented but all fields are optional.  Leaving
them blank simply disables species-aware scoring for that plant.
"""

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
    CONF_PLANTBOOK_CLIENT_ID,
    CONF_PLANTBOOK_CLIENT_SECRET,
    CONF_PLANT_SPECIES,
    CONF_TEMPERATURE_ENTITY,
    DOMAIN,
)


# ---------------------------------------------------------------------------
# Schema helpers
# ---------------------------------------------------------------------------

def _sensor_schema(
    defaults: dict[str, Any] | None = None,
    show_name: bool = True,
) -> vol.Schema:
    """Build the sensor-entity step schema."""
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


def _plantbook_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    """Build the optional Open PlantBook step schema."""
    d = defaults or {}
    return vol.Schema(
        {
            vol.Optional(
                CONF_PLANTBOOK_CLIENT_ID,
                default=d.get(CONF_PLANTBOOK_CLIENT_ID, ""),
            ): str,
            vol.Optional(
                CONF_PLANTBOOK_CLIENT_SECRET,
                default=d.get(CONF_PLANTBOOK_CLIENT_SECRET, ""),
            ): str,
            vol.Optional(
                CONF_PLANT_SPECIES,
                default=d.get(CONF_PLANT_SPECIES, ""),
            ): str,
        }
    )


def _slugify(name: str) -> str:
    """Convert a plant name to a safe slug for unique_id comparison."""
    return re.sub(r"[^a-z0-9_]+", "_", name.lower()).strip("_")


def _clean(data: dict[str, Any]) -> dict[str, Any]:
    """Strip blank-string values so absent optionals are cleanly absent."""
    return {k: v for k, v in data.items() if v != ""}


# ---------------------------------------------------------------------------
# Config flow (initial setup)
# ---------------------------------------------------------------------------

class PlantHappinessConfigFlow(ConfigFlow, domain=DOMAIN):
    """Two-step setup: sensors → optional PlantBook credentials."""

    VERSION = 1

    def __init__(self) -> None:
        self._sensor_data: dict[str, Any] = {}

    # Step 1 — sensor entities
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            plant_name = user_input.get(CONF_PLANT_NAME, "").strip()

            await self.async_set_unique_id(_slugify(plant_name))
            self._abort_if_unique_id_configured()

            if not user_input.get(CONF_MOISTURE_ENTITY):
                errors[CONF_MOISTURE_ENTITY] = "moisture_required"
            elif not user_input.get(CONF_LIGHT_ENTITY):
                errors[CONF_LIGHT_ENTITY] = "light_required"
            else:
                self._sensor_data = _clean(user_input)
                return await self.async_step_plantbook()

        return self.async_show_form(
            step_id="user",
            data_schema=_sensor_schema(user_input),
            errors=errors,
        )

    # Step 2 — optional PlantBook credentials
    async def async_step_plantbook(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            data = {**self._sensor_data, **_clean(user_input)}
            plant_name = data.get(CONF_PLANT_NAME, "Plant")
            return self.async_create_entry(title=plant_name, data=data)

        return self.async_show_form(
            step_id="plantbook",
            data_schema=_plantbook_schema(),
            errors={},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> PlantHappinessOptionsFlow:
        return PlantHappinessOptionsFlow(config_entry)


# ---------------------------------------------------------------------------
# Options flow (edit after setup)
# ---------------------------------------------------------------------------

class PlantHappinessOptionsFlow(OptionsFlow):
    """Two-step options edit: sensors → optional PlantBook credentials."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._config_entry = config_entry
        self._sensor_data: dict[str, Any] = {}

    def _current(self) -> dict[str, Any]:
        """Merged view of data + existing options."""
        return {**self._config_entry.data, **self._config_entry.options}

    # Step 1 — sensor entities
    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        current = self._current()

        if user_input is not None:
            if not user_input.get(CONF_MOISTURE_ENTITY):
                errors[CONF_MOISTURE_ENTITY] = "moisture_required"
            elif not user_input.get(CONF_LIGHT_ENTITY):
                errors[CONF_LIGHT_ENTITY] = "light_required"
            else:
                self._sensor_data = _clean(user_input)
                return await self.async_step_plantbook()

        return self.async_show_form(
            step_id="init",
            data_schema=_sensor_schema(defaults=current, show_name=False),
            errors=errors,
        )

    # Step 2 — optional PlantBook credentials
    async def async_step_plantbook(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        current = self._current()

        if user_input is not None:
            data = {**self._sensor_data, **_clean(user_input)}
            return self.async_create_entry(title="", data=data)

        return self.async_show_form(
            step_id="plantbook",
            data_schema=_plantbook_schema(defaults=current),
            errors={},
        )
