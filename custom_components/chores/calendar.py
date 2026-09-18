"""Calendar entity for the Chores integration: occurrences over a date range.

Unlike the todo list (today only, from the 5-minute coordinator), a calendar
view can be asked for an arbitrary range by Home Assistant's calendar UI, so
`async_get_events` calls the API directly rather than reading the
coordinator's cache.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ChoresConfigEntry, ChoresCoordinator
from .entity import async_add_per_child_entities
from .util import occurrence_uid


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ChoresConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up a calendar for each child in the family."""
    coordinator = entry.runtime_data.main
    unsub = async_add_per_child_entities(
        coordinator,
        async_add_entities,
        lambda child: [ChoresCalendarEntity(coordinator, child)],
    )
    entry.async_on_unload(unsub)


def _to_event(occurrence: dict[str, Any]) -> CalendarEvent | None:
    """Turn one task occurrence into an all-day CalendarEvent."""
    raw_date = occurrence.get("dueDate")
    if not raw_date:
        return None
    try:
        due = date.fromisoformat(raw_date)
    except ValueError:
        return None
    return CalendarEvent(
        start=due,
        end=due + timedelta(days=1),
        summary=occurrence.get("title") or "Chore",
        description=occurrence.get("description") or None,
        uid=occurrence_uid(occurrence),
    )


class ChoresCalendarEntity(CoordinatorEntity[ChoresCoordinator], CalendarEntity):
    """One child's task occurrences as a calendar."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_translation_key = "chores"

    def __init__(self, coordinator: ChoresCoordinator, child: dict[str, Any]) -> None:
        """Initialise the calendar."""
        super().__init__(coordinator)
        self._child_id = child["id"]
        self._attr_unique_id = f"{coordinator.family_id}_{self._child_id}_calendar"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._child_id)},
            name=child.get("name") or "Child",
            manufacturer="Chores",
            model="Child",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def event(self) -> CalendarEvent | None:
        """Return the next occurrence due today or later that isn't done yet."""
        occurrences = sorted(
            self.coordinator.data.occurrences_by_child.get(self._child_id, []),
            key=lambda o: o.get("dueDate", ""),
        )
        for occurrence in occurrences:
            if occurrence.get("completedAt"):
                continue
            if event := _to_event(occurrence):
                return event
        return None

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        """List this child's occurrences due within the requested range."""
        occurrences = await self.coordinator.client.list_task_occurrences(
            self.coordinator.family_id,
            start_date.date().isoformat(),
            end_date.date().isoformat(),
        )
        events = [
            _to_event(occurrence)
            for occurrence in occurrences
            if occurrence.get("childId") == self._child_id
        ]
        return [event for event in events if event is not None]
