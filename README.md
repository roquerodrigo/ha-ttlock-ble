# Home Assistant TTLock BLE

[![CI](https://github.com/roquerodrigo/ha-ttlock-ble/actions/workflows/ci.yml/badge.svg)](https://github.com/roquerodrigo/ha-ttlock-ble/actions/workflows/ci.yml)
[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)

[![Sponsor](https://img.shields.io/badge/Sponsor-%E2%9D%A4-db61a2?logo=githubsponsors&logoColor=white&style=for-the-badge)](https://github.com/sponsors/roquerodrigo)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=roquerodrigo&repository=ha-ttlock-ble&category=integration)

---

Local control of TTLock smart locks over Bluetooth, for [Home Assistant](https://www.home-assistant.io/). Lock / unlock, battery level and real-time push events flow over BLE — no cloud round-trip on every operation. Built on the sibling Python SDK [`ttlock-ble`](https://github.com/roquerodrigo/ttlock-ble).

## Features

- **Local BLE control** — lock, unlock, and state queries run over the lock's BLE link; the TTLock cloud is only contacted once at setup to download per-lock keys.
- **Real-time push events** — keypad presses, fingerprint reads, IC-card swipes, mechanical key turns, and auto-lock fires arrive as Home Assistant events the moment the lock emits them.
- **Battery sensor** — diagnostic entity refreshed by every poll *and* every push, no extra BLE traffic.
- **Clock alignment** — the lock's own clock, which stamps every operation-log record, is compared against local time once a day on a session something else already opened, and corrected when it has wandered. A diagnostic sensor reports the measured drift.
- **Bluetooth discovery** — a lock in range of any radio Home Assistant manages shows up on its own as a discovered device; the address and the frame header come off the advertisement, so only the keys are left to provide.
- **2FA-aware config flow** — handles TTLock's "new device" verification by emailing a one-time code and prompting for it.
- **Other TTLock-based apps** — accounts created in the Schlage Breeze app sign in the same way, by picking the app at setup.
- **Door sensor** — a lock with a paired door sensor gets a door entity, created the first time the lock reports the door.
- **Who unlocked** — every log event says what kind of credential was used, its identifier and, once named, whose it is; a sensor keeps the last unlock. Fingerprints, cards and passcodes can each be given the name of the person they belong to.
- **Works without a cloud account** — a lock initialised locally can be added by entering its key directly, no TTLock account involved at any point.
- **Passive state tracking** — the bolt position and battery level are read from the lock's own BLE advertisements, with no connection and no battery cost. This is what catches an auto-lock or an operation done from the official app.
- **Connects only on demand** — nothing is held open. A session is opened when a command needs the lock, when the lock advertises that it has records worth reading, or when the permanent connection option asks for one.
- **Reauth + reconfigure** — re-prompt for credentials in place when the cloud rejects the cached login, or edit them via the integration's three-dot menu.
- **Diagnostics** — downloadable dump with credentials/keys redacted.
- **Translations** — English, Brazilian Portuguese and Hebrew (parity enforced by tests).

## Entities

Each configured lock produces one HA device, named with the model, hardware and firmware the lock reports about itself, carrying up to twelve entities, plus one per known fingerprint, card and passcode:

| Entity | Domain | Purpose |
|---|---|---|
| `lock.<alias>` | `lock` | Locked/unlocked state, with optimistic updates, `locking`/`unlocking` transitional states and a post-command settle window. |
| `sensor.<alias>_battery` | `sensor` | Battery percentage (diagnostic). |
| `binary_sensor.<alias>_bluetooth_connection` | `binary_sensor` | Whether a BLE session is open right now (connectivity, diagnostic). A healthy idle lock holds none, so `off` says nothing about whether the lock is reachable. |
| `binary_sensor.<alias>_door` | `binary_sensor` | Whether the door is open, from the door-sensor records in the operation log. Created the first time the lock reports its door, so a lock without a paired sensor never gets one; it follows the door a few seconds behind, once the lock's new records have been read. |
| `event.<alias>_log` | `event` | Fires for every new operation-log record read from the lock. |
| `sensor.<alias>_last_seen` | `sensor` | When the lock was last heard from, read from HA's own advertisement history (diagnostic). |
| `sensor.<alias>_clock_drift` | `sensor` | How far the lock's own clock was off local time when last compared, in seconds, positive when it runs ahead (diagnostic). `unknown` until a session opened for something else has carried a comparison. |
| `sensor.<alias>_last_unlocked_by` | `sensor` | Who last unlocked the lock, from its operation log (see [Who unlocked](#who-unlocked)). |
| `switch.<alias>_sound` | `switch` | The lock's keypad/lock beep, read back from the lock on sessions opened for something else and re-read at most hourly. `unknown` until a session has carried a read. Only created for an admin key that carries an admin passcode, which a manually entered key usually does not. |

The event entity classifies each record as `unlock`, `lock`, `unlock_failed`, `password_change` or `other`, and attaches `record_type` and `battery` always, plus `timestamp`, `uid`, `credential_type`, `credential`, `credential_name`, `key_id` and `accessory_battery` when the record carries them.

### Who unlocked

Three event attributes describe the credential behind a record:

| Attribute | Meaning |
|---|---|
| `credential_type` | What was used: `fingerprint`, `card`, `passcode`, `app`, `gateway`, `key_fob`, `wireless_keypad`, `mechanical_key`, `face`, `palm_vein` or `qr_code`. |
| `credential` | Its identifier: the fingerprint number, the card number or the accessory MAC. For a passcode, the label of a known passcode — its first digit and last two, as in `1•••56` — and never the code itself; a code the lock refused shows nothing. |
| `credential_name` | Whose it is, when that is known: the name given to a fingerprint, card or passcode (see [Credentials](#credentials)), or `Home Assistant` for a lock or unlock sent over BLE by this integration. |

`sensor.<alias>_last_unlocked_by` keeps the last unlock the log reported. Its state is the `credential_name` when there is one, otherwise the `credential` — the number of a fingerprint nobody named yet, or the label of a passcode — and `unknown` when the record carries neither. It carries `credential_type`, `credential` and `unlocked_at` as attributes and survives a restart. A door sensor reporting the door open does not replace it, and a record older than the unlock already shown is ignored.

### Credentials

Every fingerprint, card and passcode the lock is known to hold gets a `text` entity on the lock's device. Its value is the name of the person the credential belongs to, empty until set, and becomes the `credential_name` of that credential's log events.

| Entity | Domain | Purpose |
|---|---|---|
| Fingerprint \<number\> | `text` | One per enrolled fingerprint, named by the number the official app shows for it. Admin keys only. |
| Card \<number\> | `text` | One per enrolled card, named by its number. Admin keys only. |
| Passcode \<label\> | `text` | One per known passcode, named by its first digit and last two (`1•••56`). Two passcodes showing the same digits are told apart with a suffix (`1•••56 #2`). |
| Enrolled fingerprints | `sensor` | How many fingerprints the lock lists (diagnostic). `unknown` until a session has carried a read. Admin keys only. |
| Enrolled cards | `sensor` | How many cards the lock lists (diagnostic). `unknown` until a session has carried a read. Admin keys only. |
| Refresh credentials | `button` | Reads the lists now instead of on the next session. No advertisement or push event tells a credential change apart from any other record, so the lists are otherwise read at most every 30 minutes, on a session opened for something else. Fails with an error when the lock cannot be reached. Admin keys only. |

The lock lists its fingerprints and cards completely, so one it no longer lists loses its entity and its name. Passcodes work differently: the lock cannot list a passcode the official app generated offline until it has been used at the keypad. They are therefore also learned from the operation log, which names the code on every use, change, deletion and expiry: a passcode is added the first time it is used, keeps its name when it is changed, and is removed when the log records its deletion or expiry, or that every passcode was cleared. A single-use passcode stays until one of those records arrives. The code itself is never stored in clear, nor shown in an entity, a state or an attribute.

Names and the known credentials are kept across restarts. The lists say nothing about cyclic (day-of-week or time-range) restrictions, so a credential shown here may still be limited to certain days or hours.

## Installation

1. Install via HACS using the button above, or add this repo as a custom HACS repository (category: Integration).
2. Restart Home Assistant.
3. Settings → Devices & Services → either pick the **TTLock BLE** card already waiting under *Discovered* (any lock in range of a radio Home Assistant manages announces itself), or Add Integration → **TTLock BLE**.
4. Choose how the keys are obtained:
   - **Sign in to a TTLock account** — pick the app your account was created in (*TTLock / DLock-XP*, or *Schlage Breeze*), then enter the email + password you use in it. If TTLock has never seen this Home Assistant before it emails a verification code; paste it into the next step. Every lock on the account is synced at once.
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
├── __init__.py        # config-entry lifecycle: setup / unload / reload
├── advertisement.py   # TtlockBleAdvertisementTracker: state from advertisements
├── api.py             # TtlockBleApiClient: TTLockCloud wrapper (cloud bootstrap only)
├── binary_sensor.py   # TtlockBleConnectionBinarySensor + TtlockBleDoorBinarySensor
├── brand/             # icon / logo PNGs (local placeholder for HA brand registry)
├── button.py          # TtlockBleRefreshFingerprintsButton: force a fingerprint read (admin keys only)
├── config_flow.py     # menu / bluetooth / cloud / manual / verify_code / reauth / reconfigure
├── connection.py      # TtlockBleConnection: persistent BLE session per lock
├── credential_resolver.py  # TtlockBleCredentialResolver: type, identifier and name behind a log record
├── credential_type.py      # TtlockBleCredentialType: the credential each record type names
├── const.py           # DOMAIN, LOGGER, defaults
├── coordinator.py     # DataUpdateCoordinator polling each connection
├── data/              # one TypedDict/dataclass per file + type aliases in __init__.py
├── device_description_store.py  # per-lock model / hardware / firmware, persisted
├── diagnostics.py     # redacted credentials/keys
├── entity.py          # base CoordinatorEntity with DeviceInfo
├── event.py           # TtlockBleLogEvent: operation-log records as HA events
├── exceptions/        # one file per exception class
├── credential_store.py     # persisted fingerprints, cards, passcodes and their names per lock
├── credential_tracker.py   # one name entity per known credential, restored and pruned
├── lock.py            # TtlockBleLock: LockEntity backed by the connection
├── manifest.json
├── manual_key.py      # TtlockBleManualKey: key entry for cloud-less locks
├── options_flow.py    # TtlockBleOptionsFlow: permanent_connection
├── passcode_ledger.py # TtlockBlePasscodeLedger: passcodes learned and forgotten from the log
├── clock_sync_store.py # persisted clock comparison per lock
├── record_store.py    # persisted operation-log cursor per lock
├── sensor.py          # battery, last-seen, clock-drift, fingerprint/card counts, last-unlocked-by sensors
├── switch.py          # TtlockBleSoundSwitch: the lock's beep (admin keys only)
├── text.py            # name entities: whose each fingerprint, card and passcode is
└── translations/
    ├── en.json
    ├── he.json
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
