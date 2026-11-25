# OBS Toggle — build

Official OBS Studio 33.0.3, whole, plus Settings > Feature Toggles
(GPU switch, Eco / Mobile Mode CPU savers), the Canvas Chatbox +
Style Chatbox plugin, and the Stream Shower source + Stream Watcher
dock. No removals, no Stinger Maker. Full spec:
`OBS-TOGGLE-SPEC.md`.

## Files in this folder

- `apply-toggle-patch.py` — applies the patch to a pristine upstream
  33.0.3 tree. Fails loudly if any anchor is missing; refuses to run
  twice on the same tree.
- `FeatureToggles.hpp` — the one toggle table (copied into
  `frontend/` by the patch script). Now 62 entries — Stream Shower
  is toggleable under Plugins.
- `canvas-chatbox/` — the chatbox plugin (copied into `plugins/` by
  the patch script).
- `stream-shower/` — the Stream Shower source + Stream Watcher dock
  (copied into `plugins/` by the patch script, registered as a core
  module after `check_obs_browser()` because it links
  `OBS::browser-panels`).
- `build-obs-toggle.yml` — GitHub Actions workflow (Windows x64).
  Lives in `.github/workflows/` on the `official-toggle` branch.
- `OBS-TOGGLE-SPEC.md` — the locked spec.

## Build it (CI, the real route)

1. Push this folder's source files to branch `official-toggle` in
   `streamguy100/OBS-Lite-v2` (patch script, spec, README, header,
   canvas-chatbox, stream-shower).
2. Push `build-obs-toggle.yml` to `.github/workflows/` on the same
   branch (via the browser — the API route 403s on workflow files).
3. The workflow clones upstream OBS 33.0.3 (HEAD pinned:
   `f2aa9ce69caa7239ef26660b5889de4f53d9880e`), inits the
   obs-browser / obs-websocket / libdshowcapture submodules, runs
   `apply-toggle-patch.py`, applies the ATL header copy fix, builds
   with `Build-Windows.ps1` (RelWithDebInfo, x64), verifies nothing
   was removed and the toggle code is present, restores the two
   runtime DLLs cmake --install does not copy (`libx264-164.dll`,
   `datachannel.dll`), and zips the install tree as
   `OBS-Toggle-Ready.zip` (obs64.exe at
   `OBS-Toggle/bin/64bit/obs64.exe`).
4. The workflow also publishes GitHub release tag
   `v33.0.3-obs-toggle` with the zip.

## Test the patch locally (no C++ compile on this VM)

```sh
git clone --depth 1 --branch 33.0.3 https://github.com/obsproject/obs-studio.git upstream
python3 apply-toggle-patch.py upstream
```

Expected: exit 0, ending with `TOGGLE PATCH OK`. Then check:

```sh
test -d upstream/plugins/obs-x264 && echo "x264 kept"
test -d upstream/plugins/vlc-video && echo "vlc kept"
test -d upstream/plugins/decklink && echo "decklink kept"
test ! -e upstream/plugins/stinger-maker && echo "no stinger maker"
grep -c "obs_add_disabled_feature" upstream/libobs/obs-module.c
```

No local C++ compile is possible on this VM (no MSVC/Windows
toolchain), so the compile check happens in CI — the workflow fails
the run if the build breaks.

## Run it (after the CI zip lands)

Unzip `OBS-Toggle-Ready.zip` to a fresh folder and run
`OBS-Toggle/bin/64bit/obs64.exe`. First checks:

1. Settings opens without crashing (even with encoders toggled off).
2. Settings has a **Feature Toggles** page at the bottom of the list,
   GPU switch at the top, all toggles ON by default.
3. Turn a toggle OFF (e.g. VLC Video Source), Apply → OBS restarts
   by itself in normal mode, no Safe Mode prompt, and the thing is
   gone from the Sources menu.
4. Canvas Chatbox dock is right of the canvas, Style Chatbox on the
   left (View > Docks if hidden).
5. Settings > Stream > Service offers WHIP (obs-webrtc, stock).
6. Add a **Stream Shower** source to a scene: put in Twitch / Kick
   links (up to 10, in order) with a timer per link — it plays them
   fullscreen, no chat, and auto-switches. The **Stream Watcher**
   dock (top left) shows the same stream, with Prev / Next and a
   countdown.
