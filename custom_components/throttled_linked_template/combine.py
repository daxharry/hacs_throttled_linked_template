"""Combine several source states without tracking state_changed."""

from __future__ import annotations

from statistics import median
from typing import Any

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant

from .const import (
    COMBINE_LAST,
    COMBINE_MAX,
    COMBINE_MEAN,
    COMBINE_MEDIAN,
    COMBINE_MIN,
    COMBINE_RANGE,
    COMBINE_SUM,
)


class CombineError(Exception):
    """Raised when a combine calculation cannot produce a value."""


def combine_states(
    hass: HomeAssistant,
    entity_ids: list[str],
    combine_type: str,
    round_digits: int,
    overrides: dict[str, Any] | None = None,
) -> float:
    """Return the combined numeric value of the given entities.

    `overrides` holds values already computed earlier in the same group tick,
    so a combine can read a previous group sensor before the rest of HA does.
    """
    values: list[float] = []
    last_value: float | None = None
    last_updated: Any = None

    for entity_id in entity_ids:
        raw: Any = None
        updated = None
        object_id = entity_id.split(".", 1)[-1] if "." in entity_id else entity_id
        if overrides and entity_id in overrides:
            raw = overrides[entity_id]
        elif overrides and object_id in overrides:
            raw = overrides[object_id]
        else:
            state = hass.states.get(entity_id)
            if state is None or state.state in (
                STATE_UNKNOWN,
                STATE_UNAVAILABLE,
                None,
                "",
            ):
                continue
            raw = state.state
            updated = getattr(state, "last_updated", None)
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        values.append(value)
        if last_updated is None or (updated is not None and updated > last_updated):
            last_updated = updated
            last_value = value

    if not values:
        raise CombineError("No numeric source states available")

    if combine_type == COMBINE_MIN:
        result = min(values)
    elif combine_type == COMBINE_MAX:
        result = max(values)
    elif combine_type == COMBINE_MEAN:
        result = sum(values) / len(values)
    elif combine_type == COMBINE_MEDIAN:
        result = float(median(values))
    elif combine_type == COMBINE_SUM:
        result = sum(values)
    elif combine_type == COMBINE_RANGE:
        result = max(values) - min(values)
    elif combine_type == COMBINE_LAST:
        result = last_value if last_value is not None else values[-1]
    else:
        raise CombineError(f"Unknown combine type: {combine_type}")

    digits = max(0, int(round_digits))
    return round(result, digits)
