"""Tests for the Chores config flow."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_TOKEN
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.chores.const import CONF_BASE_URL, CONF_FAMILY_ID, DOMAIN

from .conftest import BASE_URL, FAMILY_ID, TOKEN, rpc_url

USER_INPUT = {CONF_BASE_URL: BASE_URL, CONF_TOKEN: TOKEN}


async def test_single_family_creates_entry(
    hass: HomeAssistant, aioclient_mock, membership_response: dict[str, Any]
) -> None:
    """One membership skips the family step."""
    aioclient_mock.post(rpc_url("GetMyMembership"), json=membership_response)
    aioclient_mock.post(rpc_url("ListUsers"), json={"users": []})
    aioclient_mock.post(rpc_url("ListTaskOccurrences"), json={})

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Testfamilien"
    assert result["data"][CONF_FAMILY_ID] == FAMILY_ID


async def test_multiple_families_asks_which(
    hass: HomeAssistant, aioclient_mock, membership_response: dict[str, Any]
) -> None:
    """A token bound to two households gets a picker."""
    membership_response["memberships"].append(
        {
            "user": {"id": "parent-2", "name": "Parent", "role": "USER_ROLE_PARENT"},
            "family": {"id": "fam-2", "name": "Hytta"},
        }
    )
    aioclient_mock.post(rpc_url("GetMyMembership"), json=membership_response)
    aioclient_mock.post(rpc_url("ListUsers"), json={"users": []})
    aioclient_mock.post(rpc_url("ListTaskOccurrences"), json={})

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "family"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_FAMILY_ID: "fam-2"}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Hytta"


async def test_invalid_auth(hass: HomeAssistant, aioclient_mock) -> None:
    """A rejected token is reported on the form, not raised."""
    aioclient_mock.post(
        rpc_url("GetMyMembership"),
        status=401,
        json={"code": "unauthenticated", "message": "no"},
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_cannot_connect(hass: HomeAssistant, aioclient_mock) -> None:
    """An unreachable server is reported on the form."""
    aioclient_mock.post(
        rpc_url("GetMyMembership"), status=500, json={"code": "internal"}
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_unbound_token_aborts(hass: HomeAssistant, aioclient_mock) -> None:
    """A login that has not joined a family yet has nothing to configure."""
    aioclient_mock.post(rpc_url("GetMyMembership"), json={"bound": False})

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_already_configured(
    hass: HomeAssistant,
    aioclient_mock,
    membership_response: dict[str, Any],
    config_entry: MockConfigEntry,
) -> None:
    """The same family cannot be added twice."""
    config_entry.add_to_hass(hass)
    aioclient_mock.post(rpc_url("GetMyMembership"), json=membership_response)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth_updates_token(
    hass: HomeAssistant,
    aioclient_mock,
    membership_response: dict[str, Any],
    config_entry: MockConfigEntry,
) -> None:
    """Reauth swaps in a new token and keeps the entry."""
    config_entry.add_to_hass(hass)
    aioclient_mock.post(rpc_url("GetMyMembership"), json=membership_response)
    aioclient_mock.post(rpc_url("ListUsers"), json={"users": []})
    aioclient_mock.post(rpc_url("ListTaskOccurrences"), json={})

    result = await config_entry.start_reauth_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_TOKEN: "chorespat_new"}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert config_entry.data[CONF_TOKEN] == "chorespat_new"
