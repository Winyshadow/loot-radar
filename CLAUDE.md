# Loot Radar: notes for Claude

Owner: solitary_samurai (GitHub: Winyshadow). Not a programmer, so explain changes in plain words and prefer tables.

## Every change that ships (versioning)

1. Bump `VERSION` using `MAJOR.MINOR.PATCH`:
   - fixes and small tweaks → patch (1.0.0 → 1.0.1), the default
   - a new feature → minor (1.0.x → 1.1.0)
   - a big overhaul → major (1.x → 2.0.0)
2. Add an entry at the top of `CHANGELOG.md` (version, date, plain-language bullets).
3. Commit to `main` with the version in the message ("Loot Radar 1.0.1: ...") and push.
4. Publish a GitHub Release (only when the owner says so): tag `1.0.1` (no "v"; must equal `VERSION`),
   title "Loot Radar 1.0.1", the CHANGELOG entry as text. Publishing it builds and attaches `LootRadarSetup.exe`
   (see below); installed copies only update after that. Check the workflow run finished and the asset is there.

Docs-only changes (README, CHANGELOG, this file) don't bump `VERSION`, so users aren't prompted to update for nothing.

## How updates reach users

There are two kinds of copy (`app/paths.py` decides every path for both):

| Copy | Where things live | How it updates (`app/updates.py`, every 6 hours) |
|---|---|---|
| Installed app (2.0+, `LootRadarSetup.exe`) | Program in `%LOCALAPPDATA%\Programs\Loot Radar`; data and miner in `%LOCALAPPDATA%\Loot Radar` | Compares with the latest GitHub **Release** that has `LootRadarSetup.exe` attached; downloads it and runs it with `/VERYSILENT /LAUNCH=1`, then quits (exit 0) |
| Zip with START.bat | Everything in the folder (`app/data`, `miner`) | Compares with `VERSION` on `main`; downloads the `main` zip over the folder (keeping `app/data`, `app/.venv`, `miner`), restarts via exit code 3. Can also "Switch to the installer version" (copies data + miner, opens the setup) |

So: whatever is on `main` with a higher `VERSION` reaches zip copies straight away, and installed copies once the Release is published and the **Build installer** workflow (`.github/workflows/release.yml`, runs on release published, ~5 min) has attached the setup file. Push only finished, tested work. The workflow fails on purpose if the tag doesn't match `VERSION`.

## Building and testing the installer locally

- `build\build.ps1` builds into `%LOCALAPPDATA%\LootRadarBuild\dist` (outside OneDrive: OneDrive locks PyInstaller's files). Needs `build\.venv` (`app\requirements.txt` + `build\requirements-build.txt`) and Inno Setup 6 (installed per user via winget on the owner's PC).
- Test with a throwaway data folder: set `LOOTRADAR_HOME` (data/miner location) and optionally `LOOTRADAR_RELEASE_API` (a local JSON imitating GitHub's releases/latest) before starting `LootRadar.exe` or the setup; both inherit to the processes they start. Stop the zip copy first (both use port 5577).
- The installed app rewrites the "start with Windows" entry to itself (`autostart.refresh_path`), and uninstalling removes it: after a local test, restart the zip copy and set `start_with_windows` again.
- **Never start the owner's own Loot Radar, its setup or the miner from Claude's shell.** The Claude desktop app is a Windows (MSIX) package. Everything started from its shell, and everything those programs start, runs inside its container:
  - their `%LOCALAPPDATA%`/`%APPDATA%` and HKCU writes go to `AppData\Local\Packages\Claude_*\LocalCache` instead;
  - they are killed when Claude updates or restarts.
  
  This happened on 2026-11-13: settings looked "gone" and Loot Radar closed overnight. Start the owner's copy with `explorer.exe "<path>"`, which runs outside the container, or ask the owner to start it.

## Layout

- `START.bat`: first-run setup (Python, venv, packages), then `launcher.py --prepare` (visible) and `pythonw launcher.py` (tray, no console).
- Installed app: `LootRadar.exe` is `launcher.py` frozen by PyInstaller (`build/lootradar.spec`); it starts `LootRadar.exe --run` as Loot Radar itself. `app/window.py`: its own window (pywebview + WebView2; closing hides to the tray; falls back to the browser). `build/installer.iss`: the Inno Setup script.
- `app/lootradar.py`: Flask server on 127.0.0.1:5577, scheduler, API. `app/web/index.html`: the whole dashboard (single file).
- `app/checks.py`: drop campaigns, alerts, Steam news, mining priority, PC-scan merge. `app/gamescan.py`: other launchers.
- `app/waits.py`: why a running drop isn't being mined (channel-only campaign offline, no streams, queued), served in `/api/now` as `waits`.
- `app/minerctl.py` / `miner.py` / `miner_bridge.py` / `memguard.py`: the built-in Twitch Drops Miner (SimpliAj/twitchdropsminer, MIT): install/update, API, Twitch login hand-off, memory guard.
- `app/watcher.py`: muted-stream mode (plain window of the default Chrome-type browser, else Edge, over DevTools; own profile per browser in `data/browser-profile[-brave]`; no automation flags).
- Personal data lives in `app/data` (gitignored) or `%LOCALAPPDATA%\Loot Radar`. Never commit it.
