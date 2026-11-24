# OBS PS5 Lite — locked spec (2026-11-23, sir)

Goal: streaming software more powerful than PS5, still light — only 50% of PC.

Base: OBS Studio 33.0.3 (`f2aa9ce69caa7239ef26660b5889de4f53d9880e`).

## Locked decisions

1. x264 REMOVE (hardware NVENC/QSV/AMF only)
2. Browser Source CHANGE, keep, 720p not 1080p
3. Noise Suppression CHANGE, use VST instead (VoiceVST/AuraSplitter, not RNNoise/Speex)
4. Replay Buffer REMOVE
5. Studio Mode LEAVE
6. Display Capture LEAVE
7. Heavy filters KEEP ALL inside (Mask/Scroll/Sharpness/GPU Delay/Async Delay, user picks what to add)
8. Virtual Camera CHANGE, lighter, 720p + 30fps
9. Scripting CHANGE, keep Lua, no Python (WebSocket as-is)
10. HDR Tonemap CHANGE, SDR output like PS5, with tonemap kept so SDR shows full range, not clipped
11. NVIDIA/Intel/AMD effects CHANGE, off by default, per-vendor on/off toggle in Settings, only loads if user checks it
12. OpenH264 REMOVE
13. VLC Source REMOVE
14. GDI Text LEAVE
15. Multi-track audio LEAVE
16. Downscale CHANGE, auto based on PC, max 50% PC usage, canvas/output choices 16:9 and 9:16 based on what PC can run at 50%, first-time shows all choices, downscale greyed out if canvas = output, number picker under downscale for frames to send at once
17. DeckLink REMOVE, NDI stays
18. Stinger transitions CHANGE, custom transitions in-app (make one in app, provide one already made, or use pre-made simple ones)
19. Preview render LEAVE
20. Game Capture hook LEAVE
21. Built-in audio filters REMOVE (Compressor/Limiter/Expander/Gain out, VSTs do filtering)
22. Media preload LEAVE
23. Update checker + telemetry CHANGE, lighter way — check only once on startup, never while live, no telemetry/crash reporting

Also: mic must be a source, multiple mics separately controllable (not one
global mic channel). No FFmpeg where it can be removed without breaking
core streaming/recording.

## How each decision is implemented in this build

- 1, 12: `plugins/obs-x264` deleted; `plugins/obs-ffmpeg/obs-ffmpeg-openh264.c`
  deleted (+ CMake line + registration). Default encoders changed to
  hardware: Simple default = NVENC if present else QuickSync; Advanced
  default = `obs_qsv11`.
- 2: browser source defaults 1280x720 (was 800x600), fps 30.
- 3, 21: `noise-suppress-filter.c`, `rnnoise/`, `cmake/rnnoise.cmake`,
  `cmake/speexdsp.cmake`, `compressor/limiter/expander/gain-filter.c`
  deleted; `obs-vst` kept so VSTs do cleanup/filtering.
- 4: `OBSBasic::StartReplayBuffer` is a no-op (logs "removed"); the
  Controls-dock Replay Buffer button is hidden.
- 7, 10: Mask/Scroll/Sharpness/GPU Delay/Async Delay + HDR Tonemap /
  SDR-on-HDR kept in `obs-filters`.
- 8: first-run canvas capped at 1280x720 @ 30fps; virtual camera follows
  the canvas, so it is 720p30.
- 9: `ENABLE_SCRIPTING_PYTHON` OFF, Lua ON; `obs-websocket` untouched (stock ON).
- 11: `ENABLE_NVAFX` / `ENABLE_NVVFX` OFF at build time. Honest limit:
  there is no Intel/AMD AI-effects plugin in stock OBS (QSV/AMF are
  encoders, not effects), so there is nothing to toggle for Intel/AMD.
- 13, 17: `vlc-video`, `decklink*`, `aja*` deleted. NDI is not in stock
  OBS; nothing NDI was removed.
- 14, 15, 19, 20, 22: stock, untouched.
- 16: first-run BaseCX/BaseCY capped at 1280x720 (output was already
  capped at ≤1280x720 by stock OBS, so canvas == output on first run and
  the Downscale picker greys out — stock `LoadDownscaleFilters`
  behaviour, kept). "Frames to send at once" picker (1–5, default 2)
  added under Downscale in Settings > Video; in Simple output mode it
  sets the hardware encoder B-frame count (`bf` = frames − 1; NVENC,
  QSV and AMF all read `bf`). 16:9 and 9:16 choices remain in Settings.
  The 50% cap is a design cap (hardware-only encoding, 720p first-run
  canvas, auto downscale, no background work while live), not a live
  CPU meter — sir's live Windows run is the final check.
- 18: `obs-transitions` kept (Cut/Fade/Swipe/Luma Wipe/Stinger). Make a
  transition in the app, provide one already made, or use the pre-made
  simple ones. Stinger Maker (`stinger-maker`, Scene Transitions + and
  Tools > Stinger Maker) and WHIP (`obs-webrtc`, Settings > Stream >
  Service) are built in as CORE modules. Plugin loading fix 2026-11-24:
  OBS 33 only loads core modules on the hardcoded list in obs.dll - a
  DLL dropped into core/ by hand is never loaded, which is why both
  failed to show when sir dropped them in (log ldOl7WObBNsBmNjV).
- 23: `TimedCheckForUpdates` returns early if streaming or recording is
  active. Upstream OBS has no telemetry or crash reporting in this tree.

## FFmpeg

`obs-ffmpeg` stays: it is the core of RTMP streaming, the Media Source,
and the NVENC/AMF/QSV texture encoders. Removing it would break
streaming. Only the OpenH264 software encoder file was removed.

## The two in-app chatboxes (plugin `plugins/canvas-chatbox`)

Both are OBS docks, local only, no network, no external AI, no
background thread, no timer. Work happens only when the user types
(Style: 400 ms after they stop typing, or on Send; Canvas: on Send).

### Canvas Chatbox — RIGHT of the canvas
Docked beside the canvas in the dock area. Never on top of the canvas,
never inside the scene. Parses plain words and applies them to the
current scene via libobs: add (webcam/game/display/window/browser/mic/
text/image/colour/media), remove, move (named spots or nudges), resize
(bigger/smaller/percentage of canvas width), colour background, image
as full-canvas background. Mic joins the mixer with its own slider.

### Style Chatbox — LEFT side
Live style/colour editor for the app itself, real time as you type, no
restart. Colours ONLY — cannot add images. Each part has its own
separate stylesheet rule, so changing one part never touches another:
background, text, buttons, panels, borders, mixer, scenes, sources,
controls, transitions, titles. "reset style" clears all rules.
Session-only (resets when OBS restarts). The canvas video can't be
recoloured here — stream background belongs to the Canvas Chatbox.

First run: Style left, Canvas right. OBS remembers dock layout after
that; hidden docks come back via View > Docks.
