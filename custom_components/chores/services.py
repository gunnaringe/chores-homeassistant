"""Services for actions that don't fit an entity: task and user management.

Chores that are just "read the state" fit sensors, calendars and todo items.
These are commands with parameters (create a task with a schedule, pay out a
specific amount, add a family member) that don't map to pressing a button, so
they're services instead. `device_id` fields resolve to a child via that
child's device (see .entity / DeviceInfo(identifiers={(DOMAIN, child_id)}));
`config_entry_id` fields resolve to a family, for actions that aren't scoped
to one child.
"""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import (
    config_validation as cv,
    device_registry as dr,
    selector,
)
from homeassistant.util import dt as dt_util
import voluptuous as vol

from .api import ChoresError
from .const import (
    CLASSIFICATION_MANDATORY,
    CLASSIFICATION_OPTIONAL,
    DOMAIN,
    ROLE_CHILD,
    ROLE_PARENT,
)
from .coordinator import ChoresCoordinator, ChoresRuntimeData
from .util import money_cents

SERVICE_CREATE_PAYOUT = "create_payout"
SERVICE_CREATE_TASK = "create_task"
SERVICE_UPDATE_TASK = "update_task"
SERVICE_DELETE_TASK = "delete_task"
SERVICE_CREATE_USER = "create_user"
SERVICE_REMOVE_CHILD = "remove_child"

_DEVICE_SELECTOR = selector.DeviceSelector(
    selector.DeviceSelectorConfig(integration=DOMAIN)
)
_DEVICES_SELECTOR = selector.DeviceSelector(
    selector.DeviceSelectorConfig(integration=DOMAIN, multiple=True)
)
_CONFIG_ENTRY_SELECTOR = selector.ConfigEntrySelector(
    selector.ConfigEntrySelectorConfig(integration=DOMAIN)
)

_SCHEDULE_FIELDS = {
    vol.Optional("schedule_type"): vol.In(["once", "weekly", "cron"]),
    vol.Optional("date"): cv.string,
    vol.Optional("days_of_week"): [vol.All(vol.Coerce(int), vol.Range(min=0, max=6))],
    vol.Optional("interval_weeks"): vol.All(vol.Coerce(int), vol.Range(min=1)),
    vol.Optional("anchor_date"): cv.string,
    vol.Optional("cron_expression"): cv.string,
}

_TASK_FIELDS = {
    vol.Optional("title"): cv.string,
    vol.Optional("description"): cv.string,
    vol.Optional("children"): _DEVICES_SELECTOR,
    vol.Optional("classification"): vol.In(
        [CLASSIFICATION_MANDATORY, CLASSIFICATION_OPTIONAL]
    ),
    vol.Optional("price_cents"): vol.Coerce(int),
    **_SCHEDULE_FIELDS,
}

CREATE_PAYOUT_SCHEMA = vol.Schema(
    {
        vol.Required("device_id"): _DEVICE_SELECTOR,
        vol.Optional("full_payout", default=True): cv.boolean,
        vol.Optional("amount_cents", default=0): vol.Coerce(int),
        vol.Optional("note", default=""): cv.string,
    }
)

CREATE_TASK_SCHEMA = vol.Schema(
    {
        vol.Required("config_entry_id"): _CONFIG_ENTRY_SELECTOR,
        vol.Required("title"): cv.string,
        vol.Optional("description", default=""): cv.string,
        vol.Required("children"): _DEVICES_SELECTOR,
        vol.Optional("classification", default=CLASSIFICATION_MANDATORY): vol.In(
            [CLASSIFICATION_MANDATORY, CLASSIFICATION_OPTIONAL]
        ),
        vol.Optional("price_cents", default=0): vol.Coerce(int),
        vol.Required("schedule_type"): vol.In(["once", "weekly", "cron"]),
        vol.Optional("date"): cv.string,
        vol.Optional("days_of_week"): [
            vol.All(vol.Coerce(int), vol.Range(min=0, max=6))
        ],
        vol.Optional("interval_weeks"): vol.All(vol.Coerce(int), vol.Range(min=1)),
        vol.Optional("anchor_date"): cv.string,
        vol.Optional("cron_expression"): cv.string,
    }
)

UPDATE_TASK_SCHEMA = vol.Schema(
    {
        vol.Required("config_entry_id"): _CONFIG_ENTRY_SELECTOR,
        vol.Required("task_id"): cv.string,
        vol.Optional("active"): cv.boolean,
        **_TASK_FIELDS,
    }
)

DELETE_TASK_SCHEMA = vol.Schema(
    {
        vol.Required("config_entry_id"): _CONFIG_ENTRY_SELECTOR,
        vol.Required("task_id"): cv.string,
    }
)

CREATE_USER_SCHEMA = vol.Schema(
    {
        vol.Required("config_entry_id"): _CONFIG_ENTRY_SELECTOR,
        vol.Required("name"): cv.string,
        vol.Required("role"): vol.In([ROLE_PARENT, ROLE_CHILD]),
    }
)

REMOVE_CHILD_SCHEMA = vol.Schema({vol.Required("device_id"): _DEVICE_SELECTOR})


def _runtime_for_entry(hass: HomeAssistant, config_entry_id: str) -> ChoresRuntimeData:
    """Resolve a config_entry_id field to its runtime data."""
    entry = hass.config_entries.async_get_entry(config_entry_id)
    if entry is None or entry.domain != DOMAIN:
        raise ServiceValidationError(f"Unknown Chores config entry {config_entry_id}")
    if entry.state is not ConfigEntryState.LOADED:
        # runtime_data is only set while the entry is loaded — an entry mid
        # reauth (ConfigEntryAuthFailed) or retrying setup has none, and
        # reading .runtime_data on it would raise AttributeError instead of
        # a clean service error.
        raise ServiceValidationError(
            f"Chores config entry {config_entry_id} is not loaded"
        )
    return entry.runtime_data


def _coordinator_for_device(
    hass: HomeAssistant, device_id: str
) -> tuple[str, ChoresCoordinator]:
    """Resolve a device_id field to the child_id it represents and its coordinator."""
    device = dr.async_get(hass).async_get(device_id)
    if device is None:
        raise ServiceValidationError(f"Unknown device {device_id}")

    child_id = next(
        (identifier[1] for identifier in device.identifiers if identifier[0] == DOMAIN),
        None,
    )
    entry_id = device.primary_config_entry or next(iter(device.config_entries), None)
    entry = hass.config_entries.async_get_entry(entry_id) if entry_id else None
    if child_id is None or entry is None or entry.domain != DOMAIN:
        raise ServiceValidationError(f"{device_id} is not a Chores child device")
    if entry.state is not ConfigEntryState.LOADED:
        raise ServiceValidationError(
            f"Chores config entry for {device_id} is not loaded"
        )

    return child_id, entry.runtime_data.main


def _child_ids_for_devices(hass: HomeAssistant, device_ids: list[str]) -> list[str]:
    """Resolve device_id fields (a task's `children`) to child ids."""
    return [_coordinator_for_device(hass, device_id)[0] for device_id in device_ids]


def _build_schedule(data: dict[str, Any]) -> dict[str, Any]:
    """Build a Schedule oneof from the service call's flat fields."""
    schedule_type = data["schedule_type"]
    if schedule_type == "once":
        if not data.get("date"):
            raise ServiceValidationError("schedule_type 'once' requires 'date'")
        return {"once": {"date": data["date"]}}
    if schedule_type == "weekly":
        if not data.get("days_of_week"):
            raise ServiceValidationError(
                "schedule_type 'weekly' requires 'days_of_week'"
            )
        return {
            "weekly": {
                "daysOfWeek": data["days_of_week"],
                "intervalWeeks": data.get("interval_weeks", 1),
                "anchorDate": data.get("anchor_date")
                or data.get("date")
                or dt_util.now().date().isoformat(),
            }
        }
    if not data.get("cron_expression"):
        raise ServiceValidationError("schedule_type 'cron' requires 'cron_expression'")
    return {"cron": {"expression": data["cron_expression"]}}


def _existing_task(runtime: ChoresRuntimeData, task_id: str) -> dict[str, Any]:
    """Look up a task the coordinator already knows about, for UpdateTask's merge."""
    task = next((t for t in runtime.main.data.tasks if t.get("id") == task_id), None)
    if task is None:
        raise ServiceValidationError(f"No task with id {task_id}")
    return task


async def _handle_create_payout(hass: HomeAssistant, call: ServiceCall) -> None:
    child_id, coordinator = _coordinator_for_device(hass, call.data["device_id"])
    try:
        await coordinator.client.create_payout(
            child_id,
            call.data["full_payout"],
            call.data["amount_cents"],
            call.data["note"],
        )
    except ChoresError as err:
        raise HomeAssistantError(f"Could not create payout: {err}") from err
    await coordinator.async_request_refresh()


async def _handle_create_task(hass: HomeAssistant, call: ServiceCall) -> None:
    runtime = _runtime_for_entry(hass, call.data["config_entry_id"])
    child_ids = _child_ids_for_devices(hass, call.data["children"])
    try:
        await runtime.main.client.create_task(
            runtime.main.family_id,
            call.data["title"],
            call.data["description"],
            child_ids,
            call.data["classification"],
            call.data["price_cents"],
            _build_schedule(call.data),
        )
    except ChoresError as err:
        raise HomeAssistantError(f"Could not create task: {err}") from err
    await runtime.main.async_request_refresh()


async def _handle_update_task(hass: HomeAssistant, call: ServiceCall) -> None:
    runtime = _runtime_for_entry(hass, call.data["config_entry_id"])
    task_id = call.data["task_id"]
    existing = _existing_task(runtime, task_id)

    child_ids = (
        _child_ids_for_devices(hass, call.data["children"])
        if "children" in call.data
        else list(existing.get("childIds", []))
    )
    schedule = (
        _build_schedule(call.data)
        if "schedule_type" in call.data
        else existing.get("schedule", {})
    )

    try:
        await runtime.main.client.update_task(
            task_id,
            call.data.get("title", existing.get("title", "")),
            call.data.get("description", existing.get("description", "")),
            call.data.get("active", existing.get("active", True)),
            child_ids,
            call.data.get(
                "classification",
                existing.get("classification", CLASSIFICATION_MANDATORY),
            ),
            call.data.get("price_cents", money_cents(existing.get("price"))),
            schedule,
            icon=existing.get("icon"),
        )
    except ChoresError as err:
        raise HomeAssistantError(f"Could not update task: {err}") from err
    await runtime.main.async_request_refresh()


async def _handle_delete_task(hass: HomeAssistant, call: ServiceCall) -> None:
    runtime = _runtime_for_entry(hass, call.data["config_entry_id"])
    try:
        await runtime.main.client.delete_task(call.data["task_id"])
    except ChoresError as err:
        raise HomeAssistantError(f"Could not delete task: {err}") from err
    await runtime.main.async_request_refresh()


async def _handle_create_user(hass: HomeAssistant, call: ServiceCall) -> None:
    runtime = _runtime_for_entry(hass, call.data["config_entry_id"])
    try:
        await runtime.main.client.create_user(
            runtime.main.family_id, call.data["name"], call.data["role"]
        )
    except ChoresError as err:
        raise HomeAssistantError(f"Could not create user: {err}") from err
    await runtime.main.async_request_refresh()


async def _handle_remove_child(hass: HomeAssistant, call: ServiceCall) -> None:
    child_id, coordinator = _coordinator_for_device(hass, call.data["device_id"])
    try:
        await coordinator.client.remove_child(child_id)
    except ChoresError as err:
        raise HomeAssistantError(f"Could not remove child: {err}") from err
    await coordinator.async_request_refresh()


async def async_setup_services(hass: HomeAssistant) -> None:
    """Register Chores services, once per Home Assistant instance.

    Services are global, not per-config-entry, but async_setup_entry runs
    once per family (config entry) — guard against re-registering on the
    second and subsequent families.
    """
    if hass.services.has_service(DOMAIN, SERVICE_CREATE_PAYOUT):
        return

    async def create_payout(call: ServiceCall) -> None:
        await _handle_create_payout(hass, call)

    async def create_task(call: ServiceCall) -> None:
        await _handle_create_task(hass, call)

    async def update_task(call: ServiceCall) -> None:
        await _handle_update_task(hass, call)

    async def delete_task(call: ServiceCall) -> None:
        await _handle_delete_task(hass, call)

    async def create_user(call: ServiceCall) -> None:
        await _handle_create_user(hass, call)

    async def remove_child(call: ServiceCall) -> None:
        await _handle_remove_child(hass, call)

    hass.services.async_register(
        DOMAIN, SERVICE_CREATE_PAYOUT, create_payout, schema=CREATE_PAYOUT_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_CREATE_TASK, create_task, schema=CREATE_TASK_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_UPDATE_TASK, update_task, schema=UPDATE_TASK_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_DELETE_TASK, delete_task, schema=DELETE_TASK_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_CREATE_USER, create_user, schema=CREATE_USER_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_REMOVE_CHILD, remove_child, schema=REMOVE_CHILD_SCHEMA
    )
