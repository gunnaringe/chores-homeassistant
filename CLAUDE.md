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
- Every RPC the integration uses is a typed method in `ChoresClient` — see `api.py`. Covers the whole surface that has a sensible Home Assistant representation; see ARCHITECTURE.md's "What's deliberately out of scope" for the RPCs that don't (personal access tokens, Web Push, invitations, family lifecycle, `UpdateUser`).

If you add an RPC, implement it as a typed method in `ChoresClient`, never copy the hand-rolled HTTP logic. If you want to swap to a generated SDK later (when it lands on PyPI), `api.py` is the only place to change.

### Entity scaffolding is repeatable

Four per-child platforms exist — `todo.py`, `sensor.py`, `button.py`, `calendar.py` — plus `services.py` for actions that take parameters rather than modeling state. The pattern for a new per-child entity type is:

1. Add a new method to `ChoresClient` for the RPC(s) it needs.
2. Store the data in `ChoresCoordinator.data` (or a new coordinator, if it's one RPC per child rather than per family — see ARCHITECTURE.md on why `ChoresMonthlyEarningsCoordinator` is separate) and parse it in `_async_update_data()`.
3. Create `ChoresXxxEntity(CoordinatorEntity, SensorEntity)` (or `ButtonEntity`, etc.) and set it up with `entity.py`'s `async_add_per_child_entities(coordinator, async_add_entities, make_entities)` — don't hand-roll the "add for existing children, then listen for new ones" logic again.
4. Test the entity in a new `tests/test_xxx.py` using the fixtures in `conftest.py`.

For a new service (a command with parameters, not per-child state), add the schema, handler and registration to `services.py`, the field/service text to `strings.json` (and copy into `translations/en.json`), and the `services.yaml` selector definitions.

Don't repeat: `conftest.py` already has `occurrence()`, `task()`, `child_summary()`, `monthly_earnings()`, `users_response()`, `config_entry()`, `rpc_url()`, and `setup_integration()`. Reuse them.

### Config and coordinator are load-bearing

- **`config_flow.py`** — user step, family step (if multi-membership), reauth step, options step (scan interval, currency). Unique ID is `family_id`. Never change the unique ID logic without a migration.
- **`coordinator.py`** — `ChoresCoordinator` (one per config entry, 5-minute default interval) keeps today's list, tasks and summaries accurate across timezone boundaries; the midnight refresh is deliberate. `ChoresMonthlyEarningsCoordinator` (hourly) is separate — see ARCHITECTURE.md for why.
- **`const.py`** — centralized string constants. Enum names from proto3 JSON live here.
- **`entity.py`** — `async_add_per_child_entities`, the shared "one entity per child, plus new ones as they appear" scaffolding every per-child platform uses.
- **`util.py`** — `occurrence_uid` (the `task_id|child_id|due_date` composite key) and `money_cents` (safe `Money` → `int` cents, handling proto3's zero-value omission and `int64`-as-string).

## Schema and versioning

- **Live schema check**: `scripts/check_schema.py` runs on CI and asserts the fields we read still exist. If an RPC is renamed upstream, the check fails and you have to update `REQUIRED_FIELDS` / `REQUIRED_METHODS`.
- **No versioning of manifests**: use semver in `manifest.json:version` when you publish, but don't document API versions — the schema check prevents drift.

## Testing conventions

- Use `conftest.py` fixtures: `config_entry`, `users_response`, `membership_response`, `occurrence()`, `task()`, `child_summary()`, `monthly_earnings()`, `rpc_url()`, `setup_integration()`.
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

## What's out of scope, and why

Not "not yet built" — deliberately excluded, because the RPC doesn't have a
sensible Home Assistant representation. See ARCHITECTURE.md's "What's
deliberately out of scope" for the reasoning behind each: personal access
tokens, Web Push subscribe/unsubscribe, invitations, `CreateFamily`/
`DeleteFamily`/`ListFamilies`, the dashboard-key RPCs, `LeaveFamily`, and
`UpdateUser`.
