"""Data coordinator for the Chores integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import ChoresApiError, ChoresAuthError, ChoresClient
from .const import DEFAULT_MONTHLY_EARNINGS_INTERVAL, DOMAIN, LOGGER, ROLE_CHILD

type ChoresConfigEntry = ConfigEntry[ChoresRuntimeData]


@dataclass(slots=True)
class ChoresData:
    """One refresh worth of state: today's children and their occurrences."""

    children: list[dict[str, Any]] = field(default_factory=list)
    occurrences_by_child: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    # Task definitions (not occurrences) — needed to merge UpdateTask's
    # full-replace payload against the fields a caller didn't ask to change,
    # and by anything that needs to resolve a task_id to its current title.
    tasks: list[dict[str, Any]] = field(default_factory=list)
    summaries_by_child: dict[str, dict[str, Any]] = field(default_factory=dict)


class ChoresCoordinator(DataUpdateCoordinator[ChoresData]):
    """Fetch today's task occurrences for every child in the family."""

    config_entry: ChoresConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ChoresConfigEntry,
        client: ChoresClient,
        family_id: str,
        update_interval: timedelta,
    ) -> None:
        """Initialise the coordinator."""
        super().__init__(
            hass,
            LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=update_interval,
        )
        self.client = client
        self.family_id = family_id

    async def _async_update_data(self) -> ChoresData:
        """Fetch children and the occurrences due today.

        `today` is resolved fresh on every refresh, in Home Assistant's
        configured timezone, so the list follows the local day rather than the
        day the integration happened to start on.
        """
        today = dt_util.now().date().isoformat()

        try:
            users = await self.client.list_users(self.family_id)
            occurrences = await self.client.list_task_occurrences(
                self.family_id, today, today
            )
            tasks = await self.client.list_tasks(self.family_id)
            summaries = await self.client.list_child_summaries(self.family_id)
        except ChoresAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except ChoresApiError as err:
            raise UpdateFailed(str(err)) from err

        children = [user for user in users if user.get("role") == ROLE_CHILD]

        by_child: dict[str, list[dict[str, Any]]] = {
            child["id"]: [] for child in children
        }
        for occurrence in occurrences:
            child_id = occurrence.get("childId")
            if child_id in by_child:
                by_child[child_id].append(occurrence)

        summaries_by_child = {
            summary["child"]["id"]: summary
            for summary in summaries
            if summary.get("child")
        }

        return ChoresData(
            children=children,
            occurrences_by_child=by_child,
            tasks=tasks,
            summaries_by_child=summaries_by_child,
        )


class ChoresMonthlyEarningsCoordinator(
    DataUpdateCoordinator[dict[str, list[dict[str, Any]]]]
):
    """Fetch each child's monthly earnings history.

    Split from ChoresCoordinator because ListMonthlyEarnings is one RPC per
    child, for data (completed earnings by calendar month) that changes at
    most once a day. Folding it into the 5-minute coordinator would multiply
    that loop's request count by the number of children for no benefit.
    """

    config_entry: ChoresConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ChoresConfigEntry,
        client: ChoresClient,
        main: ChoresCoordinator,
        update_interval: timedelta = DEFAULT_MONTHLY_EARNINGS_INTERVAL,
    ) -> None:
        """Initialise the coordinator."""
        super().__init__(
            hass,
            LOGGER,
            name=f"{DOMAIN}_monthly_earnings",
            config_entry=entry,
            update_interval=update_interval,
        )
        self.client = client
        self._main = main

    async def _async_update_data(self) -> dict[str, list[dict[str, Any]]]:
        """Fetch monthly earnings for every child the main coordinator knows about."""
        result: dict[str, list[dict[str, Any]]] = {}
        try:
            for child in self._main.data.children:
                result[child["id"]] = await self.client.list_monthly_earnings(
                    child["id"]
                )
        except ChoresAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except ChoresApiError as err:
            raise UpdateFailed(str(err)) from err
        return result


@dataclass(slots=True)
class ChoresRuntimeData:
    """Everything a config entry's platforms need: both coordinators."""

    main: ChoresCoordinator
    monthly_earnings: ChoresMonthlyEarningsCoordinator
