"""Extract external entity IDs that should trigger a group tick."""

from __future__ import annotations

import re
from typing import Any

from .const import CONF_ENTITY_IDS, CONF_KIND, CONF_TEMPLATE, KIND_COMBINE

_STATES_CALL = re.compile(
    r"""(?:states|is_state|state_attr|is_state_attr|has_value)\(\s*['"]"""
    r"""([a-zA-Z0-9_]+\.[a-zA-Z0-9_]+)['"]"""
)
_STATES_DOT = re.compile(r"\bstates\.([a-zA-Z0-9_]+)\.([a-zA-Z0-9_]+)")


def collect_trigger_entity_ids(
    sensors: list[dict[str, Any]], own_entity_ids: set[str]
) -> list[str]:
    """Return source entity IDs referenced by the group, excluding our sensors."""
    found: set[str] = set()
    for sensor in sensors:
        if str(sensor.get(CONF_KIND, "")) == KIND_COMBINE:
            found.update(
                str(entity_id)
                for entity_id in sensor.get(CONF_ENTITY_IDS) or []
                if entity_id
            )
        template = str(sensor.get(CONF_TEMPLATE) or "")
        found.update(_STATES_CALL.findall(template))
        found.update(f"{domain}.{object_id}" for domain, object_id in _STATES_DOT.findall(template))
    found -= {entity_id for entity_id in own_entity_ids if entity_id}
    return sorted(found)


def resolve_trigger_entity_ids(
    sensors: list[dict[str, Any]],
    own_entity_ids: set[str],
    explicit: list[str] | None = None,
) -> list[str]:
    """Prefer entities picked in the UI, else those found in combine/templates."""
    own = {entity_id for entity_id in own_entity_ids if entity_id}
    selected = {str(entity_id) for entity_id in (explicit or []) if entity_id}
    if selected:
        return sorted(selected - own)
    return collect_trigger_entity_ids(sensors, own)
