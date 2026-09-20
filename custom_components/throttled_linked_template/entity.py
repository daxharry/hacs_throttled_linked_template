"""Shared entity helpers for a template group."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo

from .const import DOMAIN, entry_name

STATUS_UPDATE_MODE = "update_mode"
STATUS_LAST_UPDATE = "last_update"
STATUS_FORCE_UPDATE = "force_update"
STATUS_UNIQUE_SUFFIXES = (
    STATUS_UPDATE_MODE,
    STATUS_LAST_UPDATE,
    STATUS_FORCE_UPDATE,
)


def group_device_info(entry: ConfigEntry) -> DeviceInfo:
    """Return the service device that holds the group entities."""
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry_name(entry),
        manufacturer="Throttled Linked Template",
        model="Linked template group",
        entry_type=DeviceEntryType.SERVICE,
    )


def status_unique_id(entry_id: str, suffix: str) -> str:
    """Return a stable unique_id for a group status entity."""
    return f"{entry_id}_{suffix}"
