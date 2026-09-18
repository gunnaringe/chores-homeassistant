"""Fixtures for the Chores tests."""

from __future__ import annotations

from typing import Any

from homeassistant.const import CONF_TOKEN
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.chores.const import CONF_BASE_URL, CONF_FAMILY_ID, DOMAIN

BASE_URL = "https://chores.test"
FAMILY_ID = "fam-1"
TOKEN = "chorespat_abc"


def rpc_url(method: str) -> str:
    """Build the Connect endpoint for one RPC."""
    return f"{BASE_URL}/chores.v1.ChoresService/{method}"


def occurrence(**overrides: Any) -> dict[str, Any]:
    """Build a task occurrence as proto3 JSON would render it."""
    from homeassistant.util import dt as dt_util

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


def task(**overrides: Any) -> dict[str, Any]:
    """Build a task definition as proto3 JSON would render it."""
    return {
        "id": "task-1",
        "familyId": FAMILY_ID,
        "title": "Ta ut søpla",
        "description": "Alle dunkene",
        "active": True,
        "childIds": ["child-1"],
        "classification": "TASK_CLASSIFICATION_MANDATORY",
        "price": {"cents": "1500"},
        "schedule": {"weekly": {"daysOfWeek": [1, 3, 5], "intervalWeeks": 1}},
    } | overrides


def child_summary(**overrides: Any) -> dict[str, Any]:
    """Build a ChildSummary as proto3 JSON would render it."""
    return {
        "child": {"id": "child-1", "name": "Lisa", "role": "USER_ROLE_CHILD"},
        "balance": {"cents": "3000"},
        "earnedToday": {"cents": "500"},
        "earnedThisWeek": {"cents": "1500"},
        "earnedLast7Days": {"cents": "2000"},
        "totalEarned": {"cents": "10000"},
        "totalPaidOut": {"cents": "7000"},
    } | overrides


def monthly_earnings(**overrides: Any) -> list[dict[str, Any]]:
    """Build a ListMonthlyEarnings months list for one child."""
    default = [
        {"yearMonth": "2026-09", "earned": {"cents": "1500"}},
        {"yearMonth": "2026-08", "earned": {"cents": "4200"}},
    ]
    return overrides.get("months", default)


async def setup_integration(
    hass: HomeAssistant,
    aioclient_mock,
    config_entry: MockConfigEntry,
    *,
    users: dict[str, Any] | None = None,
    occurrences: list[dict[str, Any]] | None = None,
    tasks: list[dict[str, Any]] | None = None,
    summaries: list[dict[str, Any]] | None = None,
    months: list[dict[str, Any]] | None = None,
) -> None:
    """Set up the entry, mocking every RPC the coordinators make on refresh."""
    config_entry.add_to_hass(hass)
    aioclient_mock.post(
        rpc_url("ListUsers"),
        json=users
        if users is not None
        else {
            "users": [
                {"id": "parent-1", "name": "Parent", "role": "USER_ROLE_PARENT"},
                {"id": "child-1", "name": "Lisa", "role": "USER_ROLE_CHILD"},
            ]
        },
    )
    aioclient_mock.post(
        rpc_url("ListTaskOccurrences"),
        json={"occurrences": occurrences if occurrences is not None else []},
    )
    aioclient_mock.post(
        rpc_url("ListTasks"), json={"tasks": tasks if tasks is not None else []}
    )
    aioclient_mock.post(
        rpc_url("ListChildSummaries"),
        json={"summaries": summaries if summaries is not None else []},
    )
    aioclient_mock.post(
        rpc_url("ListMonthlyEarnings"),
        json={"months": months if months is not None else monthly_earnings()},
    )
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Load custom integrations in every test."""
    return


@pytest.fixture
def membership_response() -> dict[str, Any]:
    """A token bound to a single family."""
    return {
        "bound": True,
        "memberships": [
            {
                "user": {
                    "id": "parent-1",
                    "name": "Parent",
                    "role": "USER_ROLE_PARENT",
                },
                "family": {"id": FAMILY_ID, "name": "Testfamilien"},
            }
        ],
    }


@pytest.fixture
def users_response() -> dict[str, Any]:
    """One parent and one child."""
    return {
        "users": [
            {"id": "parent-1", "name": "Parent", "role": "USER_ROLE_PARENT"},
            {"id": "child-1", "name": "Lisa", "role": "USER_ROLE_CHILD"},
        ]
    }


@pytest.fixture
def config_entry() -> MockConfigEntry:
    """A configured entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Testfamilien",
        unique_id=FAMILY_ID,
        data={
            CONF_BASE_URL: BASE_URL,
            CONF_TOKEN: TOKEN,
            CONF_FAMILY_ID: FAMILY_ID,
        },
    )
