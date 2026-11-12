# Changelog

All notable changes to Loot Radar. Versions follow `MAJOR.MINOR.PATCH`:

- **Patch** (1.0.0 → 1.0.1): fixes and small tweaks. Most updates.
- **Minor** (1.0.x → 1.1.0): a new feature.
- **Major** (1.x → 2.0.0): a big overhaul.

## 2.0.3 (2026-11-12)

- **No more "update available" right after updating.** The installed app kept showing the update it had just installed (until its next check, up to 6 hours later). It now knows straight away that it's up to date.
- **Update files are cleaned up.** Each update downloads a setup file of about 20 MB to Windows' temp folder; Loot Radar now deletes them once the update has finished (including ones left over from earlier updates).

## 2.0.2 (2026-11-12)

- **Uses your whole screen.** The lists on Browse drops and Library, and the Activity log, now reach down to the bottom of the window instead of stopping at a fixed height, so a big monitor shows many more rows at once (and resizing the window resizes them). On wide screens the pages also get wider, up to 1600 pixels of content. Small windows and phones work as before.

## 2.0.1 (2026-11-12)

- **The Loot Radar window now feels like one app.** The title bar has the same colour as the menu bar, so they read as one band. The page fills the window edge to edge (no more rounded card with a gap around it), the menu stays put at the top while only the page below it scrolls, and the scrollbar is slim and in Loot Radar's colours. (Windows 11 colours the title bar; Windows 10 keeps its dark one.) In the browser, the dashboard looks the same as before.

## 2.0.0 (2026-11-12)

- **Loot Radar is now a normal Windows app.** Download **LootRadarSetup.exe** from the release, click through the installer (no admin rights needed) and that's it: no Python, no START.bat. It goes in the Start menu and the Windows apps list, can put a shortcut on your desktop and start with Windows, and uninstalls like any program (it asks whether to keep your settings).
- **Its own window.** The dashboard opens in a Loot Radar window instead of a browser tab. Closing it keeps Loot Radar collecting drops in the tray; double-click the tray icon, or start it again, to bring the window back. Prefer the browser? Settings → Preferences → "Open the dashboard in my browser instead".
- **Updates install themselves.** "Update Loot Radar" downloads the new setup, installs it quietly and opens the new version. Your settings live in their own folder (`%LOCALAPPDATA%\Loot Radar`), so updates and reinstalls never touch them.
- **Using the zip with START.bat?** It keeps working and updating as before. When you're ready: **Settings → Updates → Switch to the installer version**. It copies your settings, games and the drop miner over, opens the installer, and tells you afterwards that the old folder can go.
- The phone-access firewall tips now name the right program (Loot Radar or Python).

## 1.8.0 (2026-11-12)

- New **setup guide**: the first time Loot Radar starts, a step-by-step window walks you through everything, one step at a time: welcome, drop miner (install and Twitch login, with live progress), Steam, Discord, linking your game accounts, extras (start with Windows, game deals, phone access) and picking your games. Optional steps have a **Skip** button, **Back** goes back, and **Finish later** closes it. If you close the page halfway, it carries on where you left off.
- Already set up? You won't see it. You can open it any time from **Settings → Setup → Run the setup guide again**.

## 1.7.3 (2026-11-12)

- Safer: other websites open in your browser can no longer talk to Loot Radar. Before, a malicious page could in theory have sent it commands (like changing your Discord link). Now only Loot Radar's own dashboard, and your phone with its PIN, are accepted. Nothing changes in how you use it.
- Added a licence: Loot Radar is free for personal use, all rights reserved. See the LICENSE file and the line under Settings → Updates.

## 1.7.2 (2026-11-12)

- Tidier Deals page: the **Best official store** column is gone, so it's just **Steam** and the **Key shop**. Steam's own rand price already covers official stores, and the dollar price next to it mostly added clutter. Discord no longer pings for official-store lowest prices either; Steam sales and key-shop lowest prices still ping.
- The key-shop price is calmer too: the "key shop" and "DRM?" tags are gone, and "lowest ever" only shows when the price isn't at its lowest (the **Lowest ever** tag covers that). One line underneath says **⚠️ Check DRM · region · account/key**; hover it for what to check.
- The tips box at the top and the Discord pings list the same three checks in the same order.

## 1.7.1 (2026-11-12)

- Key-shop prices on the Deals page now have a **DRM?** marker. GG.deals doesn't say which platform the cheapest key is for, and it's sometimes an Xbox or other non-Steam key, so check it says Steam before buying. Hover the marker for the explanation.
- The key-shop tips box now lists three checks: Steam key, game key (not an account), and region. Discord deal pings say the same.

## 1.7.0 (2026-11-12)

- **Why isn't it mining?** When a running drop isn't being mined, Loot Radar now says why, under the game in Running drops and in the Now mining card. For example: "Only counts on Warframe or WarframeInternational, both offline (last live 10 h ago)", "Nobody is streaming it with drops on right now", or "Waiting its turn after Apex Legends". The status tag says the same in short: Channels offline, No live stream, Queued, Starting or Mining now.
- You don't have to do anything: the miner already skips a game with no live stream and mines the next one that has one, and it starts by itself the moment a channel goes live.
- New **Twitch button** on every game in Running drops opens its drop campaign on Twitch. Open a game to see **Campaign on Twitch** and links to the channels it counts on (or all of the game's streams).
- The **games waiting for a campaign** are now a tidy A to Z list that folds away under one line ("27 games waiting for a campaign"). Click to open it; it remembers.
- On a phone, a game's buttons now sit on their own line, so the name has room.

## 1.6.6 (2026-11-11)

- Fixed **Completed drops** showing a drop you never got. The drop miner can briefly think a drop is claimed when its own minute count runs ahead of Twitch's, then finds out when it reloads your progress from Twitch (for example 479 of 480 minutes when the campaign ended). Loot Radar now re-checks the Completed list every few minutes and takes off any drop the miner says isn't claimed, lowers the "rewards" count to match, and notes it in Activity.

## 1.6.5 (2026-11-11)

- Fixed muted mode piling up blank tabs in Brave. Brave reopens last time's tabs when it starts, so every start added another blank tab. Loot Radar's window now always opens with just one tab.
- When no stream for the game has drops on right now, the window no longer sits on a blank page. It says it's **waiting for a live drops stream**, that Loot Radar checks again every 10 minutes and opens one by itself, and that you can minimise the window.

## 1.6.4 (2026-11-11)

- GG.deals prices (best official store and key shop) now also show an **estimate in your own currency**, like "$12.49 ≈ R 206", including the "lowest ever" prices and the Discord deal pings. Handy for comparing with the Steam price in rand.
- It uses the latest exchange rate (from Exchange Rate API, with the European Central Bank's rates as a backup), updated every 6 hours. The Deals page shows the rate it used and its date. If you're offline, it uses the last rate it got.
- Settings → Game deals → **Show GG.deals prices in my currency too**: Automatic (your Steam currency, rand for South Africa), pick another currency, or Don't convert.
- It's a guide: the shop's own price and your bank's fees decide what you really pay.

## 1.6.3 (2026-11-11)

- Muted mode and the miner's Twitch sign-in now open in **your default browser** (Brave, Chrome, Edge or Vivaldi) instead of always Edge. If your default is something else (like Firefox), it still uses Edge.
- It's still Loot Radar's own window with its own profile, kept apart from your everyday browser, so Loot Radar can mute it, set the lowest quality and switch streams. The first time it opens in a new browser, sign in to Twitch there once; it remembers you after that.

## 1.6.2 (2026-11-11)

- **Tidier Settings.** Everything is now in five sections you open and close with a click: **Updates**, **Setup** (drop miner, Steam, Discord), **Game deals**, **Phone access** and **Preferences**. Each header shows its status, so you can see what's done without opening it: "Up to date", "Miner ✓ · Steam ✓ · Discord ✓", "On · 16 on sale", "On" / "Off".
- Sections open by themselves when they need you: **Setup** while the drop miner isn't set up, and **Updates** (moved to the top, with a bright "Update available" chip and glow) when a new version is out. Otherwise they stay the way you left them.
- "Start the built-in miner" and "Ping me about drops for games I have" moved to Preferences, next to "Start with Windows".
- Fixed the bottom of the "g" in page titles (like "Settings") being cut off.

## 1.6.1 (2026-11-11)

- Key-shop warnings now also say to buy a **game key** ("Steam Key" / "CD Key"), not an **account** or "gift": accounts aren't yours and can be taken back. GG.deals only shares the cheapest key-shop price (not what kind of offer it is), so the warning shows on every key-shop price, on the Deals page and in Discord pings.
- Green Man Gaming is now named among the safe official stores.

## 1.6.0 (2026-11-11)

- New **Game Deals**: Loot Radar now finds cheap games as well as free loot.
  - Reads your **Steam wishlist** (it must be visible: Steam privacy → Game details: Public), or paste Steam store links to add games by hand.
  - Checks every 6 hours (or **Check deals now**): the **Steam** price in your own currency, plus, with a free **GG.deals** key, the cheapest **official store** and the cheapest **key shop** across dozens of shops, with their all-time lows. Prices by GG.deals.
  - New **Deals** tab: cover, Steam price (−% and the old price struck through), best official store, key shop, "Lowest ever" badges, links to Steam and to every price on GG.deals. Filters: All · On sale · Lowest ever. Upcoming games show "Not out yet".
  - **Discord pings** for deals: when Steam has a game at least 50% off (you choose the %), or a game drops to its lowest price ever. Goes to its own deals channel if you add one. The same deal is never pinged twice; a further drop pings again.
  - **Key shops** (G2A, Kinguin, Eneba…) are shown separately and can be switched off. Each key-shop price reminds you to check the key's region: GLOBAL or ROW keys work in South Africa, region-locked EU/US/UK/Asia/RU keys may not.
  - GG.deals has no South Africa region, so its prices show in US dollars (or EUR/GBP if you pick that region). Steam prices stay in rand.
  - Settings → **Game deals**: on/off, GG.deals key, deals Discord channel, minimum %, region, key shops, **Send test ping**. Your phone sees deals but never the key or the channel link.

## 1.5.2 (2026-11-10)

- The bottom dock stands out more: a glowing lime border, a darker background, and a short lime pulse when it slides in, so it no longer blends into the page behind it. (No pulse on phones, where it's the always-on tab bar, or if Windows is set to reduce animations.)

## 1.5.1 (2026-11-10)

- Phone access now has an **Away from home (Tailscale) checklist** that checks your PC and shows ✓ or ✗ for each step, with the fix next to anything missing: Tailscale installed, signed in on this PC (and its 100.x address), your phone found on your Tailscale, and Windows Firewall letting your phone in. A short note explains what Tailscale does. Press **Check again** after fixing something.
- The firewall check catches a common snag: Python allowed on "Public" networks only, while Tailscale counts as "Private". It only reads the firewall settings and never changes them.
- When everything is ✓, **Show the Tailscale QR code** switches the QR code to the address that works at home and away.

## 1.5.0 (2026-11-10)

- New **bottom dock**: when you scroll down and the top menu goes out of view, the same menu slides up at the bottom of the window (Overview, Browse, Library, Activity, Settings), with one status chip ("All OK" or "1 issue"). Scroll back up and it slides away. You never lose the menu again.
- New **Phone access** (Settings): check your drops on your phone.
  - Tick **Let my phone connect**, scan the QR code with your phone's camera, and you're in. Or open the address shown and type the 6-digit PIN.
  - Works on home Wi-Fi. With **Tailscale** (free) on the PC and the phone, it also works from anywhere, without opening anything to the internet. Settings shows the Tailscale address when it finds one.
  - "Add to Home Screen" on the phone makes it open like an app, with a tab bar at the bottom.
  - Safe by default: it's off until you switch it on, it uses its own separate port (5578), every phone needs the PIN, and 5 wrong PINs lock that device out for 10 minutes. The phone never receives your Steam key, Discord link or passwords, and can't change them, log the miner in, or change phone access. **New PIN** signs every phone out.
  - Windows may ask once whether Python may use the network: allow it on Private networks.

## 1.4.3 (2026-11-10)

- Clearer Steam setup steps: after clicking **Register** on Steam's API key page, you have to approve the request in the **Steam app on your phone** (🔔 notifications). This is now its own highlighted step. It also says to click Register only once, because every extra click sends another request (if there are several, approve the newest).

## 1.4.2 (2026-11-10)

- New warning on the Overview when a game you want mined has a live campaign but its game account isn't linked on Twitch: "⚠️ 1 game can't mine yet". Twitch doesn't count watch time for those, so the miner skips them. Each game gets a **Link** button that opens its account-linking page, and mining starts by itself a few minutes after you link.
- In Running drops, those games now say "skipped until you link your account", and their drops say "Waiting for account link" instead of "Up next".

## 1.4.1 (2026-11-10)

- The Drop miner card in Settings now shows whether the miner is signed in to Twitch, and with which account ("Signed in · Twitch account: yourname"), so you never need to open the miner to check. If it's not signed in, it says so and points to the login button.
- Once you're signed in, the login button reads **Switch Twitch account**. Hovering the Miner dot at the top also shows the account.

## 1.4.0 (2026-11-10)

- Fixed: a fresh setup with no games picked yet (no Steam connected, nothing added) didn't mine at all, even with the miner logged in. Until you pick games, the miner now mines any drop your linked accounts can get. As soon as you set a game to Auto-mine or Muted, it goes back to mining only the games you picked.
- Setup is clearer. The drop miner is now step 1 and marked **Required**. Steam and Discord are marked **Optional**, with a short note on what each one adds.
- New **Skip Steam for now** and **Skip Discord for now** tick boxes. Ticking one hides its setup reminder (and the "!" on Settings); untick any time to bring it back.
- The Overview's reminder now says to start with the drop miner, and turns into a soft "Optional extras" note once the miner works.

## 1.3.0 (2026-11-09)

- New: **Streamers** button on every sub-only drop. It lists the channels streaming that game live with drops on, most viewers first, with their stream title. Each one has **Watch** and **Subscribe** links (Subscribe opens Twitch's subscribe page for that streamer), so you can pick who to sub to for the drop.
- Shows the top 12 streamers, with "Show all" for the rest. There are also links to the drop's campaign page on Twitch (which lists the channels taking part) and to all of the game's streams.

## 1.2.0 (2026-11-09)

- Drops that need a paid sub to a streamer no longer hold up the mining queue. Watching never earns them, so they're left out of the mining order, "Sort by ending soonest", muted mode and the miner's game list. A game whose only live drops need a sub comes off the miner's list until it has a drop you can earn by watching.
- New **Sub-only drops** panel on the Overview, under Running drops. It lists every sub drop for your games, how many subs it needs and when it ends, so you can still see them.
- Running drops now shows only drops you can earn by watching. A campaign that mixes both (like Legion TD 2) shows its watch drops there and notes how many sub drops it has.
- Browse drops marks campaigns where every drop needs a sub with a "Sub only" tag.

## 1.1.0 (2026-11-09)

- New: **Start Loot Radar when I sign in to Windows** tick box (Settings → Preferences). Loot Radar then starts quietly in the system tray when you sign in, without opening the dashboard. It's saved as soon as you tick it, needs no admin rights, and shows up in Windows' Startup apps list as "Loot Radar".
- If you switch it off in Windows' Startup apps list, the tick box shows that. Ticking it again in Loot Radar switches it back on.
- If you move the Loot Radar folder, the startup entry follows it the next time Loot Radar starts.

## 1.0.1 (2026-11-09)

- Fixed first-time setup failing on PCs that only have Python 3.15 ("Failed building wheel for aiohttp" / "Microsoft Visual C++ 14.0 or greater is required"). START.bat now uses Python 3.10 to 3.14 and, if none is installed, offers to install Python 3.12 next to your other Python.
- If an earlier setup was built with a Python that's too new, START.bat rebuilds it automatically.

## 1.0.0 (2026-11-08)

First public release.

- Steam library with hours played, plus a PC scan for games installed with Epic, EA app, Battle.net, Ubisoft Connect, Xbox, Rockstar, Riot and GOG (no logins).
- Browse every Twitch drop campaign and add any game, Steam or not.
- Discord alerts for new drop campaigns, official Steam news, and drops for games you have but haven't set up.
- Built-in drop miner (Twitch Drops Miner), installed and updated from its official GitHub with one click; Twitch sign-in handled by Loot Radar.
- Muted-stream mode that really watches a live drops stream, muted and at the lowest quality.
- Overview with totals, a live "Now mining" card (countdown, channel, channel points), collapsible running drops and a clearable completed-drops list.
- Mining order: sorted by ending soonest at first, then drag or use arrows to reorder; "Sort by ending soonest" and "Keep sorted" options.
- Memory guard for the miner, system tray icon (no console window), and one-click self-updates from GitHub.
