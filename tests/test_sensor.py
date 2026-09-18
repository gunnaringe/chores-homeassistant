"""Tests for the Chores balance/earnings sensors."""

from __future__ import annotations

from homeassistant.const import CONF_TOKEN
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.chores.const import (
    CONF_BASE_URL,
    CONF_CURRENCY,
    CONF_FAMILY_ID,
    DOMAIN,
)

from .conftest import BASE_URL, FAMILY_ID, TOKEN, child_summary, setup_integration


async def test_summary_sensors_report_major_units(
    hass: HomeAssistant, aioclient_mock, config_entry
) -> None:
    """Money sensors divide cents down to major units."""
    await setup_integration(
        hass, aioclient_mock, config_entry, summaries=[child_summary()]
    )

    assert hass.states.get("sensor.lisa_balance").state == "30.0"
    assert hass.states.get("sensor.lisa_earned_today").state == "5.0"
    assert hass.states.get("sensor.lisa_total_earned").state == "100.0"
    assert hass.states.get("sensor.lisa_total_paid_out").state == "70.0"


async def test_missing_summary_is_unknown(
    hass: HomeAssistant, aioclient_mock, config_entry
) -> None:
    """A child with no ChildSummary row yet reports unknown, not a crash."""
    await setup_integration(hass, aioclient_mock, config_entry, summaries=[])

    assert hass.states.get("sensor.lisa_balance").state == "unknown"


async def test_last_payout_defaults_to_unknown(
    hass: HomeAssistant, aioclient_mock, config_entry
) -> None:
    """proto3 JSON omits a never-set lastPayoutAt entirely."""
    await setup_integration(
        hass, aioclient_mock, config_entry, summaries=[child_summary()]
    )

    assert hass.states.get("sensor.lisa_last_payout").state == "unknown"


async def test_last_payout_parses_timestamp(
    hass: HomeAssistant, aioclient_mock, config_entry
) -> None:
    """A set lastPayoutAt is parsed to a timestamp state."""
    await setup_integration(
        hass,
        aioclient_mock,
        config_entry,
        summaries=[child_summary(lastPayoutAt="2026-08-30T10:00:00Z")],
    )

    state = hass.states.get("sensor.lisa_last_payout")
    assert state.state == "2026-08-30T10:00:00+00:00"


async def test_monthly_earnings_read_months_by_index(
    hass: HomeAssistant, aioclient_mock, config_entry
) -> None:
    """months[0]/months[1] map to this month/last month."""
    await setup_integration(
        hass,
        aioclient_mock,
        config_entry,
        summaries=[child_summary()],
        months=[
            {"yearMonth": "2026-09", "earned": {"cents": "1000"}},
            {"yearMonth": "2026-08", "earned": {"cents": "2500"}},
        ],
    )

    assert hass.states.get("sensor.lisa_earned_this_month").state == "10.0"
    assert hass.states.get("sensor.lisa_earned_last_month").state == "25.0"


async def test_currency_option_sets_device_class_and_unit(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """Configuring a currency turns on the monetary device class and unit."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Testfamilien",
        unique_id=FAMILY_ID,
        data={CONF_BASE_URL: BASE_URL, CONF_TOKEN: TOKEN, CONF_FAMILY_ID: FAMILY_ID},
        options={CONF_CURRENCY: "NOK"},
    )
    await setup_integration(hass, aioclient_mock, entry, summaries=[child_summary()])

    state = hass.states.get("sensor.lisa_balance")
    assert state.attributes["unit_of_measurement"] == "NOK"
    assert state.attributes["device_class"] == "monetary"


async def test_no_currency_option_omits_device_class(
    hass: HomeAssistant, aioclient_mock, config_entry
) -> None:
    """Without a configured currency, sensors are plain numbers."""
    await setup_integration(
        hass, aioclient_mock, config_entry, summaries=[child_summary()]
    )

    state = hass.states.get("sensor.lisa_balance")
    assert "unit_of_measurement" not in state.attributes
    assert "device_class" not in state.attributes
