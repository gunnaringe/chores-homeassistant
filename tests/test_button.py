"""Tests for the Chores pay-out button."""

from __future__ import annotations

from homeassistant.components.button import DOMAIN as BUTTON_DOMAIN, SERVICE_PRESS
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant

from .conftest import rpc_url, setup_integration

ENTITY_ID = "button.lisa_pay_out_balance"


async def test_press_pays_out_full_balance(
    hass: HomeAssistant, aioclient_mock, config_entry
) -> None:
    """Pressing the button calls CreatePayout with full_payout=true."""
    await setup_integration(hass, aioclient_mock, config_entry)
    aioclient_mock.post(rpc_url("CreatePayout"), json={})

    await hass.services.async_call(
        BUTTON_DOMAIN, SERVICE_PRESS, {ATTR_ENTITY_ID: ENTITY_ID}, blocking=True
    )

    payout_calls = [
        call for call in aioclient_mock.mock_calls if "CreatePayout" in str(call[1])
    ]
    assert payout_calls
    assert payout_calls[0][2] == {
        "childId": "child-1",
        "fullPayout": True,
        "amount": {"cents": 0},
        "note": "",
    }
