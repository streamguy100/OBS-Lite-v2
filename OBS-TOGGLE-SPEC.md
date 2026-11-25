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

## Files

- `apply-toggle-patch.py` — the patch. Run it against a fresh
  upstream 33.0.3 copy; it fails loudly if any anchor is missing and
  refuses to run twice on the same tree.
- `FeatureToggles.hpp` — the one toggle table, shared by the
  early-load hook and the Settings page. Every id was verified
  against OBS 33.0.3 registration code; unverified ids were left out
  rather than guessed.
- `canvas-chatbox/` — the chatbox plugin, copied in as a core module.
- `build-obs-toggle.yml` — GitHub Actions workflow (Windows).
- `README.md` — build/run instructions.

## What is NOT in this build

- No removals of any kind (unlike PS5 Lite).
- No Stinger Maker.
- No FFmpeg removal: obs-ffmpeg is the core of RTMP streaming, the
  Media Source, and the texture encoders.
- No live CPU meter promising "50% of PC": the CPU guard reacts to
  measured CPU, it does not cap it.
