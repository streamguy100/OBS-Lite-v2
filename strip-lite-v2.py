#!/usr/bin/env python3
"""OBS Lite v2 strip - run inside a fresh obsproject/obs-studio checkout
at commit 65c320b (OBS 33.0.1). Deletes everything except streaming +
canvas, removes super-CPU users. Fails loudly on any missing file.
Usage: python3 strip-lite-v2.py [path-to-upstream-checkout]
Default: current directory.
"""
import pathlib, shutil, sys

PLUGINS_CMAKE = 'cmake_minimum_required(VERSION 3.28...3.30)\n\nif(NOT TARGET libobs)\n  message(FATAL_ERROR "OBS Core modules require \'libobs\' target.")\nendif()\n\noption(ENABLE_CORE_MODULES "Enable building OBS Core Modules" ON)\nset_property(GLOBAL PROPERTY ENABLE_PLUGINS ${ENABLE_CORE_MODULES})\n\n# FIXME: Remove with OBS 34.0.0\nif(DEFINED ENABLE_PLUGINS)\n  message(DEPRECATION "The ENABLE_PLUGINS cache variable is deprecated, use \'ENABLE_CORE_MODULES\' instead")\n  set(ENABLE_CORE_MODULES ${ENABLE_PLUGINS})\nendif()\n\nif(NOT ENABLE_CORE_MODULES)\n  set_property(GLOBAL APPEND PROPERTY OBS_FEATURES_DISABLED "Core Modules")\n  set_obs_core_modules()\n  return()\nendif()\n\nset_property(GLOBAL APPEND PROPERTY OBS_FEATURES_ENABLED "Core Modules")\n\nmacro(check_obs_browser)\n  if((OS_WINDOWS AND CMAKE_VS_PLATFORM_NAME MATCHES "(ARM64|x64)") OR OS_MACOS OR OS_LINUX)\n    if(NOT EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/obs-browser/CMakeLists.txt")\n      message(FATAL_ERROR "Required submodule \'obs-browser\' not available.")\n    else()\n      add_core_module(obs-browser)\n    endif()\n  else()\n    add_custom_target(obs-browser)\n    target_disable(obs-browser)\n  endif()\nendmacro()\n\nmacro(check_obs_websocket)\n  if(NOT EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/obs-websocket/CMakeLists.txt")\n    message(FATAL_ERROR "Required submodule \'obs-websocket\' not available.")\n  else()\n    add_core_module(obs-websocket)\n  endif()\nendmacro()\n\n\n# Add plugins in alphabetical order to retain order in IDE projects\n# LITE STRIP: only the plugins for the requested scope - see LITE-README.md\n# obs-websocket is kept ONLY so its OBS::websocket-api target exists:\n# obs-browser links it. The websocket server itself is disabled below\n# (ENABLE_WEBSOCKET OFF), so no obs-websocket.dll is built.\nadd_core_module(image-source)\ncheck_obs_browser()\nadd_core_module(obs-ffmpeg)\nadd_core_module(obs-filters)\nadd_core_module(obs-nvenc PLATFORMS WINDOWS LINUX)\nadd_core_module(obs-outputs)\nadd_core_module(obs-qsv11 PLATFORMS WINDOWS LINUX ARCHITECTURES x64 x86_64)\ncheck_obs_websocket()\nadd_core_module(rtmp-services)\nadd_core_module(text-freetype2)\nadd_core_module(win-capture PLATFORMS WINDOWS)\nadd_core_module(win-dshow PLATFORMS WINDOWS)\nadd_core_module(win-wasapi PLATFORMS WINDOWS)\n\nset_obs_core_modules()\n'

FILTERS_CMAKE = 'cmake_minimum_required(VERSION 3.28...3.30)\n\nadd_library(obs-filters MODULE)\nadd_library(OBS::filters ALIAS obs-filters)\n\ntarget_sources(\n  obs-filters\n  PRIVATE\n    chroma-key-filter.c\n    color-correction-filter.c\n    color-grade-filter.c\n    color-key-filter.c\n    compressor-filter.c\n    crop-filter.c\n    eq-filter.c\n    expander-filter.c\n    gain-filter.c\n    invert-audio-polarity.c\n    limiter-filter.c\n    luma-key-filter.c\n    noise-gate-filter.c\n    obs-filters.c\n    scale-filter.c\n)\n\ntarget_link_libraries(obs-filters PRIVATE OBS::libobs $<$<PLATFORM_ID:Windows>:OBS::w32-pthreads>)\n\n\nif(OS_WINDOWS)\n  configure_file(cmake/windows/obs-module.rc.in obs-filters.rc)\n  target_sources(obs-filters PRIVATE obs-filters.rc)\nendif()\n\nset_target_properties_obs(obs-filters PROPERTIES FOLDER plugins PREFIX "")\n'

FILTERS_C = '#include <obs-module.h>\n\nOBS_DECLARE_MODULE()\nOBS_MODULE_USE_DEFAULT_LOCALE("obs-filters", "en-US")\nMODULE_EXPORT const char *obs_module_description(void)\n{\n\treturn "OBS core filters";\n}\n\nextern struct obs_source_info crop_filter;\nextern struct obs_source_info gain_filter;\nextern struct obs_source_info eq_filter;\nextern struct obs_source_info color_filter;\nextern struct obs_source_info color_filter_v2;\nextern struct obs_source_info scale_filter;\nextern struct obs_source_info color_key_filter;\nextern struct obs_source_info color_key_filter_v2;\nextern struct obs_source_info color_grade_filter;\nextern struct obs_source_info chroma_key_filter;\nextern struct obs_source_info chroma_key_filter_v2;\nextern struct obs_source_info invert_polarity_filter;\nextern struct obs_source_info noise_gate_filter;\nextern struct obs_source_info compressor_filter;\nextern struct obs_source_info limiter_filter;\nextern struct obs_source_info expander_filter;\nextern struct obs_source_info upward_compressor_filter;\nextern struct obs_source_info luma_key_filter;\nextern struct obs_source_info luma_key_filter_v2;\n\nbool obs_module_load(void)\n{\n\tobs_register_source(&crop_filter);\n\tobs_register_source(&gain_filter);\n\tobs_register_source(&eq_filter);\n\tobs_register_source(&color_filter);\n\tobs_register_source(&color_filter_v2);\n\tobs_register_source(&scale_filter);\n\tobs_register_source(&color_key_filter);\n\tobs_register_source(&color_key_filter_v2);\n\tobs_register_source(&color_grade_filter);\n\tobs_register_source(&chroma_key_filter);\n\tobs_register_source(&chroma_key_filter_v2);\n\tobs_register_source(&invert_polarity_filter);\n\tobs_register_source(&noise_gate_filter);\n\tobs_register_source(&compressor_filter);\n\tobs_register_source(&limiter_filter);\n\tobs_register_source(&expander_filter);\n\tobs_register_source(&upward_compressor_filter);\n\tobs_register_source(&luma_key_filter);\n\tobs_register_source(&luma_key_filter_v2);\n\treturn true;\n}\n'

# --- custom OBS Lite icon (green, OBS-style lens, "LITE") ---
# The .ico is embedded as base64 so the strip script stays a plain text
# file (the GitHub file API rejects binary uploads). Written over the
# stock obs-studio.ico during the strip; SHA-checked below.
ICON_SHA256 = "922c7486343b08ea48a168f57f32761f984506b344ed855ed723ccdf479e3268"
ICON_B64 = (
    "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"
    "0VTfjcf/DddNvIiMCfpl/LHLLUWYGThv02Le+9RNnLXgev5r1T10mjQJr5q6ilH8aUZo/Bkb0J893GU0ZVfvVfGHs/6TU0ZPR0of"
    "Iz3mbVjIhxZ+helt13LXmodJm3BYEyYxFT4w8ITKDgfuOO0bmKAX6fqgkuEEoAQo6ZHp28YnJl3BLSd+jowN8GThbv+ugb1F7Ut5"
    "71Nf4r1P3cC8jQsRXgUqUY8nPNKZLm79q6/yjobQ+Isx1PCilYkNfjW/mP4tqlUF0mo8vwaVqOOVjpVc++fZTJ//CX6z7o9REpPo"
    "V3WgeDhw2eEz+Mk7WggynUULljp2x93VIiOFQme6OGnUSfzw5Jsw0TRfof1XmBko6Qh6uOGlW5nx+GeZt/FppFeF8muwUW8bpDto"
    "nngR1xw5q2jGH6OEIrCak+qO5l9P+iI605UtPCK9SlSinld2rOKqZ/+BC5/+Ksu71qGE7FcdAC/6zk9PvJhrjm0mSLX3S0Qd+8YJ"
    "QBERCITJUK0q+fX0FqpUEkthmynHBTc9oXhq2yucMf9ablv+SzJCovw6TBT9F4Cxmgq/hn8+4VPRnhDF/1ljg/70xIuZ0jgVHfQi"
    "kVE7IiHwa/j9+sc5Y/413LnmoexMR6Hj9/A7NbeddAMnjzqJINPpEoWKjLubRUQKgQ56ue3Ur3FS3dFRhl/+t9hE0VgpJLe+3krT"
    "E59jeddavOQhALsV1lBCYTNdXDb+AiZXj8NEcYJiE5cF94Tiq5OuBJ3aLXU3FiTl19Fh0lz35zlct+Q77Ah6kZF4FPKdAkG1quBX"
    "01uo9WoQbouKouIEoEgoodDpDi6feDHXHDmr4Ii/ieb0O4NePvn8v3LTkn9BC4X0KglssPfxkY9x9bjzI3e7dMahoqKkF499NzWV"
    "h6JNZi9j1FYjhEIl6rnz9blc8NQNrOh+K9ub54sUMjv8+M5JN6DTzgsoJu5OFgGJwJo0h1WP47aTbii4F44/157p4j1PfYn/WtWK"
    "lzwU9uNGCwRGpziy7ijOGnVS2JYSLqgRCKw1jE028p4xp4Pu3ef3hTMWGq9iFM9ufZl3tX2KxduXZ2MJ+RLHAz531Ad5z7hz0S4o"
    "WDTcXSwCQkhMppvvnPh5xiQbsvPn+bCr8c9aeBPPblmCXzGKwAb7DaRJIcBkmFQ9njqvCjsA02Vx7t+pdZPAHNgdD0yA8mvYltnB"
    "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"
    "AZxHgt4tWc7kAAAAAElFTkSuQmCC"
)

ROOT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
def must_exist(p):
    if not p.exists():
        raise SystemExit(f"STRIP FAILED: expected file missing: {p}")
    return p
def rm_tree(rel):
    p = must_exist(ROOT / rel)
    shutil.rmtree(p)
    print(f"removed dir {rel}")
def rm_file(rel):
    p = must_exist(ROOT / rel)
    p.unlink()
    print(f"removed file {rel}")
def replace_text(rel, old, new, count=1):
    p = must_exist(ROOT / rel)
    t = p.read_text()
    if old not in t:
        raise SystemExit(f"STRIP FAILED: pattern not found in {rel}: {old[:80]!r}")
    t = t.replace(old, new, count)
    p.write_text(t)
    print(f"edited {rel}")

# --- v1 deletions: non-Windows / capture-card / extra plugins, test, metal ---
for d in [
 "plugins/aja","plugins/aja-output-ui","plugins/coreaudio-encoder",
 "plugins/decklink","plugins/decklink-captions","plugins/decklink-output-ui",
 "plugins/frontend-tools","plugins/linux-alsa","plugins/linux-capture",
 "plugins/linux-jack","plugins/linux-pipewire","plugins/linux-pulseaudio",
 "plugins/linux-v4l2","plugins/mac-avcapture","plugins/mac-capture",
 "plugins/mac-syphon","plugins/mac-videotoolbox","plugins/mac-virtualcam",
 "plugins/nv-filters","plugins/obs-libfdk","plugins/obs-transitions",
 "plugins/obs-vst","plugins/obs-webrtc",
 "plugins/oss-audio","plugins/sndio","plugins/vlc-video",
 "libobs-metal","test",
]:
    rm_tree(d)

# --- v2 deletions: super-CPU plugins ---
for d in ["plugins/obs-x264","plugins/obs-text"]:
    rm_tree(d)

# --- v2 deletions: heavy filters ---
for f in [
 "plugins/obs-filters/noise-suppress-filter.c",
 "plugins/obs-filters/hdr-tonemap-filter.c",
 "plugins/obs-filters/sdr-on-hdr-filter.c",
 "plugins/obs-filters/mask-filter.c",
 "plugins/obs-filters/scroll-filter.c",
 "plugins/obs-filters/sharpness-filter.c",
 "plugins/obs-filters/gpu-delay.c",
 "plugins/obs-filters/async-delay-filter.c",
 "plugins/obs-filters/data/hdr_tonemap_filter.effect",
 "plugins/obs-filters/data/sdr_on_hdr_filter.effect",
 "plugins/obs-filters/data/mask_alpha_filter.effect",
 "plugins/obs-filters/data/mask_color_filter.effect",
 "plugins/obs-filters/data/sharpness.effect",
 "plugins/obs-ffmpeg/obs-ffmpeg-openh264.c",
]:
    rm_file(f)
rm_tree("plugins/obs-filters/rnnoise")
rm_file("plugins/obs-filters/cmake/rnnoise.cmake")
rm_file("plugins/obs-filters/cmake/speexdsp.cmake")
if not (ROOT / "plugins/obs-filters/cmake/windows/obs-module.rc.in").exists():
    raise SystemExit("STRIP FAILED: plugins/obs-filters/cmake/windows/obs-module.rc.in is gone - strip script deleted too much")

# --- full-file replacements (exact v2 versions) ---
(ROOT / "plugins/CMakeLists.txt").write_text(PLUGINS_CMAKE)
print("wrote plugins/CMakeLists.txt")
(ROOT / "plugins/obs-filters/CMakeLists.txt").write_text(FILTERS_CMAKE)
print("wrote plugins/obs-filters/CMakeLists.txt")
(ROOT / "plugins/obs-filters/obs-filters.c").write_text(FILTERS_C)
print("wrote plugins/obs-filters/obs-filters.c")

# --- top CMakeLists: drop metal + test-input, scripting OFF ---
replace_text("CMakeLists.txt", "  add_subdirectory(libobs-metal)\n", "")
replace_text("CMakeLists.txt", "add_subdirectory(test/test-input)\n\n", "")
replace_text("CMakeLists.txt", 'option(ENABLE_SCRIPTING "Enable scripting support" ON)', 'option(ENABLE_SCRIPTING "Enable scripting support" OFF)')

# --- obs-websocket: keep the API target, disable the server ---
# Upstream defines OBS::websocket-api BEFORE the ENABLE_WEBSOCKET check,
# so OFF still leaves the target obs-browser links against, but builds no
# obs-websocket.dll and needs no websocketpp/asio deps.
replace_text("plugins/obs-websocket/CMakeLists.txt", 'option(ENABLE_WEBSOCKET "Enable building OBS with websocket plugin" ON)', 'option(ENABLE_WEBSOCKET "Enable building OBS with websocket plugin" OFF)')

# --- custom icon: replace the stock OBS exe icon ---
import base64 as _b64, hashlib as _hashlib
_icon_bytes = _b64.b64decode(ICON_B64)
if _hashlib.sha256(_icon_bytes).hexdigest() != ICON_SHA256:
    raise SystemExit("STRIP FAILED: embedded icon bytes do not match ICON_SHA256")
_icon_target = ROOT / "frontend/cmake/windows/obs-studio.ico"
must_exist(_icon_target)
_icon_target.write_bytes(_icon_bytes)
print("replaced frontend/cmake/windows/obs-studio.ico with custom OBS Lite icon")

# --- obs-ffmpeg: drop OpenH264 ---
replace_text("plugins/obs-ffmpeg/CMakeLists.txt", "    obs-ffmpeg-openh264.c\n", "")
replace_text("plugins/obs-ffmpeg/obs-ffmpeg.c", "extern struct obs_encoder_info openh264_encoder_info;\n", "")
replace_text("plugins/obs-ffmpeg/obs-ffmpeg.c", '\tregister_encoder_if_available(&openh264_encoder_info, "libopenh264");\n', "")

# --- verify: no removed names remain ---
import re
bad = ["obs-x264","obs-text","openh264","noise_suppress","mask_filter","scroll_filter","sharpness_filter","gpu_delay","async_delay","hdr_tonemap","sdr_on_hdr"]
hits = []
for pat in bad:
    for p in (ROOT / "plugins").rglob("*"):
        if p.is_file() and pat in p.name:
            hits.append(str(p))
    # also grep CMakeLists files
    for f in [(ROOT / "plugins/CMakeLists.txt"), (ROOT / "plugins/obs-filters/CMakeLists.txt"), (ROOT / "plugins/obs-ffmpeg/CMakeLists.txt")]:
        if pat in f.read_text():
            hits.append(f"{f}:{pat}")
if hits:
    raise SystemExit(f"STRIP FAILED: removed names still present: {hits}")
print("STRIP OK: 13 plugin folders left (12 built + obs-websocket API-only, server OFF):", sorted(p.name for p in (ROOT / "plugins").iterdir() if p.is_dir()))
print("STRIP OK: scripting OFF, hardware encoders only (NVENC/QSV/AMF)")

