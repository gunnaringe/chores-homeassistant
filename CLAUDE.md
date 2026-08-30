# Claude Development Guide

This repository is primarily developed and maintained by Claude. This file documents patterns, conventions, and DRY principles to keep iterations cheap and code maintainable.

## Project goals

- **No external Python dependencies at runtime** (`manifest.json` declares `requirements: []`). All work happens over plain HTTP JSON to the Connect RPC API.
- **Cheap iteration** — reusable scripts, helper functions, and clear abstractions prevent repeating work.
- **Correct async/await** — ruff catches blocking calls in event loops.
- **Test-driven** — tests are the spec, run them before committing.

## Key patterns

### No SDK dependency

The Chores Connect API is simple enough to call by hand. `api.py` contains all wire-format handling:

- **Proto3 JSON**: fields are `camelCase`, enums arrive as names (`"TASK_CLASSIFICATION_MANDATORY"`), zero values are omitted.
- **Error codes**: `unauthenticated` and `permission_denied` → `ChoresAuthError` (triggers reauth). Everything else → `ChoresApiError`.
- **Five methods**: `GetMyMembership`, `ListUsers`, `ListTaskOccurrences`, `CompleteTask`, `UncompleteTask`. All one-shot unary calls.

If you add an RPC, implement it as a typed method in `ChoresClient`, never copy the hand-rolled HTTP logic. If you want to swap to a generated SDK later (when it lands on PyPI), `api.py` is the only place to change.

### Entity scaffolding is repeatable

`todo.py` is the one entity type in phase 1. The pattern for adding more (sensors, buttons, calendar) is:

1. Add a new method to `ChoresClient` for the RPC(s) it needs.
2. Store the data in `ChoresCoordinator.data` and parse it in `_async_update_data()`.
3. Create `ChoresXxxEntity(CoordinatorEntity, TodoListEntity)` (or `SensorEntity`, etc.) with one `async def async_setup_entry()` that calls `async_add_entities`.
4. Test the entity in a new `tests/test_xxx.py` using the fixtures in `conftest.py`.

Don't repeat: `conftest.py` already has `occurrence()`, `users_response()`, `config_entry()`, and `setup_integration()`. Reuse them.

### Config and coordinator are load-bearing

- **`config_flow.py`** — user step, family step (if multi-membership), reauth step. Unique ID is `family_id`. Never change the unique ID logic without a migration.
- **`coordinator.py`** — one coordinator per config entry, responsible for keeping today's list accurate across timezone boundaries. The midnight refresh is deliberate.
- **`const.py`** — centralized string constants. Enum names from proto3 JSON live here.

## Upgrade path

### Adding a sensor

`ListChildSummaries` returns `balance`, `earned_today`, `earned_this_week`, etc. To add these:

1. Call `list_child_summaries()` in the coordinator alongside the current `list_users()` and `list_task_occurrences()`.
2. Store summaries in `ChoresCoordinator.data.summaries_by_child: dict[str, dict]`.
3. Create `ChoresBalanceSensor` in a new file `custom_components/chores/sensor.py`.
4. Add `"sensor"` to `PLATFORMS` in `const.py`.
5. Test with a new `tests/test_sensor.py` using the existing fixtures.

The coordinator is ready for this — it's why `occurrences_by_child` exists in the first place.

### Adding a payout button

`CreatePayout` takes `child_id` and either `full_payout=True` or an `amount`. To add:

1. Add a `create_payout()` method to `ChoresClient`.
2. Create `ChoresPayoutButton` in a new file `custom_components/chores/button.py`.
3. `async_press()` reads `child_id` from somewhere (entity ID parse? stored config?) and calls the client.
4. Test by mocking the button press and asserting `CreatePayout` was called.

## Schema and versioning

- **Live schema check**: `scripts/check_schema.py` runs on CI and asserts the fields we read still exist. If an RPC is renamed upstream, the check fails and you have to update `REQUIRED_FIELDS` / `REQUIRED_METHODS`.
- **No versioning of manifests**: use semver in `manifest.json:version` when you publish, but don't document API versions — the schema check prevents drift.

## Testing conventions

- Use `conftest.py` fixtures: `config_entry`, `users_response`, `membership_response`, `occurrence()`, `rpc_url()`.
- Mock with `aioclient_mock`: `aioclient_mock.post(rpc_url("Method"), json={...})`.
- Entity setup calls `await hass.async_block_till_done()` after `async_setup()`.
- Never mock the coordinator internals; mock the API.

## Linting and Git hooks

`ruff` is configured to match Home Assistant core's style. Run it manually or let prek handle it:

```sh
mise run lint      # ruff checks + format --check
mise run format    # apply ruff fixes
mise run setup-hooks  # install prek git hooks (once)
mise run hooks     # run all hooks on all files
```

Git hooks (configured in `prek.toml`) run automatically before commit:
- File cleanup (trailing whitespace, EOF, YAML/JSON validation)
- Python linting (ruff check)
- Python formatting (ruff format)
- Home Assistant validation (hassfest)

## When stuck

1. **Proto3 JSON field missing?** Check if it's a zero value (omitted) or if the server changed. The schema check should catch renamed fields.
2. **Async timeout?** Add `await hass.async_block_till_done()` after setup steps.
3. **Entity not showing up?** Confirm the coordinator's `async_setup_entry()` was called and `async_add_entities()` was invoked.
4. **Auth flow broken?** Trace through `config_flow.py` → `ChoresClient.get_my_membership()` → `ChoresAuthError` → `invalid_auth`.

## Defer for phase 2+

- Calendar entities from occurrences over a date range.
- `chores_task_completed` event for automations.
- Balance and earnings sensors (data is already one RPC away).
- Payout buttons and services.
- UI customization (icons, descriptions, entity categories).
