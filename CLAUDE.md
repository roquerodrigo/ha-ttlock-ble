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
uv run ruff format --check . && uv run ruff check . && uv run mypy custom_components/ttlock_ble && uv run pytest
```

- `ruff format --check .`, `ruff check .` and `mypy custom_components/ttlock_ble` enforce formatting, linting and strict typing. Fix any failure and re-run before moving on.
- `pytest` runs with the `--cov` flags (configured in `pyproject.toml`) and enforces the coverage gate. Both ruff and mypy configuration also live in `pyproject.toml`.

Both gates mirror CI (`.github/workflows/ci.yml`). Skip this only when the change literally cannot affect lint or tests (e.g., README-only edits).

## Bumping the Home Assistant version

The Home Assistant version is pinned in two places and **must be updated together**, otherwise CI, HACS and the test harness drift apart:

1. `pyproject.toml` — the `dependency-groups.dev` list pins both `homeassistant==<X.Y.Z>` (runtime/CI lint + mypy) and `pytest-homeassistant-custom-component==<matching release>` (the test harness ships its own pinned `homeassistant`; the two pins must come from the same HA release, otherwise lint and tests resolve different cores).
2. `hacs.json` — `"homeassistant": "<X.Y.Z>"` (minimum HA core enforced by HACS; may lag behind the dev-group pin).

Verify the pairing on PyPI before committing: the `requires_dist` of `pytest-homeassistant-custom-component` must list the same `homeassistant==<X.Y.Z>` you pinned in `pyproject.toml`. Run `uv sync` after bumping so `uv.lock` picks up the new pins.

## The `ttlock-ble` SDK pin

This integration wraps the sibling repo [`ttlock-ble`](https://github.com/roquerodrigo/ttlock-ble), which owns all BLE protocol/crypto logic and the cloud login client. The pin lives in **two places that can drift**:

- `custom_components/ttlock_ble/manifest.json` → `requirements: ["ttlock-ble==<version>"]` — this is what HACS/HA actually installs for end users.
- `pyproject.toml` → `dependency-groups.dev` → `"ttlock-ble==<version>"` — this is what lint/mypy/pytest run against locally and in CI.

If these two pins diverge, CI is green against a different SDK version than what ships to users. A breaking change in the SDK's public API (`TTLockCloud`, `TTLockClient`, `VirtualKey`, `CloudError`, the `disconnected_callback` signature) requires bumping both pins together, then re-running lint + tests here — the SDK repo's own release does not by itself update anything on this side.

## Architecture

The integration follows the HA `DataUpdateCoordinator` pattern:

```
config_flow.py   → cloud-bootstraps credentials, requests 2FA when needed,
                    pulls the per-lock VirtualKeys, creates the ConfigEntry
manual_key.py    → builds a VirtualKey from a hand-entered key, for locks
                    that were never in a TTLock account
__init__.py      → instantiates one TtlockBleConnection per lock and a
                    DataUpdateCoordinator, performs the first refresh
connection.py    → owns the long-lived BLE session, reconnect loop,
                    cooldown, and push-event dispatch
advertisement.py → decodes lock state + battery from the advertisements
                    HA's bluetooth manager already receives, no connection
coordinator.py   → polls every scan_interval seconds via each connection,
                    and publishes the advertised state as it arrives
lock.py          → LockEntity backed by the BLE connection
sensor.py        → BatterySensor backed by the same poll + push events
binary_sensor.py → connectivity BinarySensorEntity reflecting live BLE link state
event.py         → EventEntity that surfaces decoded LockEvent pushes
```

### Entry typing

`data/` is a package, one class per file, re-exported from `data/__init__.py`. `data/__init__.py` defines `TtlockBleConfigEntry = ConfigEntry[TtlockBleData]`; `data/runtime.py` defines the `TtlockBleData(keys, virtual_keys, connections, coordinator, bluetooth_unsubs)` dataclass. State lives on `entry.runtime_data` (auto-discarded on unload), never on `hass.data`.

### Config flow surface

`config_flow.py` implements the user-facing steps, sharing one module-level `_credentials_schema` builder for the credential ones and one `_manual_key_schema` for the manual one:

- `async_step_user` — a menu, nothing else: the entry can come from a cloud account or from a key entered by hand.
- `async_step_cloud` — the credential step (named `user` before the menu existed); sets unique_id from username, aborts on duplicate. Branches to `async_step_verify_code` when the cloud rejects the login with the 2FA "new device" error code.
- `async_step_verify_code` — second step of the 2FA branch; submits the emailed code via `_async_validate_code_and_login` and finalizes entry creation on success.
- `async_step_reauth` / `async_step_reauth_confirm` — HA's reauth entry points. Nothing in this integration currently raises `ConfigEntryAuthFailed` to trigger them automatically — the coordinator and `connection.py` only ever talk BLE after setup, never the cloud again — so today these steps are reachable only by manually starting a reauth flow for the entry. `async_update_reload_and_abort` rotates credentials in place on success.
- `async_step_manual` — takes a key obtained outside the cloud (see below); unique_id is the lock's MAC.
- `async_step_reconfigure` — lets the user edit credentials via the integration's three-dot menu, no delete-and-re-add cycle. **Branches on how the entry was created**: an entry with no `username` has no account to re-prompt for, so it goes to `async_step_reconfigure_manual` and re-opens the key form pre-filled instead.

### Manual key entry

`manual_key.py` defines `TtlockBleManualKey`, for locks initialised by a local BLE bridge and never registered in a TTLock account. It asks only for what reaches the wire — MAC, AES key, unlock key, optional admin passcode, and the five frame-header integers — because the rest of what the cloud returns per key is never read: `payload_check_user_time()` is called with no arguments, so uid and lockFlagPos go out zeroed and the dates are the firmware's "permanent key" literals whatever the validity window said.

Four things are load-bearing:

- **The unlock key and admin passcode are stored verbatim.** The cloud path runs them through `decode_password()`; a locally obtained one is already plain, and decoding it again would corrupt it.
- **The AES key is normalised to continuous hex on save.** The form accepts more separators than the library's `hex_key_to_bytes` parses (which takes comma, dot or continuous only), so a space-separated paste would be accepted and then fail at the first connection.
- **The advertisement cross-checks the frame header.** Protocol type, version and scene are compared against what the lock broadcasts when it is in range, turning a typo into a form error instead of a lock that never answers. `group_id`/`org_id` are not in the advertisement and cannot be checked this way.
- **A lock already held by another entry is rejected.** `_abort_if_lock_configured` scans the stored keys of every entry, because a cloud entry's unique id is the account, not the MAC — without it the same lock could be added twice and the second entry would silently collide on entity unique ids and get no entities. Both directions are checked: `async_step_manual` for a single MAC, and `_abort_if_any_lock_configured` over every key a cloud login returns. The reconfigure paths pass `ignore_entry_id` so an entry never collides with itself.

`username`/`password` are `NotRequired` on `TtlockBleConfigData` for exactly this reason; anything reading them must cope with their absence.

`async_step_reauth_confirm` and `async_step_reconfigure` both funnel through the shared `_async_step_credentials_for_entry` body, which applies `_abort_if_unique_id_mismatch` first — the entry is keyed by the account, so credentials for a *different* account are a mistake, not a re-authentication — then logs in and calls `async_update_reload_and_abort`. `async_step_reconfigure_manual` may change the MAC, which is that entry's unique id, so it moves the unique id along with it. `async_get_options_flow` returns `TtlockBleOptionsFlow` from `options_flow.py` (one class per file).

Every cloud call in the flow, `_async_fetch_keys` included, maps its exceptions onto form errors rather than letting them escape; `_classify_cloud_error` only reports an authentication failure when the cloud actually rejected the request, so an outage or a rate limit no longer reads as a wrong password.

### Options flow

`options_flow.py` exposes `scan_interval` (seconds; min 60, default 3600). Changing it triggers `async_reload_entry`, which re-instantiates the coordinator with the new `update_interval`.

### API client

`api.py` exposes `TtlockBleApiClient`, a thin async wrapper around the SDK's `TTLockCloud` used only by the config flow (cloud login + 2FA + key sync). Exceptions live under `exceptions/`:

- `TtlockBleApiClientError` (base)
- `TtlockBleApiClientCommunicationError` (httpx network failure)
- `TtlockBleApiClientAuthenticationError` (wrong credentials)
- `TtlockBleApiClientVerificationRequiredError` (errcode -1014 → 2FA branch)

`_classify_cloud_error` maps the SDK's `CloudError` body onto these by inspecting `errorCode` / `errcode`. Runtime BLE state never goes through this client — that path is `connection.py` → SDK `TTLockClient` → bleak.

### BLE connection layer

`connection.py` defines `TtlockBleConnection`, one per `VirtualKey`. Each owns:

- A long-lived `TTLockClient` (the SDK).
- An `asyncio.Lock` serializing query/lock/unlock commands.
- A reconnect maintain loop driven by an `asyncio.Event` the SDK's `disconnected_callback` toggles.
- A post-drop cooldown: after any disconnect, sleeps `RECONNECT_COOLDOWN_SECONDS` before reconnecting — no immediate retry. **The cooldown paces that loop only.** It used to also veto `async_query_state`, and since the lock drops every idle session within seconds the loop re-armed it constantly, so the configured `scan_interval` never actually ran a poll (issue #42). Reads are rate-limited by their own callers instead.
- A dispatcher forwarder: any push event the SDK emits is fanned out on `ttlock_ble_event_<mac>` so the lock, sensor, and event entities can subscribe. The BLE drop is announced from bleak's own callback, not from the teardown that follows the cooldown, so the connectivity sensor does not claim a live link for five minutes after the link died.
- Backlog seeding: the first operation-log fetch that actually reaches the lock only fills `_seen_records` and dispatches nothing. The lock returns everything unsynced since its last cursor sync, and replaying that history as live events would fire automations for unlocks from days ago. Tying it to a *successful* fetch matters — a lock out of range at startup must not spend its seeding pass on a poll that read nothing.
- A refusal to reconnect after `async_stop`: a late caller would otherwise take the lock's single central slot with no maintain loop left to release it.

### Passive advertisement tracking

`advertisement.py` defines `TtlockBleAdvertisementTracker`, subscribed per MAC through HA's `async_register_callback`. The firmware folds the bolt position, a "new records pending" flag and the battery percentage into the manufacturer data of every advertisement, so `LockAdvertisement.from_manufacturer_data` (SDK) turns them into state for free.

This is the **only** channel that reports an auto-lock: the firmware writes no operation-log record for it, and the lock drops the BLE session it pushes events on within seconds of going idle. The same applies to anything done from the official app or the keypad while we are not connected.

Two details are load-bearing:

- The decoded trailing address must equal the lock's MAC. A payload long enough to decode is not proof it is a TTLock payload, and that address is the only field whose value can be checked independently.
- An advertisement that decodes reaches the entities via `async_set_updated_data`, which also **reschedules** the next poll — a lock that keeps advertising is never connected to just to be read.

An advertisement we cannot decode falls back to a coordinator refresh, but only while no state is known yet: that bootstrap is what makes the entity available seconds after HA boots instead of after a full `scan_interval`. Refreshing on *every* advertisement (the old behaviour) is what made the cooldown look necessary in the first place.

The diagnostics dump carries the last advertisement per lock, raw bytes included, with `decoded: null` when the payload does not match the layout we know — that is what makes a "state never updates" report answerable without a round trip.

### Lock entity

`lock.py` reports the transitional states the platform defines — `locking` and `unlocking` — for as long as a command is on the wire, which is seconds: a BLE session has to be opened and the lock has to answer. Three things keep that honest:

- The flags are cleared in `finally`. A command also ends in `asyncio.CancelledError` (HA cancels the service call when the client that issued it disconnects), and `LockEntity.state` ranks `is_locking` above `is_locked`, so any escape that skipped the reset left the entity claiming a movement that had ended.
- `_command_lock` serializes the bookkeeping. The BLE layer's lock orders the round trips only; without an entity-level one, the first of two concurrent commands to finish published a settled state while the second was still turning the bolt.
- `jammed`, `open` and `opening` are never reported. The firmware exposes no jam signal — only a bolt position and a success/failure byte — and has no latch command distinct from unlocking, so any value there would be a guess.

`connection.py` converts everything that is not already a `TTLockError` into one, because the SDK's command path leaks `BleakError` from an unwrapped `write_gatt_char`, a bare `RuntimeError` from a rejected `checkUserTime`, and `ValueError` from the decrypt step.

### Event entity

`event.py` republishes decoded `LogEntry` records. The SDK carries keypad codes, card numbers, fingerprint ids and fob MACs in one `password` field; only the first are secret, so `PASSCODE_RECORD_TYPES` lists the record types whose value is a working door code and those never reach an event attribute. An attribute lands in the recorder database and is readable through the API by any user, admin or not.

### Diagnostics

`diagnostics.py` returns `TtlockBleDiagnosticsPayload`. `username`/`password`/`aesKeyStr`/`unlockKey`/`adminPs`/`keys` are redacted via `async_redact_data` (driven by `TO_REDACT: frozenset[str]`). `.github/ISSUE_TEMPLATE/bug.yml` asks users to attach the dump.
