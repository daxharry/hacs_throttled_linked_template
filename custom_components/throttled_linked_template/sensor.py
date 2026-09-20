"""Sensor platform for Throttled Linked Template."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify

from .const import (
    ATTR_LAST_ERROR,
    ATTR_LINKED_INDEX,
    CONF_COMBINE_TYPE,
    CONF_DEVICE_CLASS,
    CONF_ENTITY_IDS,
    CONF_KIND,
    CONF_SENSOR_ID,
    CONF_STATE_CLASS,
    CONF_UNIT_OF_MEASUREMENT,
    DOMAIN,
    KIND_COMBINE,
    entry_name,
    entry_sensors,
    sensor_unique_id,
)
from .coordinator import ThrottledLinkedTemplateCoordinator


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
    entities = [
        ThrottledLinkedTemplateSensor(coordinator, entry, sensor, index)
        for index, sensor in enumerate(entry_sensors(entry))
        if sensor.get(CONF_SENSOR_ID)
    ]
    async_add_entities(entities)


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
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry_name(entry),
            manufacturer="Throttled Linked Template",
            model="Linked template group",
            entry_type=DeviceEntryType.SERVICE,
        )
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
