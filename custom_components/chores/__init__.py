"""The Chores integration."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.const import CONF_TOKEN
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_change

from .api import ChoresClient
from .const import (
    CONF_BASE_URL,
    CONF_FAMILY_ID,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    PLATFORMS,
)
from .coordinator import (
    ChoresConfigEntry,
    ChoresCoordinator,
    ChoresMonthlyEarningsCoordinator,
    ChoresRuntimeData,
)
from .services import async_setup_services


async def async_setup_entry(hass: HomeAssistant, entry: ChoresConfigEntry) -> bool:
    """Set up Chores from a config entry."""
    client = ChoresClient(
        async_get_clientsession(hass),
        entry.data[CONF_BASE_URL],
        entry.data[CONF_TOKEN],
    )

    seconds = entry.options.get(CONF_SCAN_INTERVAL)
    interval = timedelta(seconds=seconds) if seconds else DEFAULT_SCAN_INTERVAL

    coordinator = ChoresCoordinator(
        hass, entry, client, entry.data[CONF_FAMILY_ID], interval
    )
    await coordinator.async_config_entry_first_refresh()

    monthly_earnings = ChoresMonthlyEarningsCoordinator(
        hass, entry, client, coordinator
    )
    await monthly_earnings.async_config_entry_first_refresh()

    entry.runtime_data = ChoresRuntimeData(
        main=coordinator, monthly_earnings=monthly_earnings
    )

    await async_setup_services(hass)

    @callback
    def _midnight_refresh(_now) -> None:
        """Roll the list over at the local day boundary.

        A five-minute poll would otherwise leave yesterday's chores on screen
        for up to five minutes into the new day.
        """
        entry.async_create_background_task(
            hass, coordinator.async_refresh(), "chores_midnight_refresh"
        )

    entry.async_on_unload(
        async_track_time_change(hass, _midnight_refresh, hour=0, minute=0, second=5)
    )
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ChoresConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_listener(hass: HomeAssistant, entry: ChoresConfigEntry) -> None:
    """Reload the entry when its options change."""
    await hass.config_entries.async_reload(entry.entry_id)
