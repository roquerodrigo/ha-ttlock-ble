from __future__ import annotations

import json
from pathlib import Path

import pytest

TRANSLATIONS_DIR = (
    Path(__file__).parent.parent
    / "custom_components"
    / "integration_blueprint"
    / "translations"
)


def _flatten_keys(data, prefix=""):
    keys = set()
    if isinstance(data, dict):
        for k, v in data.items():
            full = f"{prefix}.{k}" if prefix else k
            if isinstance(v, dict):
                keys |= _flatten_keys(v, full)
            else:
                keys.add(full)
    return keys


def _translation_files():
    return sorted(TRANSLATIONS_DIR.glob("*.json"))


def _key_sets():
    return {
        f.stem: _flatten_keys(json.loads(f.read_text(encoding="utf-8")))
        for f in _translation_files()
    }


def test_translations_directory_has_at_least_two_locales():
    assert len(_translation_files()) >= 2


def test_en_locale_exists():
    assert (TRANSLATIONS_DIR / "en.json").exists()


@pytest.mark.parametrize("locale", [f.stem for f in _translation_files()])
def test_translation_locale_matches_en_keys(locale):
    sets = _key_sets()
    reference = sets["en"]
    other = sets[locale]
    missing = reference - other
    extra = other - reference
    assert not missing, f"{locale}.json is missing keys: {sorted(missing)}"
    assert not extra, f"{locale}.json has unexpected keys: {sorted(extra)}"


def test_no_empty_translation_values():
    for path in _translation_files():
        data = json.loads(path.read_text(encoding="utf-8"))
        for key in _flatten_keys(data):
            value = data
            for part in key.split("."):
                value = value[part]
            assert value, f"{path.name} has empty value for {key}"
