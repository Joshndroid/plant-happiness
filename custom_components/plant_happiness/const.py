"""Constants for the Plant Happiness integration."""

DOMAIN = "plant_happiness"

# Config entry keys — sensor entities
CONF_PLANT_NAME = "plant_name"
CONF_MOISTURE_ENTITY = "moisture_entity"
CONF_LIGHT_ENTITY = "light_entity"
CONF_TEMPERATURE_ENTITY = "temperature_entity"
CONF_HUMIDITY_ENTITY = "humidity_entity"

# Config entry keys — Open PlantBook integration (all optional)
CONF_PLANTBOOK_CLIENT_ID = "plantbook_client_id"
CONF_PLANTBOOK_CLIENT_SECRET = "plantbook_client_secret"
CONF_PLANT_SPECIES = "plant_species"  # alias sent to PlantBook search

# Mood states (must match plant-happiness-card.js FACES keys)
MOOD_THRIVING = "thriving"
MOOD_HAPPY = "happy"
MOOD_OKAY = "okay"
MOOD_STRUGGLING = "struggling"
MOOD_NEED_WATER = "need_water"
MOOD_DARK = "dark"
MOOD_CRITICAL = "critical"

# Sensor weight defaults (normalized at runtime based on availability)
WEIGHT_MOISTURE = 0.35
WEIGHT_LIGHT = 0.25
WEIGHT_TEMPERATURE = 0.25
WEIGHT_HUMIDITY = 0.15

# Moisture thresholds (value in %)
MOISTURE_THRESHOLDS = [
    {"max": 10,  "status": "Critically Dry",  "color": "#f85149"},
    {"max": 25,  "status": "Very Thirsty",    "color": "#f85149"},
    {"max": 40,  "status": "Thirsty",         "color": "#ff9a4a"},
    {"max": 70,  "status": "Hydrated",        "color": "#58a6ff"},
    {"max": 85,  "status": "Well Watered",    "color": "#7dff9a"},
    {"max": 101, "status": "Overwatered",     "color": "#e3b341"},
]

# Light thresholds (value in %)
LIGHT_THRESHOLDS = [
    {"max": 8,   "status": "No Light",    "color": "#555555"},
    {"max": 20,  "status": "Too Dark",    "color": "#8b7355"},
    {"max": 35,  "status": "Low Light",   "color": "#e3b341"},
    {"max": 70,  "status": "Perfect",     "color": "#7dff9a"},
    {"max": 85,  "status": "Bright",      "color": "#58a6ff"},
    {"max": 101, "status": "Very Bright", "color": "#ff9a4a"},
]

# Temperature thresholds (value in °C)
TEMPERATURE_THRESHOLDS = [
    {"max": 5,   "status": "Dangerously Cold", "color": "#4fc3f7"},
    {"max": 12,  "status": "Too Cold",         "color": "#81d4fa"},
    {"max": 18,  "status": "Cool",             "color": "#b3e5fc"},
    {"max": 27,  "status": "Perfect",          "color": "#7dff9a"},
    {"max": 32,  "status": "Warm",             "color": "#e3b341"},
    {"max": 38,  "status": "Too Hot",          "color": "#ff9a4a"},
    {"max": 999, "status": "Dangerously Hot",  "color": "#f85149"},
]

# Humidity thresholds (value in %)
HUMIDITY_THRESHOLDS = [
    {"max": 20,  "status": "Very Dry Air",   "color": "#f85149"},
    {"max": 35,  "status": "Dry Air",        "color": "#ff9a4a"},
    {"max": 60,  "status": "Comfortable",    "color": "#7dff9a"},
    {"max": 75,  "status": "Humid",          "color": "#58a6ff"},
    {"max": 101, "status": "Very Humid",     "color": "#e3b341"},
]

# Attribute names exposed on the sensor entity
ATTR_HAPPINESS_SCORE = "happiness_score"
ATTR_MOOD = "mood"
ATTR_MOISTURE = "moisture"
ATTR_MOISTURE_STATUS = "moisture_status"
ATTR_MOISTURE_COLOR = "moisture_color"
ATTR_LIGHT = "light"
ATTR_LIGHT_STATUS = "light_status"
ATTR_LIGHT_COLOR = "light_color"
ATTR_TEMPERATURE = "temperature"
ATTR_TEMPERATURE_STATUS = "temperature_status"
ATTR_TEMPERATURE_COLOR = "temperature_color"
ATTR_HUMIDITY = "humidity"
ATTR_HUMIDITY_STATUS = "humidity_status"
ATTR_HUMIDITY_COLOR = "humidity_color"
ATTR_MOISTURE_ENTITY = "moisture_entity_id"
ATTR_LIGHT_ENTITY = "light_entity_id"
ATTR_TEMPERATURE_ENTITY = "temperature_entity_id"
ATTR_HUMIDITY_ENTITY = "humidity_entity_id"

# Attribute names for Open PlantBook species data
ATTR_PLANTBOOK_SYNCED  = "plantbook_synced"
ATTR_PLANTBOOK_PID     = "plantbook_pid"
ATTR_PLANTBOOK_DISPLAY = "plantbook_display_pid"
ATTR_SOIL_MOIST_MIN    = "soil_moist_min"
ATTR_SOIL_MOIST_MAX    = "soil_moist_max"
ATTR_TEMP_MIN          = "temp_min"
ATTR_TEMP_MAX          = "temp_max"
ATTR_HUMID_MIN         = "env_humid_min"
ATTR_HUMID_MAX         = "env_humid_max"
ATTR_LIGHT_LUX_MIN     = "light_lux_min"
ATTR_LIGHT_LUX_MAX     = "light_lux_max"
