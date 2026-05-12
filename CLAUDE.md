# CLAUDE.md

Guidance for Claude Code (claude.ai/code) agents working in this repository.

## Always read `CODE_STYLE.md` first

Before creating, renaming or restructuring any file/class/function, **read [`CODE_STYLE.md`](./CODE_STYLE.md)**. It is the single source of truth for conventions: language, file organisation, naming, typing, properties vs `__init__`, imports, docstrings, comments, coordinator pattern, diagnostics layout, translations, lint workflow.

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

The integration follows the HA `DataUpdateCoordinator` pattern with
**on-demand BLE sessions** (no persistent connection — the previous
always-on model was draining the lock's battery):

```
config_flow.py    → cloud-bootstraps credentials, requests 2FA when needed,
                     pulls the per-lock VirtualKeys, creates the ConfigEntry
__init__.py       → instantiates one TtlockBleConnection per lock and a
                     DataUpdateCoordinator, performs the first refresh
connection.py     → opens a fresh BLE session for every query/lock/unlock,
                     then tears it down. Serializes via asyncio.Lock.
coordinator.py    → polls every scan_interval seconds (default 1h) via
                     each connection's async_query_state
lock.py           → LockEntity backed by on-demand BLE commands; optimistic
                     update + COMMAND_SETTLE_SECONDS settle window
sensor.py         → BatterySensor refreshed from coordinator data
binary_sensor.py  → Presence sensor driven by passive Bluetooth
                     advertisements (no BLE connection)
```

### Entry typing

`data.py` defines `TtlockBleConfigEntry = ConfigEntry[TtlockBleData]` and the `TtlockBleData(keys, virtual_keys, connections, coordinator)` dataclass. State lives on `entry.runtime_data` (auto-discarded on unload), never on `hass.data`.

### Config flow surface

`config_flow.py` implements four user-facing steps; all share one `_validate` helper and one `_credentials_schema` builder:

- `async_step_user` — initial setup; sets unique_id from username, aborts on duplicate.
- `async_step_reauth` / `async_step_reauth_confirm` — fired when the coordinator raises `ConfigEntryAuthFailed`. `async_update_reload_and_abort` rotates credentials in place.
- `async_step_reconfigure` — lets the user edit credentials via the integration's three-dot menu, no delete-and-re-add cycle.
- `async_get_options_flow` — returns `TtlockBleOptionsFlow` from `options_flow.py` (one class per file).

### Options flow

`options_flow.py` exposes `scan_interval` (seconds; min 30, default 300). Changing it triggers `async_reload_entry`, which re-instantiates the coordinator with the new `update_interval`.

### API client

`api.py` exposes `TtlockBleApiClient`, a thin async wrapper around the SDK's `TTLockCloud` used only by the config flow (cloud login + 2FA + key sync). Exceptions live under `exceptions/`:

- `TtlockBleApiClientError` (base)
- `TtlockBleApiClientCommunicationError` (httpx network failure)
- `TtlockBleApiClientAuthenticationError` (wrong credentials)
- `TtlockBleApiClientVerificationRequiredError` (errcode -1014 → 2FA branch)

`_classify_cloud_error` maps the SDK's `CloudError` body onto these by inspecting `errorCode` / `errcode`. Runtime BLE state never goes through this client — that path is `connection.py` → SDK `TTLockClient` → bleak.

### BLE connection layer

`connection.py` defines `TtlockBleConnection`, one per `VirtualKey`. Each owns:

- An `asyncio.Lock` serializing query/lock/unlock commands.
- No long-lived state — every public call opens a fresh `TTLockClient`,
  runs one operation, then disconnects in a `finally` block.

The lock therefore stays asleep between operations, which the TTLock
firmware treats as battery-saving idle. There is no reconnect loop, no
cooldown, no push-event subscription — those existed to keep the
old persistent session healthy. Push-event-driven state updates are
gone; mid-cycle state changes (keypad, fingerprint) surface on the next
hourly coordinator poll.

### Bluetooth presence

`binary_sensor.py` registers a passive advertisement callback and an
`async_track_unavailable` watcher per lock. Neither opens a BLE
connection — they listen to broadcasts the lock already emits while
idle. The sensor's `is_on` delegates to
`bluetooth.async_address_present` so the state is always live.

### Diagnostics

`diagnostics.py` returns `TtlockBleDiagnosticsPayload`. `username`/`password`/`aesKeyStr`/`unlockKey`/`adminPs` are redacted via `async_redact_data` (driven by `TO_REDACT: frozenset[str]`). `.github/ISSUE_TEMPLATE/bug.yml` asks users to attach the dump.
