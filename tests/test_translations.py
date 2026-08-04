from __future__ import annotations

import json
from pathlib import Path

import pytest

TRANSLATIONS_DIR = (
    Path(__file__).parent.parent / "custom_components" / "ttlock_ble" / "translations"
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


def _authored_entity_keys() -> set[tuple[str, str]]:
    """Return every `(platform, key)` pair `en.json` defines under `entity`."""
    entity_section = json.loads(
        (TRANSLATIONS_DIR / "en.json").read_text(encoding="utf-8"),
    )["entity"]
    return {
        (platform, key) for platform, blocks in entity_section.items() for key in blocks
    }


async def test_entity_translation_keys_and_authored_names_agree(
    hass,
    setup_integration,
):
    """
    Every translation key an entity asks for is authored, and vice versa.

    Read from the entity registry rather than the classes: Home
    Assistant rewrites `_attr_translation_key` into a property, so
    inspecting the class attribute finds a descriptor and quietly checks
    nothing. Comparing the locales against each other cannot catch this
    either — a key missing from both sides matches, and the entity falls
    back to its device-class name while the authored one never shows.
    """
    from homeassistant.helpers import entity_registry as er

    registry = er.async_get(hass)
    requested = {
        (entry.domain, entry.translation_key)
        for entry in registry.entities.values()
        if entry.platform == "ttlock_ble" and entry.translation_key is not None
    }
    assert requested, "the integration registered no translated entity"
    authored = _authored_entity_keys()
    assert not requested - authored, (
        f"entities ask for keys en.json does not define: {sorted(requested - authored)}"
    )
    assert not authored - requested, (
        f"en.json defines keys no entity asks for: {sorted(authored - requested)}"
    )


def test_no_empty_translation_values():
    for path in _translation_files():
        data = json.loads(path.read_text(encoding="utf-8"))
        for key in _flatten_keys(data):
            value = data
            for part in key.split("."):
                value = value[part]
            assert value, f"{path.name} has empty value for {key}"
