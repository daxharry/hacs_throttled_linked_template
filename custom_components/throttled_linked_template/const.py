"""Constants for the Throttled Linked Template integration."""

from __future__ import annotations

from typing import Any, Final

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME

DOMAIN: Final = "throttled_linked_template"

CONF_INTERVAL: Final = "interval"
CONF_SENSORS: Final = "sensors"
CONF_TEMPLATE: Final = "template"
CONF_SENSOR_ID: Final = "id"

DEFAULT_INTERVAL: Final = 5
MIN_INTERVAL: Final = 1

ATTR_LINKED_INDEX: Final = "linked_index"
ATTR_LAST_ERROR: Final = "last_error"

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
