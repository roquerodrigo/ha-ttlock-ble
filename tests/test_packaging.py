"""The manifest pin and the tested pin must name the same SDK release."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_SDK = "ttlock-ble"


def _pinned(requirements: list[str], package: str) -> str | None:
    """Return the version `package` is pinned to within `requirements`."""
    for requirement in requirements:
        name, separator, version = requirement.partition("==")
        if separator and name.strip() == package:
            return version.strip()
    return None


def test_manifest_and_dev_group_pin_the_same_sdk_version() -> None:
    """Home Assistant installs the manifest pin; the suite runs the dev-group one.

    When they drift, every test passes against a release the running
    integration never sees.
    """
    manifest = json.loads(
        (_ROOT / "custom_components" / "ttlock_ble" / "manifest.json").read_text(),
    )
    pyproject = tomllib.loads((_ROOT / "pyproject.toml").read_text())

    manifest_pin = _pinned(manifest["requirements"], _SDK)
    dev_pin = _pinned(pyproject["dependency-groups"]["dev"], _SDK)

    assert manifest_pin is not None, f"{_SDK} is not pinned in manifest.json"
    assert dev_pin is not None, f"{_SDK} is not pinned in the dev dependency group"
    assert manifest_pin == dev_pin
