"""Tests for the Connect RPC client."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import pytest

from custom_components.chores.api import (
    ChoresApiError,
    ChoresAuthError,
    ChoresClient,
)

from .conftest import BASE_URL, TOKEN, rpc_url


def _client(hass: HomeAssistant) -> ChoresClient:
    return ChoresClient(async_get_clientsession(hass), BASE_URL, TOKEN)


async def test_sends_connect_headers_and_camel_case(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """The request carries the bearer token and a camelCase body."""
    aioclient_mock.post(rpc_url("ListUsers"), json={"users": []})

    await _client(hass).list_users("fam-1")

    _method, _url, data, headers = aioclient_mock.mock_calls[0]
    assert data == {"familyId": "fam-1"}
    assert headers["Authorization"] == f"Bearer {TOKEN}"
    assert headers["Connect-Protocol-Version"] == "1"


@pytest.mark.parametrize("code", ["unauthenticated", "permission_denied"])
async def test_auth_errors(hass: HomeAssistant, aioclient_mock, code: str) -> None:
    """Auth-shaped Connect codes raise ChoresAuthError, which triggers reauth."""
    aioclient_mock.post(
        rpc_url("GetMyMembership"), status=401, json={"code": code, "message": "no"}
    )

    with pytest.raises(ChoresAuthError):
        await _client(hass).get_my_membership()


async def test_other_errors(hass: HomeAssistant, aioclient_mock) -> None:
    """Any other Connect code is a plain API error."""
    aioclient_mock.post(
        rpc_url("GetMyMembership"),
        status=500,
        json={"code": "internal", "message": "boom"},
    )

    with pytest.raises(ChoresApiError):
        await _client(hass).get_my_membership()


async def test_omitted_fields_decode_to_empty(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """proto3 JSON omits zero values, so an empty list arrives as no key at all."""
    aioclient_mock.post(rpc_url("ListTaskOccurrences"), json={})

    assert (
        await _client(hass).list_task_occurrences("fam-1", "2026-08-30", "2026-08-30")
        == []
    )
