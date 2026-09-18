"""Tests for the Chores services: payouts, task and user management."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.util import dt as dt_util
import pytest

from custom_components.chores.const import DOMAIN

from .conftest import child_summary, rpc_url, setup_integration, task


def _child_device_id(
    hass: HomeAssistant, config_entry, child_id: str = "child-1"
) -> str:
    device = dr.async_get(hass).async_get_device_by_identifier(
        (DOMAIN, child_id), config_entry.entry_id
    )
    assert device is not None
    return device.id


async def test_create_payout_service(
    hass: HomeAssistant, aioclient_mock, config_entry
) -> None:
    """chores.create_payout calls CreatePayout for the resolved child."""
    await setup_integration(
        hass, aioclient_mock, config_entry, summaries=[child_summary()]
    )
    aioclient_mock.post(rpc_url("CreatePayout"), json={})

    await hass.services.async_call(
        DOMAIN,
        "create_payout",
        {
            "device_id": _child_device_id(hass, config_entry),
            "full_payout": False,
            "amount_cents": 500,
            "note": "Allowance",
        },
        blocking=True,
    )

    calls = [c for c in aioclient_mock.mock_calls if "CreatePayout" in str(c[1])]
    assert calls[0][2] == {
        "childId": "child-1",
        "fullPayout": False,
        "amount": {"cents": 500},
        "note": "Allowance",
    }


async def test_create_payout_unknown_device_raises(
    hass: HomeAssistant, aioclient_mock, config_entry
) -> None:
    """An unknown device_id is a validation error, not a silent no-op."""
    await setup_integration(hass, aioclient_mock, config_entry)

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "create_payout",
            {"device_id": "not-a-real-device"},
            blocking=True,
        )


async def test_service_on_unloaded_entry_raises_validation_error(
    hass: HomeAssistant, aioclient_mock, config_entry
) -> None:
    """An unloaded entry (auth failure, server down) fails cleanly.

    entry.runtime_data is only set while the entry is loaded; reading it on
    an unloaded entry raises AttributeError unless callers check entry.state
    first.
    """
    await setup_integration(
        hass, aioclient_mock, config_entry, summaries=[child_summary()]
    )
    device_id = _child_device_id(hass, config_entry)
    await hass.config_entries.async_unload(config_entry.entry_id)

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "create_payout",
            {"device_id": device_id},
            blocking=True,
        )


async def test_create_task_service(
    hass: HomeAssistant, aioclient_mock, config_entry
) -> None:
    """chores.create_task builds the Schedule oneof from flat fields."""
    await setup_integration(hass, aioclient_mock, config_entry)
    aioclient_mock.post(rpc_url("CreateTask"), json={"task": task()})

    await hass.services.async_call(
        DOMAIN,
        "create_task",
        {
            "config_entry_id": config_entry.entry_id,
            "title": "Vaske bad",
            "children": [_child_device_id(hass, config_entry)],
            "schedule_type": "weekly",
            "days_of_week": [1, 3, 5],
            "anchor_date": "2026-09-14",
            "price_cents": 1000,
        },
        blocking=True,
    )

    calls = [c for c in aioclient_mock.mock_calls if "CreateTask" in str(c[1])]
    assert calls[0][2] == {
        "familyId": "fam-1",
        "title": "Vaske bad",
        "description": "",
        "childIds": ["child-1"],
        "classification": "TASK_CLASSIFICATION_MANDATORY",
        "price": {"cents": 1000},
        "schedule": {
            "weekly": {
                "daysOfWeek": [1, 3, 5],
                "intervalWeeks": 1,
                "anchorDate": "2026-09-14",
            }
        },
    }


async def test_create_task_weekly_anchor_defaults_to_today(
    hass: HomeAssistant, aioclient_mock, config_entry
) -> None:
    """Without an explicit anchor_date, weekly schedules anchor to today.

    Not the epoch: a later interval_weeks change should produce the parity
    the user set the task up with, not an arbitrary one from 1970.
    """
    await setup_integration(hass, aioclient_mock, config_entry)
    aioclient_mock.post(rpc_url("CreateTask"), json={"task": task()})

    await hass.services.async_call(
        DOMAIN,
        "create_task",
        {
            "config_entry_id": config_entry.entry_id,
            "title": "Vaske bad",
            "children": [_child_device_id(hass, config_entry)],
            "schedule_type": "weekly",
            "days_of_week": [1, 3, 5],
        },
        blocking=True,
    )

    calls = [c for c in aioclient_mock.mock_calls if "CreateTask" in str(c[1])]
    anchor = calls[0][2]["schedule"]["weekly"]["anchorDate"]
    assert anchor == dt_util.now().date().isoformat()


async def test_update_task_merges_unset_fields(
    hass: HomeAssistant, aioclient_mock, config_entry
) -> None:
    """Fields not passed to update_task carry the existing task's values through.

    UpdateTask is a full replace on the wire: sending only {taskId, title}
    would reset active/price/child_ids/schedule to their zero values. The
    service must merge against what ListTasks already returned.
    """
    existing = task(
        title="Ta ut søpla",
        description="Alle dunkene",
        active=True,
        childIds=["child-1"],
        classification="TASK_CLASSIFICATION_OPTIONAL",
        price=None,
        schedule={"once": {"date": "2026-09-20"}},
    )
    await setup_integration(hass, aioclient_mock, config_entry, tasks=[existing])
    aioclient_mock.post(rpc_url("UpdateTask"), json={"task": existing})

    await hass.services.async_call(
        DOMAIN,
        "update_task",
        {
            "config_entry_id": config_entry.entry_id,
            "task_id": "task-1",
            "title": "Ta ut søppel",
        },
        blocking=True,
    )

    calls = [c for c in aioclient_mock.mock_calls if "UpdateTask" in str(c[1])]
    assert calls[0][2] == {
        "taskId": "task-1",
        "title": "Ta ut søppel",
        "description": "Alle dunkene",
        "active": True,
        "childIds": ["child-1"],
        "classification": "TASK_CLASSIFICATION_OPTIONAL",
        "price": {"cents": 0},
        "schedule": {"once": {"date": "2026-09-20"}},
    }


async def test_update_task_unknown_id_raises(
    hass: HomeAssistant, aioclient_mock, config_entry
) -> None:
    """Updating a task_id the coordinator doesn't know about fails clearly."""
    await setup_integration(hass, aioclient_mock, config_entry, tasks=[])

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "update_task",
            {"config_entry_id": config_entry.entry_id, "task_id": "no-such-task"},
            blocking=True,
        )


async def test_delete_task_service(
    hass: HomeAssistant, aioclient_mock, config_entry
) -> None:
    """chores.delete_task calls DeleteTask with the given task_id."""
    await setup_integration(hass, aioclient_mock, config_entry, tasks=[task()])
    aioclient_mock.post(rpc_url("DeleteTask"), json={})

    await hass.services.async_call(
        DOMAIN,
        "delete_task",
        {"config_entry_id": config_entry.entry_id, "task_id": "task-1"},
        blocking=True,
    )

    calls = [c for c in aioclient_mock.mock_calls if "DeleteTask" in str(c[1])]
    assert calls[0][2] == {"taskId": "task-1"}


async def test_create_user_service(
    hass: HomeAssistant, aioclient_mock, config_entry
) -> None:
    """chores.create_user calls CreateUser scoped to the given family."""
    await setup_integration(hass, aioclient_mock, config_entry)
    aioclient_mock.post(rpc_url("CreateUser"), json={"user": {}})

    await hass.services.async_call(
        DOMAIN,
        "create_user",
        {
            "config_entry_id": config_entry.entry_id,
            "name": "Ola",
            "role": "USER_ROLE_CHILD",
        },
        blocking=True,
    )

    calls = [c for c in aioclient_mock.mock_calls if "CreateUser" in str(c[1])]
    assert calls[0][2] == {
        "familyId": "fam-1",
        "name": "Ola",
        "role": "USER_ROLE_CHILD",
    }


async def test_remove_child_service(
    hass: HomeAssistant, aioclient_mock, config_entry
) -> None:
    """chores.remove_child calls RemoveChild for the resolved child."""
    await setup_integration(hass, aioclient_mock, config_entry)
    aioclient_mock.post(rpc_url("RemoveChild"), json={})

    await hass.services.async_call(
        DOMAIN,
        "remove_child",
        {"device_id": _child_device_id(hass, config_entry)},
        blocking=True,
    )

    calls = [c for c in aioclient_mock.mock_calls if "RemoveChild" in str(c[1])]
    assert calls[0][2] == {"childId": "child-1"}


async def test_api_error_becomes_home_assistant_error(
    hass: HomeAssistant, aioclient_mock, config_entry
) -> None:
    """A Connect error from the API surfaces as HomeAssistantError, not a crash."""
    await setup_integration(hass, aioclient_mock, config_entry, tasks=[task()])
    aioclient_mock.post(
        rpc_url("DeleteTask"),
        json={"code": "not_found", "message": "no such task"},
        status=404,
    )

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            DOMAIN,
            "delete_task",
            {"config_entry_id": config_entry.entry_id, "task_id": "task-1"},
            blocking=True,
        )
