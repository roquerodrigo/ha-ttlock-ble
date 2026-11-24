# Contributing

Bug reports, ideas and pull requests are welcome.

## Reporting a bug

Open an [issue](https://github.com/roquerodrigo/ha-ttlock-ble/issues/new/choose)
with:

- the Home Assistant version, the integration version and the lock model;
- whether the lock was added with a TTLock account or a manually entered key,
  and whether it is reached through a local adapter or an ESPHome proxy;
- what you did, what you expected and what happened;
- the diagnostics downloaded from the integration's menu (the email, password
  and lock keys are redacted) and the relevant debug log lines.

## Development setup

The project uses [uv](https://docs.astral.sh/uv/) and Python 3.14. A dev
container (`.devcontainer.json`) with everything installed is also provided.

```bash
scripts/setup      # install the dev and lint dependencies into .venv
scripts/develop    # run Home Assistant at http://localhost:8123 with this integration loaded
```

`scripts/develop` uses the configuration in [`config/`](config/). To reset
entity and device IDs during development, stop Home Assistant and run:

```bash
rm config/.storage/core.entity_registry config/.storage/core.device_registry
```

The Bluetooth protocol and the TTLock cloud login live in the
[`ttlock-ble`](https://github.com/roquerodrigo/ttlock-ble) library. Its
version is pinned in both `manifest.json` and `pyproject.toml`, and a test
fails when the two differ.

## Checks

Run these before opening a pull request. CI runs the same ones, and
`pre-commit install` runs the first three on every commit, along with basic
file hygiene checks.

```bash
uv run ruff format --check .                 # format
uv run ruff check .                          # lint
uv run mypy custom_components/ttlock_ble     # type-check
uv run pytest                                # tests, coverage must stay at 90 % or more
```

Read [CODE_STYLE.md](CODE_STYLE.md) before adding or restructuring code.
[CLAUDE.md](CLAUDE.md) describes the architecture and the reasons behind it.

## Project layout

```
custom_components/ttlock_ble/
├── __init__.py                  # config entry setup, unload and reload
├── advertisement.py             # lock state from Bluetooth advertisements
├── api.py                       # TTLock cloud client, used only by the config flow
├── binary_sensor.py             # Bluetooth connection and door sensors
├── brand/                       # icon and logo
├── button.py                    # Refresh credentials button (admin keys only)
├── clock_sync_store.py          # persisted clock comparison per lock
├── command_journal.py           # recent lock and unlock commands, to name them in the log
├── config_flow.py               # menu, Bluetooth discovery, cloud, manual key, reauth, reconfigure
├── connection.py                # Bluetooth session per lock
├── connection_quality.py        # recent connection attempts: success rate, connect time
├── const.py                     # domain, logger, option keys
├── coordinator.py               # reads state, log, clock, sound and credentials on each session
├── credential_resolver.py       # type, identifier and name behind a log record
├── credential_store.py          # persisted fingerprints, cards, passcodes and their names
├── credential_tracker.py        # one name entity per known credential
├── credential_type.py           # the credential each record type names
├── data/                        # one TypedDict or dataclass per file
├── device_description_store.py  # persisted model, hardware and firmware per lock
├── diagnostics.py               # diagnostics with credentials and keys redacted
├── entity.py                    # base entity and device info
├── event.py                     # Log event entity
├── exceptions/                  # one file per exception class
├── key_privileges.py            # what a key may administer
├── lock.py                      # Lock entity
├── lock_command.py              # lock and unlock command kinds
├── manifest.json
├── manual_key.py                # key entry for locks without a cloud account
├── options_flow.py              # Permanent connection option
├── passcode_ledger.py           # passcodes learned and forgotten from the log
├── record_store.py              # persisted operation-log cursor per lock
├── sensor.py                    # battery, last seen, signal, connection, clock drift, counts, last unlocked by
├── switch.py                    # Sound switch (admin keys only)
├── text.py                      # name entities for fingerprints, cards and passcodes
└── translations/                # en.json, he.json, pt-BR.json
```

## Continuous integration

- `ci.yml` runs the lint job (ruff and mypy), the tests with the coverage
  gate and the Home Assistant Marketplace validation on every pull request
  and on every push to `main`.
- `codeql.yml` runs the CodeQL security scan on every pull request, on every
  push to `main` and weekly.
- `release.yml` runs after a green CI on `main`. It keeps a release pull
  request up to date from the commit messages, and when that pull request is
  merged it creates the release and attaches `ttlock_ble.zip`.
- `auto-assign.yml` assigns new issues and pull requests to the maintainer
  and requests the maintainer's review on pull requests.

## Pull requests

1. Fork the repository and branch from `main`.
2. Write commit messages as [Conventional Commits](https://www.conventionalcommits.org/).
   Releases and their notes are generated from them. Mark breaking changes
   with `!` or a `BREAKING CHANGE:` footer.
3. Update every file in `translations/` (`en.json`, `pt-BR.json` and
   `he.json`) together when you change user-facing strings. A test fails when
   their keys differ.
4. Update the README when behaviour, configuration or entities change.
5. Fill in the pull request template.

## License

Contributions are released under the project's [MIT License](LICENSE).
