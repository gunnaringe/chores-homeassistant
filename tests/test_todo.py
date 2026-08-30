"""Tests for the Chores todo lists."""

from __future__ import annotations

from typing import Any

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
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import FAMILY_ID, rpc_url

ENTITY_ID = "todo.lisa"


def occurrence(**overrides: Any) -> dict[str, Any]:
    """Build a task occurrence as proto3 JSON would render it."""
    return {
        "familyId": FAMILY_ID,
        "taskId": "task-1",
        "childId": "child-1",
        "dueDate": dt_util.now().date().isoformat(),
        "title": "Ta ut søpla",
        "description": "Alle dunkene",
        "classification": "TASK_CLASSIFICATION_MANDATORY",
        "amount": {"cents": "1500"},
        "childName": "Lisa",
    } | overrides


async def setup_integration(
    hass: HomeAssistant,
    aioclient_mock,
    config_entry: MockConfigEntry,
    users_response: dict[str, Any],
    occurrences: list[dict[str, Any]],
) -> None:
    """Set up the entry with a fixed set of occurrences."""
    config_entry.add_to_hass(hass)
    aioclient_mock.post(rpc_url("ListUsers"), json=users_response)
    aioclient_mock.post(
        rpc_url("ListTaskOccurrences"), json={"occurrences": occurrences}
    )
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()


async def test_lists_todays_chores(
    hass: HomeAssistant, aioclient_mock, config_entry, users_response
) -> None:
    """Each child gets a list holding today's chores."""
    await setup_integration(
        hass, aioclient_mock, config_entry, users_response, [occurrence()]
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
        users_response,
        [occurrence(completedAt="2026-08-30T10:00:00Z")],
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
        users_response,
        [
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
        hass, aioclient_mock, config_entry, users_response, [occurrence()]
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
        users_response,
        [occurrence(completedAt="2026-08-30T10:00:00Z")],
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
        hass, aioclient_mock, config_entry, users_response, [occurrence()]
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
