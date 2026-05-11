# CLAUDE.md

Guidance for Claude Code (claude.ai/code) agents working in this repository.

## Always read `CODE_STYLE.md` first

Before creating, renaming or restructuring any file/class/function, **read [`CODE_STYLE.md`](./CODE_STYLE.md)**. It is the single source of truth for conventions: language, file organisation, naming, typing, properties vs `__init__`, imports, docstrings, comments, coordinator pattern, repairs/diagnostics layout, translations, lint workflow.

For user-facing topics (what's included, how to fork, rename steps, layout diagram, useful commands, CI list), see [`README.md`](./README.md).

This file deliberately avoids restating those rules — it only adds:

1. The verification workflow agents must run after every change.
2. The architectural reasoning that is not obvious from `CODE_STYLE.md` alone.

## Verification workflow

**After every code change, always run lint then tests, in that order, before declaring the task done:**

```bash
scripts/lint && pytest
```

- `scripts/lint` runs `ruff format`, `ruff check --fix` and `mypy` (`mypy.ini`). Fix any failure and re-run before moving on.
- `pytest` enforces a **95 % coverage gate** (`pytest.ini`).

Both gates mirror CI (`.github/workflows/lint.yml`). Skip this only when the change literally cannot affect lint or tests (e.g., README-only edits).

## Bumping the Home Assistant version

The Home Assistant version is pinned in three places and **must be updated together**, otherwise CI, HACS and the test harness drift apart:

1. `requirements.txt` — `homeassistant==<X.Y.Z>` (runtime/CI lint + mypy).
2. `hacs.json` — `"homeassistant": "<X.Y.Z>"` (minimum HA core enforced by HACS).
3. `requirements_test.txt` — `pytest-homeassistant-custom-component==<matching release>` (the test harness ships its own pinned `homeassistant`; the two pins must come from the same HA release, otherwise lint and tests resolve different cores).

Verify the pairing on PyPI before committing: the `requires_dist` of `pytest-homeassistant-custom-component` must list the same `homeassistant==<X.Y.Z>` you pinned in `requirements.txt`.

## Architecture

The integration follows the HA `DataUpdateCoordinator` pattern:

```
config_flow.py   → validates credentials and creates the ConfigEntry
__init__.py      → instantiates ApiClient + DataUpdateCoordinator, performs the first refresh
coordinator.py   → polls every scan_interval seconds; returns the typed payload
sensor.py        → reads coordinator.data and creates the entities
```

### Entry typing

`data.py` defines `IntegrationBlueprintConfigEntry = ConfigEntry[IntegrationBlueprintData]` and the `IntegrationBlueprintData(client, coordinator, integration)` dataclass. State lives on `entry.runtime_data` (auto-discarded on unload), never on `hass.data`.

### Config flow surface

`config_flow.py` implements four user-facing steps; all share one `_validate` helper and one `_credentials_schema` builder:

- `async_step_user` — initial setup; sets unique_id from username, aborts on duplicate.
- `async_step_reauth` / `async_step_reauth_confirm` — fired when the coordinator raises `ConfigEntryAuthFailed`. `async_update_reload_and_abort` rotates credentials in place.
- `async_step_reconfigure` — lets the user edit credentials via the integration's three-dot menu, no delete-and-re-add cycle.
- `async_get_options_flow` — returns `IntegrationBlueprintOptionsFlow` from `options_flow.py` (one class per file).

### Options flow

`options_flow.py` exposes `scan_interval` (seconds; min 30, default 300). Changing it triggers `async_reload_entry`, which re-instantiates the coordinator with the new `update_interval`.

### API client

`api.py` exposes `IntegrationBlueprintApiClient` plus the `_verify_response_or_raise` helper. Exceptions live under `exceptions/`:

- `IntegrationBlueprintApiClientError` (base)
- `IntegrationBlueprintApiClientCommunicationError` (timeout, connection)
- `IntegrationBlueprintApiClientAuthenticationError` (401/403)

`_api_wrapper` maps `TimeoutError`, `aiohttp.ClientError` and `socket.gaierror` to `CommunicationError`; any other exception becomes the base error.

### Diagnostics

`diagnostics.py` returns `IntegrationBlueprintDiagnosticsPayload`. `username`/`password` are redacted via `async_redact_data` (driven by `TO_REDACT: frozenset[str]`). `.github/ISSUE_TEMPLATE/bug.yml` asks users to attach the dump.

### Repairs

`repairs.py` is the entry point HA calls when the user clicks **Fix** on an issue:

- `async_create_fix_flow(hass, issue_id, data)` returns a `RepairsFlow`. Branch on `issue_id` for multiple kinds; the default returns `ConfirmRepairFlow`.
- `async_raise_deprecated_api_issue(hass)` is the sample helper that registers an issue. Call helpers like this from the coordinator/setup when you detect a recoverable problem.

Issue strings live under `issues.<issue_id>` in the translation files.
