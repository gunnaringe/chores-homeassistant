# Architecture

## Overview

The Chores Home Assistant integration is a thin adapter between Home Assistant's entity model and the [Chores Connect API](https://buf.build/apphub/chores). It speaks plain HTTP JSON, carries no external runtime dependencies, and uses Home Assistant's standard patterns (DataUpdateCoordinator, ConfigEntry, async).

## Why no SDK?

The Chores Connect SDK exists (`apphub-chores-connectrpc-python`) but only on buf's custom index, not PyPI. Home Assistant's dependency resolver cannot reach custom indexes, so a HACS user installing this integration would fail at setup.

Vendoring the generated code would add protobuf as a runtime requirement, which HA already pins for other integrations. A version conflict there breaks unrelated integrations on the user's system.

Instead, we hand-roll the five RPC calls we need. The cost is ~200 lines of wire-format handling in `api.py`. The benefit is `manifest.json:requirements = []`, which means this integration never conflicts with anything else.

## Data model

### `ChoresRuntimeData` and the two coordinators

`entry.runtime_data` holds both coordinators a config entry uses:

```python
@dataclass
class ChoresRuntimeData:
    main: ChoresCoordinator
    monthly_earnings: ChoresMonthlyEarningsCoordinator
```

`ChoresCoordinator` (5-minute interval) is the main one:

```python
@dataclass
class ChoresData:
    children: list[dict]  # User rows where role == USER_ROLE_CHILD
    occurrences_by_child: dict[str, list[dict]]  # childId → [TaskOccurrence, ...]
    tasks: list[dict]  # ListTasks — task definitions, for UpdateTask's merge
    summaries_by_child: dict[str, dict]  # childId → ChildSummary
```

`ChoresMonthlyEarningsCoordinator` (hourly) is separate — see "Why a second
coordinator for monthly earnings" below — and its data is just
`dict[str, list[dict]]`, mapping childId to its `ListMonthlyEarnings` months.

The coordinator caches the schema enough to iterate entity setup (new children) and entity updates (new/completed occurrences for existing children).

### `TaskOccurrence` (proto3 JSON from the API)

An occurrence is the single unit that appears on the UI — one chore, one child, one date:

```json
{
  "taskId": "task-1",
  "childId": "child-1",
  "dueDate": "2026-08-30",
  "title": "Ta ut søpla",
  "description": "Alle dunkene",
  "classification": "TASK_CLASSIFICATION_MANDATORY",
  "completedAt": null,  // absent if not done; present with a timestamp if done
  "amount": {"cents": "1500"}
}
```

**Key design**: the occurrence has no `id` until it's been recorded (someone marked it done). For unrecorded occurrences, we use a composite `uid = f"{taskId}|{childId}|{dueDate}"`, which is exactly the tuple `CompleteTask` takes. Recorded and unrecorded items are handled identically.

**Live fields**: `title`, `description`, `icon`, `classification` are read from the task on every load, not stored. So renaming a task fixes it everywhere. Only `amount` is frozen at record time, because repricing doesn't reach backwards.

### Timeline (midnight boundary)

The coordinator runs every 5 minutes. If a refresh happens at 23:57, the next one is 00:02 — so yesterday's list lingers for 5 minutes into the new day.

To fix this, we register an `async_track_time_change(hass, ..., hour=0, minute=0, second=5)` that forces a refresh at 00:00:05 local time. That way, the list rolls over cleanly.

`today` is recomputed on every refresh from `dt_util.now().date()` in Home Assistant's configured timezone, so DST and timezone changes are handled correctly.

## Auth and config flow

The flow is linear: **user** → (optional) **family** → **create**:

1. **User step**: ask for base URL and personal access token (from Chores app settings).
2. **Validate**: call `GetMyMembership` to confirm the token is valid and bound to a family.
3. **Family step** (if multiple memberships): dropdown to pick which family. Single membership auto-selects.
4. **Create**: unique_id = family_id, title = family name, data = {base_url, token, family_id}.

**Reauth**: When the coordinator hits `ChoresAuthError`, it raises `ConfigEntryAuthFailed`. Home Assistant triggers the reauth flow, which is identical except it only asks for the token (base_url and family_id are already known).

Unique ID is family_id, so adding the same family twice is rejected. Multiple families require multiple config entries.

## Coordinator and entities

One `ChoresCoordinator` per config entry, at the configured interval (5 minutes by default). Each refresh:

- Calls `ListUsers` → filter children.
- Calls `ListTaskOccurrences(start_date=today, end_date=today)` → group by child.
- Calls `ListTasks` → task definitions, for services that need to merge against the current task.
- Calls `ListChildSummaries` → balance/earnings, one call for the whole family.

Every per-child platform (`todo.py`, `sensor.py`, `button.py`, `calendar.py`) uses the same `async_add_per_child_entities` helper in `entity.py`: it adds entities for every current child, then listens for the coordinator to report new ones and adds those too. This means adding a child in the Chores app picks it up on the next refresh without reloading — one place implements it, so every platform gets it for free.

**This is one-directional.** `known` in `async_add_per_child_entities` only grows; a child removed from the family (via `chores.remove_child` or in the app) drops out of `coordinator.data.children`, but its entities stay registered — the sensors go `unknown`, the todo list and calendar go empty, rather than the entities disappearing. Home Assistant doesn't auto-remove devices without an explicit registry cleanup, and adding one wasn't part of this pass; a leftover device for a removed child has to be removed by hand (Settings → Devices).

`ChoresTodoListEntity` (one per child) reads from `coordinator.data.occurrences_by_child[child_id]`.

## Proto3 JSON wire format

All messages and responses follow proto3 JSON rules:

- **Field names**: camelCase on the wire, never snake_case. Request and response both expect it.
- **Enums**: names, never numbers. `"TASK_CLASSIFICATION_MANDATORY"`, not `1`.
- **Zero values**: omitted entirely. An absent `completedAt` means not done. An absent `classification` means the enum's zero value (UNSPECIFIED).
- **`int64`**: strings. `Money.cents` arrives as `"1500"`, not `1500`.

`api.py` handles all of this. Entity code reads dicts directly and never touches serialization.

## Error handling

Connect returns non-2xx with `{"code": "...", "message": "..."}`:

- `"unauthenticated"`, `"permission_denied"` → `ChoresAuthError` (triggers reauth).
- Everything else → `ChoresApiError` (logged, integration becomes unavailable, user is notified).
- Network error → `ChoresApiError`.

The coordinator catches `ChoresAuthError` and raises `ConfigEntryAuthFailed`. Home Assistant handles the rest.

## Testing strategy

Tests use `pytest-homeassistant-custom-component`, which provides:

- `hass` fixture (a Home Assistant instance).
- `aioclient_mock` (HTTP mock).
- `MockConfigEntry` (config entry builder).
- Async support via `pytest-asyncio`.

Fixtures in `conftest.py` are reused: `occurrence()`, `task()`, `child_summary()`, `monthly_earnings()`, `users_response()`, `membership_response()`, `config_entry()`, `rpc_url()`, `setup_integration()` — the last is the shared integration-setup helper, mocking every RPC either coordinator makes on refresh, with all-empty defaults so a test only has to pass the response(s) it actually cares about.

**Test layers**:

- **`test_api.py`**: client sends correct headers, parses proto3 JSON, maps error codes.
- **`test_config_flow.py`**: single/multi-family flows, auth, reauth, already-configured.
- **`test_todo.py`**: list renders correctly, complete/uncomplete calls the API, sorting works.
- **`test_sensor.py`**: money sensors convert cents correctly, missing/zero data doesn't crash, the currency option toggles device_class/unit.
- **`test_button.py`**: pressing pays out the full balance.
- **`test_calendar.py`**: `event` is the next undone occurrence; `async_get_events` fetches and filters the requested range.
- **`test_services.py`**: every service calls the right RPC with the right payload, `update_task`'s merge against the existing task, and unknown device/task ids raise `ServiceValidationError` rather than silently no-op'ing.
- **`test_check_schema.py`**: live schema still has the fields we read.

No mocking of internals or monkeypatching. Mock only the HTTP layer.

## Schema drift

`scripts/check_schema.py` runs on CI:

```sh
buf build buf.build/apphub/chores -o desc.json
```

This emits a FileDescriptorSet as JSON. The script then asserts that `TaskOccurrence`, `ListTaskOccurrencesResponse`, and the required RPC methods still exist and carry the exact fields we read.

If the schema changes:

- **New field added**: doesn't fail (we ignore it).
- **Field we read renamed or deleted**: fails, you must update REQUIRED_FIELDS and REQUIRED_METHODS in the script.
- **New enum value added**: doesn't fail (we handle the name).
- **Enum value we depend on deleted**: fails.

The check is narrowly scoped: it doesn't fail on unrelated upstream changes, only on breaking changes to our surface.

## Beyond phase 1

Everything below was "future expansion" in the original phase-1 design and has
since been built, on top of the same coordinator and data model without
changing it:

- **Sensors** (`sensor.py`): balance and earnings, from `ListChildSummaries`
  (folded into `ChoresCoordinator`, one call per family per refresh) and
  `ListMonthlyEarnings` (its own `ChoresMonthlyEarningsCoordinator`, on an
  hourly interval — see below for why it's split out).
- **Calendar** (`calendar.py`): one `CalendarEntity` per child.
  `async_get_events` calls `ListTaskOccurrences` directly for the requested
  range rather than reading the coordinator's cache, since the range a
  calendar view asks for varies and isn't bounded to "today".
- **Events**: `todo.py` fires `chores_task_completed` when `CompleteTask`
  succeeds, carrying `task_id`, `task_title`, `child_id`, `child_name`,
  `due_date`, `family_id`.
- **Payouts** (`button.py`, `services.py`): a `ChoresPayoutButton` per child
  for the common case (pay out the full balance); `chores.create_payout` for
  a specific amount and note.
- **Task management** (`services.py`): `chores.create_task`,
  `chores.update_task`, `chores.delete_task`. Flat schedule fields
  (`schedule_type`, `date`, `days_of_week`, `interval_weeks`,
  `anchor_date`, `cron_expression`) get assembled into the `Schedule` oneof
  in `_build_schedule`.
- **User management** (`services.py`): `chores.create_user`,
  `chores.remove_child`.

### Why a second coordinator for monthly earnings

`ListChildSummaries` is one RPC for the whole family, so it rides along in
the 5-minute `ChoresCoordinator` refresh for free. `ListMonthlyEarnings` is
one RPC *per child*, for data (completed earnings by calendar month) that
changes at most once a day. Folding it into the fast loop would multiply that
loop's request count by the number of children for no benefit, so
`ChoresMonthlyEarningsCoordinator` polls it separately, on an hourly
interval, reading the child list off the main coordinator.

### Why a service, not more entities, for task/user management

Home Assistant entities model *state*; these are one-shot commands with
several parameters (a task's title, schedule, price and assignees; a
payout's amount and note) that don't fit a switch or a number entity without
either a pile of per-field entities per task or a config UI this integration
doesn't have. Services take a target (`device_id` for something scoped to a
child, `config_entry_id` for something scoped to a family) plus flat fields,
resolved in `services.py` via the device/config-entry registries.

### `UpdateTask` is a full replace, not a patch

Every scalar field in `UpdateTaskRequest` is sent as-is; there's no
per-field "leave this alone" signal on the wire, and `child_ids` explicitly
replaces the task's full assignee list. A service call that only sets
`title` would otherwise silently reset `active` to false, `price` to zero,
and fail entirely on an empty `child_ids`. `chores.update_task` reads the
current task out of `ChoresCoordinator.data.tasks` (populated by `ListTasks`
in the same refresh as everything else) and merges any field the caller
didn't pass in before sending.

### What's deliberately out of scope

RPCs that don't have a sensible Home Assistant surface, and why:

- **Personal access tokens** — the integration authenticates with one; a
  service that could revoke it would let an automation lock the integration
  out of its own credential.
- **Web Push** (`SubscribeToPush`/`UnsubscribeFromPush`) — a browser API tied
  to a `PushSubscription` object HA has no equivalent of; HA has its own
  notify platform for this.
- **Invitations, `AcceptInvitation`** — onboarding flows for binding a login
  identity, which happens in the Chores app, not from a backend integration.
- **`CreateFamily`/`DeleteFamily`/`ListFamilies`, dashboard-key RPCs
  (`GetDashboardConfig`/`SetupDashboard`/`DisableDashboard`)** — bootstrap or
  destructive operations that precede having a config entry at all, or that
  return a bearer secret that would otherwise sit in Home Assistant state.
- **`LeaveFamily`** — removes the very login identity the integration
  authenticates as.
- **`UpdateUser`** — proto3 restricts renaming to self-service only ("a
  bound login can rename its own user row and no one else's, even a parent
  renaming a child"), so a "rename child" service would always fail
  `permission_denied`.
