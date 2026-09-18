"""Button entity for the Chores integration: pay out a child's balance."""

from __future__ import annotations

from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import ChoresError
from .const import DOMAIN
from .coordinator import ChoresConfigEntry, ChoresCoordinator
from .entity import async_add_per_child_entities


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ChoresConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up a pay-out button for each child in the family."""
    coordinator = entry.runtime_data.main
    unsub = async_add_per_child_entities(
        coordinator,
        async_add_entities,
        lambda child: [ChoresPayoutButton(coordinator, child)],
    )
    entry.async_on_unload(unsub)


class ChoresPayoutButton(CoordinatorEntity[ChoresCoordinator], ButtonEntity):
    """Pay out a child's full outstanding balance.

    Only the full-balance payout is exposed as a button — a specific amount
    or note needs the `chores.create_payout` service instead, since a button
    press carries no parameters.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "pay_out_balance"

    def __init__(self, coordinator: ChoresCoordinator, child: dict[str, Any]) -> None:
        """Initialise the button."""
        super().__init__(coordinator)
        self._child_id = child["id"]
        self._attr_unique_id = f"{coordinator.family_id}_{self._child_id}_pay_out"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._child_id)},
            name=child.get("name") or "Child",
            manufacturer="Chores",
            model="Child",
            entry_type=DeviceEntryType.SERVICE,
        )

    async def async_press(self) -> None:
        """Pay out this child's full balance."""
        try:
            await self.coordinator.client.create_payout(self._child_id, True, 0, "")
        except ChoresError as err:
            raise HomeAssistantError(f"Could not pay out balance: {err}") from err
        await self.coordinator.async_request_refresh()
