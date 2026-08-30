# Architecture

## Overview

The Chores Home Assistant integration is a thin adapter between Home Assistant's entity model and the [Chores Connect API](https://buf.build/apphub/chores). It speaks plain HTTP JSON, carries no external runtime dependencies, and uses Home Assistant's standard patterns (DataUpdateCoordinator, ConfigEntry, async).

## Why no SDK?

The Chores Connect SDK exists (`apphub-chores-connectrpc-python`) but only on buf's custom index, not PyPI. Home Assistant's dependency resolver cannot reach custom indexes, so a HACS user installing this integration would fail at setup.

Vendoring the generated code would add protobuf as a runtime requirement, which HA already pins for other integrations. A version conflict there breaks unrelated integrations on the user's system.

Instead, we hand-roll the five RPC calls we need. The cost is ~200 lines of wire-format handling in `api.py`. The benefit is `manifest.json:requirements = []`, which means this integration never conflicts with anything else.

## Data model

### `ChoresData` (coordinator output)

```python
@dataclass
class ChoresData:
    children: list[dict]  # User rows where role == USER_ROLE_CHILD
    occurrences_by_child: dict[str, list[dict]]  # childId → [TaskOccurrence, ...]
```

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

One `ChoresCoordinator` per config entry. Each refresh:

- Calls `ListUsers` → filter children.
- Calls `ListTaskOccurrences(start_date=today, end_date=today)` → group by child.
- Stores in `ChoresData.children` and `ChoresData.occurrences_by_child`.

`ChoresTodoListEntity` (one per child) reads from `coordinator.data.occurrences_by_child[child_id]`. When the coordinator refreshes and a new child appears, a listener calls `async_add_entities()` to create the list dynamically. This means adding a child in the Chores app picks it up on the next refresh without reloading.

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

Fixtures in `conftest.py` are reused: `occurrence()`, `users_response()`, `membership_response()`, `config_entry()`, `rpc_url()`, `setup_integration()`.

**Test layers**:

- **`test_api.py`**: client sends correct headers, parses proto3 JSON, maps error codes.
- **`test_config_flow.py`**: single/multi-family flows, auth, reauth, already-configured.
- **`test_todo.py`**: list renders correctly, complete/uncomplete calls the API, sorting works.
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

## Future expansion

### Sensors (balance, earnings)

Call `ListChildSummaries` in the coordinator, store in data, create a sensor entity. Data is already one RPC away.

### Calendar (occurrences over a date range)

Call `ListTaskOccurrences` with a date range, create calendar events. Coordinator could cache this for a week or month.

### Events and automations

Fire a `chores_task_completed` event when `CompleteTask` succeeds. Automations can trigger on it.

### Payouts

Call `CreatePayout`. Needs a button entity or a service. UI asks which child and whether full payout or custom amount.

All additive on top of the current coordinator and data model.
