# Home Assistant TTLock BLE

[![HACS Validate](https://github.com/roquerodrigo/ha-ttlock-ble/actions/workflows/validate.yml/badge.svg)](https://github.com/roquerodrigo/ha-ttlock-ble/actions/workflows/validate.yml)
[![Lint](https://github.com/roquerodrigo/ha-ttlock-ble/actions/workflows/lint.yml/badge.svg)](https://github.com/roquerodrigo/ha-ttlock-ble/actions/workflows/lint.yml)
[![CodeQL](https://github.com/roquerodrigo/ha-ttlock-ble/actions/workflows/codeql.yml/badge.svg)](https://github.com/roquerodrigo/ha-ttlock-ble/actions/workflows/codeql.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)

Local control of TTLock smart locks over Bluetooth, for [Home Assistant](https://www.home-assistant.io/). Lock / unlock, battery level and real-time push events flow over BLE — no cloud round-trip on every operation. Built on the sibling Python SDK [`ttlock-ble`](https://github.com/roquerodrigo/ttlock-ble).

## Add to Home Assistant

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=roquerodrigo&repository=ha-ttlock-ble&category=integration)

## Features

- **Local BLE control** — lock, unlock, and state queries run over the lock's BLE link; the TTLock cloud is only contacted once at setup to download per-lock keys.
- **Real-time push events** — keypad presses, fingerprint reads, IC-card swipes, mechanical key turns, and auto-lock fires arrive as Home Assistant events the moment the lock emits them.
- **Battery sensor** — diagnostic entity refreshed by every poll *and* every push, no extra BLE traffic.
- **2FA-aware config flow** — handles TTLock's "new device" verification by emailing a one-time code and prompting for it.
- **Persistent BLE session with drop-storm cooldown** — keeps the link warm to receive push events, but backs off for 5 minutes after three short drops to protect the lock's battery.
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
4. Enter the TTLock cloud email + password you use in the official app.
5. If TTLock has never seen this Home Assistant before, it will email a verification code — paste it into the next step.
6. The integration syncs every lock visible on the account and creates the entities. From this point on, all lock / unlock / state operations stay on Bluetooth.

The Bluetooth radio HA already manages (USB dongle, built-in adapter, or proxy) discovers the lock automatically — no additional configuration.

## Options

Settings → Devices & Services → TTLock BLE → **Configure** lets you tune:

- `scan_interval` (default 300 s, minimum 60 s) — how often the coordinator polls the lock for state when no push events are arriving.

To edit credentials without removing and re-adding, use the integration's three-dot menu → **Reconfigure**.

## How it works

The lock's TTLock firmware aggressively closes idle BLE sessions (~5 s of silence and it drops). The integration:

1. Keeps a persistent BLE session via `connection.py`, reconnecting on every drop signalled by bleak.
2. Detects when the lock is in idle-sleep mode (≥ 3 sub-30 s sessions) and enters a 5-minute cooldown so we don't drain its battery thrashing.
3. After a user-initiated `lock`/`unlock`, the SDK keeps the link alive for 25 s so push events (the lock's reports of keypad operations, auto-locks, etc.) reach Home Assistant in real time.
4. Each push event carries the decoded `lock_state` and `battery` when the firmware emits a heartbeat-style payload, letting the entities update without a follow-up query.

## Useful commands

```bash
scripts/setup      # install dependencies (requirements.txt)
scripts/develop    # start Home Assistant in debug mode with the integration loaded
scripts/lint       # ruff format + check + mypy
pytest             # run tests with the 95 % coverage gate
```

Each script auto-detects `./.venv` and prepends it to `PATH` — no `source .venv/bin/activate` needed.

HA runs with config in `config/` and `PYTHONPATH` pointing at the repo root. To reset entity/device IDs during development:

```bash
rm config/.storage/core.entity_registry config/.storage/core.device_registry
```

## Layout

```
custom_components/ttlock_ble/
├── __init__.py        # async_setup_entry / unload / reload + bluetooth callbacks
├── api.py             # TtlockBleApiClient: TTLockCloud wrapper (cloud bootstrap only)
├── brand/             # icon / logo PNGs (local placeholder for HA brand registry)
├── config_flow.py     # user / verify_code / reauth_confirm / reconfigure steps
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
├── options_flow.py    # TtlockBleOptionsFlow: scan_interval
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
- **`validate.yml`** — `hassfest` + HACS validation; push/PR to `main` and a daily cron
- **`codeql.yml`** — GitHub CodeQL security scan; push/PR to `main` and a weekly cron

## License

[MIT](LICENSE)
