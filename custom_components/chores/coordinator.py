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
from .const import DOMAIN, LOGGER, ROLE_CHILD

type ChoresConfigEntry = ConfigEntry[ChoresCoordinator]


@dataclass(slots=True)
class ChoresData:
    """One refresh worth of state: today's children and their occurrences."""

    children: list[dict[str, Any]] = field(default_factory=list)
    occurrences_by_child: dict[str, list[dict[str, Any]]] = field(default_factory=dict)


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

        return ChoresData(children=children, occurrences_by_child=by_child)
