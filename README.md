# TTLock BLE

<!-- ha-marketplace:exclude-start -->
[![CI](https://github.com/roquerodrigo/ha-ttlock-ble/actions/workflows/ci.yml/badge.svg)](https://github.com/roquerodrigo/ha-ttlock-ble/actions/workflows/ci.yml)
[![GitHub release](https://img.shields.io/github/v/release/roquerodrigo/ha-ttlock-ble)](https://github.com/roquerodrigo/ha-ttlock-ble/releases/latest)
[![Sponsor](https://img.shields.io/badge/Sponsor-%E2%9D%A4-db61a2?logo=githubsponsors&logoColor=white)](https://github.com/sponsors/roquerodrigo)

[![Open your Home Assistant instance and open a repository in the Marketplace.](https://my.home-assistant.io/badges/marketplace_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=roquerodrigo&repository=ha-ttlock-ble&category=integration)
<!-- ha-marketplace:exclude-end -->

Lock and unlock your TTLock smart lock from Home Assistant, follow its
battery and see who opened the door. Home Assistant talks to the lock over
Bluetooth, through the adapter or ESPHome Bluetooth proxy it already uses.
The TTLock cloud is contacted only once, at setup, to download the lock's
keys, and not at all if you enter the key yourself. Built on the
[ttlock-ble](https://github.com/roquerodrigo/ttlock-ble) library.

## Features

- Lock and unlock from Home Assistant. The lock shows Locking or Unlocking
  while the bolt moves.
- Follow the bolt and the battery even when the lock is used some other way:
  auto-lock, the keypad, a fingerprint or the official app. Home Assistant
  reads them from what the lock broadcasts, without connecting to it.
- Use every operation the lock records as an automation trigger: unlocks,
  locks, refused attempts and changes to its codes, cards and fingerprints.
- Name each fingerprint, card and passcode after the person it belongs to,
  and see who unlocked last.
- See whether the door is open, on locks with a paired door sensor.
- Turn the lock's beep on or off.
- Keep the lock's clock on time, so the times in its log are right.
- Locks in range show up on their own in Home Assistant, ready to set up.
- Check the signal and how reliably the lock connects, to find a weak link
  or a struggling Bluetooth proxy.

## Requirements

- Home Assistant 2026.10.0 or newer.
- Bluetooth in Home Assistant within range of the lock: a local adapter or
  an ESPHome Bluetooth proxy.
- A lock that works with the TTLock app or the Schlage Breeze app.
- The email and password of the TTLock or Schlage Breeze account that holds
  a key for the lock. A lock set up without an account can be added with its
  MAC address, AES key and unlock key instead.

<!-- ha-marketplace:exclude-start -->
## Installation

### Home Assistant Marketplace (recommended)

1. Select the **Open your Home Assistant instance** button above, or go to
   **Settings → Marketplace**, select **Add from link** in the upper-right
   corner, enter `roquerodrigo/ha-ttlock-ble` and select **Add**.
2. Select **Install**.
3. Restart Home Assistant.

The Marketplace ships with Home Assistant 2026.11 and later. On older
versions, add the repository to HACS as a custom repository of type
**Integration** and install it from there.

### Manual

1. Download `ttlock_ble.zip` from the
   [latest release](https://github.com/roquerodrigo/ha-ttlock-ble/releases/latest).
2. Extract it into `config/custom_components/ttlock_ble/`.
3. Restart Home Assistant.
<!-- ha-marketplace:exclude-end -->

## Configuration

A lock in range of Home Assistant's Bluetooth appears under **Discovered** in
**Settings → Devices & services**. Select **Add** on it. You can also go to
**Settings → Devices & services → Add integration** and search for
**TTLock BLE**.

Then choose how Home Assistant gets the lock's keys.

### Sign in to a TTLock account

| Field    | What to enter                                                                |
|----------|------------------------------------------------------------------------------|
| Email    | The email of your account                                                    |
| Password | The password of your account                                                 |
| App      | The app the account was created in: **TTLock / DLock-XP** or **Schlage Breeze** |

Accounts are separate per app, even with the same email. The first time you
sign in from this Home Assistant, TTLock emails you a verification code.
Enter it in the next step.

Every lock on the account is added at once. If you started from a
discovered lock, the account must hold a key for that lock.

To pick up a lock you added to the account later, or to drop one you
removed, open the integration and select **Reconfigure**. Enter the email and
password of the same account, and the keys are downloaded again. If TTLock
asks to verify Home Assistant again at that point, delete the integration
and add it back.

### Adding a lock without a TTLock account

A lock set up by a local Bluetooth tool, without a TTLock account, can be
added with its key. Each lock is added on its own.

| Field                     | What to enter                                                 | Default            |
|---------------------------|---------------------------------------------------------------|--------------------|
| Lock MAC address          | In the form `AA:BB:CC:DD:EE:FF`                               |                    |
| AES key                   | 16 bytes of hex, continuous or separated (`2c,3d,...`)        |                    |
| Unlock key                | Digits, as your setup tool produced them                      |                    |
| Admin passcode (optional) | Digits. Lets Home Assistant correct the lock's clock          |                    |
| Name (optional)           | A name for the lock                                           | `TTLock` + the MAC |
| Protocol type             | Part of the header the lock expects, from 0 to 255            | 5                  |
| Protocol version          | Part of the header the lock expects, from 0 to 255            | 3                  |
| Scene                     | Part of the header the lock expects, from 0 to 255            | 2                  |
| Group ID                  | Part of the header the lock expects, from 0 to 255            | 1                  |
| Organisation ID           | Part of the header the lock expects, from 0 to 255            | 1                  |

The defaults suit most locks. When you start from a discovered lock, the MAC
address, the name, the protocol type, the protocol version and the scene are
already filled in, so only the keys are left to type. If the lock is in range
when you submit, Home Assistant checks the protocol type, version and scene
against what the lock broadcasts.

To correct any value later, open the integration and select
**Reconfigure**.

## Options

Open the integration and select **Configure**.

| Setting              | Default | Effect                                                                 |
|----------------------|---------|------------------------------------------------------------------------|
| Permanent connection | Off     | Keeps a Bluetooth connection to the lock open and reopens it when it drops |

With the option off, Home Assistant connects only to run a command or to read
new records the lock announces. The bolt and the battery come from the lock's
broadcasts, which cost nothing.

With the option on, commands answer right away and Home Assistant reads the
bolt about every two seconds while connected. This costs the lock battery. While
the connection is open the lock stops broadcasting, so Home Assistant reads
its log after every event the lock sends instead.

## Entities

Each lock is a device, named after the lock, with the model, hardware and
firmware the lock reports about itself.

| Entity                  | Type          | Shows                                                         |
|-------------------------|---------------|---------------------------------------------------------------|
| Lock                    | Lock          | Locked, Unlocked, Locking or Unlocking                        |
| Last unlocked by        | Sensor        | Who unlocked last (see Who unlocked below)                    |
| Log                     | Event         | Every operation the lock records (see Events below)           |
| Door                    | Binary sensor | Open or Closed. Appears the first time the lock reports its door |
| Battery                 | Sensor        | Percentage. Diagnostic                                        |
| Bluetooth connection    | Binary sensor | Whether a connection is open right now. Diagnostic            |
| Last seen               | Sensor        | When the lock was last heard. Diagnostic                      |
| Signal strength         | Sensor        | dBm of the last broadcast heard. Diagnostic                   |
| Signal quality          | Sensor        | The same signal as a percentage. Diagnostic                   |
| Connection time         | Sensor        | Seconds the last connection took to open. Diagnostic          |
| Connection success rate | Sensor        | Share of the last 20 connection attempts that worked. Diagnostic |
| Clock drift             | Sensor        | Seconds the lock's clock was off when last checked. Diagnostic |
| Sound                   | Switch        | The lock's beep. Admin key only (see Credentials below)       |

Bluetooth connection is off most of the time on a healthy lock, because Home
Assistant connects only when needed. Last seen and the signal sensors tell
you whether the lock is in range. Signal strength names the adapter or proxy
that heard the lock in its `source` attribute. Signal quality reads 0 % at
-100 dBm and 100 % at -50 dBm.

### Credentials

| Entity                  | Type   | Shows                                                         |
|-------------------------|--------|---------------------------------------------------------------|
| Passcode \<label\>      | Text   | The name of the person a passcode belongs to                  |
| Fingerprint \<number\>  | Text   | The name of the person a fingerprint belongs to               |
| Card \<number\>         | Text   | The name of the person a card belongs to                      |
| Enrolled fingerprints   | Sensor | How many fingerprints the lock holds. Diagnostic              |
| Enrolled cards          | Sensor | How many cards the lock holds. Diagnostic                     |
| Refresh credentials     | Button | Reads the fingerprints, cards and passcodes from the lock now |

A passcode is labelled with its first digit and its last two, as in
`1•••56`. Two passcodes that look the same get a suffix, as in `1•••56 #2`.
The code itself is never shown or stored in clear.

Passcode entities appear for every lock. A passcode appears the first time
someone uses it at the keypad, and disappears when the lock records that it
was deleted or expired, or that all passcodes were cleared. With an admin
key, the passcodes the lock lists appear too.

The fingerprint and card entities, the counts, the Refresh credentials
button and the Sound switch need the admin key of the TTLock account that
set up the lock. A lock added with a manually entered key does not get them.
Fingerprints and cards appear on locks that support them, and come and go
as the lock lists them. Home Assistant reads the lists at most every 30
minutes, on a connection opened for something else. Press
**Refresh credentials** after you add or remove one to see it at once.
Home Assistant shows an error if the lock is out of reach. The counts and
the Sound switch read Unknown until Home Assistant has read them from the
lock.

### Who unlocked

Type a name into a fingerprint, card or passcode entity, and that name shows
up in the Log events and in Last unlocked by. A lock or unlock sent from
Home Assistant reads `Home Assistant`, or `Alice (via Home Assistant)` when
a user named Alice pressed the button.

Last unlocked by shows the name when there is one. Otherwise it shows the
number of the fingerprint or card, or the label of the passcode. Its
attributes are `credential_type`, `credential` and `unlocked_at`. It keeps
its value across restarts.

## Events

The Log entity fires for each new record read from the lock, with one of
these event types:

| Event type        | Fires for                                                          |
|-------------------|--------------------------------------------------------------------|
| `unlock`          | Any successful unlock, and the door sensor reporting the door open |
| `lock`            | Any lock, and the door sensor reporting the door closed            |
| `unlock_failed`   | A wrong code, an expired code, a refused card or fingerprint       |
| `password_change` | A passcode, card, fingerprint, face or palm vein added, changed or removed |
| `other`           | Anything else, such as a reboot or an alarm                        |

Each event carries these attributes:

| Attribute           | Meaning                                                                    |
|---------------------|----------------------------------------------------------------------------|
| `record_type`       | The exact record, for example `fr_unlock_succeed`                          |
| `battery`           | The lock's battery when the record was written                             |
| `timestamp`         | When it happened, by the lock's clock                                      |
| `credential_type`   | `fingerprint`, `card`, `passcode`, `app`, `gateway`, `key_fob`, `wireless_keypad`, `mechanical_key`, `face`, `palm_vein` or `qr_code` |
| `credential`        | The fingerprint number, card number, accessory MAC or passcode label       |
| `credential_name`   | The name you gave the credential, or `Home Assistant`                      |
| `uid`               | The user ID in the record                                                  |
| `key_id`            | The key ID in the record                                                   |
| `accessory_battery` | The battery of the keypad or key fob used                                  |

All but `record_type` and `battery` appear only when the record carries them.
A refused passcode has no `credential`.

To get a notification when the door is unlocked (replace
`event.front_door_log` with your lock's Log entity):

```yaml
triggers:
  - trigger: state
    entity_id: event.front_door_log
    not_from: unavailable
conditions:
  - condition: state
    entity_id: event.front_door_log
    attribute: event_type
    state: unlock
actions:
  - action: notify.notify
    data:
      message: >-
        Front door unlocked by
        {{ trigger.to_state.attributes.credential_name
           or trigger.to_state.attributes.credential
           or trigger.to_state.attributes.credential_type }}
```

## How it works

The lock broadcasts its bolt position and battery level over Bluetooth.
Home Assistant follows those broadcasts and connects only when there is a
reason to: a lock or unlock command, new records the lock announces, or a
bolt position Home Assistant does not know yet. Everything stays between
Home Assistant and the lock.

After a lock or unlock, the connection stays open for 25 seconds, so what
happens at the lock in that time reaches Home Assistant at once. The log
records follow a few seconds after each operation, once Home Assistant has
read them.

After a restart, the lock reads Unknown until it is next heard awake.
Nothing connects to the lock at startup.

While a connection is open anyway, Home Assistant also checks the lock's
clock once a day and corrects it when it is more than 30 seconds off. The
correction needs the admin passcode. Without it, Clock drift still reports
how far off the clock is.

## Troubleshooting

**Commands through an ESPHome proxy take 20 seconds or fail now and then.**
Look at Connection time and Connection success rate. Connections that either
open within a couple of seconds or not at all point at how the proxy listens
for the lock, not at the signal. An idle lock broadcasts about every 0.9
seconds. While opening a connection, an ESP32 listens 30 ms out of every
60 ms, and the lock's interval is a multiple of that cycle. A broadcast that
falls in the half the proxy is not listening to keeps falling there, and the
attempt runs out its 20 seconds. Make the proxy listen the whole time by
adding this to its ESPHome configuration, on the ESP-IDF framework:

```yaml
esphome:
  build_flags:
    - -DBTM_BLE_SCAN_FAST_INT=56
    - -DBTM_BLE_SCAN_FAST_WIN=56
```

Both values are in units of 0.625 ms, so 56 is 35 ms. They change the ESP32
Bluetooth defaults, which ESPHome has no option for, and apply to every
connection the proxy opens. On an ESP32-C6 proxy running ESPHome 2026.10,
this took a lock from about two failed attempts in three to 45 connections
out of 45 on the first attempt, usually in about 2 seconds. Keep the proxy's
`logger` at `WARN` too: on a Wi-Fi proxy the logs share the radio with
Bluetooth, and more detailed levels can slow connections down.

**The lock shows Unknown after a restart.** Home Assistant waits for the
lock to broadcast while awake instead of connecting at startup. Using the
lock, or sending it a command, fills it in.

**A neighbour's lock keeps showing up under Discovered.** Select **Ignore**
on it.

**"This account holds no key for the lock that was found."** The account you
signed in with does not hold the discovered lock. Sign in with the account
that owns it, or enter its key manually.

**"The lock is broadcasting a different protocol type, version or scene than
the one entered."** One of those three values is wrong. Check them against
your lock data.

**Something else is wrong.** Download the diagnostics from the integration's
menu and attach them to an
[issue](https://github.com/roquerodrigo/ha-ttlock-ble/issues), with debug
logs if you can. The email, password and lock keys are removed from the
file.

## Known limitations

- An auto-lock writes no record in the lock's log. The Lock entity follows
  it, but no Log event fires.
- A lock or unlock sent from Home Assistant is named after the user only if
  its record is read before Home Assistant restarts.
- A passcode the official app generated offline appears only after it is
  first used at the keypad.
- Day-of-week and time-of-day limits on a credential are not shown.
- The lock has no jam signal and no separate latch, so the Lock entity never
  shows Jammed or Open.
- Connection success rate starts over at every restart.
- Some older locks are not discovered automatically. Add them from
  **Add integration** instead.

## Support

This integration is built and maintained on personal time, on hardware bought
for the purpose. If it is useful to you, consider
[sponsoring the work](https://github.com/sponsors/roquerodrigo). It keeps the
devices, the testing and the releases coming.

Report bugs and ideas in the
[issue tracker](https://github.com/roquerodrigo/ha-ttlock-ble/issues).

<!-- ha-marketplace:exclude-start -->
## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for the development setup and
workflow, and [CODE_STYLE.md](CODE_STYLE.md) for the code conventions.

## License

[MIT](LICENSE)
<!-- ha-marketplace:exclude-end -->
