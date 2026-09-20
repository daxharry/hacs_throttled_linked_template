"""DataUpdateCoordinator that evaluates linked templates in order."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import TemplateError
from jinja2.utils import Namespace

from homeassistant.helpers.template import Template
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util
from homeassistant.util import slugify

from .combine import CombineError, combine_states
from .const import (
    CONF_COMBINE_TYPE,
    CONF_ENTITY_IDS,
    CONF_KIND,
    CONF_ROUND_DIGITS,
    CONF_SENSOR_ID,
    CONF_TEMPLATE,
    DEFAULT_COMBINE_TYPE,
    DEFAULT_ROUND_DIGITS,
    DOMAIN,
    KIND_COMBINE,
    KIND_TEMPLATE,
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
        self._tick_states: dict[str, Any] = {}
        self._entities_ready = asyncio.Event()
        kwargs: dict[str, Any] = {
            "name": f"{DOMAIN}_{entry.entry_id}",
            "update_interval": timedelta(seconds=entry_interval(entry)),
            "always_update": True,
        }
        try:
            super().__init__(hass, _LOGGER, config_entry=entry, **kwargs)
        except TypeError:
            kwargs.pop("always_update", None)
            super().__init__(hass, _LOGGER, **kwargs)

    @property
    def sensors(self) -> list[dict[str, Any]]:
        """Return the ordered sensor definitions."""
        return entry_sensors(self.entry)

    def register_entity(self, sensor_id: str, entity: Any) -> None:
        """Register a sensor entity for same-tick state writes."""
        self._entities[sensor_id] = entity
        expected = self._expected_entity_count()
        if expected and len(self._entities) >= expected:
            self._entities_ready.set()

    def unregister_entity(self, sensor_id: str) -> None:
        """Forget a sensor entity when it is removed."""
        self._entities.pop(sensor_id, None)

    def _expected_entity_count(self) -> int:
        return sum(1 for sensor in self.sensors if sensor.get(CONF_SENSOR_ID))

    async def async_wait_for_entities(self) -> None:
        """Wait until group sensors are added to Home Assistant."""
        expected = self._expected_entity_count()
        if expected == 0 or len(self._entities) >= expected:
            return
        try:
            await asyncio.wait_for(self._entities_ready.wait(), timeout=15)
        except TimeoutError:
            _LOGGER.warning(
                "Group '%s' starting with %s/%s sensors registered",
                entry_name(self.entry),
                len(self._entities),
                expected,
            )

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
        """Evaluate sensors in order and publish each state before the next."""
        results: dict[str, SensorTickResult] = {}
        self._tick_states = {}
        group_name = entry_name(self.entry)

        for index, sensor in enumerate(self.sensors, start=1):
            sensor_id = str(sensor[CONF_SENSOR_ID])
            entity = self._entities.get(sensor_id)
            sensor_name = str(sensor.get(CONF_NAME, sensor_id))
            try:
                native_value = self._async_evaluate_sensor(sensor, entity)
            except (TemplateError, CombineError) as err:
                _LOGGER.warning(
                    "Sensor error in group '%s' sensor '%s': %s",
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

            results[sensor_id] = result
            self._results[sensor_id] = result
            self._publish_result(entity, result, sensor_name)
            _LOGGER.debug(
                "Group '%s' [%s/%s] %s = %s (available=%s)",
                group_name,
                index,
                len(self.sensors),
                sensor_name,
                result.native_value,
                result.available,
            )
            # Let the state machine settle before the next sensor reads it.
            await asyncio.sleep(0)

        stale_ids = set(self._results) - set(results)
        for stale_id in stale_ids:
            self._results.pop(stale_id, None)

        return results

    def _async_evaluate_sensor(self, sensor: dict[str, Any], entity: Any | None) -> Any:
        """Evaluate one sensor for this tick."""
        kind = str(sensor.get(CONF_KIND, KIND_TEMPLATE))
        if kind == KIND_COMBINE:
            entity_ids = [
                str(item) for item in sensor.get(CONF_ENTITY_IDS, []) if item
            ]
            return combine_states(
                self.hass,
                entity_ids,
                str(sensor.get(CONF_COMBINE_TYPE, DEFAULT_COMBINE_TYPE)),
                int(sensor.get(CONF_ROUND_DIGITS, DEFAULT_ROUND_DIGITS) or 0),
                overrides=self._tick_states,
            )
        return self._async_render_template(
            str(sensor.get(CONF_TEMPLATE, "")), entity=entity
        )

    def _async_render_template(self, template_str: str, entity: Any | None) -> Any:
        """Render a Jinja template without setting up state listeners."""
        template = Template(template_str, self.hass)
        # Namespace is required: HA's sandboxed Jinja blocks dict.attr access.
        variables: dict[str, Any] = {"linked": Namespace(self._tick_states)}
        if entity is not None and getattr(entity, "entity_id", None):
            variables["this"] = {
                "entity_id": entity.entity_id,
                "name": getattr(entity, "name", None),
                "state": _current_state_value(entity),
                "attributes": dict(getattr(entity, "extra_state_attributes", None) or {}),
            }
        rendered = template.async_render(variables, parse_result=True)
        return _normalize_native_value(rendered)

    @property
    def linked_keys(self) -> list[str]:
        """Return the keys published earlier in the current/last tick."""
        return sorted(self._tick_states)

    def _publish_result(
        self, entity: Any | None, result: SensorTickResult, sensor_name: str
    ) -> None:
        """Write this sensor so the next one in the same tick can read it."""
        value = result.native_value if result.available else None
        entity_id = getattr(entity, "entity_id", None) if entity is not None else None
        keys: list[str] = []
        if sensor_name:
            keys.append(slugify(sensor_name))
        if entity_id and "." in entity_id and not entity_id.endswith("."):
            keys.append(entity_id)
            keys.append(entity_id.split(".", 1)[-1])
        for key in keys:
            if key:
                self._tick_states[key] = value

        if entity is not None and getattr(entity, "hass", None) is not None:
            try:
                entity.async_write_ha_state()
                return
            except Exception:  # noqa: BLE001
                _LOGGER.debug(
                    "async_write_ha_state failed for %s", entity_id, exc_info=True
                )

        if entity_id and "." in entity_id and not entity_id.endswith("."):
            published = (
                STATE_UNAVAILABLE if not result.available else _stringify_state(value)
            )
            self.hass.states.async_set(entity_id, published, None, force_update=True)


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


def _stringify_state(value: Any) -> str:
    """Convert a native value to a state string."""
    if value is None:
        return STATE_UNAVAILABLE
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)
