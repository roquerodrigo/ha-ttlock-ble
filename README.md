# Home Assistant TTLock BLE

[![CI](https://github.com/roquerodrigo/ha-ttlock-ble/actions/workflows/ci.yml/badge.svg)](https://github.com/roquerodrigo/ha-ttlock-ble/actions/workflows/ci.yml)
[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)

[![Sponsor](https://img.shields.io/badge/Sponsor-%E2%9D%A4-db61a2?logo=githubsponsors&logoColor=white&style=for-the-badge)](https://github.com/sponsors/roquerodrigo)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=roquerodrigo&repository=ha-ttlock-ble&category=integration)

---

Local control of TTLock smart locks over Bluetooth, for [Home Assistant](https://www.home-assistant.io/). Lock / unlock, battery level and real-time push events flow over BLE — no cloud round-trip on every operation. Built on the sibling Python SDK [`ttlock-ble`](https://github.com/roquerodrigo/ttlock-ble).

## Features

- **Local BLE control** — lock, unlock, and state queries run over the lock's BLE link; the TTLock cloud is only contacted once at setup to download per-lock keys.
- **Passage Mode management** — configure single or multi-interval schedules (daily, weekly, specific days) on the lock over Bluetooth. Includes quick dashboard toggle (`switch`), real-time active status (`binary_sensor`) with 0% lock battery impact (exact boundary timestamps), and dynamic upcoming schedule inspection (`sensor`).
- **Auto-Lock configuration** — customize relock delays directly from Home Assistant using a delay slider (`number`, 0 to 900s) or enable/disable toggle (`switch`).
- **Enrolled Credential counts** — diagnostic sensors reporting the total number of PIN passcodes, RFID/IC cards, and biometric fingerprints enrolled on the lock. Locks without fingerprint sensors report 0 gracefully.
- **Detailed Unlock History** — human-readable last unlock method sensor (`Fingerprint`, `Passcode`, `RFID Card`, `Mobile App`, `Auto-Lock`, `Mechanical Key`, etc.) with sequence number, timestamp, credential ID, and user ID attributes.
- **Action buttons** — trigger on-demand Bluetooth syncs directly from the dashboard: calibrate hardware clock, sync operation log, refresh state, sync passcodes, sync cards, sync fingerprints, and sync passage mode schedules.
- **Rich Bluetooth Actions (Services)** — programmatic access to configure or clear passage schedules, query auto-lock limits, read lock hardware clock, fetch operation log records with date filtering, and query enrolled passcodes, cards, and fingerprints.
- **State persistence** — sensors preserve counts, unlock history, and schedules across Home Assistant restarts and integration reloads (`RestoreEntity`).
- **Real-time push events** — keypad presses, fingerprint reads, IC-card swipes, mechanical key turns, and auto-lock fires arrive as Home Assistant events the moment the lock emits them.
- **Battery sensor** — diagnostic entity refreshed by every poll *and* every push, no extra BLE traffic.
- **Clock alignment** — the lock's own clock, which stamps every operation-log record, is compared against local time once a day on a session something else already opened, and corrected when it has wandered. A diagnostic sensor reports the measured drift.
- **Bluetooth discovery** — a lock in range of any radio Home Assistant manages shows up on its own as a discovered device; the address and the frame header come off the advertisement, so only the keys are left to provide.
- **2FA-aware config flow** — handles TTLock's "new device" verification by emailing a one-time code and prompting for it.
- **Works without a cloud account** — a lock initialised locally can be added by entering its key directly, no TTLock account involved at any point.
- **Passive state tracking** — the bolt position and battery level are read from the lock's own BLE advertisements, with no connection and no battery cost. This is what catches an auto-lock or an operation done from the official app.
- **Connects only on demand** — nothing is held open. A session is opened when a command needs the lock, when the lock advertises that it has records worth reading, or when the permanent connection option asks for one.
- **Reauth + reconfigure** — re-prompt for credentials in place when the cloud rejects the cached login, or edit them via the integration's three-dot menu.
- **Diagnostics** — downloadable dump with credentials/keys redacted.
- **Translations** — English and Brazilian Portuguese (parity enforced by tests).

## Entities

Each configured lock produces one HA device, carrying up to 23 entities across 7 domains:

| Entity | Domain | Category | Purpose |
|---|---|---|---|
| `lock.<alias>` | `lock` | Control | Locked/unlocked state, with optimistic updates, `locking`/`unlocking` transitional states and a post-command settle window. |
| `switch.<alias>_passage_mode` | `switch` | Config | Quick toggle to turn passage mode on or off. Turning ON configures passage mode on the lock; turning OFF clears passage mode. |
| `switch.<alias>_auto_lock` | `switch` | Config | Enable or disable auto-relocking. Disabling sets delay to 0; enabling restores previous delay. |
| `switch.<alias>_sound` | `switch` | Config | The lock's keypad/lock beep (admin keys only). |
| `number.<alias>_auto_lock_time` | `number` | Config | Auto-lock delay duration in seconds (`0` disables auto-lock). |
| `binary_sensor.<alias>_passage_mode_active` | `binary_sensor` | Diagnostic | Real-time state whether passage mode is currently holding the door unlocked (`on`/`off`). Evaluates schedules in HA memory at exact boundary timestamps with 0% battery drain on the lock. |
| `binary_sensor.<alias>_connection` | `binary_sensor` | Diagnostic | Whether a BLE session is open right now. A healthy idle lock holds none, so `off` means idle, not unreachable. |
| `sensor.<alias>_battery` | `sensor` | Diagnostic | Battery percentage. |
| `sensor.<alias>_last_seen` | `sensor` | Diagnostic | When the lock was last heard from, read from HA's own advertisement history. |
| `sensor.<alias>_clock_drift` | `sensor` | Diagnostic | Drift of the lock's internal hardware clock against local time, in seconds. |
| `sensor.<alias>_last_unlock_method` | `sensor` | Diagnostic | Formatted last unlock operator (e.g. `Fingerprint (66051)`, `Passcode`, `RFID Card (12345)`, `Mobile App`, `Auto-Lock`, `Mechanical Key`) with sequence number, credential ID, and timestamp attributes. |
| `sensor.<alias>_passage_mode_schedule` | `sensor` | Diagnostic | Dynamic passage status (`Active (until HH:MM)`, `Next: Today HH:MM`, or `No schedule`) with `today_slots` and full schedule list attributes. |
| `sensor.<alias>_passcodes_count` | `sensor` | Diagnostic | Total number of PIN passcodes stored on the lock chip. |
| `sensor.<alias>_cards_count` | `sensor` | Diagnostic | Total number of RFID / IC cards enrolled on the lock chip. |
| `sensor.<alias>_fingerprints_count` | `sensor` | Diagnostic | Total number of enrolled fingerprints on the lock chip (`0` if lock lacks fingerprint hardware). |
| `button.<alias>_sync_clock` | `button` | Config | Calibrate the lock's hardware clock to Home Assistant local time. |
| `button.<alias>_sync_log` | `button` | Diagnostic | Sync new operation-log records from the lock. |
| `button.<alias>_refresh_state` | `button` | Diagnostic | Force an immediate Bluetooth query to update lock state and battery. |
| `button.<alias>_sync_passcodes` | `button` | Diagnostic | Query programmed passcodes over Bluetooth in the background and update the passcodes count sensor. |
| `button.<alias>_sync_cards` | `button` | Diagnostic | Query enrolled IC/RFID cards over Bluetooth in the background and update the cards count sensor. |
| `button.<alias>_sync_fingerprints` | `button` | Diagnostic | Query enrolled fingerprints over Bluetooth in the background and update the fingerprints count sensor. |
| `button.<alias>_sync_passage_mode` | `button` | Diagnostic | Query passage mode schedules over Bluetooth in the background and update passage sensors. |
| `event.<alias>_log` | `event` | — | Fires for every new operation-log record read from the lock. |

The event entity classifies each record as `unlock`, `lock`, `unlock_failed`, `password_change` or `other`, and attaches `record_type` and `battery` always, plus `timestamp`, `uid`, `credential`, `key_id` and `accessory_battery` when the record carries them. `credential` is only populated for record types where the value is an identifier (card number, fingerprint id, fob MAC) — record types where it would be a working door code never expose it.

## Actions (Services)

The integration registers custom actions under the `ttlock_ble` domain to inspect, configure, and manage lock settings over Bluetooth.

| Action | Description | Target |
|---|---|---|
| `ttlock_ble.set_passage_mode` | Configure one or more passage mode intervals on the lock. Supports `slots` (list of schedules), `start_time`, `end_time`, `days` (or `everyday`), `all_day`, and `clear_existing`. | Lock entity / device |
| `ttlock_ble.get_passage_mode` | Read all configured passage mode schedule intervals directly from lock memory over Bluetooth. | Lock entity / device |
| `ttlock_ble.delete_passage_mode` | Delete a specific passage mode interval by start time, end time, and day. | Lock entity / device |
| `ttlock_ble.clear_passage_mode` | Remove all configured passage mode schedule intervals from the lock. | Lock entity / device |
| `ttlock_ble.get_auto_lock_time` | Query current auto-lock duration in seconds and the lock hardware's supported min/max limits. | Lock entity / device |
| `ttlock_ble.get_lock_time` | Query the lock's internal real-time hardware clock and compute current drift relative to Home Assistant local time. | Lock entity / device |
| `ttlock_ble.get_operation_log` | Fetch recent operation-log records from the lock's on-chip memory. Supports `max_entries`, `from_sequence`, `to_sequence`, `start_date`, and `end_date`. | Lock entity / device |
| `ttlock_ble.get_passcodes` | Query all programmed keyboard passcodes (PINs), passcode types, and validity periods. | Lock entity / device |
| `ttlock_ble.get_cards` | Query all enrolled RFID / IC cards, card numbers, and validity periods. | Lock entity / device |
| `ttlock_ble.get_fingerprints` | Query all enrolled biometric fingerprints, IDs, and validity periods. | Lock entity / device |

### Example: Setting Passage Mode Schedule

```yaml
action: ttlock_ble.set_passage_mode
target:
  entity_id: lock.front_door
data:
  clear_existing: true
  slots:
    - start_time: "08:00"
      end_time: "17:00"
      days: "everyday"
    - start_time: "13:00"
      end_time: "15:00"
      days: "friday"
```

## Installation

1. Install via HACS using the button above, or add this repo as a custom HACS repository (category: Integration).
2. Restart Home Assistant.
3. Settings → Devices & Services → either pick the **TTLock BLE** card already waiting under *Discovered* (any lock in range of a radio Home Assistant manages announces itself), or Add Integration → **TTLock BLE**.
4. Choose how the keys are obtained:
   - **Sign in to a TTLock account** — enter the email + password you use in the official app. If TTLock has never seen this Home Assistant before it emails a verification code; paste it into the next step. Every lock on the account is synced at once.
   - **Enter a lock key manually** — for a lock initialised outside the cloud. See below.
5. From this point on, all lock / unlock / state operations stay on Bluetooth.

### Adding a lock without a TTLock account

A lock initialised by a local BLE bridge never goes through the cloud, and its owner already holds what Bluetooth needs. That key can be entered directly, one lock per entry:

| Field | Notes |
|---|---|
| Lock MAC address | `AA:BB:CC:DD:EE:FF` |
| AES key | 16 bytes, continuous hex or separated (`2c,3d,…`) |
| Unlock key | digits, entered verbatim — not the obfuscated form the cloud returns |
| Admin passcode | optional, digits; only needed for managing passcodes |
| Protocol type / version / scene / group ID / organisation ID | the frame header the lock expects. The defaults (5, 3, 2, 1, 1) suit most V3 locks |

Started from a discovered lock, the MAC address, the name and the first three protocol numbers arrive pre-filled from the advertisement — the keys are all that is left to type.

Only these reach the wire. The rest of what the cloud returns per key — user id, lock-flag position, validity window — is never read by the Bluetooth layer, which addresses the lock with a zeroed user id and the firmware's "permanent key" date literals regardless.

If the lock is in range when the form is submitted, the protocol type, version and scene are checked against what it broadcasts, so a wrong value is caught there instead of becoming a lock that never answers. Getting a value wrong later is fixable through the integration's three-dot menu → **Reconfigure**.

Reaching the lock takes no extra configuration: whatever Bluetooth radio Home Assistant already manages — USB dongle, built-in adapter, or an ESPHome proxy — is the one used.

## Options

Settings → Devices & Services → TTLock BLE → **Configure** exposes one setting:

- `permanent_connection` (default off) — hold a BLE session open, reopening it the instant the lock drops it. Push events (keypad, auto-lock) then arrive in real time, and the lock's battery pays for it: the firmware closes an idle session within seconds, so this reconnects about as often. With the option off nothing is held open and nothing reconnects.

There is no polling interval and no reconnect pacing to configure. Earlier releases exposed `scan_interval` and `reconnect_interval`; both are gone, because nothing polls on a schedule any more — state arrives from the lock's own advertisements, and a session is opened only when something actually needs one.

To edit credentials without removing and re-adding, use the integration's three-dot menu → **Reconfigure**.

## How it works

The lock's TTLock firmware aggressively closes idle BLE sessions (~5 s of silence and it drops). The integration:

1. Reads the bolt position and battery level straight out of the lock's BLE advertisements. This costs no connection at all and is the only channel that reports an operation performed while Home Assistant is not connected — an auto-lock, the official app, a keypad code.
2. Opens a session only when there is a reason to: a `lock`/`unlock` command, an advertisement announcing unsynced operation records, or the first bolt position while none is known at all. With `permanent_connection` on, `connection.py` also holds one open and reopens it on every drop bleak signals.
3. After a user-initiated `lock`/`unlock`, the SDK keeps the link alive for 25 s so push events (the lock's reports of keypad operations, auto-locks, etc.) reach Home Assistant in real time.
4. Each push event carries the decoded `lock_state` and `battery` when the firmware emits a heartbeat-style payload, letting the entities update without a follow-up query.
5. While a session is open anyway, the lock is asked what it is — model, hardware and firmware — and the answer is remembered, so a restart shows it without connecting.

## Useful commands

```bash
scripts/setup      # install dependencies (uv sync, dev + lint groups)
scripts/develop    # start Home Assistant in debug mode with the integration loaded

# Lint and test directly (config lives in pyproject.toml):
uv run ruff format --check .
uv run ruff check .
uv run mypy custom_components/ttlock_ble
uv run pytest
```

HA runs with config in `config/` and `PYTHONPATH` pointing at the repo root. To reset entity/device IDs during development:

```bash
rm config/.storage/core.entity_registry config/.storage/core.device_registry
```

## Layout

```
custom_components/ttlock_ble/
├── __init__.py        # config-entry lifecycle & service registrations
├── advertisement.py   # TtlockBleAdvertisementTracker: state from advertisements
├── api.py             # TtlockBleApiClient: TTLockCloud wrapper (cloud bootstrap only)
├── binary_sensor.py   # BLE connection and passage mode active binary sensors
├── brand/             # icon / logo PNGs (local placeholder for HA brand registry)
├── button.py          # Action buttons (clock sync, log sync, state refresh, credential sync)
├── config_flow.py     # menu / bluetooth / cloud / manual / verify_code / reauth / reconfigure
├── connection.py      # TtlockBleConnection: persistent BLE session per lock
├── const.py           # DOMAIN, LOGGER, service constants, defaults
├── coordinator.py     # DataUpdateCoordinator polling each connection
├── credentials.py     # BLE exchange handlers for passcodes, cards, and fingerprints
├── data/              # one TypedDict/dataclass per file + type aliases in __init__.py
├── device_description_store.py  # per-lock model / hardware / firmware, persisted
├── diagnostics.py     # redacted credentials/keys
├── entity.py          # base CoordinatorEntity with DeviceInfo
├── event.py           # TtlockBleLogEvent: operation-log records as HA events
├── exceptions/        # one file per exception class
├── lock.py            # TtlockBleLock: LockEntity backed by the connection
├── manifest.json      # integration metadata and dependencies
├── manual_key.py      # TtlockBleManualKey: key entry for cloud-less locks
├── number.py          # TtlockBleAutoLockTimeNumber: auto-lock delay slider
├── options_flow.py    # TtlockBleOptionsFlow: permanent_connection
├── passage.py         # BLE frame builders and parsers for passage mode
├── clock_sync_store.py # persisted clock comparison per lock
├── record_store.py    # persisted operation-log cursor per lock
├── sensor.py          # battery, last-seen, clock drift, unlock method, credential count sensors
├── services.py        # implementations for all custom ttlock_ble actions
├── services.yaml      # action schemas, field descriptors, and selectors
├── switch.py          # sound, auto-lock, and passage mode switches
└── translations/
    ├── en.json
    └── pt-BR.json
```

Conventions for contributors live in [`CODE_STYLE.md`](./CODE_STYLE.md); architectural notes for AI agents in [`CLAUDE.md`](./CLAUDE.md).

## Pre-commit hooks

Install once per clone (after `scripts/setup`):

```bash
pre-commit install
```

This wires ruff, mypy and basic file hygiene checks (`.pre-commit-config.yaml`) into every commit, mirroring the CI lint job.

## CI

- **`ci.yml`** — lint (ruff check + format, mypy), tests (pytest with the 90 % coverage gate) and validation (`hassfest` + HACS) via the shared reusable workflows
- **`codeql.yml`** — GitHub CodeQL security scan; push/PR to `main` and a weekly cron
- **`release.yml`** — release-please opens a release PR on every push to `main` based on conventional commits
- **`auto-assign.yml`** — assigns the repository owner to new issues and pull requests

## Support

This integration is built and maintained on personal time, on hardware bought for the purpose. If it is useful to you, consider [sponsoring the work](https://github.com/sponsors/roquerodrigo) — it keeps the devices, the testing and the releases coming.

## License

[MIT](LICENSE)
