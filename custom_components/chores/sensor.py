"""Sensor entities for the Chores integration: balance and earnings.

Two kinds, both per child:

- Summary sensors read straight from the 5-minute coordinator's
  ChildSummary (balance, earned today/this week/last 7 days, totals,
  last payout time).
- Monthly earnings sensors read from the separate, slower
  ChoresMonthlyEarningsCoordinator (see coordinator.py for why it's split
  out) — "this month" and "last month" are months[0]/months[1], which the
  API guarantees are always present.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import CONF_CURRENCY, DOMAIN
from .coordinator import (
    ChoresConfigEntry,
    ChoresCoordinator,
    ChoresMonthlyEarningsCoordinator,
)
from .entity import async_add_per_child_entities
from .util import money_cents


@dataclass(frozen=True, kw_only=True)
class ChoresMoneyEntityDescription(SensorEntityDescription):
    """Describes a sensor that reads one Money field off a ChildSummary."""

    value_fn: Callable[[dict[str, Any]], dict[str, Any] | None]


SUMMARY_SENSORS: tuple[ChoresMoneyEntityDescription, ...] = (
    ChoresMoneyEntityDescription(
        key="balance",
        translation_key="balance",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda summary: summary.get("balance"),
    ),
    ChoresMoneyEntityDescription(
        key="earned_today",
        translation_key="earned_today",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda summary: summary.get("earnedToday"),
    ),
    ChoresMoneyEntityDescription(
        key="earned_this_week",
        translation_key="earned_this_week",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda summary: summary.get("earnedThisWeek"),
    ),
    ChoresMoneyEntityDescription(
        key="earned_last_7_days",
        translation_key="earned_last_7_days",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda summary: summary.get("earnedLast7Days"),
    ),
    ChoresMoneyEntityDescription(
        key="total_earned",
        translation_key="total_earned",
        # Not TOTAL_INCREASING: retention purges compact and delete aged-out
        # occurrence rows (see the Task proto's retention comments), and
        # RemoveChild cascades a child's history away entirely, so this
        # value can drop. A monotonic meter that decreases gets read by HA's
        # statistics engine as a meter reset, which corrupts long-term
        # stats — MEASUREMENT has no such assumption.
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda summary: summary.get("totalEarned"),
    ),
    ChoresMoneyEntityDescription(
        key="total_paid_out",
        translation_key="total_paid_out",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda summary: summary.get("totalPaidOut"),
    ),
)

MONTHLY_SENSORS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="earned_this_month",
        translation_key="earned_this_month",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="earned_last_month",
        translation_key="earned_last_month",
        state_class=SensorStateClass.MEASUREMENT,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ChoresConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up balance/earnings sensors for each child in the family."""
    runtime = entry.runtime_data
    currency = entry.options.get(CONF_CURRENCY) or None

    def _make_entities(child: dict[str, Any]) -> list[SensorEntity]:
        entities: list[SensorEntity] = [
            ChoresSummarySensor(runtime.main, child, description, currency)
            for description in SUMMARY_SENSORS
        ]
        entities.append(ChoresLastPayoutSensor(runtime.main, child))
        entities.extend(
            ChoresMonthlyEarningsSensor(
                runtime.main,
                runtime.monthly_earnings,
                child,
                description,
                index,
                currency,
            )
            for index, description in enumerate(MONTHLY_SENSORS)
        )
        return entities

    unsub = async_add_per_child_entities(
        runtime.main, async_add_entities, _make_entities
    )
    entry.async_on_unload(unsub)


class _ChoresChildSensor(CoordinatorEntity[ChoresCoordinator], SensorEntity):
    """Common device wiring for a per-child sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ChoresCoordinator,
        child: dict[str, Any],
        description: SensorEntityDescription,
        unique_suffix: str,
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._child_id = child["id"]
        self._attr_unique_id = (
            f"{coordinator.family_id}_{self._child_id}_{unique_suffix}"
        )
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._child_id)},
            name=child.get("name") or "Child",
            manufacturer="Chores",
            model="Child",
            entry_type=DeviceEntryType.SERVICE,
        )


def _money_value(currency: str | None, money: dict[str, Any] | None) -> float:
    """Convert a Money field to major units, e.g. cents=1500 -> 15.0."""
    return money_cents(money) / 100


class ChoresSummarySensor(_ChoresChildSensor):
    """One field off a child's ChildSummary (balance, earnings, totals)."""

    entity_description: ChoresMoneyEntityDescription

    def __init__(
        self,
        coordinator: ChoresCoordinator,
        child: dict[str, Any],
        description: ChoresMoneyEntityDescription,
        currency: str | None,
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, child, description, description.key)
        self._currency = currency
        if currency:
            self._attr_device_class = SensorDeviceClass.MONETARY
            self._attr_native_unit_of_measurement = currency
            self._attr_suggested_display_precision = 2

    @property
    def native_value(self) -> float | None:
        """Return the current value of this summary field."""
        summary = self.coordinator.data.summaries_by_child.get(self._child_id)
        if summary is None:
            return None
        return _money_value(self._currency, self.entity_description.value_fn(summary))


class ChoresLastPayoutSensor(_ChoresChildSensor):
    """When the child was last paid out, or unknown if never."""

    def __init__(self, coordinator: ChoresCoordinator, child: dict[str, Any]) -> None:
        """Initialise the sensor."""
        description = SensorEntityDescription(
            key="last_payout_at",
            translation_key="last_payout_at",
            device_class=SensorDeviceClass.TIMESTAMP,
        )
        super().__init__(coordinator, child, description, "last_payout_at")

    @property
    def native_value(self) -> datetime | None:
        """Return the last payout's timestamp, parsed from RFC3339."""
        summary = self.coordinator.data.summaries_by_child.get(self._child_id)
        if summary is None:
            return None
        raw = summary.get("lastPayoutAt")
        if not raw:
            return None
        return dt_util.parse_datetime(raw)


class ChoresMonthlyEarningsSensor(
    CoordinatorEntity[ChoresMonthlyEarningsCoordinator], SensorEntity
):
    """One month's completed earnings (this month or last), by index."""

    _attr_has_entity_name = True

    def __init__(
        self,
        main: ChoresCoordinator,
        monthly: ChoresMonthlyEarningsCoordinator,
        child: dict[str, Any],
        description: SensorEntityDescription,
        index: int,
        currency: str | None,
    ) -> None:
        """Initialise the sensor."""
        super().__init__(monthly)
        self.entity_description = description
        self._child_id = child["id"]
        self._index = index
        self._currency = currency
        self._attr_unique_id = f"{main.family_id}_{self._child_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._child_id)},
            name=child.get("name") or "Child",
            manufacturer="Chores",
            model="Child",
            entry_type=DeviceEntryType.SERVICE,
        )
        if currency:
            self._attr_device_class = SensorDeviceClass.MONETARY
            self._attr_native_unit_of_measurement = currency
            self._attr_suggested_display_precision = 2

    @property
    def native_value(self) -> float | None:
        """Return this month's (or last month's) earned total."""
        months = self.coordinator.data.get(self._child_id, [])
        if len(months) <= self._index:
            return None
        return _money_value(self._currency, months[self._index].get("earned"))
