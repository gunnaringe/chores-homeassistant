"""Tests for the Chores calendar."""

from __future__ import annotations

from homeassistant.components.calendar import DOMAIN as CALENDAR_DOMAIN
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant

from .conftest import occurrence, setup_integration

ENTITY_ID = "calendar.lisa"


async def test_event_is_next_undone_occurrence(
    hass: HomeAssistant, aioclient_mock, config_entry
) -> None:
    """The `event` property is the next occurrence not yet completed."""
    await setup_integration(
        hass, aioclient_mock, config_entry, occurrences=[occurrence()]
    )

    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.attributes["message"] == "Ta ut søpla"


async def test_completed_occurrence_is_not_the_event(
    hass: HomeAssistant, aioclient_mock, config_entry
) -> None:
    """A completed occurrence today doesn't surface as the calendar's event."""
    await setup_integration(
        hass,
        aioclient_mock,
        config_entry,
        occurrences=[occurrence(completedAt="2026-08-30T10:00:00Z")],
    )

    assert hass.states.get(ENTITY_ID).state == "off"


async def test_get_events_queries_the_requested_range(
    hass: HomeAssistant, aioclient_mock, config_entry
) -> None:
    """async_get_events fetches the range directly, filtered to this child.

    The mock for ListTaskOccurrences is shared with the coordinator's own
    "today" refresh (aioclient_mock matches the first-registered mock for a
    URL), so the fixture data is set up front rather than re-registered.
    """
    await setup_integration(
        hass,
        aioclient_mock,
        config_entry,
        occurrences=[
            occurrence(dueDate="2026-09-10"),
            occurrence(dueDate="2026-09-11", childId="child-2"),
        ],
    )

    events = await hass.services.async_call(
        CALENDAR_DOMAIN,
        "get_events",
        {
            ATTR_ENTITY_ID: ENTITY_ID,
            "start_date_time": "2026-09-01T00:00:00Z",
            "end_date_time": "2026-09-30T00:00:00Z",
        },
        blocking=True,
        return_response=True,
    )

    summaries = [e["summary"] for e in events[ENTITY_ID]["events"]]
    assert summaries == ["Ta ut søpla"]
