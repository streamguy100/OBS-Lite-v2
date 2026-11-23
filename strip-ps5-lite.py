#!/usr/bin/env python3
"""OBS PS5 Lite strip - run inside a fresh obsproject/obs-studio checkout
at tag 33.0.3 (commit f2aa9ce69caa7239ef26660b5889de4f53d9880e).
Streaming software more powerful than PS5, still light: 50% PC budget.

Locked decisions (23, from sir, 2026-11-23):
 1. x264 REMOVE (hardware NVENC/QSV/AMF only)
 2. Browser Source CHANGE, keep, 720p not 1080p
 3. Noise Suppression CHANGE, use VST instead (RNNoise/Speex out)
 4. Replay Buffer REMOVE (button hidden, start is a no-op)
 5. Studio Mode LEAVE
 6. Display Capture LEAVE
 7. Heavy filters KEEP ALL (Mask/Scroll/Sharpness/GPU Delay/Async Delay)
 8. Virtual Camera CHANGE, lighter, 720p + 30fps (follows 720p30 canvas)
 9. Scripting CHANGE, keep Lua, no Python (WebSocket as-is, stock ON)
10. HDR Tonemap CHANGE, SDR like PS5, tonemap kept so SDR shows full range
11. NVIDIA/Intel/AMD effects CHANGE, off by default (NVAFX/NVVFX OFF at
    build time; no Intel/AMD AI-effects plugin exists in stock OBS to toggle)
12. OpenH264 REMOVE
13. VLC Source REMOVE
14. GDI Text LEAVE
15. Multi-track audio LEAVE
16. Downscale CHANGE, auto based on PC, max 50%: first-run canvas capped
    at 1280x720 (16:9 and 9:16 choices still in Settings), downscale
    greyed out when canvas == output (stock OBS behaviour, kept), number
    picker under Downscale for frames to send at once (wired to the
    hardware encoder B-frame count: 1 frame = 0 B-frames ... 5 = 4)
17. DeckLink REMOVE, NDI stays (NDI is not in stock OBS; nothing to remove)
18. Stinger transitions CHANGE, custom transitions in-app (obs-transitions
    kept: make one in the app, provide one already made, or use the
    pre-made simple ones - Cut/Fade/Swipe/Luma Wipe/Stinger)
19. Preview render LEAVE
20. Game Capture hook LEAVE
21. Built-in audio filters REMOVE (Compressor/Limiter/Expander/Gain out,
    VSTs do the filtering - obs-vst kept)
22. Media preload LEAVE
23. Update checker + telemetry CHANGE, lighter way: check only once on
    startup, never while live; upstream OBS has no telemetry or crash
    reporting in this tree, so there is nothing else to remove

Plus: mic is a SOURCE (win-wasapi Audio Input Capture, per-mic mixer
sliders - stock OBS already does this, kept). Two in-app chatboxes
(docks, local only, no network, no external AI):
- Canvas Chatbox, docked BESIDE the canvas on the RIGHT: type plain
  words and it does it on the canvas - add/remove/move/resize sources,
  set a colour background, or use an image as a full-canvas background.
- Style Chatbox, docked on the LEFT side: live style/colour editor for
  the app itself, in real time as you type, no restart. Colours ONLY,
  no images. Every part gets its own separate colour change:
  background, text, buttons, panels, borders, mixer, scenes, sources,
  controls, transitions, titles - each separately, never one colour
  for everything. E.g. "make the buttons red", "text white",
  "background dark grey".

FFmpeg: obs-ffmpeg STAYS. It is the core of RTMP streaming, the Media
Source, and the NVENC/AMF/QSV texture encoders in OBS - removing it
would break streaming itself. Only the OpenH264 software encoder file
is removed. No other FFmpeg parts are removed.

Usage: python3 strip-ps5-lite.py [path-to-upstream-checkout]
Default: current directory. Fails loudly on any missing file.
"""
import pathlib
import shutil
import sys
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
SCRIPT_DIR = pathlib.Path(__file__).resolve().parent

PLUGINS_CMAKE = '''cmake_minimum_required(VERSION 3.28...3.30)

if(NOT TARGET libobs)
  message(FATAL_ERROR "OBS Core modules require 'libobs' target.")
endif()

option(ENABLE_CORE_MODULES "Enable building OBS Core Modules" ON)
set_property(GLOBAL PROPERTY ENABLE_PLUGINS ${ENABLE_CORE_MODULES})

# FIXME: Remove with OBS 34.0.0
if(DEFINED ENABLE_PLUGINS)
  message(DEPRECATION "The ENABLE_PLUGINS cache variable is deprecated, use 'ENABLE_CORE_MODULES' instead")
  set(ENABLE_CORE_MODULES ${ENABLE_PLUGINS})
endif()

if(NOT ENABLE_CORE_MODULES)
  set_property(GLOBAL APPEND PROPERTY OBS_FEATURES_DISABLED "Core Modules")
  set_obs_core_modules()
  return()
endif()

set_property(GLOBAL APPEND PROPERTY OBS_FEATURES_ENABLED "Core Modules")

macro(check_obs_browser)
  if((OS_WINDOWS AND CMAKE_VS_PLATFORM_NAME MATCHES "(ARM64|x64)") OR OS_MACOS OR OS_LINUX)
    if(NOT EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/obs-browser/CMakeLists.txt")
      message(FATAL_ERROR "Required submodule 'obs-browser' not available.")
    else()
      add_core_module(obs-browser)
    endif()
  else()
    add_custom_target(obs-browser)
    target_disable(obs-browser)
  endif()
endmacro()

macro(check_obs_websocket)
  if(NOT EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/obs-websocket/CMakeLists.txt")
    message(FATAL_ERROR "Required submodule 'obs-websocket' not available.")
  else()
    add_core_module(obs-websocket)
  endif()
endmacro()

# Add plugins in alphabetical order to retain order in IDE projects
# PS5 LITE: only the plugins for the requested scope (see README.md).
# obs-websocket is kept AS-IS (stock ON). obs-vst is kept so VSTs do the
# filtering instead of the removed built-in audio filters. obs-transitions
# is kept for custom transitions. frontend-tools is kept for the Lua
# scripting UI. nv-filters is kept but both NVIDIA SDK effects are OFF
# (see its CMakeLists patch below) so nothing loads unless enabled.
# canvas-chatbox is the new in-app dock beside the canvas.
add_core_module(canvas-chatbox)
add_core_module(frontend-tools PLATFORMS WINDOWS MACOS LINUX WITH_MESSAGE)
add_core_module(image-source)
add_core_module(nv-filters PLATFORMS WINDOWS)
check_obs_browser()
add_core_module(obs-ffmpeg)
add_core_module(obs-filters)
add_core_module(obs-nvenc PLATFORMS WINDOWS LINUX)
add_core_module(obs-outputs)
add_core_module(obs-qsv11 PLATFORMS WINDOWS LINUX ARCHITECTURES x64 x86_64)
add_core_module(obs-text PLATFORMS WINDOWS)
add_core_module(obs-transitions)
add_core_module(obs-vst PLATFORMS WINDOWS MACOS LINUX WITH_MESSAGE)
check_obs_websocket()
add_core_module(rtmp-services)
add_core_module(text-freetype2)
add_core_module(win-capture PLATFORMS WINDOWS)
add_core_module(win-dshow PLATFORMS WINDOWS)
add_core_module(win-wasapi PLATFORMS WINDOWS)

set_obs_core_modules()
'''

FILTERS_CMAKE = '''cmake_minimum_required(VERSION 3.28...3.30)

add_library(obs-filters MODULE)
add_library(OBS::filters ALIAS obs-filters)

target_sources(
  obs-filters
  PRIVATE
    async-delay-filter.c
    chroma-key-filter.c
    color-correction-filter.c
    color-grade-filter.c
    color-key-filter.c
    crop-filter.c
    eq-filter.c
    gpu-delay.c
    hdr-tonemap-filter.c
    invert-audio-polarity.c
    luma-key-filter.c
    mask-filter.c
    noise-gate-filter.c
    obs-filters.c
    scale-filter.c
    scroll-filter.c
    sdr-on-hdr-filter.c
    sharpness-filter.c
)

target_link_libraries(obs-filters PRIVATE OBS::libobs $<$<PLATFORM_ID:Windows>:OBS::w32-pthreads>)

if(OS_WINDOWS)
  configure_file(cmake/windows/obs-module.rc.in obs-filters.rc)
  target_sources(obs-filters PRIVATE obs-filters.rc)
endif()

set_target_properties_obs(obs-filters PROPERTIES FOLDER plugins PREFIX "")
'''

FILTERS_C = '''#include <obs-module.h>

OBS_DECLARE_MODULE()
OBS_MODULE_USE_DEFAULT_LOCALE("obs-filters", "en-US")
MODULE_EXPORT const char *obs_module_description(void)
{
\treturn "OBS core filters";
}

extern struct obs_source_info mask_filter;
extern struct obs_source_info mask_filter_v2;
extern struct obs_source_info crop_filter;
extern struct obs_source_info eq_filter;
extern struct obs_source_info hdr_tonemap_filter;
extern struct obs_source_info sdr_on_hdr_filter;
extern struct obs_source_info color_filter;
extern struct obs_source_info color_filter_v2;
extern struct obs_source_info scale_filter;
extern struct obs_source_info scroll_filter;
extern struct obs_source_info gpu_delay_filter;
extern struct obs_source_info color_key_filter;
extern struct obs_source_info color_key_filter_v2;
extern struct obs_source_info color_grade_filter;
extern struct obs_source_info sharpness_filter;
extern struct obs_source_info sharpness_filter_v2;
extern struct obs_source_info chroma_key_filter;
extern struct obs_source_info chroma_key_filter_v2;
extern struct obs_source_info async_delay_filter;
extern struct obs_source_info invert_polarity_filter;
extern struct obs_source_info noise_gate_filter;
extern struct obs_source_info luma_key_filter;
extern struct obs_source_info luma_key_filter_v2;

bool obs_module_load(void)
{
\tobs_register_source(&mask_filter);
\tobs_register_source(&mask_filter_v2);
\tobs_register_source(&crop_filter);
\tobs_register_source(&eq_filter);
\tobs_register_source(&hdr_tonemap_filter);
\tobs_register_source(&sdr_on_hdr_filter);
\tobs_register_source(&color_filter);
\tobs_register_source(&color_filter_v2);
\tobs_register_source(&scale_filter);
\tobs_register_source(&scroll_filter);
\tobs_register_source(&gpu_delay_filter);
\tobs_register_source(&color_key_filter);
\tobs_register_source(&color_key_filter_v2);
\tobs_register_source(&color_grade_filter);
\tobs_register_source(&sharpness_filter);
\tobs_register_source(&sharpness_filter_v2);
\tobs_register_source(&chroma_key_filter);
\tobs_register_source(&chroma_key_filter_v2);
\tobs_register_source(&async_delay_filter);
\tobs_register_source(&invert_polarity_filter);
\tobs_register_source(&noise_gate_filter);
\tobs_register_source(&luma_key_filter);
\tobs_register_source(&luma_key_filter_v2);
\treturn true;
}
'''


def must_exist(rel):
    p = ROOT / rel
    if not p.exists():
        raise SystemExit(f"STRIP FAILED: expected file/dir missing: {rel}")
    return p


def rm_tree(rel):
    p = must_exist(rel)
    shutil.rmtree(p)
    print(f"removed dir {rel}")


def rm_file(rel):
    p = must_exist(rel)
    p.unlink()
    print(f"removed file {rel}")


def replace_text(rel, old, new, count=1):
    p = must_exist(rel)
    text = p.read_text(encoding="utf-8")
    found = text.count(old)
    if found < count:
        raise SystemExit(
            f"STRIP FAILED: {rel}: expected {count}x {old[:70]!r}, found {found}x"
        )
    text = text.replace(old, new, count)
    p.write_text(text, encoding="utf-8")
    print(f"patched {rel}: {old[:60]!r} x{count}")


def add_frames_picker_ui():
    """Add the 'Frames to send at once' number picker UNDER the Downscale
    Filter row in Settings > Video (frontend/forms/OBSBasicSettings.ui).
    Inserts a new grid row after the downscaleFilter row and shifts the
    rows below it down by one. The picker is a QSpinBox named
    framesPerSend (1-5, default 2)."""
    rel = "frontend/forms/OBSBasicSettings.ui"
    p = must_exist(rel)
    tree = ET.parse(p)
    root = tree.getroot()

    # Map every element to its parent so we can find the grid layout.
    parent = {c: par for par in tree.iter() for c in par}
    downscale_item = None
    for el in root.iter("widget"):
        if el.get("name") == "downscaleFilter":
            downscale_item = parent.get(el)
            break
    if downscale_item is None:
        raise SystemExit(f"STRIP FAILED: {rel}: downscaleFilter widget not found")
    if downscale_item.tag != "item":
        raise SystemExit(f"STRIP FAILED: {rel}: downscaleFilter is not in a grid item")
    grid = parent.get(downscale_item)
    row = int(downscale_item.get("row"))
    # Shift every row below the downscale row down by one.
    for item in grid.findall("item"):
        r = item.get("row")
        if r is not None and int(r) > row:
            item.set("row", str(int(r) + 1))
    # Label cell.
    label_item = ET.SubElement(grid, "item")
    label_item.set("row", str(row + 1))
    label_item.set("column", "0")
    label = ET.SubElement(label_item, "widget")
    label.set("class", "QLabel")
    label.set("name", "framesPerSendLabel")
    prop = ET.SubElement(label, "property")
    prop.set("name", "text")
    s = ET.SubElement(prop, "string")
    s.text = "Frames to send at once"
    # Spinbox cell.
    spin_item = ET.SubElement(grid, "item")
    spin_item.set("row", str(row + 1))
    spin_item.set("column", "1")
    spin = ET.SubElement(spin_item, "widget")
    spin.set("class", "QSpinBox")
    spin.set("name", "framesPerSend")
    for name, val in (("minimum", "1"), ("maximum", "5"), ("value", "2")):
        prop = ET.SubElement(spin, "property")
        prop.set("name", name)
        num = ET.SubElement(prop, "number")
        num.text = val
    tree.write(p, encoding="UTF-8", xml_declaration=True)
    print(f"patched {rel}: added framesPerSend picker under Downscale Filter")

# ----------------------------------------------------------------------
# Strip sequence
# ----------------------------------------------------------------------

REMOVE_DIRS = [
    "plugins/aja",
    "plugins/aja-output-ui",
    "plugins/coreaudio-encoder",
    "plugins/decklink",
    "plugins/decklink-captions",
    "plugins/decklink-output-ui",
    "plugins/linux-alsa",
    "plugins/linux-capture",
    "plugins/linux-jack",
    "plugins/linux-pipewire",
    "plugins/linux-pulseaudio",
    "plugins/linux-v4l2",
    "plugins/mac-avcapture",
    "plugins/mac-capture",
    "plugins/mac-syphon",
    "plugins/mac-videotoolbox",
    "plugins/mac-virtualcam",
    "plugins/obs-libfdk",
    "plugins/obs-webrtc",
    "plugins/obs-x264",
    "plugins/oss-audio",
    "plugins/sndio",
    "plugins/vlc-video",
]

REMOVE_FILES = [
    # 12. OpenH264 software encoder (obs-ffmpeg itself stays - it is core)
    "plugins/obs-ffmpeg/obs-ffmpeg-openh264.c",
    # 3. Noise suppression (RNNoise + Speex) - VSTs do cleanup instead
    "plugins/obs-filters/noise-suppress-filter.c",
    "plugins/obs-filters/cmake/rnnoise.cmake",
    "plugins/obs-filters/cmake/speexdsp.cmake",
    # 21. Built-in audio filters - VSTs do the filtering instead
    "plugins/obs-filters/compressor-filter.c",
    "plugins/obs-filters/limiter-filter.c",
    "plugins/obs-filters/expander-filter.c",
    "plugins/obs-filters/gain-filter.c",
]


def main():
    must_exist("CMakeLists.txt")
    must_exist("plugins/CMakeLists.txt")
    must_exist("plugins/obs-browser/CMakeLists.txt")
    must_exist("plugins/obs-websocket/CMakeLists.txt")

    # --- 1/12/13/17: remove whole plugin folders ---
    for d in REMOVE_DIRS:
        rm_tree(d)
    rm_tree("plugins/obs-filters/rnnoise")
    for f in REMOVE_FILES:
        rm_file(f)

    # --- plugins list: kept plugins + canvas-chatbox (both chatboxes) ---
    (ROOT / "plugins/CMakeLists.txt").write_text(PLUGINS_CMAKE, encoding="utf-8")
    print("wrote plugins/CMakeLists.txt")
    (ROOT / "plugins/obs-filters/CMakeLists.txt").write_text(FILTERS_CMAKE, encoding="utf-8")
    print("wrote plugins/obs-filters/CMakeLists.txt")
    (ROOT / "plugins/obs-filters/obs-filters.c").write_text(FILTERS_C, encoding="utf-8")
    print("wrote plugins/obs-filters/obs-filters.c")

    # --- copy the Canvas Chatbox + Style Chatbox plugin into the tree ---
    src = SCRIPT_DIR / "canvas-chatbox"
    if not src.is_dir():
        raise SystemExit(f"STRIP FAILED: canvas-chatbox plugin missing next to strip script: {src}")
    dst = ROOT / "plugins/canvas-chatbox"
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    for rel in ("CMakeLists.txt", "canvas-chatbox.cpp",
                "data/locale/en-US.ini", "cmake/windows/obs-module.rc.in"):
        must_exist(f"plugins/canvas-chatbox/{rel}")
    print("copied plugins/canvas-chatbox (Canvas Chatbox right + Style Chatbox left)")

    # --- top CMakeLists: drop metal + test-input, scripting stays ON ---
    replace_text("CMakeLists.txt", "  add_subdirectory(libobs-metal)\n", "")
    replace_text("CMakeLists.txt", "add_subdirectory(test/test-input)\n\n", "")

    # --- 9. Scripting: keep Lua, no Python ---
    replace_text(
        "shared/obs-scripting/cmake/python.cmake",
        'option(ENABLE_SCRIPTING_PYTHON "Enable Python scripting support" ON)',
        'option(ENABLE_SCRIPTING_PYTHON "Enable Python scripting support" OFF)',
    )

    # --- 11. NVIDIA effects OFF by default (nothing loads unless enabled) ---
    replace_text(
        "plugins/nv-filters/CMakeLists.txt",
        'option(ENABLE_NVAFX "Enable building with NVIDIA Audio Effects SDK (requires redistributable to be installed)" ON)',
        'option(ENABLE_NVAFX "Enable building with NVIDIA Audio Effects SDK (requires redistributable to be installed)" OFF)',
    )
    replace_text(
        "plugins/nv-filters/CMakeLists.txt",
        'option(ENABLE_NVVFX "Enable building with NVIDIA Video Effects SDK (requires redistributable to be installed)" ON)',
        'option(ENABLE_NVVFX "Enable building with NVIDIA Video Effects SDK (requires redistributable to be installed)" OFF)',
    )

    # --- 2. Browser Source default 1280x720 (was 800x600) ---
    replace_text(
        "plugins/obs-browser/obs-browser-plugin.cpp",
        'obs_data_set_default_int(settings, "width", 800);',
        'obs_data_set_default_int(settings, "width", 1280);',
    )
    replace_text(
        "plugins/obs-browser/obs-browser-plugin.cpp",
        'obs_data_set_default_int(settings, "height", 600);',
        'obs_data_set_default_int(settings, "height", 720);',
    )

    # --- 12. OpenH264: drop from obs-ffmpeg build + registration ---
    replace_text("plugins/obs-ffmpeg/CMakeLists.txt", "    obs-ffmpeg-openh264.c\n", "")
    replace_text(
        "plugins/obs-ffmpeg/obs-ffmpeg.c",
        "extern struct obs_encoder_info openh264_encoder_info;\n",
        "",
    )
    replace_text(
        "plugins/obs-ffmpeg/obs-ffmpeg.c",
        '\tregister_encoder_if_available(&openh264_encoder_info, "libopenh264");\n',
        "",
    )

    # --- 16. First-run canvas capped at 1280x720 (was 1920x1080 cap) ---
    # Output is already capped at <=1280x720 pixels by stock OBS, so on
    # first run canvas == output and the downscale picker greys out.
    replace_text(
        "frontend/widgets/OBSBasic.cpp",
        "\tif (!oldResolutionDefaults && (cx * cy) > (1920 * 1080)) {\n\t\tcx = 1920;\n\t\tcy = 1080;\n\t}",
        "\tif (!oldResolutionDefaults && (cx * cy) > (1280 * 720)) {\n\t\tcx = 1280;\n\t\tcy = 720;\n\t}",
    )
    # --- 1. Default encoders must be hardware (x264 is gone) ---
    replace_text(
        "frontend/widgets/OBSBasic.cpp",
        'config_set_default_string(activeConfiguration, "AdvOut", "Encoder", "obs_x264");',
        'config_set_default_string(activeConfiguration, "AdvOut", "Encoder", "obs_qsv11");',
    )
    replace_text(
        "frontend/widgets/OBSBasic.cpp",
        "useNV ? SIMPLE_ENCODER_NVENC : SIMPLE_ENCODER_X264",
        "useNV ? SIMPLE_ENCODER_NVENC : SIMPLE_ENCODER_QSV",
        count=2,
    )
    # --- 16. Frames-per-send default (2 frames) ---
    replace_text(
        "frontend/widgets/OBSBasic.cpp",
        '\tconfig_set_default_uint(activeConfiguration, "Video", "FPSDen", 1);',
        '\tconfig_set_default_uint(activeConfiguration, "Video", "FPSDen", 1);\n\tconfig_set_default_uint(activeConfiguration, "Video", "FramesPerSend", 2);',
    )

    # --- 16. Frames picker under Downscale Filter in Settings > Video ---
    add_frames_picker_ui()
    replace_text(
        "frontend/settings/OBSBasicSettings.cpp",
        "\tHookWidget(ui->downscaleFilter,      COMBO_CHANGED,  VIDEO_CHANGED);",
        "\tHookWidget(ui->downscaleFilter,      COMBO_CHANGED,  VIDEO_CHANGED);\n\tHookWidget(ui->framesPerSend,       SCROLL_CHANGED, VIDEO_CHANGED);",
    )
    replace_text(
        "frontend/settings/OBSBasicSettings.cpp",
        "\tLoadDownscaleFilters();\n",
        "\tLoadDownscaleFilters();\n\n\tint framesPerSend = (int)config_get_uint(main->Config(), \"Video\", \"FramesPerSend\");\n\tui->framesPerSend->setValue(framesPerSend < 1 ? 2 : framesPerSend);\n",
    )
    replace_text(
        "frontend/settings/OBSBasicSettings.cpp",
        '\tSaveComboData(ui->downscaleFilter, "Video", "ScaleType");',
        '\tSaveComboData(ui->downscaleFilter, "Video", "ScaleType");\n\tSaveSpinBox(ui->framesPerSend, "Video", "FramesPerSend");',
    )

    # --- 16. Frames-per-send drives the hardware encoder B-frame count ---
    # NVENC, QSV and AMF all read "bf" (B-frames): 1 frame = 0 B-frames,
    # 2 = 1, ... 5 = 4. Applies in Simple output mode (the default).
    replace_text(
        "frontend/utility/SimpleOutput.cpp",
        '\tobs_data_set_int(videoSettings, "bitrate", videoBitrate);\n',
        '\tobs_data_set_int(videoSettings, "bitrate", videoBitrate);\n\n\t/* PS5 Lite: frames to send at once (Settings > Video). */\n\tint framesPerSend = (int)config_get_uint(main->Config(), "Video", "FramesPerSend");\n\tif (framesPerSend < 1)\n\t\tframesPerSend = 2;\n\tif (framesPerSend > 5)\n\t\tframesPerSend = 5;\n\tobs_data_set_int(videoSettings, "bf", framesPerSend - 1);\n',
        count=1,
    )

    # --- 4. Replay Buffer: start is a no-op + hide the Controls button ---
    replace_text(
        "frontend/widgets/OBSBasic_ReplayBuffer.cpp",
        "\tif (!outputHandler || !outputHandler->replayBuffer) {\n\t\treturn;\n\t}",
        "\t/* PS5 Lite: Replay Buffer removed - no second encode running. */\n\tblog(LOG_INFO, \"Replay Buffer is removed in OBS PS5 Lite\");\n\treturn;\n\n\tif (!outputHandler || !outputHandler->replayBuffer) {\n\t\treturn;\n\t}",
    )
    replace_text(
        "frontend/widgets/OBSBasicControls.cpp",
        "\tui->replayBufferButton->setVisible(enabled);",
        "\t(void)enabled;\n\tui->replayBufferButton->setVisible(false); // PS5 Lite: Replay Buffer removed",
    )

    # --- 23. Updater: never check while live (startup only) ---
    replace_text(
        "frontend/widgets/OBSBasic_Updater.cpp",
        '\tif (!config_get_bool(App()->GetAppConfig(), "General", "EnableAutoUpdates")) {\n\t\treturn;\n\t}',
        '\tif (!config_get_bool(App()->GetAppConfig(), "General", "EnableAutoUpdates")) {\n\t\treturn;\n\t}\n\n\t/* PS5 Lite: never check for updates while live - startup only. */\n\tif (outputHandler && (outputHandler->StreamingActive() || outputHandler->RecordingActive())) {\n\t\treturn;\n\t}',
    )

    # --- verify: no removed names remain in the files we touched ---
    banned = [
        "obs-x264",
        "openh264",
        "noise_suppress",
        "compressor_filter",
        "limiter_filter",
        "expander_filter",
        "gain_filter",
        "vlc-video",
        "decklink",
    ]
    for f in [
        ROOT / "plugins/CMakeLists.txt",
        ROOT / "plugins/obs-filters/CMakeLists.txt",
        ROOT / "plugins/obs-filters/obs-filters.c",
        ROOT / "plugins/obs-ffmpeg/CMakeLists.txt",
        ROOT / "plugins/obs-ffmpeg/obs-ffmpeg.c",
    ]:
        text = f.read_text(encoding="utf-8")
        hits = [b for b in banned if b in text]
        if hits:
            raise SystemExit(f"STRIP FAILED: removed names still present in {f}: {hits}")

    # Python scripting must be OFF, Lua ON, NVIDIA effects OFF.
    py = (ROOT / "shared/obs-scripting/cmake/python.cmake").read_text(encoding="utf-8")
    if 'ENABLE_SCRIPTING_PYTHON "Enable Python scripting support" ON' in py:
        raise SystemExit("STRIP FAILED: Python scripting is still ON")
    lua = (ROOT / "shared/obs-scripting/cmake/lua.cmake").read_text(encoding="utf-8")
    if 'ENABLE_SCRIPTING_LUA "Enable Lua scripting support" ON' not in lua:
        raise SystemExit("STRIP FAILED: Lua scripting is not ON")
    nv = (ROOT / "plugins/nv-filters/CMakeLists.txt").read_text(encoding="utf-8")
    if "ENABLE_NVAFX" in nv and '" ON)' in nv:
        raise SystemExit("STRIP FAILED: NVIDIA effects are still ON")

    # Plugin count + names.
    plugins = sorted(p.name for p in (ROOT / "plugins").iterdir() if p.is_dir())
    print(f"plugins left ({len(plugins)}): {', '.join(plugins)}")
    expected = sorted([
        "canvas-chatbox", "frontend-tools", "image-source", "nv-filters",
        "obs-browser", "obs-ffmpeg", "obs-filters", "obs-nvenc",
        "obs-outputs", "obs-qsv11", "obs-text", "obs-transitions",
        "obs-vst", "obs-websocket", "rtmp-services", "text-freetype2",
        "win-capture", "win-dshow", "win-wasapi",
    ])
    if plugins != expected:
        raise SystemExit(
            f"STRIP FAILED: expected plugins {expected}, got {plugins}"
        )

    # Frames picker present in the settings UI.
    ui = (ROOT / "frontend/forms/OBSBasicSettings.ui").read_text(encoding="utf-8")
    if "framesPerSend" not in ui:
        raise SystemExit("STRIP FAILED: framesPerSend picker missing from Settings UI")
    ET.fromstring(ui.encode("utf-8"))
    print("PS5 Lite strip OK: 19 plugins, Lua-only scripting, hardware encoders only, both chatboxes in")


if __name__ == "__main__":
    main()
