"""Shared entity-setup scaffolding for the per-child platforms.

Every platform (todo, sensor, button, calendar) creates the same entities
once per child, and needs to pick up new children that appear after the
initial refresh without a reload. This is that pattern, written once.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from homeassistant.core import callback
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import ChoresCoordinator


def async_add_per_child_entities(
    coordinator: ChoresCoordinator,
    async_add_entities: AddConfigEntryEntitiesCallback,
    make_entities: Callable[[dict[str, Any]], Iterable[Entity]],
) -> Callable[[], None]:
    """Add entities for every current child, then for any that appear later.

    Returns the coordinator listener's unsubscribe callback, which the
    caller is responsible for registering with `entry.async_on_unload`.
    """
    known: set[str] = set()

    @callback
    def _add_new_children() -> None:
        new = [child for child in coordinator.data.children if child["id"] not in known]
        if not new:
            return
        known.update(child["id"] for child in new)
        entities: list[Entity] = []
        for child in new:
            entities.extend(make_entities(child))
        async_add_entities(entities)

    _add_new_children()
    return coordinator.async_add_listener(_add_new_children)
