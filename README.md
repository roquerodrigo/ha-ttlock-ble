# Home Assistant TTLock BLE

[![CI](https://github.com/roquerodrigo/ha-ttlock-ble/actions/workflows/ci.yml/badge.svg)](https://github.com/roquerodrigo/ha-ttlock-ble/actions/workflows/ci.yml)
[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)

Local control of TTLock smart locks over Bluetooth, for [Home Assistant](https://www.home-assistant.io/). Lock / unlock, battery level and real-time push events flow over BLE — no cloud round-trip on every operation. Built on the sibling Python SDK [`ttlock-ble`](https://github.com/roquerodrigo/ttlock-ble).

## Add to Home Assistant

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=roquerodrigo&repository=ha-ttlock-ble&category=integration)

## Features

- **Local BLE control** — lock, unlock, and state queries run over the lock's BLE link; the TTLock cloud is only contacted once at setup to download per-lock keys.
- **Real-time push events** — keypad presses, fingerprint reads, IC-card swipes, mechanical key turns, and auto-lock fires arrive as Home Assistant events the moment the lock emits them.
- **Battery sensor** — diagnostic entity refreshed by every poll *and* every push, no extra BLE traffic.
- **2FA-aware config flow** — handles TTLock's "new device" verification by emailing a one-time code and prompting for it.
- **Works without a cloud account** — a lock initialised locally can be added by entering its key directly, no TTLock account involved at any point.
- **Passive state tracking** — the bolt position and battery level are read from the lock's own BLE advertisements, with no connection and no battery cost. This is what catches an auto-lock or an operation done from the official app.
- **Persistent BLE session with a post-drop cooldown** — keeps the link warm to receive push events, and waits before reconnecting so a lock in idle-sleep isn't thrashed.
- **Reauth + reconfigure** — re-prompt for credentials in place when the cloud rejects the cached login, or edit them via the integration's three-dot menu.
- **Diagnostics** — downloadable dump with credentials/keys redacted.
- **Translations** — English and Brazilian Portuguese (parity enforced by tests).

## Entities

Each configured lock produces one HA device with three entities:

| Entity | Domain | Purpose |
|---|---|---|
| `lock.<alias>` | `lock` | Locked/unlocked state, with optimistic updates and a post-command settle window. |
| `sensor.<alias>_battery` | `sensor` | Battery percentage (diagnostic). |
| `event.<alias>_operation` | `event` | Fires on every push from the lock, with decoded `lock_state`, `battery`, `uid`, `record_id`, `timestamp` attributes when present. |

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

Settings → Devices & Services → TTLock BLE → **Configure** lets you tune:

- `scan_interval` (default 3600 s, minimum 60 s) — how often the coordinator opens a BLE session to read state. Every advertisement received postpones the next poll, so a lock in range is rarely polled at all; lowering this only adds connections (and battery drain) for a lock that has gone quiet.
- `reconnect_interval` (default 300 s, minimum 10 s) — how long the connection layer waits after the lock drops the BLE session before reconnecting. The lock closes every idle session within seconds, so this is effectively how often a session is reopened to listen for push events.
- `permanent_connection` (default off) — reconnect immediately after every drop, keeping the session open as continuously as the lock allows. Overrides `reconnect_interval` and increases the lock's battery drain; push events (keypad, auto-lock) arrive in real time in exchange.

To edit credentials without removing and re-adding, use the integration's three-dot menu → **Reconfigure**.

## How it works

The lock's TTLock firmware aggressively closes idle BLE sessions (~5 s of silence and it drops). The integration:

1. Reads the bolt position and battery level straight out of the lock's BLE advertisements. This costs no connection at all and is the only channel that reports an operation performed while Home Assistant is not connected — an auto-lock, the official app, a keypad code.
2. Keeps a persistent BLE session via `connection.py`, reconnecting on every drop signalled by bleak, and waiting out the configured `reconnect_interval` before doing so — or none at all with `permanent_connection`.
3. After a user-initiated `lock`/`unlock`, the SDK keeps the link alive for 25 s so push events (the lock's reports of keypad operations, auto-locks, etc.) reach Home Assistant in real time.
4. Each push event carries the decoded `lock_state` and `battery` when the firmware emits a heartbeat-style payload, letting the entities update without a follow-up query.

## Useful commands

```bash
scripts/setup      # install dependencies (requirements.txt)
scripts/develop    # start Home Assistant in debug mode with the integration loaded

# Lint and test directly (config lives in pyproject.toml):
uv run ruff format --check .
uv run ruff check .
uv run mypy custom_components/ttlock_ble
uv run pytest
```

Each `scripts/*` helper auto-detects `./.venv` and prepends it to `PATH` — no `source .venv/bin/activate` needed.

HA runs with config in `config/` and `PYTHONPATH` pointing at the repo root. To reset entity/device IDs during development:

```bash
rm config/.storage/core.entity_registry config/.storage/core.device_registry
```

## Layout

```
custom_components/ttlock_ble/
├── __init__.py        # async_setup_entry / unload / reload + bluetooth callbacks
├── advertisement.py   # TtlockBleAdvertisementTracker: state from advertisements
├── api.py             # TtlockBleApiClient: TTLockCloud wrapper (cloud bootstrap only)
├── brand/             # icon / logo PNGs (local placeholder for HA brand registry)
├── config_flow.py     # menu / cloud / manual / verify_code / reauth / reconfigure
├── manual_key.py      # TtlockBleManualKey: key entry for cloud-less locks
├── connection.py      # TtlockBleConnection: persistent BLE session per lock
├── const.py           # DOMAIN, LOGGER, defaults
├── coordinator.py     # DataUpdateCoordinator polling each connection
├── data.py            # TypedDicts + TtlockBleData dataclass
├── diagnostics.py     # redacted credentials/keys
├── entity.py          # base CoordinatorEntity with DeviceInfo
├── event.py           # TtlockBleOperationEvent push surface
├── exceptions/        # one file per exception class
├── lock.py            # TtlockBleLock: LockEntity backed by the connection
├── manifest.json
├── options_flow.py    # TtlockBleOptionsFlow: scan_interval, reconnect_interval, permanent_connection
├── sensor.py          # TtlockBleBatterySensor backed by polls + pushes
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

This wires ruff + basic file hygiene checks (`.pre-commit-config.yaml`) into every commit, mirroring the CI lint job.

## CI

- **`lint.yml`** — ruff (check + format) and mypy (Python 3.14)
- **`tests.yml`** — pytest with the 90 % coverage gate
- **`validate.yml`** — `hassfest` + HACS validation; push/PR to `main` and a daily cron
- **`codeql.yml`** — GitHub CodeQL security scan; push/PR to `main` and a weekly cron
- **`release.yml`** — release-please opens a release PR on every push to `main` based on conventional commits

## License

[MIT](LICENSE)
