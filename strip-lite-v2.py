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

