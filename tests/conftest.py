"""Fixtures for the Chores tests."""

from __future__ import annotations

from typing import Any

from homeassistant.const import CONF_TOKEN
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.chores.const import CONF_BASE_URL, CONF_FAMILY_ID, DOMAIN

BASE_URL = "https://chores.test"
FAMILY_ID = "fam-1"
TOKEN = "chorespat_abc"


def rpc_url(method: str) -> str:
    """Build the Connect endpoint for one RPC."""
    return f"{BASE_URL}/chores.v1.ChoresService/{method}"


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
