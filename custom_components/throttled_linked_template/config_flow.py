"""Config and options flows for Throttled Linked Template."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
import uuid

try:
    import probatio as vol
except ImportError:  # Home Assistant < 2026.9 still ships voluptuous
    import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.exceptions import TemplateError
from homeassistant.helpers import selector

from .const import (
    COMBINE_TYPES,
    CONF_COMBINE_TYPE,
    CONF_DEVICE_CLASS,
    CONF_ENTITY_IDS,
    CONF_INTERVAL,
    CONF_KIND,
    CONF_ROUND_DIGITS,
    CONF_SENSOR_ID,
    CONF_SENSORS,
    CONF_STATE_CLASS,
    CONF_TEMPLATE,
    CONF_UNIT_OF_MEASUREMENT,
    DEFAULT_COMBINE_TYPE,
    DEFAULT_INTERVAL,
    DEFAULT_ROUND_DIGITS,
    DEVICE_CLASS_OPTIONS,
    DOMAIN,
    KIND_COMBINE,
    KIND_TEMPLATE,
    MIN_INTERVAL,
    STATE_CLASS_OPTIONS,
    UNIT_OPTIONS,
    entry_interval,
    entry_name,
    entry_sensors,
)

CONF_INDEX = "index"
CONF_ACTION = "action"

ACTION_UP = "up"
ACTION_DOWN = "down"
ACTION_TOP = "top"
ACTION_BOTTOM = "bottom"


def _group_schema(name: str, interval: int) -> vol.Schema:
    """Return the schema for group name and interval."""
    return vol.Schema(
        {
            vol.Required(CONF_NAME, default=name): selector.TextSelector(),
            vol.Required(CONF_INTERVAL, default=interval): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=MIN_INTERVAL,
                    step=1,
                    mode=selector.NumberSelectorMode.BOX,
                    unit_of_measurement="s",
                )
            ),
        }
    )


def _meta_fields(sensor: Mapping[str, Any]) -> dict[Any, Any]:
    """Return optional unit / device class / state class fields."""
    fields: dict[Any, Any] = {}
    unit = sensor.get(CONF_UNIT_OF_MEASUREMENT) or None
    if unit:
        fields[
            vol.Optional(CONF_UNIT_OF_MEASUREMENT, default=str(unit))
        ] = _unit_selector()
    else:
        fields[vol.Optional(CONF_UNIT_OF_MEASUREMENT)] = _unit_selector()

    device_class = sensor.get(CONF_DEVICE_CLASS) or None
    if device_class:
        fields[
            vol.Optional(CONF_DEVICE_CLASS, default=str(device_class))
        ] = _select_selector(DEVICE_CLASS_OPTIONS)
    else:
        fields[vol.Optional(CONF_DEVICE_CLASS)] = _select_selector(DEVICE_CLASS_OPTIONS)

    state_class = sensor.get(CONF_STATE_CLASS) or None
    if state_class:
        fields[
            vol.Optional(CONF_STATE_CLASS, default=str(state_class))
        ] = _select_selector(STATE_CLASS_OPTIONS)
    else:
        fields[vol.Optional(CONF_STATE_CLASS)] = _select_selector(STATE_CLASS_OPTIONS)
    return fields


def _sensor_schema(sensor: Mapping[str, Any] | None = None) -> vol.Schema:
    """Return the schema for one template sensor."""
    sensor = sensor or {}
    fields: dict[Any, Any] = {
        vol.Required(CONF_NAME, default=str(sensor.get(CONF_NAME, ""))): selector.TextSelector(),
        vol.Required(
            CONF_TEMPLATE, default=str(sensor.get(CONF_TEMPLATE, ""))
        ): selector.TemplateSelector(),
    }
    fields.update(_meta_fields(sensor))
    return vol.Schema(fields)


def _combine_schema(sensor: Mapping[str, Any] | None = None) -> vol.Schema:
    """Return the schema for one combine sensor."""
    sensor = sensor or {}
    entity_ids = sensor.get(CONF_ENTITY_IDS) or []
    combine_type = sensor.get(CONF_COMBINE_TYPE) or DEFAULT_COMBINE_TYPE
    round_digits = sensor.get(CONF_ROUND_DIGITS, DEFAULT_ROUND_DIGITS)
    try:
        round_digits = int(round_digits)
    except (TypeError, ValueError):
        round_digits = DEFAULT_ROUND_DIGITS
    fields: dict[Any, Any] = {
        vol.Required(CONF_NAME, default=str(sensor.get(CONF_NAME, ""))): selector.TextSelector(),
        vol.Required(
            CONF_ENTITY_IDS, default=list(entity_ids)
        ): selector.EntitySelector(
            selector.EntitySelectorConfig(multiple=True)
        ),
        vol.Required(
            CONF_COMBINE_TYPE, default=str(combine_type)
        ): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=list(COMBINE_TYPES),
                mode=selector.SelectSelectorMode.DROPDOWN,
                translation_key="combine_type",
            )
        ),
        vol.Required(
            CONF_ROUND_DIGITS, default=round_digits
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=0,
                max=6,
                step=1,
                mode=selector.NumberSelectorMode.BOX,
            )
        ),
    }
    fields.update(_meta_fields(sensor))
    return vol.Schema(fields)


def _unit_selector() -> selector.SelectSelector:
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=UNIT_OPTIONS,
            mode=selector.SelectSelectorMode.DROPDOWN,
            custom_value=True,
            sort=True,
        )
    )


def _select_selector(options: list[str]) -> selector.SelectSelector:
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=options,
            mode=selector.SelectSelectorMode.DROPDOWN,
            sort=True,
        )
    )


def _index_schema(sensors: list[dict[str, Any]]) -> vol.Schema:
    options = [
        {"value": str(index), "label": f"{index + 1}. {sensor.get(CONF_NAME, sensor.get(CONF_SENSOR_ID, index))}"}
        for index, sensor in enumerate(sensors)
    ]
    return vol.Schema(
        {
            vol.Required(CONF_INDEX): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=options,
                    mode=selector.SelectSelectorMode.LIST,
                )
            )
        }
    )


def _reorder_schema(sensors: list[dict[str, Any]]) -> vol.Schema:
    schema = dict(_index_schema(sensors).schema)
    schema[
        vol.Required(CONF_ACTION, default=ACTION_UP)
    ] = selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=[ACTION_UP, ACTION_DOWN, ACTION_TOP, ACTION_BOTTOM],
            mode=selector.SelectSelectorMode.LIST,
            translation_key="reorder_action",
        )
    )
    return vol.Schema(schema)


def _blank_to_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_entity_ids(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value else []
    return [str(item) for item in value if item]


def _normalize_sensor(
    user_input: Mapping[str, Any],
    *,
    kind: str,
    sensor_id: str | None = None,
) -> dict[str, Any]:
    """Normalize a sensor form into stored config."""
    data: dict[str, Any] = {
        CONF_SENSOR_ID: sensor_id or uuid.uuid4().hex,
        CONF_KIND: kind,
        CONF_NAME: str(user_input[CONF_NAME]).strip(),
        CONF_UNIT_OF_MEASUREMENT: _blank_to_none(
            user_input.get(CONF_UNIT_OF_MEASUREMENT)
        ),
        CONF_DEVICE_CLASS: _blank_to_none(user_input.get(CONF_DEVICE_CLASS)),
        CONF_STATE_CLASS: _blank_to_none(user_input.get(CONF_STATE_CLASS)),
    }
    if kind == KIND_COMBINE:
        data[CONF_ENTITY_IDS] = _normalize_entity_ids(user_input.get(CONF_ENTITY_IDS))
        data[CONF_COMBINE_TYPE] = str(
            user_input.get(CONF_COMBINE_TYPE, DEFAULT_COMBINE_TYPE)
        )
        try:
            data[CONF_ROUND_DIGITS] = int(
                user_input.get(CONF_ROUND_DIGITS, DEFAULT_ROUND_DIGITS)
            )
        except (TypeError, ValueError):
            data[CONF_ROUND_DIGITS] = DEFAULT_ROUND_DIGITS
        data[CONF_TEMPLATE] = ""
    else:
        data[CONF_TEMPLATE] = str(user_input.get(CONF_TEMPLATE, "")).strip()
        data[CONF_ENTITY_IDS] = []
        data[CONF_COMBINE_TYPE] = None
        data[CONF_ROUND_DIGITS] = DEFAULT_ROUND_DIGITS
    return data


def _sensor_summary(sensors: list[dict[str, Any]]) -> str:
    if not sensors:
        return "-"
    lines: list[str] = []
    for index, sensor in enumerate(sensors, start=1):
        kind = str(sensor.get(CONF_KIND, KIND_TEMPLATE))
        if kind == KIND_COMBINE:
            combine_type = sensor.get(CONF_COMBINE_TYPE, DEFAULT_COMBINE_TYPE)
            count = len(sensor.get(CONF_ENTITY_IDS) or [])
            detail = f"combine {combine_type} ({count})"
        else:
            detail = " ".join(str(sensor.get(CONF_TEMPLATE, "")).split())
            if len(detail) > 72:
                detail = f"{detail[:69]}..."
        lines.append(f"{index}. {sensor.get(CONF_NAME, index)} — {detail}")
    return "\n".join(lines)


def move_sensor(
    sensors: list[dict[str, Any]], index: int, action: str
) -> list[dict[str, Any]]:
    """Return a copy of sensors with one item moved."""
    items = list(sensors)
    if not 0 <= index < len(items):
        return items
    item = items.pop(index)
    if action == ACTION_TOP:
        items.insert(0, item)
    elif action == ACTION_BOTTOM:
        items.append(item)
    elif action == ACTION_UP:
        items.insert(max(0, index - 1), item)
    elif action == ACTION_DOWN:
        items.insert(min(len(items), index + 1), item)
    else:
        items.insert(index, item)
    return items


class _SensorListMixin:
    """Sensor list editor used by config and options flows.

    Methods are copied onto the flow classes so ConfigFlow keeps a single
    Home Assistant base class (required for handler registration).
    """

    hass: Any
    _name: str
    _interval: int
    _sensors: list[dict[str, Any]]
    _edit_index: int | None
    _menu_step_id: str

    def _init_list_state(
        self,
        name: str = "",
        interval: int = DEFAULT_INTERVAL,
        sensors: list[dict[str, Any]] | None = None,
        menu_step_id: str = "menu",
    ) -> None:
        self._name = name
        self._interval = interval
        self._sensors = [dict(sensor) for sensor in (sensors or [])]
        self._edit_index = None
        self._menu_step_id = menu_step_id

    def _validate_group(self, user_input: Mapping[str, Any]) -> dict[str, str]:
        errors: dict[str, str] = {}
        name = str(user_input.get(CONF_NAME, "")).strip()
        if not name:
            errors[CONF_NAME] = "invalid_name"
        try:
            interval = int(user_input.get(CONF_INTERVAL, DEFAULT_INTERVAL))
        except (TypeError, ValueError):
            errors[CONF_INTERVAL] = "invalid_interval"
            interval = DEFAULT_INTERVAL
        if interval < MIN_INTERVAL:
            errors[CONF_INTERVAL] = "invalid_interval"
        if not errors:
            self._name = name
            self._interval = interval
        return errors

    def _validate_sensor(self, user_input: Mapping[str, Any]) -> dict[str, str]:
        errors: dict[str, str] = {}
        name = str(user_input.get(CONF_NAME, "")).strip()
        template_str = str(user_input.get(CONF_TEMPLATE, "")).strip()
        if not name:
            errors[CONF_NAME] = "invalid_name"
        if not template_str:
            errors[CONF_TEMPLATE] = "invalid_template"
        else:
            try:
                from homeassistant.helpers.template import Template

                Template(template_str, self.hass).ensure_valid()
            except (TemplateError, ValueError, TypeError):
                errors[CONF_TEMPLATE] = "invalid_template"
        return errors

    def _validate_combine(self, user_input: Mapping[str, Any]) -> dict[str, str]:
        errors: dict[str, str] = {}
        name = str(user_input.get(CONF_NAME, "")).strip()
        entity_ids = _normalize_entity_ids(user_input.get(CONF_ENTITY_IDS))
        if not name:
            errors[CONF_NAME] = "invalid_name"
        if not entity_ids:
            errors[CONF_ENTITY_IDS] = "no_entities"
        combine_type = str(user_input.get(CONF_COMBINE_TYPE, ""))
        if combine_type not in COMBINE_TYPES:
            errors[CONF_COMBINE_TYPE] = "invalid_combine_type"
        return errors

    def _menu_options(self) -> list[str]:
        options = ["add_sensor"]
        if self._sensors:
            options.extend(["pick_edit", "pick_remove"])
        if len(self._sensors) > 1:
            options.append("reorder")
        options.append("finish")
        return options

    def _show_menu(self):
        return self.async_show_menu(
            step_id=self._menu_step_id,
            menu_options=self._menu_options(),
            description_placeholders={
                "name": self._name or "",
                "interval": str(self._interval),
                "count": str(len(self._sensors)),
                "sensors": _sensor_summary(self._sensors),
            },
        )

    async def async_step_menu(self, user_input: dict[str, Any] | None = None):
        """Show the sensor list menu."""
        return self._show_menu()

    async def async_step_add_sensor(self, user_input: dict[str, Any] | None = None):
        """Choose whether the new sensor is a template or a combine."""
        return self.async_show_menu(
            step_id="add_sensor",
            menu_options=["add_template", "add_combine"],
            description_placeholders={
                "position": str(len(self._sensors) + 1),
                "sensors": _sensor_summary(self._sensors),
            },
        )

    async def async_step_add_template(self, user_input: dict[str, Any] | None = None):
        """Add a Jinja template sensor."""
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = self._validate_sensor(user_input)
            if not errors:
                self._sensors.append(
                    _normalize_sensor(user_input, kind=KIND_TEMPLATE)
                )
                return self._show_menu()
        return self.async_show_form(
            step_id="add_template",
            data_schema=_sensor_schema(),
            errors=errors,
            description_placeholders={
                "position": str(len(self._sensors) + 1),
                "sensors": _sensor_summary(self._sensors),
            },
        )

    async def async_step_add_combine(self, user_input: dict[str, Any] | None = None):
        """Add a combine sensor."""
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = self._validate_combine(user_input)
            if not errors:
                self._sensors.append(
                    _normalize_sensor(user_input, kind=KIND_COMBINE)
                )
                return self._show_menu()
        return self.async_show_form(
            step_id="add_combine",
            data_schema=_combine_schema(),
            errors=errors,
            description_placeholders={
                "position": str(len(self._sensors) + 1),
                "sensors": _sensor_summary(self._sensors),
            },
        )

    async def async_step_pick_edit(self, user_input: dict[str, Any] | None = None):
        """Pick a sensor to edit."""
        if not self._sensors:
            return self._show_menu()
        if len(self._sensors) == 1:
            self._edit_index = 0
            return await self._async_edit_current()
        if user_input is not None:
            self._edit_index = int(user_input[CONF_INDEX])
            return await self._async_edit_current()
        return self.async_show_form(
            step_id="pick_edit",
            data_schema=_index_schema(self._sensors),
            description_placeholders={"sensors": _sensor_summary(self._sensors)},
        )

    async def _async_edit_current(self):
        """Open the editor matching the selected sensor kind."""
        if self._edit_index is None or not (0 <= self._edit_index < len(self._sensors)):
            return self._show_menu()
        current = self._sensors[self._edit_index]
        if str(current.get(CONF_KIND, KIND_TEMPLATE)) == KIND_COMBINE:
            return await self.async_step_edit_combine()
        return await self.async_step_edit_sensor()

    async def async_step_edit_sensor(self, user_input: dict[str, Any] | None = None):
        """Edit the selected template sensor without changing its unique id."""
        if self._edit_index is None or not (0 <= self._edit_index < len(self._sensors)):
            return self._show_menu()
        current = self._sensors[self._edit_index]
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = self._validate_sensor(user_input)
            if not errors:
                self._sensors[self._edit_index] = _normalize_sensor(
                    user_input,
                    kind=KIND_TEMPLATE,
                    sensor_id=str(current[CONF_SENSOR_ID]),
                )
                self._edit_index = None
                return self._show_menu()
        return self.async_show_form(
            step_id="edit_sensor",
            data_schema=_sensor_schema(current),
            errors=errors,
            description_placeholders={
                "name": str(current.get(CONF_NAME, "")),
                "sensors": _sensor_summary(self._sensors),
            },
        )

    async def async_step_edit_combine(self, user_input: dict[str, Any] | None = None):
        """Edit the selected combine sensor without changing its unique id."""
        if self._edit_index is None or not (0 <= self._edit_index < len(self._sensors)):
            return self._show_menu()
        current = self._sensors[self._edit_index]
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = self._validate_combine(user_input)
            if not errors:
                self._sensors[self._edit_index] = _normalize_sensor(
                    user_input,
                    kind=KIND_COMBINE,
                    sensor_id=str(current[CONF_SENSOR_ID]),
                )
                self._edit_index = None
                return self._show_menu()
        return self.async_show_form(
            step_id="edit_combine",
            data_schema=_combine_schema(current),
            errors=errors,
            description_placeholders={
                "name": str(current.get(CONF_NAME, "")),
                "sensors": _sensor_summary(self._sensors),
            },
        )

    async def async_step_pick_remove(self, user_input: dict[str, Any] | None = None):
        """Remove a sensor from the group."""
        errors: dict[str, str] = {}
        if not self._sensors:
            return self._show_menu()
        if user_input is not None:
            if len(self._sensors) <= 1:
                errors[CONF_INDEX] = "last_sensor"
            else:
                self._sensors.pop(int(user_input[CONF_INDEX]))
                return self._show_menu()
        return self.async_show_form(
            step_id="pick_remove",
            data_schema=_index_schema(self._sensors),
            errors=errors,
            description_placeholders={"sensors": _sensor_summary(self._sensors)},
        )

    async def async_step_reorder(self, user_input: dict[str, Any] | None = None):
        """Change evaluation order."""
        if len(self._sensors) < 2:
            return self._show_menu()
        if user_input is not None:
            self._sensors = move_sensor(
                self._sensors,
                int(user_input[CONF_INDEX]),
                str(user_input[CONF_ACTION]),
            )
            return self._show_menu()
        return self.async_show_form(
            step_id="reorder",
            data_schema=_reorder_schema(self._sensors),
            description_placeholders={"sensors": _sensor_summary(self._sensors)},
        )

    async def async_step_finish(self, user_input: dict[str, Any] | None = None):
        """Persist the group when at least one sensor is configured."""
        if not self._sensors:
            return await self.async_step_add_sensor()
        return await self._async_finish_flow()

    async def _async_finish_flow(self):
        """Implemented by the config or options flow."""
        raise NotImplementedError


def _attach_sensor_list(cls):
    """Copy editor methods onto a ConfigFlow/OptionsFlow subclass."""
    for name, attr in _SensorListMixin.__dict__.items():
        if name.startswith("__") or not callable(attr):
            continue
        if name not in cls.__dict__:
            setattr(cls, name, attr)
    return cls


@_attach_sensor_list
class ThrottledLinkedTemplateConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Throttled Linked Template."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._init_list_state(menu_step_id="menu")

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Return the options flow."""
        return ThrottledLinkedTemplateOptionsFlow(config_entry)

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Create a new group: name and interval."""
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = self._validate_group(user_input)
            if not errors:
                return await self.async_step_add_sensor()
        return self.async_show_form(
            step_id="user",
            data_schema=_group_schema(self._name, self._interval),
            errors=errors,
        )

    async def _async_finish_flow(self):
        """Create the config entry."""
        return self.async_create_entry(
            title=self._name,
            data={CONF_NAME: self._name},
            options={
                CONF_INTERVAL: self._interval,
                CONF_SENSORS: self._sensors,
            },
        )


@_attach_sensor_list
class ThrottledLinkedTemplateOptionsFlow(config_entries.OptionsFlow):
    """Handle options for an existing template group."""

    def __init__(self, config_entry: config_entries.ConfigEntry | None = None) -> None:
        """Initialize the options flow."""
        self._config_entry = config_entry
        self._init_list_state(menu_step_id="menu")

    @property
    def _entry(self) -> config_entries.ConfigEntry:
        entry = getattr(self, "_config_entry", None)
        if entry is not None:
            return entry
        return self.config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        """Edit group name and interval, then manage sensors."""
        if not self._name and self._entry is not None:
            self._name = entry_name(self._entry)
            self._interval = entry_interval(self._entry)
            self._sensors = entry_sensors(self._entry)
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = self._validate_group(user_input)
            if not errors:
                return self._show_menu()
        return self.async_show_form(
            step_id="init",
            data_schema=_group_schema(self._name, self._interval),
            errors=errors,
            description_placeholders={
                "sensors": _sensor_summary(self._sensors),
                "count": str(len(self._sensors)),
            },
        )

    async def _async_finish_flow(self):
        """Save options without recreating the group."""
        entry = self._entry
        self.hass.config_entries.async_update_entry(
            entry,
            title=self._name,
            data={**dict(entry.data), CONF_NAME: self._name},
        )
        return self.async_create_entry(
            title="",
            data={
                CONF_INTERVAL: self._interval,
                CONF_SENSORS: self._sensors,
            },
        )
