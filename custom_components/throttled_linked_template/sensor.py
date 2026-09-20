"""Sensor platform for Throttled Linked Template."""

from __future__ import annotations

import inspect
from typing import Any

from datetime import datetime

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify

from .const import (
    ATTR_INTERVAL,
    ATTR_LAST_ERROR,
    ATTR_LAST_TRIGGER,
    ATTR_LAST_TRIGGER_ENTITY,
    ATTR_LINKED_INDEX,
    ATTR_TRIGGER_ENTITIES,
    ATTR_UPDATE_MODE,
    CONF_COMBINE_TYPE,
    CONF_DEVICE_CLASS,
    CONF_ENTITY_IDS,
    CONF_KIND,
    CONF_SENSOR_ID,
    CONF_STATE_CLASS,
    CONF_UNIT_OF_MEASUREMENT,
    KIND_COMBINE,
    UPDATE_MODE_STATE,
    entry_interval,
    entry_sensors,
    entry_update_mode,
    sensor_unique_id,
)
from .coordinator import ThrottledLinkedTemplateCoordinator
from .entity import (
    STATUS_LAST_UPDATE,
    STATUS_UPDATE_MODE,
    group_device_info,
    status_unique_id,
)


def _coerce_enum(enum_cls: type, value: Any) -> Any:
    """Return an enum member when possible, otherwise the raw value."""
    if not value:
        return None
    try:
        return enum_cls(value)
    except ValueError:
        return value


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors for a template group."""
    coordinator: ThrottledLinkedTemplateCoordinator = entry.runtime_data
    entities: list[CoordinatorEntity] = [
        ThrottledLinkedTemplateSensor(coordinator, entry, sensor, index)
        for index, sensor in enumerate(entry_sensors(entry))
        if sensor.get(CONF_SENSOR_ID)
    ]
    entities.extend(
        [
            GroupUpdateModeSensor(coordinator, entry),
            GroupLastUpdateSensor(coordinator, entry),
        ]
    )
    result = async_add_entities(entities)
    if inspect.isawaitable(result):
        await result


class ThrottledLinkedTemplateSensor(
    CoordinatorEntity[ThrottledLinkedTemplateCoordinator],
    RestoreSensor,
    SensorEntity,
):
    """A template sensor evaluated on the group interval."""

    _attr_has_entity_name = False
    _attr_should_poll = False

    def __init__(
        self,
        coordinator: ThrottledLinkedTemplateCoordinator,
        entry: ConfigEntry,
        sensor: dict[str, Any],
        index: int,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._sensor_id = str(sensor[CONF_SENSOR_ID])
        self._index = index
        self._kind = str(sensor.get(CONF_KIND, "template"))
        self._entity_ids = [
            str(item) for item in sensor.get(CONF_ENTITY_IDS, []) if item
        ]
        self._combine_type = sensor.get(CONF_COMBINE_TYPE)
        self._attr_icon = (
            "mdi:calculator" if self._kind == KIND_COMBINE else "mdi:code-braces"
        )
        name = str(sensor.get(CONF_NAME) or f"Sensor {index + 1}")
        self._attr_name = name
        self._attr_suggested_object_id = slugify(name)
        self._attr_unique_id = sensor_unique_id(entry.entry_id, self._sensor_id)
        self._attr_device_info = group_device_info(entry)
        unit = sensor.get(CONF_UNIT_OF_MEASUREMENT)
        self._attr_native_unit_of_measurement = unit or None
        self._attr_device_class = _coerce_enum(
            SensorDeviceClass, sensor.get(CONF_DEVICE_CLASS)
        )
        self._attr_state_class = _coerce_enum(
            SensorStateClass, sensor.get(CONF_STATE_CLASS)
        )
        self._restored_value: Any = None

    async def async_added_to_hass(self) -> None:
        """Restore the last value and register for sequential writes."""
        await super().async_added_to_hass()
        last = await self.async_get_last_sensor_data()
        if last is not None and last.native_value is not None:
            self._restored_value = last.native_value
            self.coordinator.seed_restored(self._sensor_id, last.native_value)
        self.coordinator.register_entity(self._sensor_id, self)

    async def async_will_remove_from_hass(self) -> None:
        """Unregister from the coordinator."""
        self.coordinator.unregister_entity(self._sensor_id)
        await super().async_will_remove_from_hass()

    @property
    def native_value(self) -> Any:
        """Return the latest evaluated or restored value."""
        result = self.coordinator.result_for(self._sensor_id)
        if result is not None:
            return result.native_value if result.available else None
        return self._restored_value

    @property
    def available(self) -> bool:
        """Return True when the last evaluation succeeded or a value was restored."""
        result = self.coordinator.result_for(self._sensor_id)
        if result is not None:
            return result.available
        return self._restored_value is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return order and last template error."""
        attributes: dict[str, Any] = {
            ATTR_LINKED_INDEX: self._index + 1,
            CONF_KIND: self._kind,
            "linked_keys": self.coordinator.linked_keys,
        }
        if self._kind == KIND_COMBINE:
            attributes[CONF_COMBINE_TYPE] = self._combine_type
            attributes[CONF_ENTITY_IDS] = self._entity_ids
        result = self.coordinator.result_for(self._sensor_id)
        if result is not None and result.error:
            attributes[ATTR_LAST_ERROR] = result.error
        return attributes

    @callback
    def _handle_coordinator_update(self) -> None:
        """Write state when the coordinator finishes a tick."""
        self.async_write_ha_state()


class GroupUpdateModeSensor(
    CoordinatorEntity[ThrottledLinkedTemplateCoordinator], SensorEntity
):
    """Describe how and from which entities the group is recalculated."""

    _attr_has_entity_name = True
    _attr_translation_key = "update_mode"
    _attr_icon = "mdi:update"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_should_poll = False

    def __init__(
        self,
        coordinator: ThrottledLinkedTemplateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the update-mode sensor."""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = status_unique_id(entry.entry_id, STATUS_UPDATE_MODE)
        self._attr_device_info = group_device_info(entry)
        self._attr_suggested_object_id = "update_mode"

    @property
    def available(self) -> bool:
        """The mode sensor is always available."""
        return True

    @property
    def native_value(self) -> str:
        """Return a precise human-readable update mode."""
        mode = entry_update_mode(self._entry)
        interval = entry_interval(self._entry)
        if mode != UPDATE_MODE_STATE:
            return f"every {interval} seconds"
        sources = self.coordinator.trigger_entities
        if not sources:
            return "on entity update (no sources found)"
        joined = ", ".join(sources)
        if len(joined) <= 200:
            return f"on update of {joined}"
        return f"on update of {len(sources)} sources"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return mode, interval, sources and last trigger."""
        return {
            ATTR_UPDATE_MODE: entry_update_mode(self._entry),
            ATTR_INTERVAL: entry_interval(self._entry),
            ATTR_TRIGGER_ENTITIES: self.coordinator.trigger_entities,
            ATTR_LAST_TRIGGER: self.coordinator.last_trigger,
            ATTR_LAST_TRIGGER_ENTITY: self.coordinator.last_trigger_entity,
        }


class GroupLastUpdateSensor(
    CoordinatorEntity[ThrottledLinkedTemplateCoordinator],
    RestoreSensor,
    SensorEntity,
):
    """Timestamp of the last group tick."""

    _attr_has_entity_name = True
    _attr_translation_key = "last_update"
    _attr_icon = "mdi:clock-outline"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_should_poll = False

    def __init__(
        self,
        coordinator: ThrottledLinkedTemplateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the last-update sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = status_unique_id(entry.entry_id, STATUS_LAST_UPDATE)
        self._attr_device_info = group_device_info(entry)
        self._attr_suggested_object_id = "last_update"
        self._restored_value: datetime | None = None

    async def async_added_to_hass(self) -> None:
        """Restore the last tick time after a restart."""
        await super().async_added_to_hass()
        last = await self.async_get_last_sensor_data()
        if last is not None and isinstance(last.native_value, datetime):
            self._restored_value = last.native_value
            if self.coordinator.last_update is None:
                self.coordinator.last_update = last.native_value

    @property
    def native_value(self) -> datetime | None:
        """Return when the group last finished a tick."""
        return self.coordinator.last_update or self._restored_value

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return what triggered the last tick."""
        return {
            ATTR_LAST_TRIGGER: self.coordinator.last_trigger,
            ATTR_LAST_TRIGGER_ENTITY: self.coordinator.last_trigger_entity,
        }
