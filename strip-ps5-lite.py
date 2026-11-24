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
    PLUS: Stinger Maker plugin (plugins/stinger-maker) is a CORE module,
    so it shows in Scene Transitions + and in Tools > Stinger Maker.
    WHIP is also back as a CORE module (plugins/obs-webrtc) so it shows
    in Settings > Stream > Service.
    PLUGIN LOADING FIX (2026-11-24, sir's log ldOl7WObBNsBmNjV): OBS 33
    core modules are a HARDCODED list built into obs.dll - a DLL dropped
    into core/ is NEVER loaded if its name is not on that list (no log
    entry at all). That is why obs-webrtc and stinger-maker never showed
    up when dropped into core/ by hand. Both are now on the core list
    via add_core_module(), exactly like canvas-chatbox. Do NOT remove
    either again without also removing the plugin from the build.
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
# obs-webrtc is back as a CORE module (WHIP in Settings > Stream > Service).
# stinger-maker is a CORE module too (Scene Transitions + and Tools menu).
# Both MUST be on this list: OBS 33 only loads core modules whose names
# are in the hardcoded list built into obs.dll - a DLL dropped into
# core/ by hand is never loaded (sir's log, 2026-11-24).
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
add_core_module(stinger-maker)
add_core_module(obs-vst PLATFORMS WINDOWS MACOS LINUX WITH_MESSAGE)
add_core_module(obs-webrtc)
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
    # NOTE: plugins/obs-webrtc is NOT removed - WHIP (Settings > Stream >
    # Service) needs it, and it must be a CORE module to load at all.
    # Only plugins/obs-x264 (the x264 ENCODER plugin) is removed.
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
    # Run #4 root cause guard: the plugin must actually be REGISTERED
    # with CMake (add_core_module -> add_subdirectory) and must declare
    # a MODULE_LIBRARY target, otherwise the build succeeds silently
    # with no canvas-chatbox.dll and step 8 is the first to notice.
    plugins_cmake = (ROOT / "plugins/CMakeLists.txt").read_text(encoding="utf-8")
    if "add_core_module(canvas-chatbox)" not in plugins_cmake:
        raise SystemExit("STRIP FAILED: plugins/CMakeLists.txt does not register canvas-chatbox")
    chatbox_cmake = (ROOT / "plugins/canvas-chatbox/CMakeLists.txt").read_text(encoding="utf-8")
    if "add_library(canvas-chatbox MODULE)" not in chatbox_cmake:
        raise SystemExit("STRIP FAILED: canvas-chatbox/CMakeLists.txt has no MODULE_LIBRARY target")
    print("copied plugins/canvas-chatbox (Canvas Chatbox right + Style Chatbox left)")

    # --- copy the Stinger Maker plugin into the tree (CORE module) ---
    # Same pattern as canvas-chatbox: OBS 33 only loads core modules on
    # the hardcoded list in obs.dll, so a hand-dropped DLL in core/ is
    # never loaded (sir's log, 2026-11-24). It must be built in.
    src = SCRIPT_DIR / "stinger-maker"
    if not src.is_dir():
        raise SystemExit(f"STRIP FAILED: stinger-maker plugin missing next to strip script: {src}")
    dst = ROOT / "plugins/stinger-maker"
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    for rel in ("CMakeLists.txt", "stinger-maker.cpp",
                "data/stinger_maker.effect", "data/locale/en-US.ini",
                "cmake/windows/obs-module.rc.in"):
        must_exist(f"plugins/stinger-maker/{rel}")
    plugins_cmake = (ROOT / "plugins/CMakeLists.txt").read_text(encoding="utf-8")
    if "add_core_module(stinger-maker)" not in plugins_cmake:
        raise SystemExit("STRIP FAILED: plugins/CMakeLists.txt does not register stinger-maker")
    if "add_core_module(obs-webrtc)" not in plugins_cmake:
        raise SystemExit("STRIP FAILED: plugins/CMakeLists.txt does not register obs-webrtc (WHIP)")
    stinger_cmake = (ROOT / "plugins/stinger-maker/CMakeLists.txt").read_text(encoding="utf-8")
    if "add_library(stinger-maker MODULE)" not in stinger_cmake:
        raise SystemExit("STRIP FAILED: stinger-maker/CMakeLists.txt has no MODULE_LIBRARY target")
    print("copied plugins/stinger-maker (Stinger Maker transition + Tools maker)")

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

    # --- 1b. Settings crash fix: x264 removed but Settings assumed it ---
    # Sir's PC, OBS 33.0.3, crash opening Settings:
    #   obs64.exe!DisableIncompatibleSimpleContainer <- SimpleRecordingEncoderChanged
    #   <- LoadSimpleOutputSettings <- LoadSettings <- OBSBasicSettings ctor
    # Cause: get_simple_output_encoder() returns "obs_x264" for "x264" /
    # "x264_lowcpu" AND as the default fallback, but the obs-x264 plugin
    # is removed so obs_get_encoder_codec("obs_x264") returns NULL and
    # std::string(NULL) crashes in ucrtbase (c0000005).
    # (1) Null-guard DisableIncompatibleSimpleContainer.
    replace_text(
        "frontend/settings/OBSBasicSettings.cpp",
        '\tstring vCodec = obs_get_encoder_codec(get_simple_output_encoder(QT_TO_UTF8(vEncoder)));',
        '\t/* PS5 Lite: obs_x264 is removed, so obs_get_encoder_codec() can\n\t * return NULL for an unregistered encoder id. std::string(NULL)\n\t * crashes in ucrtbase - guard it (this was the Settings crash). */\n'
        '\tconst char *vCodecC = obs_get_encoder_codec(get_simple_output_encoder(QT_TO_UTF8(vEncoder)));\n'
        '\tstring vCodec = vCodecC ? vCodecC : "";',
    )
    # (2) Null-guard DisableIncompatibleSimpleCodecs (same NULL hazard:
    # assigning NULL char* to a QString is also unsafe).
    replace_text(
        "frontend/settings/OBSBasicSettings.cpp",
        '\t\t\tconst char *encoder_id = get_simple_output_encoder(QT_TO_UTF8(encName));\n'
        '\t\t\tcodec = obs_get_encoder_codec(encoder_id);',
        '\t\t\tconst char *encoder_id = get_simple_output_encoder(QT_TO_UTF8(encName));\n'
        '\t\t\t/* PS5 Lite: obs_get_encoder_codec() returns NULL for an\n\t\t\t * unregistered encoder id (obs_x264 is removed); assigning\n\t\t\t * NULL to a QString crashes - guard it. */\n'
        '\t\t\tconst char *codecC = obs_get_encoder_codec(encoder_id);\n'
        '\t\t\tcodec = codecC ? codecC : QString();',
    )
    # (3) FillSimpleRecordingValues: drop the two Software (x264) entries.
    # Hardware entries (QSV/NVENC/AMD) below are left untouched.
    replace_text(
        "frontend/settings/OBSBasicSettings.cpp",
        '\tui->simpleOutRecEncoder->addItem(ENCODER_STR("Software"), QString(SIMPLE_ENCODER_X264));\n'
        '\tui->simpleOutRecEncoder->addItem(ENCODER_STR("SoftwareLowCPU"), QString(SIMPLE_ENCODER_X264_LOWCPU));',
        '\t/* PS5 Lite: x264 removed - hardware encoders only, no Software entries. */',
    )
    # (4) Stream settings: drop the Software (x264) entry.
    replace_text(
        "frontend/settings/OBSBasicSettings_Stream.cpp",
        '\tui->simpleOutStrEncoder->addItem(ENCODER_STR("Software"), QString(SIMPLE_ENCODER_X264));',
        '\t/* PS5 Lite: x264 removed - hardware encoders only, no Software entry. */',
    )
    # (5) get_simple_output_encoder: never return "obs_x264" again.
    # Old "x264"/"x264_lowcpu" configs fall through to the hardware
    # fallback at the end of the function instead of returning the
    # unregistered obs_x264 id. EncoderAvailable is already declared
    # extern in SimpleOutput.cpp.
    replace_text(
        "frontend/utility/SimpleOutput.cpp",
        '\tif (strcmp(encoder, SIMPLE_ENCODER_X264) == 0) {\n'
        '\t\treturn "obs_x264";\n'
        '\t} else if (strcmp(encoder, SIMPLE_ENCODER_X264_LOWCPU) == 0) {\n'
        '\t\treturn "obs_x264";\n'
        '\t} else if (strcmp(encoder, SIMPLE_ENCODER_QSV) == 0) {',
        '\t/* PS5 Lite: x264 removed - old "x264"/"x264_lowcpu" configs fall\n'
        '\t * through to the hardware fallback at the end of this function. */\n'
        '\tif (strcmp(encoder, SIMPLE_ENCODER_X264) == 0) {\n'
        '\t} else if (strcmp(encoder, SIMPLE_ENCODER_X264_LOWCPU) == 0) {\n'
        '\t} else if (strcmp(encoder, SIMPLE_ENCODER_QSV) == 0) {',
    )
    replace_text(
        "frontend/utility/SimpleOutput.cpp",
        '\t} else if (strcmp(encoder, SIMPLE_ENCODER_APPLE_HEVC) == 0) {\n'
        '\t\treturn "com.apple.videotoolbox.videoencoder.ave.hevc";\n'
        '#endif\n'
        '\t}\n'
        '\n'
        '\treturn "obs_x264";\n'
        '}',
        '\t} else if (strcmp(encoder, SIMPLE_ENCODER_APPLE_HEVC) == 0) {\n'
        '\t\treturn "com.apple.videotoolbox.videoencoder.ave.hevc";\n'
        '#endif\n'
        '\t}\n'
        '\n'
        '\t/* PS5 Lite: x264 is removed - never fall back to obs_x264 (it is\n'
        '\t * never registered, so obs_get_encoder_codec() returns NULL and\n'
        '\t * Settings crashes). Pick the first AVAILABLE hardware encoder. */\n'
        '\tif (EncoderAvailable("obs_nvenc_h264_tex"))\n'
        '\t\treturn "obs_nvenc_h264_tex";\n'
        '\tif (EncoderAvailable("obs_qsv11_v2"))\n'
        '\t\treturn "obs_qsv11_v2";\n'
        '\tif (EncoderAvailable("h264_texture_amf"))\n'
        '\t\treturn "h264_texture_amf";\n'
        '\tif (EncoderAvailable("ffmpeg_nvenc"))\n'
        '\t\treturn "ffmpeg_nvenc";\n'
        '\t/* Last resort - the null-guards in OBSBasicSettings keep this from\n'
        '\t * crashing; Settings shows the encoder as incompatible instead. */\n'
        '\treturn "obs_qsv11_v2";\n'
        '}',
    )
    # (6) Profiles: an unsupported hardware encoder used to fall back to
    # x264. Fall back to the first hardware encoder that IS available
    # on this PC instead (QSV > NVENC > AMD, QSV last resort).
    replace_text(
        "frontend/widgets/OBSBasic_Profiles.cpp",
        '\tauto CheckEncoder = [&](const char *&name) {',
        '\t/* PS5 Lite: x264 is removed - an unsupported hardware encoder must\n'
        '\t * fall back to the first hardware encoder that IS available on this\n'
        '\t * PC, never to x264 (unregistered -> NULL codec -> Settings crash). */\n'
        '\tauto PickFallback = [&]() -> const char * {\n'
        '\t\tif (qsv_supported)\n'
        '\t\t\treturn SIMPLE_ENCODER_QSV;\n'
        '\t\tif (nve_supported)\n'
        '\t\t\treturn SIMPLE_ENCODER_NVENC;\n'
        '\t\tif (amd_supported)\n'
        '\t\t\treturn SIMPLE_ENCODER_AMD;\n'
        '\t\treturn SIMPLE_ENCODER_QSV;\n'
        '\t};\n'
        '\n'
        '\tauto CheckEncoder = [&](const char *&name) {',
    )
    replace_text(
        "frontend/widgets/OBSBasic_Profiles.cpp",
        "\t\t\t\tname = SIMPLE_ENCODER_X264;",
        "\t\t\t\tname = PickFallback();",
        count=10,
    )
    # (6b) Same crash family in the Settings stream fallbacks: a missing
    # encoder used to fall back to x264 / obs_x264, which no longer
    # exists in the dropdowns. Fall back to hardware instead.
    replace_text(
        "frontend/settings/OBSBasicSettings_Stream.cpp",
        '\tif (enc == SIMPLE_ENCODER_QSV_AV1) {\n'
        '\t\treturn SIMPLE_ENCODER_QSV;\n'
        '\t}\n'
        '\treturn SIMPLE_ENCODER_X264;\n'
        '}',
        '\tif (enc == SIMPLE_ENCODER_QSV_AV1) {\n'
        '\t\treturn SIMPLE_ENCODER_QSV;\n'
        '\t}\n'
        '\t/* PS5 Lite: x264 removed - fall back to QSV (hardware). */\n'
        '\treturn SIMPLE_ENCODER_QSV;\n'
        '}',
    )
    replace_text(
        "frontend/settings/OBSBasicSettings_Stream.cpp",
        '\tif (enc == "obs_qsv11_av1") {\n'
        '\t\treturn "obs_qsv11";\n'
        '\t}\n'
        '\treturn "obs_x264";\n'
        '}',
        '\tif (enc == "obs_qsv11_av1") {\n'
        '\t\treturn "obs_qsv11";\n'
        '\t}\n'
        '\t/* PS5 Lite: obs_x264 removed - fall back to QSV (hardware). */\n'
        '\treturn "obs_qsv11_v2";\n'
        '}',
    )
    # (6c) service_supports_codec does strcmp(*codecs, codec) - if the
    # encoder id is unregistered, codec is NULL and strcmp(NULL) crashes.
    # Guard it (same Settings-load path as the reported crash).
    replace_text(
        "frontend/settings/OBSBasicSettings_Stream.cpp",
        'static bool service_supports_codec(const char **codecs, const char *codec)\n'
        '{\n'
        '\tif (!codecs) {\n'
        '\t\treturn true;\n'
        '\t}',
        'static bool service_supports_codec(const char **codecs, const char *codec)\n'
        '{\n'
        '\tif (!codecs) {\n'
        '\t\treturn true;\n'
        '\t}\n'
        '\t/* PS5 Lite: codec is NULL when the encoder id is unregistered\n'
        '\t * (obs_x264 removed); strcmp(NULL) crashes - guard it. */\n'
        '\tif (!codec) {\n'
        '\t\treturn false;\n'
        '\t}',
    )

    # --- 1c. libx264-164.dll must be KEPT (not a strip removal, a guard) ---
    # avcodec-62.dll (FFmpeg) links libx264-164.dll at load time, so
    # obs64.exe will not even start without it (sir hit this in run #6:
    # "libx264-164.dll was not found"). Only the obs-x264 PLUGIN
    # (plugins/obs-x264) is removed - the runtime DLL in bin/64bit is
    # never deleted by this strip. The workflow copies it from the
    # obs-deps tree into the install tree (cmake --install does not,
    # official packaging does it via CPack, which we do not run).
    if any("libx264" in d for d in REMOVE_DIRS) or any("libx264" in f for f in REMOVE_FILES):
        raise SystemExit("STRIP FAILED: strip must never remove libx264-164.dll (avcodec needs it to load)")
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
        "obs-vst", "obs-webrtc", "obs-websocket", "rtmp-services",
        "stinger-maker", "text-freetype2",
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

    # Settings crash fix (run #6, sir's PC): x264 gone but Settings
    # assumed obs_x264 exists. Verify every patch landed.
    settings = (ROOT / "frontend/settings/OBSBasicSettings.cpp").read_text(encoding="utf-8")
    if 'string vCodec = obs_get_encoder_codec(' in settings:
        raise SystemExit("STRIP FAILED: DisableIncompatibleSimpleContainer still has unguarded obs_get_encoder_codec")
    if 'const char *vCodecC = obs_get_encoder_codec(' not in settings:
        raise SystemExit("STRIP FAILED: DisableIncompatibleSimpleContainer null-guard missing")
    if 'codec = obs_get_encoder_codec(encoder_id);' in settings:
        raise SystemExit("STRIP FAILED: DisableIncompatibleSimpleCodecs still has unguarded obs_get_encoder_codec")
    if 'addItem(ENCODER_STR("Software"), QString(SIMPLE_ENCODER_X264))' in settings:
        raise SystemExit("STRIP FAILED: FillSimpleRecordingValues still offers x264")
    if 'addItem(ENCODER_STR("SoftwareLowCPU"), QString(SIMPLE_ENCODER_X264_LOWCPU))' in settings:
        raise SystemExit("STRIP FAILED: FillSimpleRecordingValues still offers x264 LowCPU")
    stream = (ROOT / "frontend/settings/OBSBasicSettings_Stream.cpp").read_text(encoding="utf-8")
    if 'simpleOutStrEncoder->addItem(ENCODER_STR("Software")' in stream:
        raise SystemExit("STRIP FAILED: simpleOutStrEncoder still offers x264")
    if 'return SIMPLE_ENCODER_X264;' in stream:
        raise SystemExit("STRIP FAILED: get_simple_fallback still falls back to x264")
    if 'return "obs_x264";' in stream:
        raise SystemExit("STRIP FAILED: get_adv_fallback still falls back to obs_x264")
    simple = (ROOT / "frontend/utility/SimpleOutput.cpp").read_text(encoding="utf-8")
    if 'return "obs_x264";' in simple:
        raise SystemExit("STRIP FAILED: get_simple_output_encoder still returns obs_x264")
    if 'EncoderAvailable("obs_nvenc_h264_tex")' not in simple:
        raise SystemExit("STRIP FAILED: get_simple_output_encoder hardware fallback missing")
    profiles = (ROOT / "frontend/widgets/OBSBasic_Profiles.cpp").read_text(encoding="utf-8")
    if 'name = SIMPLE_ENCODER_X264;' in profiles:
        raise SystemExit("STRIP FAILED: CheckForSimpleModeX264Fallback still falls back to x264")
    if 'PickFallback' not in profiles:
        raise SystemExit("STRIP FAILED: CheckForSimpleModeX264Fallback PickFallback missing")
    print("PS5 Lite strip OK: 21 plugins, Lua-only scripting, hardware encoders only, both chatboxes in, WHIP + Stinger Maker as core modules")


if __name__ == "__main__":
    main()
