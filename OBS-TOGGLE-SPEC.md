# OBS Toggle — locked spec (2026-11-24, sir)

Goal: official OBS Studio 33.0.3, whole and untouched, plus a
Settings page that turns any toggleable thing on or off — and nothing
else. No strip, no removals, no Stinger Maker.

Base: OBS Studio 33.0.3 (`f2aa9ce69caa7239ef26660b5889de4f53d9880e`).

## What it is

- **Everything original, kept.** x264, VLC, DeckLink, AJA, all
  encoders, sources, filters, transitions, outputs, plugins. The
  patch script verifies at the end that none of them are gone, and
  the CI workflow fails the build if any are missing.
- **Canvas Chatbox + Style Chatbox included** as a core module
  (`plugins/canvas-chatbox`, same as PS5 Lite): Canvas Chatbox docked
  right of the canvas, Style Chatbox on the left. WHIP is already in
  official OBS (obs-webrtc) and stays.
- **Stream Shower + Stream Watcher included** as a core module
  (`plugins/stream-shower`): a "Stream Shower" source that shows up
  to 10 Twitch / Kick streams in order, fullscreen, no chat, with a
  timer per link and auto-switching; and a "Stream Watcher" pop-out
  window (v4, 2026-11-26 — was a dock, top left), showing the exact
  same stream the source is showing, with Prev / Next buttons and a
  countdown. See "Stream Shower" below. Toggleable under Plugins in
  Feature Toggles (62 entries now, was 61).
- **NO Stinger Maker.**

## Settings > Feature Toggles

A new page at the bottom of the Settings list. Default: everything ON.

### How OFF works (the honest mechanism)

OBS already has a disabled-modules list (`obs_add_disabled_module`,
fed by the Plugin Manager before any module loads). Two extensions:

1. **Core modules honour it too.** Stock OBS only skips
   *third-party* modules here — every encoder/source that ships with
   OBS is a *core* module, so the stock Plugin Manager can never turn
   one off. One-line change in `libobs/obs-module.c` drops the
   core-module exemption. OFF module = its DLL is never loaded. Files
   stay on disk; OBS just does not see the module.
2. **Per-item disable.** Modules that hold many things (obs-ffmpeg,
   win-capture, obs-filters, obs-transitions, obs-outputs) get
   per-registered-id gating: libobs keeps a disabled-features set and
   the four `obs_register_*()` functions refuse a matching id, so
   that one encoder / source / filter / transition / output never
   registers while the rest of its module loads normally.

Toggles persist in the user config, section `FeatureToggles`
(missing key = ON). They are applied in
`PluginManager::preLoad()` — the only point that runs before
`obs_load_core_modules()`, so OFF really means "never loaded".

### GPU switch (top of the page)

"Run OBS for:" Auto / AMD / Intel / Nvidia.

- AMD = AMF on, NVENC + QuickSync off.
- Intel = QuickSync on, NVENC + AMF off.
- Nvidia = NVENC on, QuickSync + AMF off.
- Auto = detect the GPU and pick that vendor. Detection probes the
  encoders that actually registered on this launch — each encoder
  module only registers when its hardware is present (obs-nvenc
  refuses to load without NVIDIA, obs-qsv11 only registers on Intel
  adapters, AMF only registers when the AMF runtime answers). If no
  hardware encoder is found, Auto changes nothing.

The switch writes concrete encoder toggles; they take effect after
the restart, like any other toggle.

### Apply = automatic clean restart

Changing a module/feature toggle or the GPU vendor needs a restart.
Pressing Apply restarts OBS automatically in normal mode: the app
quits through the normal clean-shutdown path (which clears the crash
sentinel), then obs-main relaunches the same command line. No
question dialog, no Normal / Safe Mode prompt.

### Groups on the page

- **Encoders** — x264, NVENC (NVIDIA), NVENC via FFmpeg (+ HEVC),
  QuickSync (Intel), AMF H.264 / HEVC / AV1 (AMD), OpenH264.
- **Sources** — Browser, Game Capture, Display Capture, Window
  Capture, Media Source, Image, Text (GDI+), Text (FreeType 2),
  Video Capture Device, Audio Input / Output / Application Capture,
  VLC Video Source.
- **Filters** — Mask, Crop/Pad, Gain, 3-Band EQ, HDR Tone Mapping
  (Override), Compose SDR on HDR (Override), Color Correction, Apply
  LUT, Scaling, Scroll, Render Delay, Video Delay (Async), Color Key,
  Chroma Key, Luma Key, Sharpness, Noise Suppression, Noise Gate,
  Compressor, Limiter, Expander, Upward Compressor, Invert Polarity.
  (NVIDIA AI filters live under Plugins as the nv-filters module.)
- **Transitions** — Cut, Fade, Swipe, Slide, Stinger (the stock
  transition — NOT the Stinger Maker plugin, which is not in this
  build), Fade to Color, Luma Wipe.
- **Outputs** — RTMP (Stream), Recording FLV / MP4 / MOV, FFmpeg
  Output / Muxer / MPEG-TS / HLS, Replay Buffer, WHIP (obs-webrtc).
- **Plugins** — VST Filters, WebSocket Server, Stream Services list
  (Twitch, YouTube, …), DeckLink (+ Captions + Output UI), AJA,
  Fraunhofer AAC, CoreAudio AAC, NVIDIA Audio/Video Effects,
  Scripts / Frontend Tools.

Deliberately NOT toggleable: the built-in Scene / Group / Audio Line
sources (registered inside libobs before any config is read), and the
FFmpeg built-in audio encoders (AAC/Opus/PCM — streaming needs them).
Turning a whole module off also turns off everything inside it; the
fine-grained toggles are for modules that hold many things.

### Settings-crash fix (from PS5 Lite)

Any encoder can now be toggled off, so `obs_get_encoder_codec()` can
return NULL for an unregistered id — the exact NULL hazard that
crashed Settings on sir's PC in PS5 Lite. The null-guards in
`DisableIncompatibleSimpleContainer`,
`DisableIncompatibleSimpleCodecs` and `service_supports_codec` are
ported, and every encoder fallback (Simple output, profile load,
stream settings) picks the first encoder that is actually
registered — x264 first when it is on — instead of assuming one.

## Eco / Mobile Mode (CPU savers, same page)

Master toggle turns all five savers on at once. Each saver is also
individually toggleable.

1. **Eco / Mobile Mode master** — checks all five savers on.
2. **Preview off while live** — when a stream or recording starts,
   the preview display is disabled; when nothing is live any more it
   comes back (previous on/off state restored). Studio Mode is
   untouched: its program/preview stays up.
3. **Preview at 15 fps while live** — the preview draw callback
   (`OBSBasic::RenderMain`) skips draws until 66 ms have passed, so
   the preview updates at 15 fps. The stream/recording render from
   the video pipeline, not from this display callback, so they are
   unaffected.
4. **Hidden sources sleep** — libobs gate in
   `obs_source_video_tick()`: a source that is not showing anywhere
   and is not producing audio stops ticking, so hidden media /
   browser / VLC sources stop decoding. The tick still runs once
   while the source is mid-hide so the hide callback fires, and
   audio-active sources keep ticking so hidden audio keeps playing.
   Showing the source again resumes instantly (it may skip ahead).
   Applies live, no restart.
5. **Browser sources pause when hidden, capped at 720p** — every
   browser source gets `shutdown` (pause when not visible) turned on
   and width/height clamped to 1280x720 (only shrunk, never
   enlarged). Applied at startup, when the dialog closes, and to any
   browser source created afterwards (new source, scene collection
   load, undo, paste).
6. **Auto CPU guard** — a 2-second timer watches total CPU usage
   (the same reading as the status bar). Over the threshold (default
   80%, adjustable 50–95%) for 6 seconds while live: output drops to
   720p30. Under 60% for 60 seconds: the saved output size and frame
   rate come back. Honest cost, stated in the UI: changing the
   output size mid-stream stops and restarts the stream/recording
   outputs, so the stream briefly drops when the guard fires or
   restores. Cooldown: at most one drop per 5 minutes.
7. **Update checker** — same as PS5 Lite #23: checks on startup
   only, never while streaming or recording. Upstream OBS 33 has no
   telemetry or crash reporting in this tree.

## Stream Shower + Stream Watcher (added 2026-11-24, sir; v4 2026-11-26)

v4 changes only these two things, same file `stream-shower.dll`:
1. Links are locked to `twitch.tv/<name>` / `kick.com/<name>` only.
2. The Watcher dock is gone — it is a pop-out window now (Tools >
   Stream Watcher, or the button in the source properties).

One core module, `plugins/stream-shower`, two parts that work as one.

### Stream Shower source

Add it to a scene (Sources + > Stream Shower). It shows a Twitch or
Kick stream fullscreen, no chat panel, in the stream output.

- **Up to 10 links, Twitch or Kick only, in order 1–10.** A link can
  ONLY be `twitch.tv/<streamer name>` or `kick.com/<streamer name>`
  (v4, 2026-11-26 — like a Browser Source, but locked to those two:
  any other link, site or format is rejected and does not load), or
  just a channel name (`kaicenat`) — plain names use the "Default
  platform for plain channel names" setting (Twitch or Kick). Empty
  links are skipped. The source properties say this plainly.
- **Timer per link** (1–180 minutes, default 10). Plays link 1 for
  its timer, auto-switches to link 2, and so on, then loops back to
  link 1.
- **Players are the official embeds**: `player.twitch.tv` for Twitch
  (parent=localhost, the standard OBS browser-source value),
  `player.kick.com/<channel>` for Kick. No chat panel in either.
- Internally the source owns a private child `browser_source` (the
  same trick OBS's own Stinger transition uses) and renders it
  fullscreen at 1920x1080.

### Stream Watcher pop-out window (v4, 2026-11-26 — was a dock, top left)

A separate pop-out window, still inside OBS and still part of the
same `stream-shower.dll` — no separate .exe, no new file. Open it
from Tools > Stream Watcher, or the "Open Stream Watcher" button in
the source properties. It shows the EXACT same stream the source is
showing, at the same time — when the source auto-switches, the window
switches with it. It uses OBS's own CEF browser widget (the
`OBS::browser-panels` API, the same one OBS's BrowserDock uses), so
it is a real player, not a screenshot. One shared playlist drives
both; the window's 1-second timer is the switcher. The window is
created at module load and kept hidden — closing it only hides it,
so the timer keeps running and the source keeps auto-switching (and
the offline-screen probe keeps running) even while the window is
closed.

### The five extras (all in)

1. **Skip if offline** — before a link plays, the dock checks it
   with OFFICIAL APIs only, never page scraping: Kick via its
   public `api/v2/channels/<name>` endpoint (no login), Twitch via
   Helix `/streams` (needs a Client ID + access token pasted in the
   source properties, from dev.twitch.tv). A cached-offline link is
   skipped for the next live one. Auto-switch only lands on a link
   already checked LIVE, or on a link that cannot be checked at all
   (Twitch without Helix credentials — it just plays on the timer).
   An unchecked-but-checkable link is skipped this time and becomes
   eligible on the next loop. It never auto-plays a stream the
   second it goes live — switching happens only on sir's timer.
   The Shower is MUTED by default (player muted + source volume 0),
   so other streams' audio never goes out to viewers unless sir
   turns on "Play audio from the current stream", which unmutes only
   the link playing now. The Watcher dock (his own monitoring) is
   not muted.
2. **Offline-screen watch (added 2026-11-25, sir)** — the Watcher
   dock also watches the player IT is showing for the official
   Twitch / Kick offline screen, and when that screen shows it
   triggers the same skip. This is the skip that works WITHOUT
   Helix credentials: a Twitch link with no credentials can still
   be skipped once its offline screen is actually seen. How: a
   DOM / JS probe runs once a second in the dock's player page
   (and as the startup script on every page load, so a stream that
   goes offline mid-play is caught without a reload). It reports
   OFFLINE only when the page text contains "offline" AND there is
   no playing `<video>`; a live stream reads LIVE (playing video),
   a loading / buffering stream reads UNKNOWN (never a skip). The
   probe reports back by setting `document.title` to
   `SHOWER:<state>:<n>` — the only return channel the OBS
   browser-panel API gives (`executeJavaScript` is fire-and-forget,
   `titleChanged` is the signal). The offline screen must be
   present for ~3 seconds straight before it skips, so a brief
   buffering / loading screen never false-triggers. Either trigger
   (API says offline OR offline screen seen) causes the same skip,
   and a LIVE probe result is cached LIVE the same way an API
   result is. Toggleable in the source properties ("Watch for the
   offline screen", on by default). It watches the Watcher window's player —
   the source's private browser_source has no JS API OBS exposes
   to a plugin, so the dock (same player URL) is the only place
   the page can be probed.
2. **Next / Previous buttons** in the dock — jump early without
   waiting for the timer.
3. **Countdown in the dock** — "Now: #2 kaicenat (twitch) — switches
   in 07:32", plus an offline note when the current link is cached
   offline.
4. **Channel name only** — see above.
5. **Saved lists** — in the source properties: type a list name and
   hit "Save this list" to save the current 10 links + timers; pick a
   saved list from the "Saved list" dropdown to load it; "Delete
   named list" removes one. Lists live in the source settings
   (`saved_lists` array), so they travel with the scene collection.

### Honest limits

- Twitch embeds need a "parent" host; this build uses
  parent=localhost. If Twitch ever shows a "refused to connect" page,
  that is the embed parent check, not the shower.
- Offline detection uses official APIs only (see above). Without
  Twitch Helix credentials, Twitch links cannot be checked by the
  API: they still play on sir's timer, they are just never
  auto-skipped by the API path — the offline-screen watch is the
  path that skips them, once the official offline screen is seen
  for ~3 seconds. If Twitch / Kick change their offline screen
  layout or wording, the probe's text match may need updating; the
  API check keeps working regardless. If OBS / CEF throttles the
  window while it is hidden, the screen watch may be delayed — the
  API check still runs on its own timer.
  Login-gated / subscriber-only streams need the user signed in
  inside OBS's browser (cookies are shared with the CEF browser,
  same as any Browser Source).
- The source properties carry a note: only show streams you have
  permission to rebroadcast / co-stream with.
- One Stream Shower source per scene collection is the supported
  setup: the window follows the most recently created source.

## Files

- `apply-toggle-patch.py` — the patch. Run it against a fresh
  upstream 33.0.3 copy; it fails loudly if any anchor is missing and
  refuses to run twice on the same tree.
- `FeatureToggles.hpp` — the one toggle table, shared by the
  early-load hook and the Settings page. Every id was verified
  against OBS 33.0.3 registration code; unverified ids were left out
  rather than guessed.
- `canvas-chatbox/` — the chatbox plugin, copied in as a core module.
- `stream-shower/` — the Stream Shower source + Stream Watcher
  pop-out window, copied in as a core module (registered after
  `check_obs_browser()` because it links `OBS::browser-panels`).
- `build-obs-toggle.yml` — GitHub Actions workflow (Windows).
- `README.md` — build/run instructions.

## What is NOT in this build

- No removals of any kind (unlike PS5 Lite).
- No Stinger Maker.
- No FFmpeg removal: obs-ffmpeg is the core of RTMP streaming, the
  Media Source, and the texture encoders.
- No live CPU meter promising "50% of PC": the CPU guard reacts to
  measured CPU, it does not cap it.
