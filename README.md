# Stinger Maker — OBS plugin

Simple stinger transition maker, as an OBS plugin. Works on OBS 30–33.

- Adds **"Stinger Maker"** to Scene Transitions **+** dropdown.
- Adds **Tools > Stinger Maker** — same maker, open any time.
- No timeline, no video file: pick a style (Wipe / Slide / Zoom / Glitch / Neon),
  two colours, text, duration (0.5 / 1 / 1.5 / 2 s) and transition point (default 50%).
  The transition draws live while OBS switches scenes.
- Sound on/off property exists but this version ships **no sound** — nothing is faked.
- Only stable libobs APIs since OBS 28. No FFmpeg, no external DLLs.

## Install

Drop the `stinger-maker` folder into OBS:

```
OBS install folder / core / stinger-maker / stinger-maker.dll
OBS install folder / core / stinger-maker / data / stinger_maker.effect
OBS install folder / core / stinger-maker / data / locale / en-US.ini
```

Restart OBS. Scene Transitions + > Stinger Maker, or Tools > Stinger Maker.

## Build

GitHub Actions, Windows runner, OBS 33.0.3 headers: `.github/workflows/build-stinger-maker.yml`.
It clones upstream OBS 33.0.3, copies `plugin/` into `upstream/plugins/stinger-maker`,
configures with `cmake --preset windows-ci-x64` and builds **only** the
`stinger-maker` target — it does not rebuild all of OBS. Release tag `v1.0.0-stinger-maker`.
