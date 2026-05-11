# Home Assistant Integration Blueprint

[![HACS Validate](https://github.com/roquerodrigo/ha-integration-blueprint/actions/workflows/validate.yml/badge.svg)](https://github.com/roquerodrigo/ha-integration-blueprint/actions/workflows/validate.yml)
[![Lint](https://github.com/roquerodrigo/ha-integration-blueprint/actions/workflows/lint.yml/badge.svg)](https://github.com/roquerodrigo/ha-integration-blueprint/actions/workflows/lint.yml)
[![CodeQL](https://github.com/roquerodrigo/ha-integration-blueprint/actions/workflows/codeql.yml/badge.svg)](https://github.com/roquerodrigo/ha-integration-blueprint/actions/workflows/codeql.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)

Template for creating custom [Home Assistant](https://www.home-assistant.io/) integrations distributable via [HACS](https://hacs.xyz/).

Based on [ludeeus/integration_blueprint](https://github.com/ludeeus/integration_blueprint), with adaptations used in the [@roquerodrigo](https://github.com/roquerodrigo) integrations. Conventions for contributors live in [`CODE_STYLE.md`](./CODE_STYLE.md); architectural notes for AI agents in [`CLAUDE.md`](./CLAUDE.md).

## Add to Home Assistant

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=roquerodrigo&repository=ha-integration-blueprint&category=integration)

## What's included

- **Full integration scaffold** with `DataUpdateCoordinator`, config flow, options flow, sample sensor and typed `runtime_data`.
- **Reauth + reconfigure flows** triggered automatically by `ConfigEntryAuthFailed` or by the user.
- **Options flow** with a configurable `scan_interval` plumbed through to the coordinator.
- **Diagnostics platform** with credential redaction (`diagnostics.py`).
- **Repairs platform** (`repairs.py`) wired into HA's Issue Registry, with sample issue + `ConfirmRepairFlow`.
- **CI**: ruff lint + format, mypy type-check, `hassfest`, HACS validation, CodeQL security scan.
- **Pre-commit hooks** (`.pre-commit-config.yaml`) — ruff + JSON/YAML/TOML checks.
- **Coverage gate** at 95 % enforced by `pytest.ini` (currently at 100 %).
- **Devcontainer** (Debian + Python 3.14) and VS Code extension recommendations.
- **Scripts** that auto-detect `./.venv` (no `source activate` needed) to start HA in debug or run lint.
- **Tests** with `pytest-homeassistant-custom-component` covering init, config + reauth + reconfigure flows, options flow, coordinator, API client, base entity, sensor, diagnostics, repairs and translation parity.
- **Issue templates**, **PR template**, **`.editorconfig`** and grouped Dependabot updates.
- **Translations** for English and Brazilian Portuguese (with parity test).

## How to use

1. Use this repository as a **template** on GitHub ("Use this template" button) or clone it manually.
2. Rename the domain throughout the codebase:
   - `custom_components/integration_blueprint/` → `custom_components/<your_domain>/`
   - `DOMAIN = "integration_blueprint"` in `const.py`; `domain` in `manifest.json`; `name` in `hacs.json`
   - `name`, `documentation`, `issue_tracker`, `codeowners` in `manifest.json`
   - Rename classes: `IntegrationBlueprint*` → `<YourDomain>*`
   - Run `grep -rn integration_blueprint .` to catch leftover imports (especially in `tests/`)
3. Replace the sample API in `api.py` with your real client and adjust `coordinator.py`, `config_flow.py`, `sensor.py` to match.
4. Update `translations/en.json` and `translations/pt-BR.json` (parity is enforced by tests).
5. Replace the placeholder brand assets in `custom_components/integration_blueprint/brand/` (`icon.png`, `icon@2x.png`, `logo.png`, `logo@2x.png`) with your own — these satisfy the HACS brand check locally until you register the integration in [`home-assistant/brands`](https://github.com/home-assistant/brands).
6. Update `README.md` and `CLAUDE.md` for your integration.

## Useful commands

```bash
scripts/setup      # install dependencies (requirements.txt)
scripts/develop    # start Home Assistant in debug mode with the integration loaded
scripts/lint       # ruff format + check + mypy
pytest             # run tests with the 95 % coverage gate
```

Each script auto-detects `./.venv` and prepends it to `PATH` — no `source .venv/bin/activate` needed. For ad-hoc commands the same trick works: `.venv/bin/pytest`, `.venv/bin/ruff …`.

HA runs with config in `config/` and `PYTHONPATH` pointing at `custom_components/` — no symlinks. To recreate entity/device IDs during development:

```bash
rm config/.storage/core.entity_registry config/.storage/core.device_registry
```

## Layout

```
custom_components/integration_blueprint/
├── __init__.py        # async_setup_entry / unload / reload
├── api.py             # ApiClient (single class)
├── config_flow.py     # user / reauth / reconfigure steps
├── const.py           # DOMAIN, LOGGER, URLs, ATTRIBUTION, scan-interval defaults
├── coordinator.py     # DataUpdateCoordinator (interval injected from options)
├── data.py            # typed ConfigEntry + IntegrationBlueprintData dataclass + TypedDicts
├── diagnostics.py     # downloadable diagnostics with credential redaction
├── entity.py          # base CoordinatorEntity
├── exceptions/        # one file per exception class
│   ├── __init__.py
│   ├── api_client_authentication_error.py
│   ├── api_client_communication_error.py
│   └── api_client_error.py
├── manifest.json
├── options_flow.py    # OptionsFlow with scan_interval
├── repairs.py         # Repair platform: async_create_fix_flow + sample issue
├── sensor.py          # sample platform
└── translations/
    ├── en.json
    └── pt-BR.json
```

Layout convention (one top-level class per file; related classes grouped under a directory) is documented in [`CODE_STYLE.md`](./CODE_STYLE.md).

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
