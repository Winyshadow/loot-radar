# Loot Radar: notes for Claude

Owner: solitary_samurai (GitHub: Winyshadow). Not a programmer, so explain changes in plain words and prefer tables.

## Every change that ships (versioning)

1. Bump `VERSION` using `MAJOR.MINOR.PATCH`:
   - fixes and small tweaks → patch (1.0.0 → 1.0.1), the default
   - a new feature → minor (1.0.x → 1.1.0)
   - a big overhaul → major (1.x → 2.0.0)
2. Add an entry at the top of `CHANGELOG.md` (version, date, plain-language bullets).
3. Commit to `main` with the version in the message ("Loot Radar 1.0.1: ...") and push.
4. Tags can't be pushed from Claude's sessions (the proxy refuses them), so ask the owner to publish a
   GitHub Release: repo → Releases → Draft a new release → tag `1.0.1` (no "v", matching `1.0.0`; create on publish, target `main`)
   → title "Loot Radar 1.0.1" → paste the CHANGELOG entry → Publish. The updater doesn't need tags.

Docs-only changes (README, CHANGELOG, this file) don't bump `VERSION`, so users aren't prompted to update for nothing.

## How updates reach users

`app/updates.py` compares the local `VERSION` with `VERSION` on `main` (raw.githubusercontent.com) every 6 hours. "Update Loot Radar" downloads the `main` zip and copies it over the install, keeping `app/data`, `app/.venv` and `miner`, then restarts via `app/launcher.py` (exit code 3). So whatever is on `main` with a higher `VERSION` goes to everyone: push only finished, tested work.

## Layout

- `START.bat`: first-run setup (Python, venv, packages), then `launcher.py --prepare` (visible) and `pythonw launcher.py` (tray, no console).
- `app/lootradar.py`: Flask server on 127.0.0.1:5577, scheduler, API. `app/web/index.html`: the whole dashboard (single file).
- `app/checks.py`: drop campaigns, alerts, Steam news, mining priority, PC-scan merge. `app/gamescan.py`: other launchers.
- `app/minerctl.py` / `miner.py` / `miner_bridge.py` / `memguard.py`: the built-in Twitch Drops Miner (SimpliAj/twitchdropsminer, MIT): install/update, API, Twitch login hand-off, memory guard.
- `app/watcher.py`: muted-stream mode (plain Edge window over DevTools; no automation flags).
- Personal data lives in `app/data` (gitignored). Never commit it.
