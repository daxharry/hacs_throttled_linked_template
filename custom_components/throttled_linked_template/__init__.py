"""Throttled Linked Template helper for Home Assistant."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import CONF_SENSOR_ID, DOMAIN, entry_sensors, sensor_unique_id

PLATFORMS = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a template group from a config entry."""
    from .coordinator import ThrottledLinkedTemplateCoordinator

    coordinator = ThrottledLinkedTemplateCoordinator(hass, entry)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    entry.runtime_data = coordinator

    _async_cleanup_orphaned_entities(hass, entry)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # First tick runs after entities are registered so same-tick chaining works.
    await coordinator.async_config_entry_first_refresh()
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the group when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


def _async_cleanup_orphaned_entities(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove registry entries for sensors that are no longer in the group."""
    registry = er.async_get(hass)
    valid_unique_ids = {
        sensor_unique_id(entry.entry_id, str(sensor[CONF_SENSOR_ID]))
        for sensor in entry_sensors(entry)
        if sensor.get(CONF_SENSOR_ID)
    }
    for entity_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
        if entity_entry.unique_id not in valid_unique_ids:
            registry.async_remove(entity_entry.entity_id)
