"""Button platform for Throttled Linked Template."""

from __future__ import annotations

import inspect

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import ThrottledLinkedTemplateCoordinator
from .entity import (
    STATUS_FORCE_UPDATE,
    group_device_info,
    status_unique_id,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the force-update button for a group."""
    coordinator: ThrottledLinkedTemplateCoordinator = entry.runtime_data
    result = async_add_entities([GroupForceUpdateButton(coordinator, entry)])
    if inspect.isawaitable(result):
        await result


class GroupForceUpdateButton(
    CoordinatorEntity[ThrottledLinkedTemplateCoordinator], ButtonEntity
):
    """Button that immediately recalculates every sensor in the group."""

    _attr_has_entity_name = True
    _attr_translation_key = "force_update"
    _attr_icon = "mdi:refresh"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_should_poll = False

    def __init__(
        self,
        coordinator: ThrottledLinkedTemplateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        self._attr_unique_id = status_unique_id(entry.entry_id, STATUS_FORCE_UPDATE)
        self._attr_device_info = group_device_info(entry)
        self._attr_suggested_object_id = "force_update"

    async def async_press(self) -> None:
        """Force a group tick now, ignoring the debounce."""
        self.coordinator.mark_trigger("manual")
        await self.coordinator.async_refresh()
