"""Constants for the Throttled Linked Template integration."""

from __future__ import annotations

from typing import Any, Final

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME

DOMAIN: Final = "throttled_linked_template"

CONF_INTERVAL: Final = "interval"
CONF_UPDATE_MODE: Final = "update_mode"
CONF_SENSORS: Final = "sensors"
CONF_TEMPLATE: Final = "template"
CONF_SENSOR_ID: Final = "id"
CONF_KIND: Final = "kind"
CONF_ENTITY_IDS: Final = "entity_ids"
CONF_COMBINE_TYPE: Final = "combine_type"
CONF_ROUND_DIGITS: Final = "round_digits"
CONF_DEVICE_CLASS: Final = "device_class"
CONF_STATE_CLASS: Final = "state_class"
CONF_UNIT_OF_MEASUREMENT: Final = "unit_of_measurement"

KIND_TEMPLATE: Final = "template"
KIND_COMBINE: Final = "combine"

COMBINE_MIN: Final = "min"
COMBINE_MAX: Final = "max"
COMBINE_MEAN: Final = "mean"
COMBINE_MEDIAN: Final = "median"
COMBINE_LAST: Final = "last"
COMBINE_RANGE: Final = "range"
COMBINE_SUM: Final = "sum"

COMBINE_TYPES: Final = (
    COMBINE_SUM,
    COMBINE_MEAN,
    COMBINE_MIN,
    COMBINE_MAX,
    COMBINE_MEDIAN,
    COMBINE_LAST,
    COMBINE_RANGE,
)

DEFAULT_COMBINE_TYPE: Final = COMBINE_SUM
DEFAULT_ROUND_DIGITS: Final = 2

DEFAULT_INTERVAL: Final = 5
MIN_INTERVAL: Final = 1

UPDATE_MODE_INTERVAL: Final = "interval"
UPDATE_MODE_STATE: Final = "state"
DEFAULT_UPDATE_MODE: Final = UPDATE_MODE_INTERVAL
UPDATE_MODES: Final = (UPDATE_MODE_INTERVAL, UPDATE_MODE_STATE)

ATTR_LINKED_INDEX: Final = "linked_index"
ATTR_LAST_ERROR: Final = "last_error"
ATTR_UPDATE_MODE: Final = "update_mode"
ATTR_INTERVAL: Final = "interval"
ATTR_TRIGGER_ENTITIES: Final = "trigger_entities"
ATTR_LAST_TRIGGER: Final = "last_trigger"
ATTR_LAST_TRIGGER_ENTITY: Final = "last_trigger_entity"

DEVICE_CLASS_OPTIONS: Final = [
    "apparent_power",
    "aqi",
    "atmospheric_pressure",
    "battery",
    "carbon_dioxide",
    "carbon_monoxide",
    "current",
    "distance",
    "duration",
    "energy",
    "energy_storage",
    "frequency",
    "gas",
    "humidity",
    "illuminance",
    "irradiance",
    "moisture",
    "monetary",
    "nitrogen_dioxide",
    "nitrogen_monoxide",
    "nitrous_oxide",
    "ozone",
    "ph",
    "pm1",
    "pm10",
    "pm25",
    "power",
    "power_factor",
    "precipitation",
    "precipitation_intensity",
    "pressure",
    "reactive_power",
    "signal_strength",
    "sound_pressure",
    "speed",
    "sulphur_dioxide",
    "temperature",
    "timestamp",
    "volatile_organic_compounds",
    "volatile_organic_compounds_parts",
    "voltage",
    "volume",
    "volume_flow_rate",
    "volume_storage",
    "water",
    "weight",
    "wind_speed",
]

STATE_CLASS_OPTIONS: Final = [
    "measurement",
    "total",
    "total_increasing",
]

# Common units offered in the UI; custom values remain allowed.
UNIT_OPTIONS: Final = [
    "%",
    "A",
    "Ah",
    "EUR",
    "Hz",
    "L",
    "USD",
    "V",
    "VA",
    "W",
    "Wh",
    "dB",
    "kW",
    "kWh",
    "km",
    "km/h",
    "lx",
    "m",
    "m³",
    "min",
    "s",
    "°C",
    "°F",
    "µg/m³",
]


def entry_name(entry: ConfigEntry) -> str:
    """Return the group name from options or data."""
    name = entry.options.get(CONF_NAME, entry.data.get(CONF_NAME, entry.title))
    return str(name).strip() or entry.title


def entry_interval(entry: ConfigEntry) -> int:
    """Return the group interval in seconds."""
    raw = entry.options.get(CONF_INTERVAL, entry.data.get(CONF_INTERVAL, DEFAULT_INTERVAL))
    try:
        interval = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_INTERVAL
    return max(MIN_INTERVAL, interval)


def entry_update_mode(entry: ConfigEntry) -> str:
    """Return how the group is recalculated."""
    mode = entry.options.get(
        CONF_UPDATE_MODE, entry.data.get(CONF_UPDATE_MODE, DEFAULT_UPDATE_MODE)
    )
    if mode == UPDATE_MODE_STATE:
        return UPDATE_MODE_STATE
    return UPDATE_MODE_INTERVAL


def entry_sensors(entry: ConfigEntry) -> list[dict[str, Any]]:
    """Return the ordered sensor definitions for a group."""
    sensors = entry.options.get(CONF_SENSORS)
    if sensors is None:
        sensors = entry.data.get(CONF_SENSORS, [])
    if not isinstance(sensors, list):
        return []
    return [dict(sensor) for sensor in sensors if isinstance(sensor, dict)]


def sensor_unique_id(entry_id: str, sensor_id: str) -> str:
    """Return the entity unique_id for a sensor in a group."""
    return f"{entry_id}_{sensor_id}"
