# Home Assistant TTLock BLE

[![CI](https://github.com/roquerodrigo/ha-ttlock-ble/actions/workflows/ci.yml/badge.svg)](https://github.com/roquerodrigo/ha-ttlock-ble/actions/workflows/ci.yml)
[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=roquerodrigo&repository=ha-ttlock-ble&category=integration)

---

Local control of TTLock smart locks over Bluetooth, for [Home Assistant](https://www.home-assistant.io/). Lock / unlock, battery level and real-time push events flow over BLE — no cloud round-trip on every operation. Built on the sibling Python SDK [`ttlock-ble`](https://github.com/roquerodrigo/ttlock-ble).

## Features

- **Local BLE control** — lock, unlock, and state queries run over the lock's BLE link; the TTLock cloud is only contacted once at setup to download per-lock keys.
- **Real-time push events** — keypad presses, fingerprint reads, IC-card swipes, mechanical key turns, and auto-lock fires arrive as Home Assistant events the moment the lock emits them.
- **Battery sensor** — diagnostic entity refreshed by every poll *and* every push, no extra BLE traffic.
- **2FA-aware config flow** — handles TTLock's "new device" verification by emailing a one-time code and prompting for it.
- **Works without a cloud account** — a lock initialised locally can be added by entering its key directly, no TTLock account involved at any point.
- **Passive state tracking** — the bolt position and battery level are read from the lock's own BLE advertisements, with no connection and no battery cost. This is what catches an auto-lock or an operation done from the official app.
- **Connects only on demand** — nothing is held open. A session is opened when a command needs the lock, when the lock advertises that it has records worth reading, or when the permanent connection option asks for one.
- **Reauth + reconfigure** — re-prompt for credentials in place when the cloud rejects the cached login, or edit them via the integration's three-dot menu.
- **Diagnostics** — downloadable dump with credentials/keys redacted.
- **Translations** — English and Brazilian Portuguese (parity enforced by tests).

## Entities

Each configured lock produces one HA device, named with the model, hardware and firmware the lock reports about itself, carrying up to six entities:

| Entity | Domain | Purpose |
|---|---|---|
| `lock.<alias>` | `lock` | Locked/unlocked state, with optimistic updates, `locking`/`unlocking` transitional states and a post-command settle window. |
| `sensor.<alias>_battery` | `sensor` | Battery percentage (diagnostic). |
| `binary_sensor.<alias>_bluetooth_connection` | `binary_sensor` | Whether a BLE session is open right now (connectivity, diagnostic). A healthy idle lock holds none, so `off` says nothing about whether the lock is reachable. |
| `event.<alias>_log` | `event` | Fires for every new operation-log record read from the lock. |
| `sensor.<alias>_last_seen` | `sensor` | When the lock was last heard from, read from HA's own advertisement history (diagnostic). |
| `switch.<alias>_sound` | `switch` | The lock's keypad/lock beep. Assumed state — the firmware reports no readback — and only created for an admin key that carries an admin passcode, which a manually entered key usually does not. |

The event entity classifies each record as `unlock`, `lock`, `unlock_failed`, `password_change` or `other`, and attaches `record_type` and `battery` always, plus `timestamp`, `uid`, `credential`, `key_id` and `accessory_battery` when the record carries them. `credential` is only populated for record types where the value is an identifier (card number, fingerprint id, fob MAC) — record types where it would be a working door code never expose it.

## Installation

1. Install via HACS using the button above, or add this repo as a custom HACS repository (category: Integration).
2. Restart Home Assistant.
3. Settings → Devices & Services → Add Integration → **TTLock BLE**.
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

Only these reach the wire. The rest of what the cloud returns per key — user id, lock-flag position, validity window — is never read by the Bluetooth layer, which addresses the lock with a zeroed user id and the firmware's "permanent key" date literals regardless.

If the lock is in range when the form is submitted, the protocol type, version and scene are checked against what it broadcasts, so a wrong value is caught there instead of becoming a lock that never answers. Getting a value wrong later is fixable through the integration's three-dot menu → **Reconfigure**.

The Bluetooth radio HA already manages (USB dongle, built-in adapter, or proxy) discovers the lock automatically — no additional configuration.

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
├── __init__.py        # config-entry lifecycle: setup / unload / reload
├── advertisement.py   # TtlockBleAdvertisementTracker: state from advertisements
├── api.py             # TtlockBleApiClient: TTLockCloud wrapper (cloud bootstrap only)
├── binary_sensor.py   # TtlockBleConnectionBinarySensor: live BLE link state
├── brand/             # icon / logo PNGs (local placeholder for HA brand registry)
├── config_flow.py     # menu / cloud / manual / verify_code / reauth / reconfigure
├── connection.py      # TtlockBleConnection: persistent BLE session per lock
├── const.py           # DOMAIN, LOGGER, defaults
├── coordinator.py     # DataUpdateCoordinator polling each connection
├── data/              # one TypedDict/dataclass per file + type aliases in __init__.py
├── device_description_store.py  # per-lock model / hardware / firmware, persisted
├── diagnostics.py     # redacted credentials/keys
├── entity.py          # base CoordinatorEntity with DeviceInfo
├── event.py           # TtlockBleLogEvent: operation-log records as HA events
├── exceptions/        # one file per exception class
├── lock.py            # TtlockBleLock: LockEntity backed by the connection
├── manifest.json
├── manual_key.py      # TtlockBleManualKey: key entry for cloud-less locks
├── options_flow.py    # TtlockBleOptionsFlow: permanent_connection
├── record_store.py    # persisted operation-log cursor per lock
├── sensor.py          # TtlockBleBatterySensor + TtlockBleLastSeenSensor
├── switch.py          # TtlockBleSoundSwitch: the lock's beep (admin keys only)
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

## License

[MIT](LICENSE)
