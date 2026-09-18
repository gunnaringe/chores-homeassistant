"""Tests for the Chores todo lists."""

from __future__ import annotations

from homeassistant.components.todo import (
    ATTR_ITEM,
    ATTR_STATUS,
    DOMAIN as TODO_DOMAIN,
    TodoServices,
)
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util
import pytest

from .conftest import FAMILY_ID, occurrence, rpc_url, setup_integration

ENTITY_ID = "todo.lisa"


async def test_lists_todays_chores(
    hass: HomeAssistant, aioclient_mock, config_entry, users_response
) -> None:
    """Each child gets a list holding today's chores."""
    await setup_integration(
        hass,
        aioclient_mock,
        config_entry,
        users=users_response,
        occurrences=[occurrence()],
    )

    state = hass.states.get(ENTITY_ID)
    assert state is not None
    # An uncompleted chore counts towards the list's state.
    assert state.state == "1"


async def test_completed_chore_is_not_pending(
    hass: HomeAssistant, aioclient_mock, config_entry, users_response
) -> None:
    """A completedAt timestamp marks the item done."""
    await setup_integration(
        hass,
        aioclient_mock,
        config_entry,
        users=users_response,
        occurrences=[occurrence(completedAt="2026-08-30T10:00:00Z")],
    )

    assert hass.states.get(ENTITY_ID).state == "0"


async def test_mandatory_sorts_before_optional(
    hass: HomeAssistant, aioclient_mock, config_entry, users_response
) -> None:
    """Must-do chores come first, mirroring the app's own split."""
    await setup_integration(
        hass,
        aioclient_mock,
        config_entry,
        users=users_response,
        occurrences=[
            occurrence(
                taskId="task-2",
                title="Vanne blomster",
                classification="TASK_CLASSIFICATION_OPTIONAL",
            ),
            occurrence(),
        ],
    )

    items = await hass.services.async_call(
        TODO_DOMAIN,
        TodoServices.GET_ITEMS,
        {ATTR_ENTITY_ID: ENTITY_ID},
        blocking=True,
        return_response=True,
    )
    summaries = [item["summary"] for item in items[ENTITY_ID]["items"]]
    assert summaries == ["Ta ut søpla", "Vanne blomster"]


async def test_ticking_completes_the_task(
    hass: HomeAssistant, aioclient_mock, config_entry, users_response
) -> None:
    """Checking an item calls CompleteTask with the occurrence's own tuple."""
    await setup_integration(
        hass,
        aioclient_mock,
        config_entry,
        users=users_response,
        occurrences=[occurrence()],
    )
    aioclient_mock.post(rpc_url("CompleteTask"), json={})

    await hass.services.async_call(
        TODO_DOMAIN,
        TodoServices.UPDATE_ITEM,
        {
            ATTR_ENTITY_ID: ENTITY_ID,
            ATTR_ITEM: "Ta ut søpla",
            ATTR_STATUS: "completed",
        },
        blocking=True,
    )

    complete_calls = [
        call for call in aioclient_mock.mock_calls if "CompleteTask" in str(call[1])
    ]
    assert complete_calls
    assert complete_calls[0][2] == {
        "taskId": "task-1",
        "childId": "child-1",
        "dueDate": dt_util.now().date().isoformat(),
    }


async def test_unticking_uncompletes_the_task(
    hass: HomeAssistant, aioclient_mock, config_entry, users_response
) -> None:
    """Unchecking an item calls UncompleteTask."""
    await setup_integration(
        hass,
        aioclient_mock,
        config_entry,
        users=users_response,
        occurrences=[occurrence(completedAt="2026-08-30T10:00:00Z")],
    )
    aioclient_mock.post(rpc_url("UncompleteTask"), json={})

    await hass.services.async_call(
        TODO_DOMAIN,
        TodoServices.UPDATE_ITEM,
        {
            ATTR_ENTITY_ID: ENTITY_ID,
            ATTR_ITEM: "Ta ut søpla",
            ATTR_STATUS: "needs_action",
        },
        blocking=True,
    )

    assert any("UncompleteTask" in str(call[1]) for call in aioclient_mock.mock_calls)


async def test_renaming_is_rejected(
    hass: HomeAssistant, aioclient_mock, config_entry, users_response
) -> None:
    """Chores are renamed in the Chores app, not from Home Assistant."""
    await setup_integration(
        hass,
        aioclient_mock,
        config_entry,
        users=users_response,
        occurrences=[occurrence()],
    )

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            TODO_DOMAIN,
            TodoServices.UPDATE_ITEM,
            {
                ATTR_ENTITY_ID: ENTITY_ID,
                ATTR_ITEM: "Ta ut søpla",
                "rename": "Noe annet",
            },
            blocking=True,
        )


async def test_completion_fires_event(
    hass: HomeAssistant, aioclient_mock, config_entry, users_response
) -> None:
    """Completing a chore fires chores_task_completed event."""
    await setup_integration(
        hass,
        aioclient_mock,
        config_entry,
        users=users_response,
        occurrences=[occurrence()],
    )
    aioclient_mock.post(rpc_url("CompleteTask"), json={})

    events = []
    hass.bus.async_listen("chores_task_completed", lambda e: events.append(e))

    await hass.services.async_call(
        TODO_DOMAIN,
        TodoServices.UPDATE_ITEM,
        {
            ATTR_ENTITY_ID: ENTITY_ID,
            ATTR_ITEM: "Ta ut søpla",
            ATTR_STATUS: "completed",
        },
        blocking=True,
    )

    assert len(events) == 1
    assert events[0].data["task_id"] == "task-1"
    assert events[0].data["task_title"] == "Ta ut søpla"
    assert events[0].data["child_id"] == "child-1"
    assert events[0].data["child_name"] == "Lisa"
    assert events[0].data["family_id"] == FAMILY_ID
