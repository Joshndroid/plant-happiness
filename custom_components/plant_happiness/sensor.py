"""Plant Happiness sensor platform.

One PlantHappinessSensor entity is created per config entry.

Entity state  : mood string — one of thriving / happy / okay / struggling /
                need_water / dark / critical / unavailable
Attributes    : happiness_score, per-sensor value + status label + color,
                entity_id references so the Lovelace card can look up
                last_changed timestamps, and (when PlantBook is configured)
                species-specific min/max thresholds.

Open PlantBook integration
--------------------------
If the config entry contains plantbook_client_id, plantbook_client_secret,
and plant_species, the sensor fetches species data from Open PlantBook on
startup.  The returned min/max ranges for soil moisture, temperature,
humidity, and light are used to:

  • Calibrate the bell-curve peak and width for each sensor, so happiness
    scoring reflects what *this specific plant* actually needs rather than
    generic defaults.
  • Set the critical thresholds for the need_water and dark mood overrides.
  • Expose all raw PlantBook values as extra attributes so the card (and
    any automations) can reference the species limits directly.

If PlantBook is not configured, or if the API call fails, the integration
falls back to the built-in generic thresholds without any error state.
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
    ATTR_HUMID_MAX,
    ATTR_HUMID_MIN,
    ATTR_HUMIDITY,
    ATTR_HUMIDITY_COLOR,
    ATTR_HUMIDITY_ENTITY,
    ATTR_HUMIDITY_STATUS,
    ATTR_LIGHT,
    ATTR_LIGHT_COLOR,
    ATTR_LIGHT_ENTITY,
    ATTR_LIGHT_LUX_MAX,
    ATTR_LIGHT_LUX_MIN,
    ATTR_LIGHT_STATUS,
    ATTR_MOISTURE,
    ATTR_MOISTURE_COLOR,
    ATTR_MOISTURE_ENTITY,
    ATTR_MOISTURE_STATUS,
    ATTR_PLANTBOOK_DISPLAY,
    ATTR_PLANTBOOK_PID,
    ATTR_PLANTBOOK_SYNCED,
    ATTR_SOIL_MOIST_MAX,
    ATTR_SOIL_MOIST_MIN,
    ATTR_TEMPERATURE,
    ATTR_TEMPERATURE_COLOR,
    ATTR_TEMPERATURE_ENTITY,
    ATTR_TEMPERATURE_STATUS,
    ATTR_TEMP_MAX,
    ATTR_TEMP_MIN,
    CONF_HUMIDITY_ENTITY,
    CONF_LIGHT_ENTITY,
    CONF_MOISTURE_ENTITY,
    CONF_PLANT_NAME,
    CONF_PLANTBOOK_CLIENT_ID,
    CONF_PLANTBOOK_CLIENT_SECRET,
    CONF_PLANT_SPECIES,
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
from .plantbook import PlantBookClient

_LOGGER = logging.getLogger(__name__)

# Units that indicate the light sensor reports in lux (not %)
_LUX_UNITS = {"lux", "lx"}

# Minimum bell-curve width to prevent overly sharp scoring curves
_MIN_CURVE_WIDTH = 5.0


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


def _curve_from_range(
    min_val: float | None,
    max_val: float | None,
    default_peak: float,
    default_width: float,
) -> tuple[float, float]:
    """Derive (peak, width) from a PlantBook min/max pair.

    If either bound is missing or the range is invalid, returns the
    supplied defaults unchanged.
    """
    if min_val is not None and max_val is not None and max_val > min_val:
        peak = (min_val + max_val) / 2.0
        width = max((max_val - min_val) / 4.0, _MIN_CURVE_WIDTH)
        return peak, width
    return default_peak, default_width


def _build_overrides(pb: dict[str, Any]) -> dict[str, tuple[float, float]]:
    """Build a sensor→(peak, width) dict from PlantBook data.

    Only keys that the PlantBook data can actually improve are included;
    sensors with missing ranges keep their defaults via fallback logic in
    _compute_happiness.
    """
    overrides: dict[str, tuple[float, float]] = {}

    moisture_peak, moisture_width = _curve_from_range(
        pb.get("soil_moist_min"), pb.get("soil_moist_max"),
        55.0, 22.0,
    )
    # Only override if PlantBook data actually changed the defaults
    if pb.get("soil_moist_min") is not None and pb.get("soil_moist_max") is not None:
        overrides["moisture"] = (moisture_peak, moisture_width)

    if pb.get("temp_min") is not None and pb.get("temp_max") is not None:
        overrides["temperature"] = _curve_from_range(
            pb.get("temp_min"), pb.get("temp_max"), 22.0, 7.0
        )

    if pb.get("env_humid_min") is not None and pb.get("env_humid_max") is not None:
        overrides["humidity"] = _curve_from_range(
            pb.get("env_humid_min"), pb.get("env_humid_max"), 50.0, 18.0
        )

    # Light (lux) — only applied when the HA sensor reports in lux; see sensor
    if pb.get("light_lux_min") is not None and pb.get("light_lux_max") is not None:
        overrides["light_lux"] = _curve_from_range(
            pb.get("light_lux_min"), pb.get("light_lux_max"), None, None  # type: ignore[arg-type]
        )

    return overrides


def _compute_happiness(
    moisture: float | None,
    light: float | None,
    temperature: float | None,
    humidity: float | None,
    overrides: dict[str, tuple[float, float]] | None = None,
) -> int:
    """Return a weighted happiness score 0–100 from available sensor values.

    *overrides* maps sensor name → (peak, width) and is used when
    PlantBook data provides species-specific optimal ranges.
    """
    overrides = overrides or {}

    # Default peaks and widths (generic, plant-agnostic)
    defaults: dict[str, tuple[float, float]] = {
        "moisture":    (55.0, 22.0),
        "light":       (48.0, 25.0),
        "temperature": (22.0,  7.0),
        "humidity":    (50.0, 18.0),
    }

    sensor_map: dict[str, tuple[float | None, float]] = {
        "moisture":    (moisture,    WEIGHT_MOISTURE),
        "light":       (light,       WEIGHT_LIGHT),
        "temperature": (temperature, WEIGHT_TEMPERATURE),
        "humidity":    (humidity,    WEIGHT_HUMIDITY),
    }

    total_weight = 0.0
    total_score  = 0.0

    for name, (value, weight) in sensor_map.items():
        if value is not None:
            peak, width = overrides.get(name, defaults[name])
            score = _bell_score(value, peak, width)
            total_score  += score * weight
            total_weight += weight

    if total_weight == 0:
        return 0

    return round(total_score / total_weight)


def _mood_from_score(
    score: int,
    moisture: float | None,
    light: float | None,
    moisture_critical: float = 25.0,
    light_critical: float = 15.0,
) -> str:
    """Derive mood string from happiness score and critical sensor extremes.

    *moisture_critical* and *light_critical* can be overridden with
    species-specific thresholds from PlantBook (e.g. soil_moist_min).
    """
    if score >= 88:
        return MOOD_THRIVING
    if score >= 70:
        return MOOD_HAPPY
    if score >= 50:
        return MOOD_OKAY

    # Below 50 — let sensor extremes override to a specific face
    if moisture is not None and moisture < moisture_critical:
        return MOOD_NEED_WATER
    if light is not None and light < light_critical:
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
    return raw


def _float_value(state: State) -> float | None:
    """Return a numeric state value or None."""
    try:
        return float(state.state)
    except (ValueError, TypeError):
        return None


def _unit(state: State) -> str:
    """Return the lower-cased unit_of_measurement from a state, or ''."""
    return (state.attributes.get("unit_of_measurement") or "").lower().strip()


# ---------------------------------------------------------------------------
# Entity
# ---------------------------------------------------------------------------


class PlantHappinessSensor(SensorEntity):
    """Aggregates plant health into a single mood state.

    State   : mood string (thriving / happy / okay / struggling /
              need_water / dark / critical / unavailable)
    Attributes : happiness_score, per-sensor value/status/color,
                 entity_id references, and optional PlantBook species data.
    """

    _attr_icon = "mdi:sprout"
    _attr_has_entity_name = True
    _attr_should_poll = False  # Driven by state-change events

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self._entry = entry
        self._config: dict[str, Any] = {**entry.data, **entry.options}

        plant_name: str = self._config.get(CONF_PLANT_NAME, "Plant")

        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}"
        self._attr_name = f"{plant_name} Happiness"
        self._attr_native_value: str = "unavailable"

        self._extra_attrs: dict[str, Any] = {}
        self._unsub_listeners: list = []

        # PlantBook species data — populated in async_added_to_hass
        self._plantbook_data: dict[str, Any] | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def async_added_to_hass(self) -> None:
        """Subscribe to sensor state changes and fetch PlantBook data."""

        # Fetch Open PlantBook data if credentials are configured
        client_id     = self._config.get(CONF_PLANTBOOK_CLIENT_ID, "").strip()
        client_secret = self._config.get(CONF_PLANTBOOK_CLIENT_SECRET, "").strip()
        species       = self._config.get(CONF_PLANT_SPECIES, "").strip()

        if client_id and client_secret and species:
            client = PlantBookClient(self.hass, client_id, client_secret)
            self._plantbook_data = await client.async_get_plant_data(species)
            if self._plantbook_data:
                _LOGGER.info(
                    "%s: PlantBook data loaded for '%s' (pid=%s)",
                    self._config.get(CONF_PLANT_NAME),
                    species,
                    self._plantbook_data.get("pid"),
                )
            else:
                _LOGGER.warning(
                    "%s: PlantBook lookup for '%s' returned no data — "
                    "falling back to generic thresholds",
                    self._config.get(CONF_PLANT_NAME),
                    species,
                )

        # Subscribe to HA sensor state changes
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
                ATTR_MOISTURE_ENTITY:    self._config.get(CONF_MOISTURE_ENTITY),
                ATTR_LIGHT_ENTITY:       self._config.get(CONF_LIGHT_ENTITY),
                ATTR_TEMPERATURE_ENTITY: self._config.get(CONF_TEMPERATURE_ENTITY),
                ATTR_HUMIDITY_ENTITY:    self._config.get(CONF_HUMIDITY_ENTITY),
                ATTR_PLANTBOOK_SYNCED:   self._plantbook_data is not None,
            }
            return

        # Parse values
        moisture    = _float_value(moisture_state)
        light_raw   = _float_value(light_state)
        temperature = _celsius_value(temp_state) if temp_state else None
        humidity    = _float_value(humid_state) if humid_state else None

        if moisture is None or light_raw is None:
            self._attr_native_value = "unavailable"
            return

        # Determine light sensor unit so we know whether to apply lux curves
        light_unit_str = _unit(light_state)
        light_is_lux   = light_unit_str in _LUX_UNITS

        # Clamp percentage values (lux is unbounded, leave as-is)
        moisture = max(0.0, min(100.0, moisture))
        light    = light_raw if light_is_lux else max(0.0, min(100.0, light_raw))
        if humidity is not None:
            humidity = max(0.0, min(100.0, humidity))

        # ------------------------------------------------------------------
        # Build PlantBook-derived scoring overrides
        # ------------------------------------------------------------------
        pb = self._plantbook_data
        overrides: dict[str, tuple[float, float]] = {}
        moisture_critical = 25.0   # default need_water threshold
        light_critical    = 15.0   # default dark threshold

        if pb:
            overrides = _build_overrides(pb)

            # Apply lux curve to 'light' only when the sensor reports lux
            if light_is_lux and "light_lux" in overrides:
                overrides["light"] = overrides["light_lux"]

            # Species-specific critical thresholds for mood override
            if pb.get("soil_moist_min") is not None:
                moisture_critical = float(pb["soil_moist_min"])
            if light_is_lux and pb.get("light_lux_min") is not None:
                light_critical = float(pb["light_lux_min"])

        # ------------------------------------------------------------------
        # Score and mood
        # ------------------------------------------------------------------
        score = _compute_happiness(moisture, light, temperature, humidity, overrides)
        mood  = _mood_from_score(score, moisture, light, moisture_critical, light_critical)

        # ------------------------------------------------------------------
        # Threshold label/colour lookups (percentage-based sensors)
        # ------------------------------------------------------------------
        m_thresh = _get_threshold(moisture, MOISTURE_THRESHOLDS)
        t_thresh = (
            _get_threshold(temperature, TEMPERATURE_THRESHOLDS)
            if temperature is not None else None
        )
        h_thresh = (
            _get_threshold(humidity, HUMIDITY_THRESHOLDS)
            if humidity is not None else None
        )

        # Light label — use lux-aware thresholds if sensor reports lux and
        # PlantBook gave us a lux range; otherwise fall back to % thresholds.
        if light_is_lux and pb and pb.get("light_lux_max"):
            lux_max = float(pb["light_lux_max"])
            lux_min = float(pb.get("light_lux_min") or 0)
            lux_range = lux_max - lux_min if lux_max > lux_min else lux_max
            # Derive a simple label from relative position in the species range
            if light < lux_min * 0.5:
                l_status, l_color = "Too Dark", "#555555"
            elif light < lux_min:
                l_status, l_color = "Below Ideal", "#e3b341"
            elif light <= lux_max:
                l_status, l_color = "Ideal Light", "#7dff9a"
            elif light <= lux_max * 1.5:
                l_status, l_color = "Bright", "#58a6ff"
            else:
                l_status, l_color = "Very Bright", "#ff9a4a"
        else:
            l_thresh = _get_threshold(light, LIGHT_THRESHOLDS)
            l_status, l_color = l_thresh["status"], l_thresh["color"]

        # ------------------------------------------------------------------
        # Build attributes
        # ------------------------------------------------------------------
        attrs: dict[str, Any] = {
            ATTR_HAPPINESS_SCORE: score,
            # Moisture
            ATTR_MOISTURE:        round(moisture, 1),
            ATTR_MOISTURE_STATUS: m_thresh["status"],
            ATTR_MOISTURE_COLOR:  m_thresh["color"],
            # Light
            ATTR_LIGHT:           round(light, 1),
            ATTR_LIGHT_STATUS:    l_status,
            ATTR_LIGHT_COLOR:     l_color,
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

        # PlantBook species data
        if pb:
            attrs.update(
                {
                    ATTR_PLANTBOOK_SYNCED:  True,
                    ATTR_PLANTBOOK_PID:     pb.get("pid"),
                    ATTR_PLANTBOOK_DISPLAY: pb.get("display_pid"),
                    ATTR_SOIL_MOIST_MIN:    pb.get("soil_moist_min"),
                    ATTR_SOIL_MOIST_MAX:    pb.get("soil_moist_max"),
                    ATTR_TEMP_MIN:          pb.get("temp_min"),
                    ATTR_TEMP_MAX:          pb.get("temp_max"),
                    ATTR_HUMID_MIN:         pb.get("env_humid_min"),
                    ATTR_HUMID_MAX:         pb.get("env_humid_max"),
                    ATTR_LIGHT_LUX_MIN:     pb.get("light_lux_min"),
                    ATTR_LIGHT_LUX_MAX:     pb.get("light_lux_max"),
                }
            )
        else:
            attrs[ATTR_PLANTBOOK_SYNCED] = False

        self._attr_native_value = mood
        self._extra_attrs = attrs

        _LOGGER.debug(
            "%s → mood=%s score=%d moisture=%.1f light=%.1f%s temp=%s humid=%s pb=%s",
            self._config.get(CONF_PLANT_NAME),
            mood,
            score,
            moisture,
            light,
            " lux" if light_is_lux else "%",
            f"{temperature:.1f}" if temperature is not None else "n/a",
            f"{humidity:.1f}"    if humidity    is not None else "n/a",
            pb.get("display_pid") if pb else "none",
        )
