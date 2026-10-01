# UI — Neumorphism themes

## What changed

- New `app/static/themes.css`: palette tokens for **yaru-orange** (default) and **teal**, each with light/dark modes via `data-theme` + `data-mode` on `<html>`.
- Neumorphism helpers: `.neu-raised`, `.neu-pressed`, `.neu-btn`, `.top.neu`.
- `app/static/theme.js`: reads/writes `localStorage` keys `nobat-theme` / `nobat-mode`; applies attributes early (script in `<head>`, not deferred) to limit flash; updates `theme-color` meta from `--brand`.
- Header chrome Option A′: primary **تقویم** / **+** only; sun/moon switch beside **حساب**; **پالت** and admin tools under Account menu. Preferences persist across sessions.
- `style.css` no longer uses `prefers-color-scheme`; surfaces use soft shadows instead of hard borders. Print CSS and PWA assets unchanged in intent (chrome / page ⋮ hidden when printing).

## How to toggle

1. Log in → header sun/moon switch (کنار حساب) for **تیره** / **روشن**.
2. **حساب** → **ظاهر** → **پالت** → نارنجی یارو (default) or سبزآبی.
3. Choice is stored in the browser (`localStorage`). Self-hosters pick per browser/device.

## How to run

```bash
python -m unittest discover -s tests -t . -v
# specifically:
python -m unittest tests.test_ui_themes -v
```
