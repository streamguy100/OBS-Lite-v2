/* OBS Toggle — Feature Toggles table (shared by the Plugin Manager
 * early-load hook and the Settings > Feature Toggles page).
 *
 * One table, one source of truth. Each entry maps to exactly one
 * mechanism, and the config key IS the module name / registered id:
 *   - is_module=true  -> obs_add_disabled_module(id): the whole module
 *     DLL is never loaded (files stay on disk, OBS just does not see it).
 *   - is_module=false -> obs_add_disabled_feature(id): libobs refuses
 *     that one registration (encoder / source / filter / transition /
 *     output / service id) while the rest of its module loads normally.
 * Missing config key = ON (default all ON). Only an explicit false
 * disables something.
 *
 * Every id below was verified against OBS 33.0.3 registration code
 * (plugins/*.c, libobs/obs-module.c). Ids that could not be verified
 * were left OUT rather than guessed.
 *
 * Config section: "FeatureToggles" in the user (global) config.
 * GPU switch key: "FeatureToggles"/"GPUVendor" = Auto|AMD|Intel|Nvidia.
 * Eco keys: "FeatureToggles"/"EcoMode", "PreviewOffWhileLive",
 * "Preview15Fps", "HiddenSourcesSleep", "BrowserPauseHidden",
 * "CpuGuard", "CpuGuardThreshold".
 */
#pragma once

#include <obs.h>
#include <util/config-file.h>

#include <cstring>

struct OBSFeatureToggle {
	const char *id; /* config key AND module name / registered id */
	const char *label; /* Settings page text */
	const char *group; /* Encoders | Sources | Filters | Transitions | Outputs | Plugins */
	bool is_module;
	const char *alias_id; /* second registered id disabled with this entry, or nullptr */
};

/* clang-format off */
static const OBSFeatureToggle obs_feature_toggles[] = {
	/* ---- Encoders ---- */
	{"obs-x264", "x264 (Software)", "Encoders", true, nullptr},
	{"obs-nvenc", "NVENC (NVIDIA)", "Encoders", true, nullptr},
	{"ffmpeg_nvenc", "NVENC via FFmpeg", "Encoders", false, nullptr},
	{"ffmpeg_hevc_nvenc", "NVENC HEVC via FFmpeg", "Encoders", false, nullptr},
	{"obs-qsv11", "QuickSync (Intel)", "Encoders", true, nullptr},
	{"h264_texture_amf", "AMF H.264 (AMD)", "Encoders", false, "h264_fallback_amf"},
	{"h265_texture_amf", "AMF HEVC (AMD)", "Encoders", false, "h265_fallback_amf"},
	{"av1_texture_amf", "AMF AV1 (AMD)", "Encoders", false, "av1_fallback_amf"},
	{"ffmpeg_openh264", "OpenH264", "Encoders", false, nullptr},
	/* ---- Sources ---- */
	{"obs-browser", "Browser Source", "Sources", true, nullptr},
	{"game_capture", "Game Capture", "Sources", false, nullptr},
	{"monitor_capture", "Display Capture", "Sources", false, nullptr},
	{"window_capture", "Window Capture", "Sources", false, nullptr},
	{"ffmpeg_source", "Media Source", "Sources", false, nullptr},
	{"image-source", "Image Source", "Sources", true, nullptr},
	{"obs-text", "Text (GDI+)", "Sources", true, nullptr},
	{"text-freetype2", "Text (FreeType 2)", "Sources", true, nullptr},
	{"win-dshow", "Video Capture Device", "Sources", true, nullptr},
	{"wasapi_input_capture", "Audio Input Capture", "Sources", false, nullptr},
	{"wasapi_output_capture", "Audio Output Capture", "Sources", false, nullptr},
	{"wasapi_process_output_capture", "Application Audio Capture", "Sources", false, nullptr},
	{"vlc-video", "VLC Video Source", "Sources", true, nullptr},
	/* ---- Filters (all live in obs-filters; one id each) ---- */
	{"mask_filter", "Image Mask / Blend", "Filters", false, nullptr},
	{"crop_filter", "Crop / Pad", "Filters", false, nullptr},
	{"gain_filter", "Gain", "Filters", false, nullptr},
	{"basic_eq_filter", "3-Band Equalizer", "Filters", false, nullptr},
	{"hdr_tonemap_filter", "HDR Tone Mapping (Override)", "Filters", false, nullptr},
	{"sdr_on_hdr_filter", "Compose SDR on HDR (Override)", "Filters", false, nullptr},
	{"color_filter", "Color Correction", "Filters", false, nullptr},
	{"clut_filter", "Apply LUT", "Filters", false, nullptr},
	{"scale_filter", "Scaling / Aspect Ratio", "Filters", false, nullptr},
	{"scroll_filter", "Scroll", "Filters", false, nullptr},
	{"gpu_delay", "Render Delay", "Filters", false, nullptr},
	{"async_delay_filter", "Video Delay (Async)", "Filters", false, nullptr},
	{"color_key_filter", "Color Key", "Filters", false, nullptr},
	{"chroma_key_filter", "Chroma Key", "Filters", false, nullptr},
	{"luma_key_filter", "Luma Key", "Filters", false, nullptr},
	{"sharpness_filter", "Sharpness", "Filters", false, nullptr},
	{"noise_suppress_filter", "Noise Suppression", "Filters", false, nullptr},
	{"noise_gate_filter", "Noise Gate", "Filters", false, nullptr},
	{"compressor_filter", "Compressor", "Filters", false, nullptr},
	{"limiter_filter", "Limiter", "Filters", false, nullptr},
	{"expander_filter", "Expander", "Filters", false, nullptr},
	{"upward_compressor_filter", "Upward Compressor", "Filters", false, nullptr},
	{"invert_polarity_filter", "Invert Polarity", "Filters", false, nullptr},
	/* ---- Transitions (all live in obs-transitions) ---- */
	{"cut_transition", "Cut", "Transitions", false, nullptr},
	{"fade_transition", "Fade", "Transitions", false, nullptr},
	{"swipe_transition", "Swipe", "Transitions", false, nullptr},
	{"slide_transition", "Slide", "Transitions", false, nullptr},
	{"obs_stinger_transition", "Stinger", "Transitions", false, nullptr},
	{"fade_to_color_transition", "Fade to Color", "Transitions", false, nullptr},
	{"wipe_transition", "Luma Wipe", "Transitions", false, nullptr},
	/* ---- Outputs ---- */
	{"rtmp_output", "RTMP (Stream)", "Outputs", false, nullptr},
	{"flv_output", "Recording: FLV", "Outputs", false, nullptr},
	{"mp4_output", "Recording: MP4", "Outputs", false, nullptr},
	{"mov_output", "Recording: MOV", "Outputs", false, nullptr},
	{"ffmpeg_output", "FFmpeg Output", "Outputs", false, nullptr},
	{"ffmpeg_muxer", "FFmpeg Muxer", "Outputs", false, nullptr},
	{"ffmpeg_mpegts_muxer", "FFmpeg MPEG-TS Muxer", "Outputs", false, nullptr},
	{"ffmpeg_hls_muxer", "FFmpeg HLS Muxer", "Outputs", false, nullptr},
	{"replay_buffer", "Replay Buffer", "Outputs", false, nullptr},
	{"obs-webrtc", "WHIP (obs-webrtc)", "Outputs", true, nullptr},
	/* ---- Plugins (whole modules with no finer-grained entry above) ---- */
	{"obs-vst", "VST Filters (obs-vst)", "Plugins", true, nullptr},
	{"obs-websocket", "WebSocket Server (obs-websocket)", "Plugins", true, nullptr},
	{"rtmp-services", "Stream Services list (Twitch, YouTube, ...)", "Plugins", true, nullptr},
	{"decklink", "DeckLink (input + output)", "Plugins", true, nullptr},
	{"decklink-captions", "DeckLink Captions", "Plugins", true, nullptr},
	{"decklink-output-ui", "DeckLink Output UI", "Plugins", true, nullptr},
	{"aja", "AJA Devices", "Plugins", true, nullptr},
	{"obs-libfdk", "Fraunhofer AAC (obs-libfdk)", "Plugins", true, nullptr},
	{"coreaudio-encoder", "CoreAudio AAC (macOS)", "Plugins", true, nullptr},
	{"nv-filters", "NVIDIA Audio/Video Effects", "Plugins", true, nullptr},
	{"frontend-tools", "Scripts / Frontend Tools", "Plugins", true, nullptr},
	{"stream-shower", "Stream Shower + Watcher (stream-shower)", "Plugins", true, nullptr},
};
/* clang-format on */

static const size_t obs_feature_toggles_count =
	sizeof(obs_feature_toggles) / sizeof(obs_feature_toggles[0]);

/* True when the toggle is ON (missing key = ON, only explicit false is OFF). */
inline bool obs_toggle_is_on(config_t *config, const char *key)
{
	if (!config || !key)
		return true;
	if (!config_has_user_value(config, "FeatureToggles", key))
		return true;
	return config_get_bool(config, "FeatureToggles", key);
}

/* Apply every OFF toggle to libobs BEFORE any module loads. Call from
 * PluginManager::preLoad() — the only place that runs before
 * obs_load_core_modules(). Safe to call twice: libobs dedupes by name
 * for modules; duplicate feature ids are harmless (linear scan). */
inline void obs_apply_feature_toggles(config_t *config)
{
	if (!config)
		return;
	for (size_t i = 0; i < obs_feature_toggles_count; i++) {
		const OBSFeatureToggle *t = &obs_feature_toggles[i];
		if (obs_toggle_is_on(config, t->id))
			continue;
		if (t->is_module) {
			obs_add_disabled_module(t->id);
		} else {
			obs_add_disabled_feature(t->id);
			if (t->alias_id)
				obs_add_disabled_feature(t->alias_id);
		}
		blog(LOG_INFO, "[Feature Toggles] '%s' is OFF, not loading it", t->id);
	}
}

/* GPU switch. Writes concrete encoder toggles for the chosen vendor, so
 * the next launch loads only that vendor's encoders. Auto probes the
 * encoders that actually registered on THIS launch (each encoder module
 * only registers when its hardware is present: obs-nvenc fails load
 * without NVIDIA, obs-qsv11 only registers on Intel adapters, AMF only
 * registers when the AMF runtime answers) and picks that vendor; if
 * none is present it leaves every encoder ON. */
inline void obs_apply_gpu_vendor(config_t *config, const char *vendor)
{
	if (!config || !vendor)
		return;

	const char *pick = vendor;
	if (strcmp(vendor, "Auto") == 0) {
		if (obs_get_encoder_codec("obs_nvenc_h264_tex"))
			pick = "Nvidia";
		else if (obs_get_encoder_codec("obs_qsv11_v2"))
			pick = "Intel";
		else if (obs_get_encoder_codec("h264_texture_amf"))
			pick = "AMD";
		else
			pick = nullptr; /* no hardware encoder found, change nothing */
	}
	if (!pick)
		return;

	auto set_enc = [&](const char *key, bool on) {
		config_set_bool(config, "FeatureToggles", key, on);
	};
	bool amd = strcmp(pick, "AMD") == 0;
	bool intel = strcmp(pick, "Intel") == 0;
	bool nvidia = strcmp(pick, "Nvidia") == 0;
	set_enc("obs-nvenc", nvidia);
	set_enc("ffmpeg_nvenc", nvidia);
	set_enc("ffmpeg_hevc_nvenc", nvidia);
	set_enc("obs-qsv11", intel);
	set_enc("h264_texture_amf", amd);
	set_enc("h264_fallback_amf", amd);
	set_enc("h265_texture_amf", amd);
	set_enc("h265_fallback_amf", amd);
	set_enc("av1_texture_amf", amd);
	set_enc("av1_fallback_amf", amd);
	config_set_string(config, "FeatureToggles", "GPUVendor", pick);
}
