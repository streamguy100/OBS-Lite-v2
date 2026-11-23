# OBS PS5 Lite 33.0.3

Streaming software more powerful than PS5, still light on the PC — 50% PC budget.

Base: obsproject/obs-studio, tag 33.0.3, commit `f2aa9ce69caa7239ef26660b5889de4f53d9880e`.
License: GPL-2.0, see the upstream COPYING.

## What it is

OBS Studio 33.0.3 stripped to the PS5-lite spec sir locked one by one (23 decisions).
Hardware encoding only, no software encoders, no heavy extras — but with more
power than PS5: multiple scenes, multiple mics as separate sources, browser
sources, NDI, Lua scripting, multi-track audio, custom transitions, virtual
camera, Studio Mode, and two in-app chatboxes.

## The two chatboxes (both in the app, both local, no internet, no AI service)

### Canvas Chatbox — docked BESIDE the canvas, on the RIGHT
Type plain words and it does it on the canvas. Never on top of the canvas,
never inside the scene.
- `add my webcam bottom right` / `add game` / `add display` / `add browser https://…` / `add mic` / `add text hello` / `add image "C:\path\pic.png"`
- `make the game bigger` / `resize the image to 50%`
- `move the webcam to top left`
- `remove the text`
- `set background to black`
- `use this image as background` (stretches an image to the full canvas)

### Style Chatbox — docked on the LEFT side
Live style/colour editor for the app itself, in real time as you type,
no restart. **Colours only — it cannot add images.**
Every part gets its own separate colour change, never one colour for everything:
background, text, buttons, panels, borders, mixer, scenes, sources,
controls, transitions, titles.
- `make the buttons red` · `text white` · `background dark grey` · `mixer green` · `scenes blue`
- `reset style` puts everything back to normal.
- The canvas video itself can't be recoloured here — for the stream
  background use the Canvas Chatbox on the right.

First run: Style Chatbox on the left, Canvas Chatbox on the right.
Drag them anywhere you like — OBS remembers the layout. If a dock is
hidden, turn it back on in View > Docks.

## Kept

- Hardware encoders only: NVENC (NVIDIA), QuickSync / QSV (Intel), AMF (AMD).
  First-run default encoder is QuickSync if no NVIDIA card is found.
- Streaming: Custom RTMP (obs-outputs + obs-ffmpeg + rtmp-services), NDI in.
- Mic as a SOURCE: Audio Input Capture (win-wasapi), each mic its own
  mixer slider — turn one up without touching the others.
- Canvas: Display, Window, Game Capture, Webcam, Image, Browser Source
  (720p default), Text (FreeType + GDI), Media Source, Colour, Mic/Desktop audio.
- Filters kept: Mask, Scroll, Sharpness, GPU Delay, Async Delay, Chroma Key,
  Colour Correction/Grade/Key, Luma Key, Crop, Scale, EQ, Noise Gate,
  Invert Polarity, HDR Tonemap + SDR-on-HDR (SDR output like PS5, tonemap
  kept so SDR shows the full range, not clipped).
- VST plugins kept (obs-vst) — VSTs do the audio cleanup/filtering.
- Lua scripting kept, WebSocket as-is (stock ON), Studio Mode, Preview,
  Game Capture hook, multi-track audio, media preload all left as stock.
- Virtual Camera: 720p + 30fps (follows the 720p30 first-run canvas).
- Downscale: first-run canvas capped at 1280x720 (16:9 and 9:16 choices
  still in Settings > Video). Downscale greys out when canvas == output.
  Under Downscale, a "Frames to send at once" picker (1–5, default 2)
  drives the hardware encoder B-frame count in Simple output mode.
- Update checker, lighter way: checks only once on startup, never while
  live. No telemetry or crash reporting exists in upstream OBS to remove.

## Removed

- obs-x264 — software x264 encoder, biggest CPU hog
- obs-ffmpeg-openh264.c — software OpenH264 encoder
- Noise Suppression (RNNoise + SpeexDSP) — use a VST instead
- Built-in audio filters (Compressor / Limiter / Expander / Gain) — use a VST instead
- Replay Buffer — button hidden, starting it does nothing (no second encode)
- VLC Video Source, DeckLink (+ captions/output UI), AJA, WebRTC, Linux/mac capture, obs-libfdk
- Python scripting (Lua stays)

## FFmpeg — honest note

obs-ffmpeg STAYS. It is the core of RTMP streaming, the Media Source,
and the NVENC/AMF/QSV texture encoders in OBS — removing it would break
streaming itself. Only the OpenH264 software encoder file was removed.

## NVIDIA / Intel / AMD effects — honest note

The NVIDIA Audio/Video Effects SDK options are OFF by default in this
build, so nothing loads unless enabled. There is no Intel or AMD
AI-effects plugin in stock OBS to toggle — QSV/AMF are encoders, not
effects — so the per-vendor Settings toggle in the spec is implemented
as build-time OFF for NVIDIA, and there is nothing to load for Intel/AMD.

## How the build works

`.github/workflows/build-obs-ps5-lite.yml` clones upstream OBS 33.0.3,
runs `strip-ps5-lite.py` on it (fails loudly if any step fails, verifies
exactly 19 plugins remain), then runs upstream's own
`.github/scripts/Build-Windows.ps1`, verifies no x264 / VLC / DeckLink
files are in the install folder and that `canvas-chatbox.dll` is built,
and uploads `OBS-PS5-Lite-33.0.3.zip` + `obs64.exe`.

## Honest limits

- No software encoder left. If a PC has no hardware encoder (no NVENC,
  no Intel QuickSync, no AMD AMF), this build cannot encode. Intel
  graphics PCs should have QuickSync — pick Encoder: QuickSync H.264.
- The "Frames to send at once" picker applies in Simple output mode
  (the default). In Advanced output mode, set B-frames in the encoder
  settings yourself.
- Virtual Camera still needs its separate admin driver install from
  win-dshow/virtualcam-module — it does not appear as a webcam from a
  portable exe alone.
- The 50% PC cap is implemented as: hardware-only encoding, 720p
  first-run canvas, auto downscale, light defaults, and no background
  work while live. It is not a live CPU meter — sir's live Windows run
  is the final check that it stays around 50% on his PC.
- The Style Chatbox colours the app UI only, and only for the session
  (they reset when OBS restarts). The Canvas Chatbox changes the scene,
  which is saved with the scene collection like any other edit.
