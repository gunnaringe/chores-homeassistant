# Implementation Plan — Chores Home Assistant Integration

## Scope

A HACS-installable custom integration (`custom_components/chores`) that talks to the
hosted Chores API with a Personal Access Token.

**Phase 1 ships exactly one entity type:** a `todo` list per child holding today's task
occurrences, where ticking an item calls `CompleteTask` and unticking calls
`UncompleteTask`.

Not in scope for phase 1: a Supervisor add-on. This is an integration against the
hosted (or self-hosted) service, not a packaging of the server itself.

## Transport — Connect RPC over plain JSON

Connect unary calls are ordinary HTTP POSTs with JSON bodies, so the integration needs
no protobuf or grpc dependency at all — `manifest.json` declares `"requirements": []`.

```
POST {base_url}/chores.v1.ChoresService/ListTaskOccurrences
Authorization: Bearer chorespat_...
Content-Type: application/json
Connect-Protocol-Version: 1

{"familyId": "...", "startDate": "2026-08-30", "endDate": "2026-08-30"}
```

### Why not the generated SDK

The BSR does publish `apphub-chores-{protocolbuffers,connectrpc,grpc}-python`, but only
on buf's own index (`https://buf.build/gen/python/simple/`), never PyPI. Home Assistant
installs a custom integration's requirements with pip against the default index and has
no per-integration `--extra-index-url`, so those packages cannot be declared as
requirements — a HACS install would fail at setup. Vendoring the generated code instead
would add a runtime `protobuf` requirement, which HA already pins for other
integrations; a version conflict there breaks unrelated integrations on the user's
system.

If a plain-PyPI client ever exists (a hand-written package, which is also what HA core
requires for upstream inclusion), swapping to it is contained: `api.py` is the only
module that knows about the wire format.

### proto3 JSON gotchas to handle explicitly

- **`int64` serializes as a JSON string.** `Money.cents` arrives as `"1500"`, not
  `1500`. Phase 1 ignores `amount`, but this bites the moment balance sensors land.
- **Enums arrive as names**, e.g. `"TASK_CLASSIFICATION_MANDATORY"`.
- **Zero-valued fields are omitted entirely.** Absent `completedAt` means not done,
  which is what we want; absent `classification` means UNSPECIFIED.
- Requests are lenient — servers using `protojson` accept both `family_id` and
  `familyId` — so only *response* parsing has to match. Pin all of the above in unit
  tests.

### Schema drift guard

No vendored copy of the proto. CI fetches the live schema with the buf CLI and asserts
that the field and method names `api.py` depends on still exist:

```sh
buf build buf.build/apphub/chores -o desc.json
```

`-o` with a `.json` extension emits a `FileDescriptorSet` as JSON, which stdlib `json`
reads without any protobuf dependency — and it carries the authoritative `jsonName` for
every field, which is exactly what our hand-written decoder has to match:

```python
msgs = {
    m["name"]: {f["jsonName"] for f in m.get("field", [])} for m in file["messageType"]
}
assert {"taskId", "childId", "dueDate", "completedAt"} <= msgs["TaskOccurrence"]
```

This is deliberately narrower than diffing a vendored file: an unrelated upstream change
should not fail our build, but a field we actually read being renamed or removed must.
The test skips when `buf` is unavailable or the network is down, so it never breaks a
local run.

## `api.py`

A thin `ChoresClient` over `async_get_clientsession(hass)`: one `_rpc(method, payload)`
helper plus typed wrappers for the five calls phase 1 needs — `GetMyMembership`,
`ListUsers`, `ListTaskOccurrences`, `CompleteTask`, `UncompleteTask`.

Connect errors come back as non-2xx with `{"code": "unauthenticated", "message": ...}`.
Map `unauthenticated` and `permission_denied` to `ChoresAuthError`, everything else to
`ChoresApiError`.

## Config flow

1. **user step** — `base_url` (default `https://chores.apphub.casa`) and `token`.
2. Validate by calling `GetMyMembership`. Unbound or auth error → `invalid_auth`;
   connection failure → `cannot_connect`.
3. If the response carries more than one membership, a **family step** with a dropdown.
   A single membership auto-selects.
4. `unique_id = family_id`, title = family name, data = `{base_url, token, family_id}`.
5. A **reauth flow** for token rotation, triggered by `ConfigEntryAuthFailed` raised
   from the coordinator.

Options flow: scan interval (default 5 minutes). Nothing else for now.

## Coordinator

`ChoresCoordinator(DataUpdateCoordinator)`, stored in `entry.runtime_data` via the typed
`ChoresConfigEntry = ConfigEntry[ChoresCoordinator]` pattern. Each refresh:

- `ListUsers(family_id)` → filter `role == USER_ROLE_CHILD` for the entity set.
- `ListTaskOccurrences(family_id, start_date=today, end_date=today)` → group by
  `childId`.

`today` is `dt_util.now().date()`, recomputed on every refresh in Home Assistant's
configured timezone. Because a 5-minute poll makes midnight rollover ragged, also
register `async_track_time_change(..., hour=0, minute=0, second=5)` to force a refresh
at the day boundary — otherwise yesterday's list lingers until the next tick.

Children appearing between refreshes are picked up by an `_async_add_new_children`
listener that adds entities dynamically, so adding a child in the web app does not
require reloading the integration.

## The todo entity

`ChoresTodoListEntity(CoordinatorEntity, TodoListEntity)`, one per child, each its own
device (`identifiers={(DOMAIN, child_id)}`, named for the child).

- `supported_features = TodoListEntityFeature.UPDATE_TODO_ITEM` only. Occurrences are
  generated by the task schedule, so create, delete and move are deliberately
  unsupported and Home Assistant hides those affordances.
- **uid** is the composite `f"{task_id}|{child_id}|{due_date}"`. This matters: an
  occurrence that has not been recorded yet has no `id` at all, and the composite is
  exactly the tuple `CompleteTask` takes — so recorded and unrecorded occurrences are
  handled identically.
- `TodoItem(summary=title, description=description, due=due_date,
  status=COMPLETED if completedAt else NEEDS_ACTION)`.
- Items sorted mandatory before optional, mirroring the app's "Must do" / "Can do"
  split. Classification also goes into the description prefix, since `TodoItem` has no
  category field.
- `async_update_todo_item` splits the uid back apart, calls `CompleteTask` or
  `UncompleteTask`, then awaits `self.coordinator.async_request_refresh()`. An attempted
  summary or description edit raises `HomeAssistantError` — those live in the Chores
  app, not here.

## Development environment

Install `mise` (one-time setup):

```sh
curl https://mise.jdx.dev/install.sh | sh
```

Tool versions come from `mise`, dependencies from `uv`. The split matters because the
two overlap: **mise owns tool versions** (Python, uv, ruff, buf), **uv owns the
dependency graph** (`.venv`, `pyproject.toml`, `uv.lock`). Let `uv run` create and
manage `.venv`, and do not also enable mise's auto-venv (`_.python.venv`) — either alone
is fine, both at once gives two tools owning one directory.

`UV_PYTHON_PREFERENCE = "only-system"` is set so uv uses the mise-provided interpreter
rather than quietly downloading its own and ignoring the pin.

Then for each session:

```sh
mise install       # entire toolchain
mise run test      # uv run pytest
mise run lint      # ruff check + format --check
mise run schema    # live-schema drift check
```

Nothing is installed globally, and nothing is installed into Home Assistant: the
integration declares `"requirements": []`, so the whole dependency tree here — which
includes `homeassistant` itself, several hundred megabytes of it, pulled in by
`pytest-homeassistant-custom-component` — is dev-only and confined to `.venv`.

Home Assistant 2026.8.3 requires Python >= 3.14.2, which the pinned 3.14 satisfies.

`ruff` is Home Assistant core's own linter and formatter, so adopting its rule set keeps
the integration in the style core reviewers expect, and catches the async mistakes that
otherwise surface as "Detected blocking call inside the event loop" at runtime.

## Repo layout

```
custom_components/chores/{__init__,api,config_flow,const,coordinator,entity,util}.py
custom_components/chores/{todo,sensor,button,calendar,services}.py
custom_components/chores/{manifest.json,strings.json,icons.json,services.yaml}
custom_components/chores/translations/en.json
scripts/check_schema.py
tests/
hacs.json
.github/workflows/validate.yml
```

`manifest.json`: `domain: chores`, `config_flow: true`, `iot_class: cloud_polling`,
`integration_type: hub`, `requirements: []`, `codeowners: ["@gunnaringe"]`.

CI runs hassfest, the HACS validation action, ruff, and the schema check above.

## Tests

Using `pytest-homeassistant-custom-component`:

- Config flow: success, invalid auth, cannot connect, multi-family selection, reauth.
- Client: Connect error-code mapping, and the proto3 JSON decoding rules above.
- Schema: the live-descriptor check, skipped without `buf` or network.
- Todo round trip: tick an item, assert `CompleteTask` was called with the right
  `task_id`, `child_id` and `due_date`; untick, assert `UncompleteTask`.

## Beyond phase 1

This document describes phase 1 (the todo list) as originally planned. Balance
and earnings sensors, calendar entities, payout buttons and services, task and
user management services, and the `chores_task_completed` event have all since
been built on top of the same coordinator and data model, without changing
either — see ARCHITECTURE.md's "Beyond phase 1" section for how each one
works and what was deliberately left out (personal access tokens, Web Push,
invitations, family lifecycle, `UpdateUser`).
