# OBS Lite v2

Light OBS Studio for Windows, built from the official OBS code.

Base: obsproject/obs-studio, tag 33.0.1, commit `65c320b46e1af5c7a555161aea6182cdf7a8c524`.
License: GPL-2.0, see the upstream COPYING.

## What it is

Streaming + canvas only. Everything that is a super CPU user is removed.
Canvas stuff is untouched.

## Kept

Streaming: Custom RTMP only (obs-outputs + obs-ffmpeg + rtmp-services),
hardware encoders only — NVENC (NVIDIA), QuickSync / QSV (Intel), AMF (AMD).
Audio mixer, Mic + Desktop audio, Stream / Video / Audio / Output settings,
Canvas (Base) and Output (Scaled) sizes separate.

Canvas, untouched: Display, Window, Game Capture, Webcam, Image,
Browser Source, Text (FreeType), Media Source, Colour, Mic / Desktop audio.

Light filters only: Crop, Scale, Colour Correction, Colour Grade,
Colour Key, Luma Key, Chroma Key, Gain, Compressor, Limiter, Expander,
Noise Gate, EQ, Invert Polarity.

## Removed

- obs-x264 — software x264 encoder, the biggest CPU hog
- obs-ffmpeg-openh264.c — software OpenH264 encoder
- obs-text — old GDI text, duplicate of FreeType text
- Noise Suppression (RNNoise neural + SpeexDSP)
- HDR Tonemap, SDR-on-HDR
- Mask, Scroll, Sharpness, GPU Delay, Async Delay filters
- Scripting (Lua / Python) — ENABLE_SCRIPTING OFF
- Plus the v1 removals: DeckLink / AJA, Linux / mac capture, VST, WebSocket,
  WebRTC, VLC, transitions, frontend-tools, libobs-metal, test/

12 plugins left: image-source, obs-browser, obs-ffmpeg, obs-filters,
obs-nvenc, obs-outputs, obs-qsv11, rtmp-services, text-freetype2,
win-capture, win-dshow, win-wasapi.

## How the build works

`.github/workflows/build-obs-lite-v2.yml` clones upstream OBS 33.0.1,
runs `strip-lite-v2.py` on it (fail loudly if any step fails, verifies
exactly 12 plugins remain), then runs upstream's own
`.github/scripts/Build-Windows.ps1`, verifies no x264 / noise-suppress
files are in the install folder, and uploads `OBS-Lite-v2.zip` + `obs64.exe`.

## Honest limits

- No software encoder left. If a PC has no hardware encoder
  (no NVENC, no Intel QuickSync, no AMD AMF), this build cannot encode.
  Intel graphics PCs should have QuickSync — pick Encoder: QuickSync H.264.
- The OBS frontend is kept intact. Studio Mode etc. are still in the code,
  just do not use them. Use Scenes, Sources, Mixer, Controls, and
  Settings > Stream / Video / Audio / Output only.
- Virtual Camera still needs its separate admin driver install from
  win-dshow/virtualcam-module.
