"""DataUpdateCoordinator that evaluates linked templates in order."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import TemplateError
from homeassistant.helpers.template import Template
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    CONF_SENSOR_ID,
    CONF_TEMPLATE,
    DOMAIN,
    entry_interval,
    entry_name,
    entry_sensors,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class SensorTickResult:
    """Result of one template evaluation inside a group tick."""

    available: bool
    native_value: Any
    error: str | None = None


class ThrottledLinkedTemplateCoordinator(
    DataUpdateCoordinator[dict[str, SensorTickResult]]
):
    """Evaluate an ordered list of templates once per interval.

    Templates are not tracked. Source `state_changed` events never trigger a
    refresh. After each successful or failed evaluation the matching entity
    state is written so the next template in the same tick can read it with
    `states('sensor.xxx')`.
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the group coordinator."""
        self.entry = entry
        self._entities: dict[str, Any] = {}
        self._results: dict[str, SensorTickResult] = {}
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=timedelta(seconds=entry_interval(entry)),
        )

    @property
    def sensors(self) -> list[dict[str, Any]]:
        """Return the ordered sensor definitions."""
        return entry_sensors(self.entry)

    def register_entity(self, sensor_id: str, entity: Any) -> None:
        """Register a sensor entity for same-tick state writes."""
        self._entities[sensor_id] = entity

    def unregister_entity(self, sensor_id: str) -> None:
        """Forget a sensor entity when it is removed."""
        self._entities.pop(sensor_id, None)

    def result_for(self, sensor_id: str) -> SensorTickResult | None:
        """Return the latest result, including in-progress tick values."""
        if sensor_id in self._results:
            return self._results[sensor_id]
        if self.data:
            return self.data.get(sensor_id)
        return None

    def seed_restored(self, sensor_id: str, native_value: Any) -> None:
        """Store a restored value so the group has a state before the first tick."""
        if sensor_id in self._results:
            return
        self._results[sensor_id] = SensorTickResult(
            available=True,
            native_value=native_value,
        )

    async def _async_update_data(self) -> dict[str, SensorTickResult]:
        """Evaluate templates in order and publish each state before the next."""
        results: dict[str, SensorTickResult] = dict(self._results)
        group_name = entry_name(self.entry)

        for sensor in self.sensors:
            sensor_id = str(sensor[CONF_SENSOR_ID])
            template_str = str(sensor.get(CONF_TEMPLATE, ""))
            entity = self._entities.get(sensor_id)
            sensor_name = str(sensor.get(CONF_NAME, sensor_id))
            try:
                native_value = self._async_render_template(
                    template_str, entity=entity
                )
            except TemplateError as err:
                _LOGGER.warning(
                    "Template error in group '%s' sensor '%s': %s",
                    group_name,
                    sensor_name,
                    err,
                )
                result = SensorTickResult(
                    available=False,
                    native_value=None,
                    error=str(err),
                )
            except Exception as err:  # noqa: BLE001
                _LOGGER.exception(
                    "Unexpected error in group '%s' sensor '%s'",
                    group_name,
                    sensor_name,
                )
                result = SensorTickResult(
                    available=False,
                    native_value=None,
                    error=str(err),
                )
            else:
                if _is_unavailable_value(native_value):
                    result = SensorTickResult(
                        available=False,
                        native_value=None,
                    )
                else:
                    result = SensorTickResult(
                        available=True,
                        native_value=native_value,
                    )

            # Publish before evaluating the next template in this same tick.
            results[sensor_id] = result
            self._results[sensor_id] = result
            if entity is not None and getattr(entity, "hass", None) is not None:
                entity.async_write_ha_state()

        stale_ids = set(results) - {
            str(sensor[CONF_SENSOR_ID]) for sensor in self.sensors
        }
        for stale_id in stale_ids:
            results.pop(stale_id, None)
            self._results.pop(stale_id, None)

        return results

    def _async_render_template(self, template_str: str, entity: Any | None) -> Any:
        """Render a Jinja template without setting up state listeners."""
        template = Template(template_str, self.hass)
        variables: dict[str, Any] = {}
        if entity is not None and getattr(entity, "entity_id", None):
            variables["this"] = {
                "entity_id": entity.entity_id,
                "name": getattr(entity, "name", None),
                "state": _current_state_value(entity),
                "attributes": dict(getattr(entity, "extra_state_attributes", None) or {}),
            }
        rendered = template.async_render(
            variables=variables or None,
            parse_result=True,
        )
        return _normalize_native_value(rendered)


def _current_state_value(entity: Any) -> Any:
    """Return the entity state for the `this` template variable."""
    state = getattr(entity, "state", None)
    if state in (None, STATE_UNKNOWN, STATE_UNAVAILABLE):
        return None
    return state


def _is_unavailable_value(value: Any) -> bool:
    """Return True when the rendered value should make the sensor unavailable."""
    if value is None:
        return True
    if isinstance(value, str) and value.strip().lower() in {
        STATE_UNKNOWN,
        STATE_UNAVAILABLE,
    }:
        return True
    return False


def _normalize_native_value(value: Any) -> Any:
    """Coerce a rendered template result into a sensor native value."""
    if value is None:
        return None
    if isinstance(value, (bool, int, float, Decimal, date, datetime)):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.lower() in {STATE_UNKNOWN, STATE_UNAVAILABLE}:
            return stripped.lower()
        return dt_util.parse_datetime(stripped) or stripped
    return str(value)
