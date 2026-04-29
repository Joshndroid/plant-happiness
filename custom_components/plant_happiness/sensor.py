"""Plant Happiness sensor platform.

One PlantHappinessSensor entity is created per config entry.

Entity state  : mood string — one of thriving / happy / okay / struggling /
                need_water / dark / critical / unavailable
Attributes    : happiness_score, per-sensor value + status label + color,
                entity_id references so the Lovelace card can look up
                last_changed timestamps.
"""

from __future__ import annotations

import logging
import math
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, State, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.util.unit_conversion import TemperatureConverter
from homeassistant.const import UnitOfTemperature

from .const import (
    ATTR_HAPPINESS_SCORE,
    ATTR_HUMIDITY,
    ATTR_HUMIDITY_COLOR,
    ATTR_HUMIDITY_ENTITY,
    ATTR_HUMIDITY_STATUS,
    ATTR_LIGHT,
    ATTR_LIGHT_COLOR,
    ATTR_LIGHT_ENTITY,
    ATTR_LIGHT_STATUS,
    ATTR_MOISTURE,
    ATTR_MOISTURE_COLOR,
    ATTR_MOISTURE_ENTITY,
    ATTR_MOISTURE_STATUS,
    ATTR_TEMPERATURE,
    ATTR_TEMPERATURE_COLOR,
    ATTR_TEMPERATURE_ENTITY,
    ATTR_TEMPERATURE_STATUS,
    CONF_HUMIDITY_ENTITY,
    CONF_LIGHT_ENTITY,
    CONF_MOISTURE_ENTITY,
    CONF_PLANT_NAME,
    CONF_TEMPERATURE_ENTITY,
    DOMAIN,
    HUMIDITY_THRESHOLDS,
    LIGHT_THRESHOLDS,
    MOISTURE_THRESHOLDS,
    MOOD_CRITICAL,
    MOOD_DARK,
    MOOD_HAPPY,
    MOOD_NEED_WATER,
    MOOD_OKAY,
    MOOD_STRUGGLING,
    MOOD_THRIVING,
    TEMPERATURE_THRESHOLDS,
    WEIGHT_HUMIDITY,
    WEIGHT_LIGHT,
    WEIGHT_MOISTURE,
    WEIGHT_TEMPERATURE,
)

_LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Platform setup
# ---------------------------------------------------------------------------


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create the PlantHappinessSensor for this config entry."""
    async_add_entities([PlantHappinessSensor(hass, entry)], update_before_add=True)


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------


def _bell_score(value: float, peak: float, width: float) -> float:
    """Return a 0–100 score on a Gaussian curve centred at *peak*.

    *width* is the standard deviation — values within ±width of peak score
    above ~37; values at ±2×width score ~2.
    """
    diff = value - peak
    return max(0.0, 100.0 * math.exp(-(diff * diff) / (2.0 * width * width)))


def _get_threshold(value: float, thresholds: list[dict]) -> dict:
    """Return the first threshold dict whose *max* key exceeds *value*."""
    for t in thresholds:
        if value < t["max"]:
            return t
    return thresholds[-1]


def _compute_happiness(
    moisture: float | None,
    light: float | None,
    temperature: float | None,
    humidity: float | None,
) -> int:
    """Return a weighted happiness score 0–100 from available sensor values."""

    sensor_map = {
        "moisture": (moisture, WEIGHT_MOISTURE, 55.0, 22.0),
        "light":    (light,    WEIGHT_LIGHT,    48.0, 25.0),
        "temperature": (temperature, WEIGHT_TEMPERATURE, 22.0, 7.0),
        "humidity": (humidity, WEIGHT_HUMIDITY, 50.0, 18.0),
    }

    total_weight = 0.0
    total_score = 0.0

    for _name, (value, weight, peak, width) in sensor_map.items():
        if value is not None:
            score = _bell_score(value, peak, width)
            total_score += score * weight
            total_weight += weight

    if total_weight == 0:
        return 0

    # Normalise so missing sensors don't deflate the result
    return round(total_score / total_weight)


def _mood_from_score(
    score: int,
    moisture: float | None,
    light: float | None,
) -> str:
    """Derive mood string from happiness score and critical sensor extremes."""
    if score >= 88:
        return MOOD_THRIVING
    if score >= 70:
        return MOOD_HAPPY
    if score >= 50:
        return MOOD_OKAY

    # Below 50 — let sensor extremes override to a specific face
    if moisture is not None and moisture < 25:
        return MOOD_NEED_WATER
    if light is not None and light < 15:
        return MOOD_DARK
    if score >= 30:
        return MOOD_STRUGGLING
    return MOOD_CRITICAL


def _celsius_value(state: State) -> float | None:
    """Return a temperature state value normalised to °C, or None."""
    try:
        raw = float(state.state)
    except (ValueError, TypeError):
        return None

    unit = state.attributes.get("unit_of_measurement", "")
    if unit in (UnitOfTemperature.FAHRENHEIT, "°F", "F"):
        return TemperatureConverter.convert(
            raw, UnitOfTemperature.FAHRENHEIT, UnitOfTemperature.CELSIUS
        )
    return raw  # assume °C for anything else


def _float_value(state: State) -> float | None:
    """Return a numeric state value or None."""
    try:
        return float(state.state)
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Entity
# ---------------------------------------------------------------------------


class PlantHappinessSensor(SensorEntity):
    """A sensor entity that aggregates plant health into a single mood state.

    State   : mood string (thriving / happy / okay / struggling /
              need_water / dark / critical / unavailable)
    Attributes : happiness_score, per-sensor value/status/color,
                 entity_id references for timestamp lookups by the card.
    """

    _attr_icon = "mdi:sprout"
    _attr_has_entity_name = True
    _attr_should_poll = False  # Driven by state-change events

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self._entry = entry
        self._config: dict[str, Any] = {**entry.data, **entry.options}

        plant_name: str = self._config.get(CONF_PLANT_NAME, "Plant")
        slug = plant_name.lower().replace(" ", "_")

        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}"
        self._attr_name = f"{plant_name} Happiness"
        self._attr_native_value: str = "unavailable"

        self._extra_attrs: dict[str, Any] = {}
        self._unsub_listeners: list = []

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def async_added_to_hass(self) -> None:
        """Subscribe to state changes on all configured sensor entities."""
        entity_ids = [
            self._config.get(CONF_MOISTURE_ENTITY),
            self._config.get(CONF_LIGHT_ENTITY),
            self._config.get(CONF_TEMPERATURE_ENTITY),
            self._config.get(CONF_HUMIDITY_ENTITY),
        ]
        watch_ids = [eid for eid in entity_ids if eid]

        @callback
        def _state_changed(_event: Event) -> None:
            self._update_state()
            self.async_write_ha_state()

        self._unsub_listeners.append(
            async_track_state_change_event(self.hass, watch_ids, _state_changed)
        )
        # Compute initial state
        self._update_state()

    async def async_will_remove_from_hass(self) -> None:
        """Clean up state-change subscriptions."""
        for unsub in self._unsub_listeners:
            unsub()
        self._unsub_listeners.clear()

    # ------------------------------------------------------------------
    # HA properties
    # ------------------------------------------------------------------

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return self._extra_attrs

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=self._config.get(CONF_PLANT_NAME, "Plant"),
            manufacturer="Plant Happiness",
            model="Plant Monitor",
        )

    # ------------------------------------------------------------------
    # State computation
    # ------------------------------------------------------------------

    def _get_sensor_state(self, entity_id: str | None) -> State | None:
        """Return a non-unavailable HA state object or None."""
        if not entity_id:
            return None
        state = self.hass.states.get(entity_id)
        if state is None or state.state in ("unavailable", "unknown", ""):
            return None
        return state

    def _update_state(self) -> None:
        """Recompute mood state and all attributes from current sensor values."""
        moisture_state = self._get_sensor_state(self._config.get(CONF_MOISTURE_ENTITY))
        light_state    = self._get_sensor_state(self._config.get(CONF_LIGHT_ENTITY))
        temp_state     = self._get_sensor_state(self._config.get(CONF_TEMPERATURE_ENTITY))
        humid_state    = self._get_sensor_state(self._config.get(CONF_HUMIDITY_ENTITY))

        # Required sensors — if either is unavailable the plant is unavailable
        if moisture_state is None or light_state is None:
            self._attr_native_value = "unavailable"
            self._extra_attrs = {
                ATTR_MOISTURE_ENTITY: self._config.get(CONF_MOISTURE_ENTITY),
                ATTR_LIGHT_ENTITY:    self._config.get(CONF_LIGHT_ENTITY),
                ATTR_TEMPERATURE_ENTITY: self._config.get(CONF_TEMPERATURE_ENTITY),
                ATTR_HUMIDITY_ENTITY:    self._config.get(CONF_HUMIDITY_ENTITY),
            }
            return

        # Parse values
        moisture    = _float_value(moisture_state)
        light       = _float_value(light_state)
        temperature = _celsius_value(temp_state) if temp_state else None
        humidity    = _float_value(humid_state) if humid_state else None

        if moisture is None or light is None:
            self._attr_native_value = "unavailable"
            return

        # Clamp percentages
        moisture = max(0.0, min(100.0, moisture))
        light    = max(0.0, min(100.0, light))
        if humidity is not None:
            humidity = max(0.0, min(100.0, humidity))

        # Score and mood
        score = _compute_happiness(moisture, light, temperature, humidity)
        mood  = _mood_from_score(score, moisture, light)

        # Threshold lookups
        m_thresh = _get_threshold(moisture, MOISTURE_THRESHOLDS)
        l_thresh = _get_threshold(light,    LIGHT_THRESHOLDS)
        t_thresh = _get_threshold(temperature, TEMPERATURE_THRESHOLDS) if temperature is not None else None
        h_thresh = _get_threshold(humidity,    HUMIDITY_THRESHOLDS)    if humidity    is not None else None

        # Build attributes
        attrs: dict[str, Any] = {
            ATTR_HAPPINESS_SCORE: score,
            # Moisture
            ATTR_MOISTURE:        round(moisture, 1),
            ATTR_MOISTURE_STATUS: m_thresh["status"],
            ATTR_MOISTURE_COLOR:  m_thresh["color"],
            # Light
            ATTR_LIGHT:           round(light, 1),
            ATTR_LIGHT_STATUS:    l_thresh["status"],
            ATTR_LIGHT_COLOR:     l_thresh["color"],
            # Entity IDs (for last_changed lookups in the card)
            ATTR_MOISTURE_ENTITY:     self._config.get(CONF_MOISTURE_ENTITY),
            ATTR_LIGHT_ENTITY:        self._config.get(CONF_LIGHT_ENTITY),
            ATTR_TEMPERATURE_ENTITY:  self._config.get(CONF_TEMPERATURE_ENTITY),
            ATTR_HUMIDITY_ENTITY:     self._config.get(CONF_HUMIDITY_ENTITY),
        }

        # Optional sensors
        if temperature is not None and t_thresh:
            attrs[ATTR_TEMPERATURE]        = round(temperature, 1)
            attrs[ATTR_TEMPERATURE_STATUS] = t_thresh["status"]
            attrs[ATTR_TEMPERATURE_COLOR]  = t_thresh["color"]

        if humidity is not None and h_thresh:
            attrs[ATTR_HUMIDITY]        = round(humidity, 1)
            attrs[ATTR_HUMIDITY_STATUS] = h_thresh["status"]
            attrs[ATTR_HUMIDITY_COLOR]  = h_thresh["color"]

        self._attr_native_value = mood
        self._extra_attrs = attrs

        _LOGGER.debug(
            "%s → mood=%s score=%d moisture=%.1f light=%.1f temp=%s humid=%s",
            self._config.get(CONF_PLANT_NAME),
            mood, score, moisture, light,
            f"{temperature:.1f}" if temperature is not None else "n/a",
            f"{humidity:.1f}"    if humidity    is not None else "n/a",
        )
