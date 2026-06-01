## Summary

<!-- 1-3 bullets describing what changed and why. -->

## Type of change

- [ ] Bug fix
- [ ] New feature
- [ ] Refactor / cleanup
- [ ] Documentation
- [ ] Tooling / CI

## Test plan

- [ ] `uv run ruff format --check .`, `uv run ruff check .` and `uv run mypy custom_components/ttlock_ble` pass
- [ ] `uv run pytest` passes with the coverage gate
- [ ] All translation locales updated (if user-facing strings changed)

## Checklist

- [ ] Code is in English (only `translations/<locale>.json` follows the locale)
- [ ] One top-level class per file
- [ ] CLAUDE.md / README updated if architecture or workflow changed
- [ ] `manifest.json` version bumped if releasing
