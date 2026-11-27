#!/usr/bin/env python3
"""OBS Toggle — apply the Feature Toggles patch to pristine OBS 33.0.3.

Usage:  python3 apply-toggle-patch.py <upstream-dir>

What it does (see OBS-TOGGLE-SPEC.md for the full spec):
  * libobs: extend the existing disabled_modules mechanism to CORE
    modules, add a disabled-FEATURES set (per registered id) that the
    four obs_register_*() functions consult, and add the hidden-source
    sleep gate in obs_source_video_tick().
  * frontend: Settings > Feature Toggles page (GPU switch, Eco master,
    every toggleable encoder/source/filter/transition/output/plugin),
    automatic clean restart on Apply, Eco/CPU-saver runtime hooks in
    OBSBasic, update-checker-never-while-live, and the PS5 Lite
    Settings-crash null-guards (adapted: nothing is removed here, so
    x264 stays a valid fallback when it is available).
  * plugins: add canvas-chatbox (Canvas Chatbox right + Style Chatbox
    left) and stream-shower (Stream Shower source + Stream Watcher
    dock, top left) as core modules. NOTHING is removed — official OBS
    33.0.3 stays whole: x264, VLC, DeckLink, all encoders/sources/filters.

Fails loudly (non-zero exit) if any anchor text is not found, so a
silent no-op patch is impossible. Run it against a fresh upstream
copy; it refuses to run twice on the same tree.
"""
import shutil
import sys
from pathlib import Path

UPSTREAM_HEAD = "f2aa9ce69caa7239ef26660b5889de4f53d9880e"
SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else None
MARKER = "OBS Toggle"


def fail(msg):
    raise SystemExit(f"TOGGLE PATCH FAILED: {msg}")


def must_exist(rel):
    if not (ROOT / rel).exists():
        fail(f"missing expected upstream file: {rel}")


def read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def write(rel, text):
    (ROOT / rel).write_text(text, encoding="utf-8")


def replace_text(rel, old, new, count=1):
    text = read(rel)
    if MARKER in text and rel.endswith(".cpp"):
        pass  # marker check is per-section, not per-file
    n = text.count(old)
    if n != count:
        fail(f"{rel}: expected {count}x anchor, found {n}x:\n{old[:160]!r}")
    write(rel, text.replace(old, new))


def insert_after(rel, anchor, block, count=1):
    text = read(rel)
    n = text.count(anchor)
    if n != count:
        fail(f"{rel}: expected {count}x anchor for insert, found {n}x:\n{anchor[:160]!r}")
    write(rel, text.replace(anchor, anchor + block, 1))


def check_not_patched(rel, needle):
    if needle in read(rel):
        fail(f"{rel} looks already patched ({needle!r} present) - refusing to run twice")


# ----------------------------------------------------------------------
# libobs — disabled FEATURES set + core-module disable + register gates
# ----------------------------------------------------------------------

def patch_libobs():
    # --- obs.h: new API next to obs_add_disabled_module ---
    replace_text(
        "libobs/obs.h",
        "EXPORT void obs_add_disabled_module(const char *name);",
        r"""EXPORT void obs_add_disabled_module(const char *name);

/**
 * Adds a registered id (encoder / source / filter / transition /
 * output / service) to the disabled features list. obs_register_*()
 * refuses to register a matching id, so the thing never exists in
 * OBS even though its module still loads. Files stay on disk.
 *
 * @param  id    The registered id to disable (e.g. "game_capture")
 */
EXPORT void obs_add_disabled_feature(const char *id);

/**
 * Returns whether a registered id is on the disabled features list.
 */
EXPORT bool obs_feature_disabled(const char *id);

/**
 * Eco / hidden-source sleep master switch (libobs side). When true,
 * obs_source_video_tick() skips sources that are not showing anywhere
 * and are not producing audio, so hidden media/browser/VLC sources
 * stop decoding until they are shown again.
 */
EXPORT void obs_set_hidden_sources_sleep(bool enabled);""",
    )

    # --- obs-internal.h: the set lives next to disabled_modules ---
    replace_text(
        "libobs/obs-internal.h",
        "\tDARRAY(char *) disabled_modules;\n",
        "\tDARRAY(char *) disabled_modules;\n\tDARRAY(char *) disabled_features;\n",
    )

    # --- obs.c: free the set at shutdown, next to disabled_modules ---
    replace_text(
        "libobs/obs.c",
        """	for (size_t i = 0; i < obs->disabled_modules.num; i++) {
		bfree(obs->disabled_modules.array[i]);
	}
	da_free(obs->disabled_modules);
""",
        """	for (size_t i = 0; i < obs->disabled_modules.num; i++) {
		bfree(obs->disabled_modules.array[i]);
	}
	da_free(obs->disabled_modules);

	for (size_t i = 0; i < obs->disabled_features.num; i++) {
		bfree(obs->disabled_features.array[i]);
	}
	da_free(obs->disabled_features);
""",
    )

    # --- obs-module.c: API + gates ---
    replace_text(
        "libobs/obs-module.c",
        """void obs_add_disabled_module(const char *name)
{
	if (!obs || !name)
		return;

	char *item = bstrdup(name);
	da_push_back(obs->disabled_modules, &item);
}
""",
        """void obs_add_disabled_module(const char *name)
{
	if (!obs || !name)
		return;

	char *item = bstrdup(name);
	da_push_back(obs->disabled_modules, &item);
}

void obs_add_disabled_feature(const char *id)
{
	if (!obs || !id)
		return;

	for (size_t i = 0; i < obs->disabled_features.num; i++) {
		if (strcmp(obs->disabled_features.array[i], id) == 0)
			return;
	}

	char *item = bstrdup(id);
	da_push_back(obs->disabled_features, &item);
}

bool obs_feature_disabled(const char *id)
{
	if (!obs || !id || obs->disabled_features.num == 0)
		return false;

	for (size_t i = 0; i < obs->disabled_features.num; i++) {
		if (strcmp(obs->disabled_features.array[i], id) == 0)
			return true;
	}

	return false;
}
""",
    )

    # Core modules honour disabled_modules too. Stock OBS only skips
    # NON-core modules here, which is why the stock Plugin Manager can
    # never turn off an encoder/source that ships with OBS (obs-x264,
    # obs-nvenc, obs-browser, ... are all core modules). The toggle
    # page feeds this same list, so OFF really means "not loaded".
    replace_text(
        "libobs/obs-module.c",
        """	if (info->type != OBS_MODULE_TYPE_CORE && is_disabled_module(info->name)) {
		obs_create_disabled_module(&disabled_module, info->bin_path, info->data_path, OBS_MODULE_DISABLED);
		blog(LOG_WARNING, "Skipping module '%s', is disabled", info->name);
		return;
	}
""",
        """	/* OBS Toggle: the disabled list applies to core modules too
	 * (stock OBS only honoured it for third-party plugins). */
	if (is_disabled_module(info->name)) {
		obs_create_disabled_module(&disabled_module, info->bin_path, info->data_path, OBS_MODULE_DISABLED);
		blog(LOG_WARNING, "Skipping module '%s', is disabled", info->name);
		return;
	}
""",
    )

    # Plugin Manager may offer core modules for disable too.
    replace_text(
        "libobs/obs-module.c",
        """bool obs_get_module_allow_disable(const char *name)
{
	return !is_core_module(name);
}
""",
        """bool obs_get_module_allow_disable(const char *name)
{
	/* OBS Toggle: core modules are toggleable from Settings >
	 * Feature Toggles, so the Plugin Manager may offer them too. */
	UNUSED_PARAMETER(name);
	return true;
}
""",
    )

    # Register gates: one check at the top of each obs_register_*_s().
    replace_text(
        "libobs/obs-module.c",
        """void obs_register_source_s(const struct obs_source_info *info, size_t size)
{
	struct obs_source_info data = {0};""",
        """void obs_register_source_s(const struct obs_source_info *info, size_t size)
{
	/* OBS Toggle: a toggled-off source/filter/transition id never registers. */
	if (obs_feature_disabled(info->id)) {
		blog(LOG_INFO, "Skipping source '%s', disabled by Feature Toggles", info->id);
		return;
	}

	struct obs_source_info data = {0};""",
    )
    replace_text(
        "libobs/obs-module.c",
        """void obs_register_output_s(const struct obs_output_info *info, size_t size)
{
	if (find_output(info->id)) {""",
        """void obs_register_output_s(const struct obs_output_info *info, size_t size)
{
	/* OBS Toggle: a toggled-off output id never registers. */
	if (obs_feature_disabled(info->id)) {
		blog(LOG_INFO, "Skipping output '%s', disabled by Feature Toggles", info->id);
		return;
	}

	if (find_output(info->id)) {""",
    )
    replace_text(
        "libobs/obs-module.c",
        """void obs_register_encoder_s(const struct obs_encoder_info *info, size_t size)
{
	if (find_encoder(info->id)) {""",
        """void obs_register_encoder_s(const struct obs_encoder_info *info, size_t size)
{
	/* OBS Toggle: a toggled-off encoder id never registers. */
	if (obs_feature_disabled(info->id)) {
		blog(LOG_INFO, "Skipping encoder '%s', disabled by Feature Toggles", info->id);
		return;
	}

	if (find_encoder(info->id)) {""",
    )
    replace_text(
        "libobs/obs-module.c",
        """void obs_register_service_s(const struct obs_service_info *info, size_t size)
{
	if (find_service(info->id)) {""",
        """void obs_register_service_s(const struct obs_service_info *info, size_t size)
{
	/* OBS Toggle: a toggled-off service id never registers. */
	if (obs_feature_disabled(info->id)) {
		blog(LOG_INFO, "Skipping service '%s', disabled by Feature Toggles", info->id);
		return;
	}

	if (find_service(info->id)) {""",
    )
    print("patched libobs (disabled modules + features, register gates)")


def patch_hidden_sleep():
    # --- obs-source.c: the sleep gate + setter ---
    replace_text(
        "libobs/obs-source.c",
        """void obs_source_video_tick(obs_source_t *source, float seconds)
{
	bool now_showing, now_active;

	if (!obs_source_valid(source, "obs_source_video_tick"))
		return;
""",
        """/* OBS Toggle: Eco / hidden-source sleep, set from the frontend. */
static bool hidden_sources_sleep = false;

void obs_set_hidden_sources_sleep(bool enabled)
{
	hidden_sources_sleep = enabled;
}

void obs_source_video_tick(obs_source_t *source, float seconds)
{
	bool now_showing, now_active;

	if (!obs_source_valid(source, "obs_source_video_tick"))
		return;

	/* OBS Toggle: hidden-source sleep. A source that is not showing
	 * anywhere (show_refs == 0) and is not producing audio stops
	 * ticking, so hidden media / browser / VLC sources stop decoding
	 * instead of burning CPU on frames nobody sees. The tick still
	 * runs while source->showing is true so the pending hide callback
	 * fires exactly once, and audio-active sources keep ticking so
	 * hidden audio keeps playing. Showing the source again resumes
	 * ticking immediately; the source may skip ahead to live. */
	if (hidden_sources_sleep && !source->show_refs && !source->showing &&
	    !os_atomic_load_bool(&source->audio_active))
		return;
""",
    )
    print("patched libobs hidden-source sleep gate")


# ----------------------------------------------------------------------
# frontend — shared toggle table + early-load hook
# ----------------------------------------------------------------------

def patch_plugin_manager():
    src = SCRIPT_DIR / "FeatureToggles.hpp"
    if not src.is_file():
        fail("FeatureToggles.hpp missing next to patch script")
    dst = ROOT / "frontend/FeatureToggles.hpp"
    shutil.copyfile(src, dst)
    must_exist("frontend/FeatureToggles.hpp")

    replace_text(
        "frontend/plugin-manager/PluginManager.cpp",
        '#include <OBSApp.hpp>\n',
        '#include <OBSApp.hpp>\n#include <FeatureToggles.hpp>\n',
    )
    # preLoad() runs before obs_load_core_modules(), and the user config
    # is already open by then (OBSApp::loadAppModules). This is the one
    # place where OFF toggles can still keep a module / feature from
    # ever loading — anything later would be too late.
    replace_text(
        "frontend/plugin-manager/PluginManager.cpp",
        """void PluginManager::preLoad()
{
	loadModuleConfiguration_();
	disableModules_();
}
""",
        """void PluginManager::preLoad()
{
	loadModuleConfiguration_();
	disableModules_();
	/* OBS Toggle: apply Settings > Feature Toggles before any module
	 * loads. OFF modules never load, OFF feature ids never register.
	 * Defaults are all ON, so a fresh profile changes nothing. */
	obs_apply_feature_toggles(App()->GetUserConfig());
}
""",
    )
    print("patched PluginManager preLoad (toggles applied before module load)")


# ----------------------------------------------------------------------
# frontend — Settings > Feature Toggles page
# ----------------------------------------------------------------------

TOGGLES_PAGE_CPP = r'''
/* OBS Toggle: Settings > Feature Toggles page. Built in code (no .ui
 * edit): one checkbox per entry in obs_feature_toggles, grouped by
 * group, plus the GPU switch, the Eco master switch and the CPU-saver
 * toggles. Module / feature toggles need a restart to take effect;
 * Apply does an automatic clean restart (no Safe Mode prompt, because
 * a clean shutdown clears the crash sentinel). The Eco savers that
 * can apply live do so as soon as the dialog closes.
 */
bool toggle_restart = false;

void OBSBasicSettings::BuildTogglesPage()
{
	QWidget *page = new QWidget();
	QVBoxLayout *pageLayout = new QVBoxLayout(page);
	pageLayout->setContentsMargins(0, 0, 0, 0);

	QScrollArea *scroll = new QScrollArea(page);
	scroll->setWidgetResizable(true);
	scroll->setFrameShape(QFrame::NoFrame);
	QWidget *inner = new QWidget(scroll);
	QVBoxLayout *layout = new QVBoxLayout(inner);

	/* --- GPU switch --- */
	QGroupBox *gpuBox = new QGroupBox("Run OBS for:", inner);
	QVBoxLayout *gpuLayout = new QVBoxLayout(gpuBox);
	QLabel *gpuNote = new QLabel(
		"Picking a vendor turns OFF the other vendors' hardware encoders. "
		"Auto detects the GPU on this PC. Takes effect after the restart.",
		gpuBox);
	gpuNote->setWordWrap(true);
	gpuLayout->addWidget(gpuNote);
	QComboBox *gpuCombo = new QComboBox(gpuBox);
	gpuCombo->setObjectName("togglesGpuVendor");
	gpuCombo->addItem("Auto", "Auto");
	gpuCombo->addItem("AMD", "AMD");
	gpuCombo->addItem("Intel", "Intel");
	gpuCombo->addItem("Nvidia", "Nvidia");
	gpuLayout->addWidget(gpuCombo);
	layout->addWidget(gpuBox);

	/* --- Eco / Mobile Mode master + CPU savers --- */
	QGroupBox *ecoBox = new QGroupBox("Eco / Mobile Mode (CPU savers)", inner);
	QVBoxLayout *ecoLayout = new QVBoxLayout(ecoBox);
	QCheckBox *ecoCheck = new QCheckBox("Eco / Mobile Mode: turn on all CPU savers at once", ecoBox);
	ecoCheck->setObjectName("togglesEcoMode");
	ecoLayout->addWidget(ecoCheck);
	QCheckBox *prevOffCheck =
		new QCheckBox("Preview off while live (preview comes back when the stream / recording stops)", ecoBox);
	prevOffCheck->setObjectName("togglesPreviewOffWhileLive");
	ecoLayout->addWidget(prevOffCheck);
	QCheckBox *prev15Check = new QCheckBox("Preview at 15 fps while live (instead of full rate)", ecoBox);
	prev15Check->setObjectName("togglesPreview15Fps");
	ecoLayout->addWidget(prev15Check);
	QCheckBox *hiddenCheck =
		new QCheckBox("Hidden sources sleep (sources not visible anywhere stop decoding)", ecoBox);
	hiddenCheck->setObjectName("togglesHiddenSourcesSleep");
	ecoLayout->addWidget(hiddenCheck);
	QCheckBox *browserCheck =
		new QCheckBox("Browser sources pause when hidden and are capped at 720p", ecoBox);
	browserCheck->setObjectName("togglesBrowserPauseHidden");
	ecoLayout->addWidget(browserCheck);
	QHBoxLayout *cpuRow = new QHBoxLayout();
	QCheckBox *cpuCheck = new QCheckBox("Auto CPU guard: if CPU goes over", ecoBox);
	cpuCheck->setObjectName("togglesCpuGuard");
	cpuRow->addWidget(cpuCheck);
	QSpinBox *cpuSpin = new QSpinBox(ecoBox);
	cpuSpin->setObjectName("togglesCpuGuardThreshold");
	cpuSpin->setRange(50, 95);
	cpuSpin->setSingleStep(5);
	cpuSpin->setSuffix("%");
	cpuRow->addWidget(cpuSpin);
	QLabel *cpuNote = new QLabel("auto-drop output to 720p30 until CPU drops "
				      "(the stream briefly restarts when it drops / restores).",
				      ecoBox);
	cpuNote->setWordWrap(true);
	cpuRow->addWidget(cpuNote, 1);
	ecoLayout->addLayout(cpuRow);
	QLabel *ecoNote = new QLabel(
		"Eco savers apply live when the dialog closes, except the preview "
		"and CPU-guard changes, which take effect on the next stream / recording.",
		ecoBox);
	ecoNote->setWordWrap(true);
	ecoLayout->addWidget(ecoNote);
	layout->addWidget(ecoBox);
	connect(ecoCheck, &QCheckBox::toggled, this, [=](bool on) {
		if (loading || !on)
			return;
		prevOffCheck->setChecked(true);
		prev15Check->setChecked(true);
		hiddenCheck->setChecked(true);
		browserCheck->setChecked(true);
		cpuCheck->setChecked(true);
	});
	/* Any user change on this page marks it changed (loading is true
	 * while LoadToggleSettings() fills the widgets in, so a load
	 * never marks the page changed). */
	auto markChanged = [this]() {
		if (!loading) {
			togglesChanged = true;
			EnableApplyButton(true);
		}
	};
	connect(ecoCheck, &QCheckBox::toggled, this, markChanged);
	connect(prevOffCheck, &QCheckBox::toggled, this, markChanged);
	connect(prev15Check, &QCheckBox::toggled, this, markChanged);
	connect(hiddenCheck, &QCheckBox::toggled, this, markChanged);
	connect(browserCheck, &QCheckBox::toggled, this, markChanged);
	connect(cpuCheck, &QCheckBox::toggled, this, markChanged);
	connect(gpuCombo, qOverload<int>(&QComboBox::currentIndexChanged), this, markChanged);
	connect(cpuSpin, qOverload<int>(&QSpinBox::valueChanged), this, markChanged);

	/* --- One checkbox per toggleable thing, grouped --- */
	const char *groups[] = {"Encoders", "Sources", "Filters", "Transitions", "Outputs", "Plugins"};
	for (const char *group : groups) {
		QGroupBox *box = new QGroupBox(group, inner);
		QVBoxLayout *boxLayout = new QVBoxLayout(box);
		for (size_t i = 0; i < obs_feature_toggles_count; i++) {
			const OBSFeatureToggle *t = &obs_feature_toggles[i];
			if (strcmp(t->group, group) != 0)
				continue;
			QCheckBox *check = new QCheckBox(t->label, box);
			check->setProperty("toggleKey", QString(t->id));
			check->setChecked(true);
			connect(check, &QCheckBox::toggled, this, [this]() {
				if (!loading) {
					togglesChanged = true;
					EnableApplyButton(true);
				}
			});
			boxLayout->addWidget(check);
		}
		layout->addWidget(box);
	}
	QLabel *restartNote = new QLabel(
		"Turning anything above on or off needs a restart. Pressing Apply "
		"restarts OBS automatically in normal mode — no Safe Mode prompt.",
		inner);
	restartNote->setWordWrap(true);
	layout->addWidget(restartNote);
	layout->addStretch(1);

	scroll->setWidget(inner);
	pageLayout->addWidget(scroll);

	togglesPage = page;
	ui->listWidget->addItem("Feature Toggles");
	ui->stackedWidget->addWidget(page);
}

static QCheckBox *FindToggleCheck(QWidget *page, const char *objectName)
{
	if (!page)
		return nullptr;
	return page->findChild<QCheckBox *>(objectName);
}

static void LoadToggleCheck(QWidget *page, const char *objectName, config_t *config, const char *key,
			    bool defaultOn = true)
{
	QCheckBox *check = FindToggleCheck(page, objectName);
	if (!check)
		return;
	bool on = defaultOn;
	if (config_has_user_value(config, "FeatureToggles", key))
		on = config_get_bool(config, "FeatureToggles", key);
	check->setChecked(on);
}

void OBSBasicSettings::LoadToggleSettings()
{
	if (!togglesPage)
		return;
	loading = true;
	config_t *config = App()->GetUserConfig();

	QComboBox *gpuCombo = togglesPage->findChild<QComboBox *>("togglesGpuVendor");
	if (gpuCombo) {
		const char *vendor = config_get_string(config, "FeatureToggles", "GPUVendor");
		int idx = gpuCombo->findData(vendor ? vendor : "Auto");
		gpuCombo->setCurrentIndex(idx < 0 ? 0 : idx);
	}
	LoadToggleCheck(togglesPage, "togglesEcoMode", config, "EcoMode", false);
	LoadToggleCheck(togglesPage, "togglesPreviewOffWhileLive", config, "PreviewOffWhileLive", false);
	LoadToggleCheck(togglesPage, "togglesPreview15Fps", config, "Preview15Fps", false);
	LoadToggleCheck(togglesPage, "togglesHiddenSourcesSleep", config, "HiddenSourcesSleep", false);
	LoadToggleCheck(togglesPage, "togglesBrowserPauseHidden", config, "BrowserPauseHidden", false);
	LoadToggleCheck(togglesPage, "togglesCpuGuard", config, "CpuGuard", false);
	QSpinBox *cpuSpin = togglesPage->findChild<QSpinBox *>("togglesCpuGuardThreshold");
	if (cpuSpin) {
		uint64_t threshold = config_get_uint(config, "FeatureToggles", "CpuGuardThreshold");
		cpuSpin->setValue(threshold == 0 ? 80 : (int)threshold);
	}

	for (QCheckBox *check : togglesPage->findChildren<QCheckBox *>()) {
		QVariant key = check->property("toggleKey");
		if (!key.isValid())
			continue;
		check->setChecked(obs_toggle_is_on(config, key.toString().toUtf8().constData()));
	}
	loading = false;
}

void OBSBasicSettings::SaveToggleSettings()
{
	if (!togglesPage)
		return;
	config_t *config = App()->GetUserConfig();
	bool needsRestart = false;

	auto saveCheck = [&](const char *objectName, const char *key) {
		QCheckBox *check = FindToggleCheck(togglesPage, objectName);
		if (!check)
			return;
		config_set_bool(config, "FeatureToggles", key, check->isChecked());
	};

	saveCheck("togglesEcoMode", "EcoMode");
	saveCheck("togglesPreviewOffWhileLive", "PreviewOffWhileLive");
	saveCheck("togglesPreview15Fps", "Preview15Fps");
	saveCheck("togglesHiddenSourcesSleep", "HiddenSourcesSleep");
	saveCheck("togglesBrowserPauseHidden", "BrowserPauseHidden");
	saveCheck("togglesCpuGuard", "CpuGuard");
	QSpinBox *cpuSpin = togglesPage->findChild<QSpinBox *>("togglesCpuGuardThreshold");
	if (cpuSpin)
		config_set_uint(config, "FeatureToggles", "CpuGuardThreshold", (uint64_t)cpuSpin->value());

	QComboBox *gpuCombo = togglesPage->findChild<QComboBox *>("togglesGpuVendor");
	if (gpuCombo) {
		/* Keep the vendor string owned: toUtf8() returns a temporary
		 * QByteArray, so holding its constData() across statements
		 * would dangle. */
		std::string vendorStr = gpuCombo->currentData().toString().toStdString();
		const char *vendor = vendorStr.c_str();
		const char *savedVendor = config_get_string(config, "FeatureToggles", "GPUVendor");
		if (!savedVendor)
			savedVendor = "Auto";
		if (strcmp(vendor, savedVendor) != 0) {
			/* Resolves Auto against the hardware that is actually
			 * present, then writes the concrete encoder toggles. */
			obs_apply_gpu_vendor(config, vendor);
			needsRestart = true;
		}
	}

	for (QCheckBox *check : togglesPage->findChildren<QCheckBox *>()) {
		QVariant key = check->property("toggleKey");
		if (!key.isValid())
			continue;
		std::string id = key.toString().toStdString();
		bool wasOn = obs_toggle_is_on(config, id.c_str());
		config_set_bool(config, "FeatureToggles", id.c_str(), check->isChecked());
		if (wasOn != check->isChecked())
			needsRestart = true;
	}

	/* Eco master writes the savers on as well, so a single Eco tick is
	 * enough and the saved state stays consistent. */
	if (FindToggleCheck(togglesPage, "togglesEcoMode") &&
	    FindToggleCheck(togglesPage, "togglesEcoMode")->isChecked()) {
		config_set_bool(config, "FeatureToggles", "PreviewOffWhileLive", true);
		config_set_bool(config, "FeatureToggles", "Preview15Fps", true);
		config_set_bool(config, "FeatureToggles", "HiddenSourcesSleep", true);
		config_set_bool(config, "FeatureToggles", "BrowserPauseHidden", true);
		config_set_bool(config, "FeatureToggles", "CpuGuard", true);
	}

	if (needsRestart) {
		restart = true;
		toggle_restart = true;
	}
}
'''


def patch_settings():
    replace_text(
        "frontend/settings/OBSBasicSettings.cpp",
        '#include <widgets/OBSBasic.hpp>\n',
        '#include <widgets/OBSBasic.hpp>\n#include <FeatureToggles.hpp>\n#include <QScrollArea>\n#include <QVBoxLayout>\n#include <QHBoxLayout>\n',
    )
    # Global for the automatic restart, read by OBSBasic_MainControls.cpp.
    replace_text(
        "frontend/settings/OBSBasicSettings.cpp",
        'extern bool restart;\n',
        'extern bool restart;\nextern bool toggle_restart;\n',
        count=1,
    )
    # Build the page once, before first load; reload values with the rest.
    replace_text(
        "frontend/settings/OBSBasicSettings.cpp",
        "\tLoadSettings(false);\n",
        "\tBuildTogglesPage();\n\tLoadSettings(false);\n",
    )
    replace_text(
        "frontend/settings/OBSBasicSettings.cpp",
        """	if (!changedOnly || advancedChanged) {
		LoadAdvancedSettings();
	}
}
""",
        """	if (!changedOnly || advancedChanged) {
		LoadAdvancedSettings();
	}
	if (!changedOnly || togglesChanged) {
		LoadToggleSettings();
	}
}
""",
    )
    # Save + restart flag hookup in SaveSettings().
    replace_text(
        "frontend/settings/OBSBasicSettings.cpp",
        """	if (advancedChanged) {
		SaveAdvancedSettings();
	}
""",
        """	if (advancedChanged) {
		SaveAdvancedSettings();
	}
	if (togglesChanged) {
		SaveToggleSettings();
	}
""",
    )
    replace_text(
        "frontend/settings/OBSBasicSettings.cpp",
        """		if (advancedChanged) {
			AddChangedVal(changed, "advanced");
		}
""",
        """		if (advancedChanged) {
			AddChangedVal(changed, "advanced");
		}
		if (togglesChanged) {
			AddChangedVal(changed, "feature toggles");
		}
""",
    )
    # Append the page implementation at the end of the file.
    text = read("frontend/settings/OBSBasicSettings.cpp")
    if "OBSBasicSettings::BuildTogglesPage" in text:
        fail("frontend/settings/OBSBasicSettings.cpp already has the toggles page")
    write("frontend/settings/OBSBasicSettings.cpp", text + TOGGLES_PAGE_CPP)
    print("patched Settings (Feature Toggles page)")

    # --- OBSBasicSettings.hpp: members + decls + Changed() ---
    replace_text(
        "frontend/settings/OBSBasicSettings.hpp",
        "\tbool advancedChanged = false;\n",
        "\tbool advancedChanged = false;\n\tbool togglesChanged = false;\n\tQWidget *togglesPage = nullptr;\n",
    )
    replace_text(
        "frontend/settings/OBSBasicSettings.hpp",
        """		return generalChanged || appearanceChanged || outputsChanged || stream1Changed || audioChanged ||
		       videoChanged || advancedChanged || hotkeysChanged || a11yChanged;""",
        """		return generalChanged || appearanceChanged || outputsChanged || stream1Changed || audioChanged ||
		       videoChanged || advancedChanged || hotkeysChanged || a11yChanged || togglesChanged;""",
    )
    replace_text(
        "frontend/settings/OBSBasicSettings.hpp",
        """		advancedChanged = false;
		appearanceChanged = false;
		EnableApplyButton(false);""",
        """		advancedChanged = false;
		appearanceChanged = false;
		togglesChanged = false;
		EnableApplyButton(false);""",
    )
    # Declarations: hook onto the Save/Load declarations. Anchor on an
    # existing Load/Save pair near the toggles area.
    hpp = read("frontend/settings/OBSBasicSettings.hpp")
    anchor = "\tvoid LoadAdvancedSettings();"
    if anchor not in hpp:
        fail("OBSBasicSettings.hpp: LoadAdvancedSettings decl not found")
    if "LoadToggleSettings" in hpp:
        fail("OBSBasicSettings.hpp already has toggle decls")
    write(
        "frontend/settings/OBSBasicSettings.hpp",
        hpp.replace(
            anchor,
            anchor + "\n\tvoid BuildTogglesPage();\n\tvoid LoadToggleSettings();\n\tvoid SaveToggleSettings();",
            1,
        ),
    )
    print("patched OBSBasicSettings.hpp")


def patch_auto_restart():
    # After the settings dialog closes, a toggles change restarts OBS
    # automatically (clean close -> crash sentinel cleared -> no Safe
    # Mode prompt on relaunch). Other restart reasons keep the existing
    # "restart?" question.
    replace_text(
        "frontend/widgets/OBSBasic_MainControls.cpp",
        'extern bool restart;\n',
        'extern bool restart;\nextern bool toggle_restart;\n',
        count=1,
    )
    replace_text(
        "frontend/widgets/OBSBasic_MainControls.cpp",
        """	if (restart) {
		QMessageBox::StandardButton button =
			OBSMessageBox::question(this, QTStr("Restart"), QTStr("NeedsRestart"));
""",
        """	if (toggle_restart) {
		/* OBS Toggle: Apply already saved everything; restart now,
		 * cleanly, in normal mode. No question, no Safe Mode prompt:
		 * close() is the normal quit path, which clears the crash
		 * sentinel before obs-main relaunches the same command line.
		 * (If the close is refused — e.g. a stream is live and the
		 * user cancels the close prompt — closeEvent clears
		 * toggle_restart, mirroring stock restart handling, and the
		 * saved toggles apply at the next manual restart.) */
		close();
		return;
	}

	if (restart) {
		QMessageBox::StandardButton button =
			OBSMessageBox::question(this, QTStr("Restart"), QTStr("NeedsRestart"));
""",
    )
    print("patched automatic clean restart after toggles Apply")


# ----------------------------------------------------------------------
# frontend — OBSBasic Eco / CPU guard / preview savers / browser eco
# ----------------------------------------------------------------------

ECO_CPP = r'''
/* OBS Toggle: Eco / Mobile Mode runtime hooks. */

static bool ToggleEcoSaverOn(const char *key, bool ecoOn)
{
	if (ecoOn)
		return true;
	config_t *config = App()->GetUserConfig();
	if (!config_has_user_value(config, "FeatureToggles", key))
		return false;
	return config_get_bool(config, "FeatureToggles", key);
}

void OBSBasic::ApplyEcoSettings()
{
	config_t *config = App()->GetUserConfig();
	bool eco = config_has_user_value(config, "FeatureToggles", "EcoMode") &&
		   config_get_bool(config, "FeatureToggles", "EcoMode");

	preview15Fps = ToggleEcoSaverOn("Preview15Fps", eco);
	obs_set_hidden_sources_sleep(ToggleEcoSaverOn("HiddenSourcesSleep", eco));
	ApplyBrowserEco();
	if (ToggleEcoSaverOn("CpuGuard", eco))
		StartCpuGuard();
	else
		StopCpuGuard();
}

static bool ApplyBrowserEcoEnum(void *param, obs_source_t *source)
{
	OBSBasic *window = static_cast<OBSBasic *>(param);
	window->ApplyBrowserEcoToSource(source);
	return true;
}

void OBSBasic::ApplyBrowserEco()
{
	obs_enum_sources(ApplyBrowserEcoEnum, this);
}

void OBSBasic::ApplyBrowserEcoToSource(OBSSource source)
{
	if (!source)
		return;
	const char *id = obs_source_get_id(source);
	if (!id || strcmp(id, "browser_source") != 0)
		return;

	config_t *config = App()->GetUserConfig();
	bool eco = config_has_user_value(config, "FeatureToggles", "EcoMode") &&
		   config_get_bool(config, "FeatureToggles", "EcoMode");
	if (!ToggleEcoSaverOn("BrowserPauseHidden", eco))
		return;

	OBSDataAutoRelease settings = obs_source_get_settings(source);
	if (!settings)
		return;
	bool changed = false;
	if (!obs_data_get_bool(settings, "shutdown")) {
		obs_data_set_bool(settings, "shutdown", true);
		changed = true;
	}
	/* Cap at 720p: only shrink, never enlarge a smaller source. */
	if (obs_data_get_int(settings, "width") > 1280) {
		obs_data_set_int(settings, "width", 1280);
		changed = true;
	}
	if (obs_data_get_int(settings, "height") > 720) {
		obs_data_set_int(settings, "height", 720);
		changed = true;
	}
	if (changed) {
		obs_source_update(source, settings);
		blog(LOG_INFO,
		     "[Feature Toggles] Browser source '%s' set to pause when hidden, capped at 720p",
		     obs_source_get_name(source));
	}
}

void OBSBasic::StartCpuGuard()
{
	if (!cpuGuardTimer) {
		cpuGuardTimer = new QTimer(this);
		connect(cpuGuardTimer.data(), &QTimer::timeout, this, &OBSBasic::CpuGuardTick);
	}
	if (!cpuGuardTimer->isActive())
		cpuGuardTimer->start(2000);
}

void OBSBasic::StopCpuGuard()
{
	if (cpuGuardTimer)
		cpuGuardTimer->stop();
	cpuGuardActive = false;
	cpuGuardHighCount = 0;
	cpuGuardLowCount = 0;
}

void OBSBasic::CpuGuardTick()
{
	if (!outputHandler)
		return;
	bool live = outputHandler->StreamingActive() || outputHandler->RecordingActive();
	if (!live) {
		/* Not live: nothing to protect. If a drop is active and the
		 * stream ended, restore now — ResetVideo is free while idle. */
		cpuGuardHighCount = 0;
		if (cpuGuardActive)
			CpuGuardRestore();
		return;
	}

	config_t *config = App()->GetUserConfig();
	uint64_t threshold = config_get_uint(config, "FeatureToggles", "CpuGuardThreshold");
	if (threshold == 0)
		threshold = 80;
	double cpu = GetCPUUsage();

	if (!cpuGuardActive) {
		if (cpu > (double)threshold) {
			if (++cpuGuardHighCount >= 3)
				CpuGuardDrop();
		} else {
			cpuGuardHighCount = 0;
		}
		return;
	}

	/* Dropped already: restore after 60s under 60% CPU. */
	if (cpu < 60.0) {
		if (++cpuGuardLowCount >= 30)
			CpuGuardRestore();
	} else {
		cpuGuardLowCount = 0;
	}
}

void OBSBasic::CpuGuardApplyVideo(uint32_t cx, uint32_t cy, uint32_t fpsType, const char *fpsCommon,
				  uint64_t fpsInt, uint64_t fpsNum, uint64_t fpsDen)
{
	/* ResetVideo refuses while outputs are active, so stop them, reset
	 * the video pipeline, and start them again. The stream/recording
	 * briefly drops — that is the honest cost of changing the output
	 * size mid-stream, and it is logged. */
	bool wasStreaming = outputHandler && outputHandler->StreamingActive();
	bool wasRecording = outputHandler && outputHandler->RecordingActive();
	if (wasStreaming)
		StopStreaming();
	if (wasRecording)
		StopRecording();

	config_set_uint(activeConfiguration, "Video", "OutputCX", cx);
	config_set_uint(activeConfiguration, "Video", "OutputCY", cy);
	config_set_uint(activeConfiguration, "Video", "FPSType", fpsType);
	config_set_string(activeConfiguration, "Video", "FPSCommon", fpsCommon);
	config_set_uint(activeConfiguration, "Video", "FPSInt", fpsInt);
	config_set_uint(activeConfiguration, "Video", "FPSNum", fpsNum);
	config_set_uint(activeConfiguration, "Video", "FPSDen", fpsDen);
	int ret = ResetVideo();
	if (ret != 0)
		blog(LOG_WARNING, "[Feature Toggles] CPU guard: ResetVideo returned %d", ret);

	if (wasStreaming)
		StartStreaming();
	if (wasRecording)
		StartRecording();
}

void OBSBasic::CpuGuardDrop()
{
	uint64_t now = os_gettime_ns();
	if (cpuGuardLastDropNs != 0 && now - cpuGuardLastDropNs < 300000000000ULL)
		return; /* cooldown: at most one drop per 5 minutes */
	cpuGuardLastDropNs = now;

	cpuGuardSavedCX = (uint32_t)config_get_uint(activeConfiguration, "Video", "OutputCX");
	cpuGuardSavedCY = (uint32_t)config_get_uint(activeConfiguration, "Video", "OutputCY");
	cpuGuardSavedFPSType = (uint32_t)config_get_uint(activeConfiguration, "Video", "FPSType");
	const char *fpsCommon = config_get_string(activeConfiguration, "Video", "FPSCommon");
	cpuGuardSavedFPSCommon = fpsCommon ? fpsCommon : "30";
	cpuGuardSavedFPSInt = config_get_uint(activeConfiguration, "Video", "FPSInt");
	cpuGuardSavedFPSNum = config_get_uint(activeConfiguration, "Video", "FPSNum");
	cpuGuardSavedFPSDen = config_get_uint(activeConfiguration, "Video", "FPSDen");

	blog(LOG_WARNING,
	     "[Feature Toggles] CPU guard: CPU over threshold, dropping output to 720p30 "
	     "(was %ux%u)",
	     cpuGuardSavedCX, cpuGuardSavedCY);
	CpuGuardApplyVideo(1280, 720, 0, "30", 30, 30, 1);
	cpuGuardActive = true;
	cpuGuardHighCount = 0;
	cpuGuardLowCount = 0;
}

void OBSBasic::CpuGuardRestore()
{
	if (!cpuGuardActive)
		return;
	blog(LOG_INFO, "[Feature Toggles] CPU guard: CPU recovered, restoring output to %ux%u",
	     cpuGuardSavedCX, cpuGuardSavedCY);
	CpuGuardApplyVideo(cpuGuardSavedCX, cpuGuardSavedCY, cpuGuardSavedFPSType,
			   cpuGuardSavedFPSCommon.c_str(), cpuGuardSavedFPSInt, cpuGuardSavedFPSNum,
			   cpuGuardSavedFPSDen);
	cpuGuardActive = false;
	cpuGuardHighCount = 0;
	cpuGuardLowCount = 0;
}

/* Preview off while live: hide the preview when a stream/recording
 * starts, bring it back when nothing is live any more. Studio Mode
 * keeps its program/preview (DisablePreview is a no-op there). */
void OBSBasic::PreviewOffWhileLiveStart()
{
	if (IsPreviewProgramMode())
		return;
	config_t *config = App()->GetUserConfig();
	bool eco = config_has_user_value(config, "FeatureToggles", "EcoMode") &&
		   config_get_bool(config, "FeatureToggles", "EcoMode");
	if (!ToggleEcoSaverOn("PreviewOffWhileLive", eco))
		return;
	if (previewOffWhileLiveActive)
		return;
	previewWasEnabled = previewEnabled;
	previewOffWhileLiveActive = true;
	EnablePreviewDisplay(false);
	blog(LOG_INFO, "[Feature Toggles] Preview off while live");
}

void OBSBasic::PreviewOffWhileLiveStop()
{
	if (!previewOffWhileLiveActive)
		return;
	if (outputHandler && outputHandler->Active())
		return;
	previewOffWhileLiveActive = false;
	EnablePreviewDisplay(previewWasEnabled);
	blog(LOG_INFO, "[Feature Toggles] Preview restored");
}
'''


def patch_obsbasic():
    # --- OBSBasic.hpp: members + method decls ---
    replace_text(
        "frontend/widgets/OBSBasic.hpp",
        """	QPointer<QTimer> cpuUsageTimer;
	os_cpu_usage_info_t *cpuUsageInfo = nullptr;
""",
        """	QPointer<QTimer> cpuUsageTimer;
	os_cpu_usage_info_t *cpuUsageInfo = nullptr;

	/* OBS Toggle: Eco / CPU guard state */
	QPointer<QTimer> cpuGuardTimer;
	bool cpuGuardActive = false;
	int cpuGuardHighCount = 0;
	int cpuGuardLowCount = 0;
	uint64_t cpuGuardLastDropNs = 0;
	uint32_t cpuGuardSavedCX = 0;
	uint32_t cpuGuardSavedCY = 0;
	uint32_t cpuGuardSavedFPSType = 0;
	std::string cpuGuardSavedFPSCommon;
	uint64_t cpuGuardSavedFPSInt = 0;
	uint64_t cpuGuardSavedFPSNum = 0;
	uint64_t cpuGuardSavedFPSDen = 0;
	bool previewOffWhileLiveActive = false;
	bool previewWasEnabled = true;
	bool preview15Fps = false;
	uint64_t lastPreviewRenderNs = 0;
""",
    )
    replace_text(
        "frontend/widgets/OBSBasic.hpp",
        """	inline double GetCPUUsage() const { return os_cpu_usage_info_query(cpuUsageInfo); }
""",
        """	inline double GetCPUUsage() const { return os_cpu_usage_info_query(cpuUsageInfo); }
	void ApplyEcoSettings();
	void ApplyBrowserEco();
	void ApplyBrowserEcoToSource(OBSSource source);
	void StartCpuGuard();
	void StopCpuGuard();
	void CpuGuardTick();
	void CpuGuardApplyVideo(uint32_t cx, uint32_t cy, uint32_t fpsType, const char *fpsCommon,
				uint64_t fpsInt, uint64_t fpsNum, uint64_t fpsDen);
	void CpuGuardDrop();
	void CpuGuardRestore();
	void PreviewOffWhileLiveStart();
	void PreviewOffWhileLiveStop();
""",
    )
    # --- OBSBasic.cpp: run Eco setup once the main window exists ---
    replace_text(
        "frontend/widgets/OBSBasic.cpp",
        "extern bool restart;\n",
        "extern bool restart;\nextern bool toggle_restart;\n",
        count=1,
    )
    # If the restart-close is refused (stream live, user cancels the
    # close prompt), clear the pending toggle restart, mirroring the
    # stock restart handling in closeEvent.
    replace_text(
        "frontend/widgets/OBSBasic.cpp",
        "\t\tevent->ignore();\n\t\trestart = false;\n",
        "\t\tevent->ignore();\n\t\trestart = false;\n\t\ttoggle_restart = false;\n",
        count=2,
    )
    replace_text(
        "frontend/widgets/OBSBasic.cpp",
        """	cpuUsageTimer = new QTimer(this);
	connect(cpuUsageTimer.data(), &QTimer::timeout, ui->statusbar, &OBSBasicStatusBar::UpdateCPUUsage);
	cpuUsageTimer->start(3000);
""",
        """	cpuUsageTimer = new QTimer(this);
	connect(cpuUsageTimer.data(), &QTimer::timeout, ui->statusbar, &OBSBasicStatusBar::UpdateCPUUsage);
	cpuUsageTimer->start(3000);

	/* OBS Toggle: Eco savers that apply live (hidden-source sleep,
	 * browser eco, CPU guard timer). Module/feature toggles were
	 * already applied before module load, in PluginManager::preLoad. */
	ApplyEcoSettings();
""",
    )
    # Append the Eco implementation at the end of OBSBasic.cpp.
    text = read("frontend/widgets/OBSBasic.cpp")
    if "OBSBasic::ApplyEcoSettings" in text:
        fail("frontend/widgets/OBSBasic.cpp already has Eco hooks")
    write("frontend/widgets/OBSBasic.cpp", text + ECO_CPP)
    # Destructor: stop the guard timer's info cleanly (QTimer itself is
    # a child of OBSBasic and is deleted with it; stop it explicitly so
    # no tick fires during teardown).
    replace_text(
        "frontend/widgets/OBSBasic.cpp",
        """	delete cpuUsageTimer;
	os_cpu_usage_info_destroy(cpuUsageInfo);
""",
        """	delete cpuUsageTimer;
	os_cpu_usage_info_destroy(cpuUsageInfo);
	StopCpuGuard();
""",
    )
    print("patched OBSBasic (Eco, CPU guard, browser eco)")

    # --- Preview 15 fps: throttle RenderMain while live ---
    replace_text(
        "frontend/widgets/OBSBasic_Preview.cpp",
        """	OBSBasic *window = static_cast<OBSBasic *>(data);
	obs_video_info ovi;

	obs_get_video_info(&ovi);
""",
        """	OBSBasic *window = static_cast<OBSBasic *>(data);
	obs_video_info ovi;

	obs_get_video_info(&ovi);

	/* OBS Toggle: preview saver — 15 fps while live. Skipping a draw
	 * leaves the last presented frame on screen; the stream and the
	 * recording are unaffected (they render from the video pipeline,
	 * not from this display callback). */
	if (window->preview15Fps && window->outputHandler && window->outputHandler->Active()) {
		uint64_t now = os_gettime_ns();
		if (now - window->lastPreviewRenderNs < 66000000ULL) {
			GS_DEBUG_MARKER_END();
			return;
		}
		window->lastPreviewRenderNs = now;
	}
""",
    )
    print("patched preview 15 fps throttle")

    # --- Preview off while live: hooks on real start/stop ---
    replace_text(
        "frontend/widgets/OBSBasic_Streaming.cpp",
        """	blog(LOG_INFO, STREAMING_START);
}
""",
        """	blog(LOG_INFO, STREAMING_START);
	PreviewOffWhileLiveStart();
}
""",
    )
    # StreamingStop: restore at the end of the function is risky to
    # anchor, so hook the first lines instead — the stop has begun and
    # the preview restore is safe once Active() is false. We restore
    # via a queued call: StopStreaming returns before the output
    # actually stops, so check again on the next event loop turn.
    replace_text(
        "frontend/widgets/OBSBasic_Streaming.cpp",
        """void OBSBasic::StreamingStop(int code, QString last_error)
{
	const char *errorDescription = "";
""",
        """void OBSBasic::StreamingStop(int code, QString last_error)
{
	QMetaObject::invokeMethod(this, [this]() { PreviewOffWhileLiveStop(); }, Qt::QueuedConnection);
	const char *errorDescription = "";
""",
    )
    replace_text(
        "frontend/widgets/OBSBasic_Recording.cpp",
        """	blog(LOG_INFO, RECORDING_START);
}
""",
        """	blog(LOG_INFO, RECORDING_START);
	PreviewOffWhileLiveStart();
}
""",
    )
    replace_text(
        "frontend/widgets/OBSBasic_Recording.cpp",
        """void OBSBasic::RecordingStop(int code, QString last_error)
{
	ui->statusbar->RecordingStopped();
""",
        """void OBSBasic::RecordingStop(int code, QString last_error)
{
	QMetaObject::invokeMethod(this, [this]() { PreviewOffWhileLiveStop(); }, Qt::QueuedConnection);
	ui->statusbar->RecordingStopped();
""",
    )
    print("patched preview-off-while-live hooks")

    # --- Browser eco for newly created sources (queued, ref-held) ---
    replace_text(
        "frontend/widgets/OBSBasic_SceneItems.cpp",
        """void OBSBasic::SourceCreated(void *data, calldata_t *params)
{
	OBSSource source = (obs_source_t *)calldata_ptr(params, "source");

	if (obs_scene_from_source(source) != NULL) {
		QMetaObject::invokeMethod(static_cast<OBSBasic *>(data), &OBSBasic::AddScene, WaitConnection(), source);
	}
}
""",
        """void OBSBasic::SourceCreated(void *data, calldata_t *params)
{
	OBSSource source = (obs_source_t *)calldata_ptr(params, "source");

	if (obs_scene_from_source(source) != NULL) {
		QMetaObject::invokeMethod(static_cast<OBSBasic *>(data), &OBSBasic::AddScene, WaitConnection(), source);
	}

	/* OBS Toggle: a browser source created after launch (new source,
	 * scene collection load, undo, paste) gets the same pause-when-
	 * hidden + 720p cap. Queued so it runs after creation finishes;
	 * the OBSSource capture keeps the source alive until then. */
	OBSBasic *window = static_cast<OBSBasic *>(data);
	QMetaObject::invokeMethod(
		window,
		[window, source]() { window->ApplyBrowserEcoToSource(source); }, Qt::QueuedConnection);
}
""",
    )
    # --- After the settings dialog closes, re-apply the live Eco savers ---
    replace_text(
        "frontend/widgets/OBSBasic_MainControls.cpp",
        """	settings_already_executing = false;
""",
        """	settings_already_executing = false;

	/* OBS Toggle: Eco savers that apply live (hidden-source sleep,
	 * browser eco, CPU guard) take effect as soon as the dialog
	 * closes. Module/feature toggles need the restart below. */
	ApplyEcoSettings();
""",
    )
    print("patched browser-eco on source creation + settings close")


def patch_updater():
    # Same as PS5 Lite #23: update check only on startup, never while live.
    replace_text(
        "frontend/widgets/OBSBasic_Updater.cpp",
        '\tif (!config_get_bool(App()->GetAppConfig(), "General", "EnableAutoUpdates")) {\n\t\treturn;\n\t}',
        '\tif (!config_get_bool(App()->GetAppConfig(), "General", "EnableAutoUpdates")) {\n\t\treturn;\n\t}\n\n\t/* OBS Toggle: never check for updates while live - startup only. */\n\tif (outputHandler && (outputHandler->StreamingActive() || outputHandler->RecordingActive())) {\n\t\treturn;\n\t}',
    )
    print("patched updater (never while live)")


def patch_settings_crash_guards():
    # PS5 Lite Settings-crash fix, adapted: nothing is removed in the
    # Toggle fork, but any encoder CAN be toggled off, so
    # obs_get_encoder_codec() can still return NULL for an unregistered
    # id — the same NULL hazards apply. (1) + (2) are verbatim; the
    # SimpleOutput fallback (5) and the profile/stream fallbacks (6)
    # keep x264 as a candidate ONLY when it is actually available.
    replace_text(
        "frontend/settings/OBSBasicSettings.cpp",
        '\tstring vCodec = obs_get_encoder_codec(get_simple_output_encoder(QT_TO_UTF8(vEncoder)));',
        '\t/* OBS Toggle: the encoder id can be toggled off, so\n\t * obs_get_encoder_codec() can return NULL for an unregistered\n\t * id. std::string(NULL) crashes in ucrtbase - guard it (this was\n\t * the PS5 Lite Settings crash). */\n'
        '\tconst char *vCodecC = obs_get_encoder_codec(get_simple_output_encoder(QT_TO_UTF8(vEncoder)));\n'
        '\tstring vCodec = vCodecC ? vCodecC : "";',
    )
    replace_text(
        "frontend/settings/OBSBasicSettings.cpp",
        '\t\t\tconst char *encoder_id = get_simple_output_encoder(QT_TO_UTF8(encName));\n'
        '\t\t\tcodec = obs_get_encoder_codec(encoder_id);',
        '\t\t\tconst char *encoder_id = get_simple_output_encoder(QT_TO_UTF8(encName));\n'
        '\t\t\t/* OBS Toggle: obs_get_encoder_codec() returns NULL for an\n\t\t\t * unregistered encoder id (toggled off); assigning NULL to\n\t\t\t * a QString crashes - guard it. */\n'
        '\t\t\tconst char *codecC = obs_get_encoder_codec(encoder_id);\n'
        '\t\t\tcodec = codecC ? codecC : QString();',
    )
    replace_text(
        "frontend/utility/SimpleOutput.cpp",
        '\tif (strcmp(encoder, SIMPLE_ENCODER_X264) == 0) {\n'
        '\t\treturn "obs_x264";\n'
        '\t} else if (strcmp(encoder, SIMPLE_ENCODER_X264_LOWCPU) == 0) {\n'
        '\t\treturn "obs_x264";\n'
        '\t} else if (strcmp(encoder, SIMPLE_ENCODER_QSV) == 0) {',
        '\t/* OBS Toggle: x264 may be toggled off - only return obs_x264\n\t * when it is actually registered. */\n'
        '\tif (strcmp(encoder, SIMPLE_ENCODER_X264) == 0) {\n'
        '\t\tif (EncoderAvailable("obs_x264"))\n'
        '\t\t\treturn "obs_x264";\n'
        '\t} else if (strcmp(encoder, SIMPLE_ENCODER_X264_LOWCPU) == 0) {\n'
        '\t\tif (EncoderAvailable("obs_x264"))\n'
        '\t\t\treturn "obs_x264";\n'
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
        '\t/* OBS Toggle: never fall back to an unregistered encoder id\n\t * (it makes obs_get_encoder_codec() return NULL and Settings\n\t * crash). Pick the first AVAILABLE encoder, x264 included when\n\t * it is on. */\n'
        '\tif (EncoderAvailable("obs_x264"))\n'
        '\t\treturn "obs_x264";\n'
        '\tif (EncoderAvailable("obs_nvenc_h264_tex"))\n'
        '\t\treturn "obs_nvenc_h264_tex";\n'
        '\tif (EncoderAvailable("obs_qsv11_v2"))\n'
        '\t\treturn "obs_qsv11_v2";\n'
        '\tif (EncoderAvailable("h264_texture_amf"))\n'
        '\t\treturn "h264_texture_amf";\n'
        '\tif (EncoderAvailable("ffmpeg_nvenc"))\n'
        '\t\treturn "ffmpeg_nvenc";\n'
        '\t/* Last resort - the null-guards in OBSBasicSettings keep this from\n\t * crashing; Settings shows the encoder as incompatible instead. */\n'
        '\treturn "obs_qsv11_v2";\n'
        '}',
    )
    # Profiles: an unsupported hardware encoder used to fall back to
    # x264. In the Toggle fork x264 itself can be toggled off, so fall
    # back to the first encoder that IS registered on this PC — x264
    # first when it is on (the historical fallback), then hardware.
    # (Same shape as the PS5 Lite PickFallback, which was proven in CI.)
    replace_text(
        "frontend/widgets/OBSBasic_Profiles.cpp",
        '\tbool amd_supported = false;\n'
        '\tbool nve_supported = false;\n',
        '\tbool amd_supported = false;\n'
        '\tbool nve_supported = false;\n'
        '\tbool x264_supported = false;\n',
    )
    replace_text(
        "frontend/widgets/OBSBasic_Profiles.cpp",
        '\t\tif (strcmp(id, "h264_texture_amf") == 0) {\n',
        '\t\tif (strcmp(id, "obs_x264") == 0) {\n'
        '\t\t\tx264_supported = true;\n'
        '\t\t} else if (strcmp(id, "h264_texture_amf") == 0) {\n',
    )
    replace_text(
        "frontend/widgets/OBSBasic_Profiles.cpp",
        '\tauto CheckEncoder = [&](const char *&name) {',
        '\t/* OBS Toggle: fall back to the first encoder that is actually\n'
        '\t * registered on this PC (x264 first when it is on), never to an\n'
        '\t * id that was toggled off. */\n'
        '\tauto PickFallback = [&]() -> const char * {\n'
        '\t\tif (x264_supported)\n'
        '\t\t\treturn SIMPLE_ENCODER_X264;\n'
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
        '\t\t\t\tname = SIMPLE_ENCODER_X264;',
        '\t\t\t\tname = PickFallback();',
        count=10,
    )
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
        '\t/* OBS Toggle: x264 may be toggled off - fall back to QSV. */\n'
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
        '\t/* OBS Toggle: obs_x264 may be toggled off - fall back to QSV. */\n'
        '\treturn "obs_qsv11_v2";\n'
        '}',
    )
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
        '\t/* OBS Toggle: codec is NULL when the encoder id is unregistered\n\t * (toggled off); strcmp(NULL) crashes - guard it. */\n'
        '\tif (!codec) {\n'
        '\t\treturn false;\n'
        '\t}',
    )
    print("patched Settings-crash null-guards (adapted from PS5 Lite)")


def patch_canvas_chatbox():
    src = SCRIPT_DIR / "canvas-chatbox"
    if not src.is_dir():
        fail("canvas-chatbox plugin missing next to patch script")
    dst = ROOT / "plugins/canvas-chatbox"
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    for rel in ("CMakeLists.txt", "canvas-chatbox.cpp",
                "data/locale/en-US.ini", "cmake/windows/obs-module.rc.in"):
        must_exist(f"plugins/canvas-chatbox/{rel}")
    # Register as a core module (alphabetical: after aja-output-ui,
    # before coreaudio-encoder). OBS 33 only loads core modules on the
    # hardcoded list built into obs.dll — a hand-dropped DLL is never
    # loaded, which is why this registration matters.
    replace_text(
        "plugins/CMakeLists.txt",
        "add_core_module(aja-output-ui PLATFORMS WINDOWS MACOS LINUX WITH_MESSAGE)\n",
        "add_core_module(aja-output-ui PLATFORMS WINDOWS MACOS LINUX WITH_MESSAGE)\nadd_core_module(canvas-chatbox)\n",
    )
    chatbox_cmake = read("plugins/canvas-chatbox/CMakeLists.txt")
    if "add_library(canvas-chatbox MODULE)" not in chatbox_cmake:
        fail("plugins/canvas-chatbox/CMakeLists.txt has no MODULE_LIBRARY target")
    print("copied plugins/canvas-chatbox (Canvas Chatbox right + Style Chatbox left)")


def patch_stream_shower():
    src = SCRIPT_DIR / "stream-shower"
    if not src.is_dir():
        fail("stream-shower plugin missing next to patch script")
    dst = ROOT / "plugins/stream-shower"
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    for rel in ("CMakeLists.txt", "stream-shower.cpp",
                "data/locale/en-US.ini", "cmake/windows/obs-module.rc.in"):
        must_exist(f"plugins/stream-shower/{rel}")
    # Register as a core module AFTER check_obs_browser(): this plugin
    # links OBS::browser-panels (OBS's own CEF browser widget, the
    # same API OBS's BrowserDock uses), and that target only exists
    # once obs-browser's CMakeLists has run. Registering it earlier
    # (e.g. next to canvas-chatbox) would fail configure with
    # "target OBS::browser-panels not found".
    # OBS 33 only loads core modules on the hardcoded list built into
    # obs.dll — a hand-dropped DLL is never loaded, which is why this
    # registration matters.
    replace_text(
        "plugins/CMakeLists.txt",
        "check_obs_browser()\n",
        "check_obs_browser()\nadd_core_module(stream-shower)\n",
    )
    shower_cpp = read("plugins/stream-shower/stream-shower.cpp")
    if "obs_frontend_add_dock_by_id(" in shower_cpp:
        fail("plugins/stream-shower/stream-shower.cpp still registers a dock — v4 replaced the dock with a pop-out window")
    if "StreamWatcherDock" in shower_cpp:
        fail("plugins/stream-shower/stream-shower.cpp still has the old StreamWatcherDock class — v4 renamed it StreamWatcherWindow")
    shower_cmake = read("plugins/stream-shower/CMakeLists.txt")
    if "add_library(stream-shower MODULE)" not in shower_cmake:
        fail("plugins/stream-shower/CMakeLists.txt has no MODULE_LIBRARY target")
    if "OBS::browser-panels" not in shower_cmake:
        fail("plugins/stream-shower/CMakeLists.txt does not link OBS::browser-panels (Watcher window needs it)")
    if "AUTOMOC" not in shower_cmake:
        fail("plugins/stream-shower/CMakeLists.txt has no AUTOMOC — "
             "QCefWidget's moc (titleChanged/staticMetaObject) would not be "
             "compiled into stream-shower.dll and the link fails with LNK2019/LNK2001 "
             "(run 45653951425). See the AUTOMOC comment in that CMakeLists.txt.")
    print("copied plugins/stream-shower (Stream Shower source + Watcher window, Tools > Stream Watcher)")


# ----------------------------------------------------------------------
# verify + main
# ----------------------------------------------------------------------

def verify_no_removals():
    # The Toggle fork removes NOTHING. Every stock plugin / encoder file
    # must still be here after the patch.
    for rel in (
        "plugins/obs-x264",
        "plugins/vlc-video",
        "plugins/decklink",
        "plugins/aja",
        "plugins/obs-ffmpeg/obs-ffmpeg-openh264.c",
        "plugins/obs-filters/noise-suppress-filter.c",
        "plugins/obs-filters/compressor-filter.c",
        "plugins/obs-filters/gain-filter.c",
        "plugins/obs-webrtc/whip-service.cpp",
        "plugins/obs-vst",
        "plugins/obs-transitions",
        "plugins/obs-websocket",
        "plugins/obs-text",
        "plugins/win-capture",
        "plugins/win-dshow",
        "plugins/obs-browser",
        "plugins/obs-nvenc",
        "plugins/obs-qsv11",
        "plugins/canvas-chatbox/canvas-chatbox.cpp",
        "plugins/stream-shower/stream-shower.cpp",
        "frontend/FeatureToggles.hpp",
    ):
        must_exist(rel)
    if (ROOT / "plugins/stinger-maker").exists():
        fail("stinger-maker must NOT be in the Toggle fork")
    for needle, rel in (
        ("obs_add_disabled_feature", "libobs/obs-module.c"),
        ("obs_feature_disabled(info->id)", "libobs/obs-module.c"),
        ("hidden_sources_sleep", "libobs/obs-source.c"),
        ("obs_apply_feature_toggles", "frontend/plugin-manager/PluginManager.cpp"),
        ("BuildTogglesPage", "frontend/settings/OBSBasicSettings.cpp"),
        ("toggle_restart", "frontend/widgets/OBSBasic_MainControls.cpp"),
        ("CpuGuardDrop", "frontend/widgets/OBSBasic.cpp"),
        ("PreviewOffWhileLiveStart", "frontend/widgets/OBSBasic.cpp"),
        ("StreamingActive() || outputHandler->RecordingActive()", "frontend/widgets/OBSBasic_Updater.cpp"),
        ("add_core_module(canvas-chatbox)", "plugins/CMakeLists.txt"),
        ("add_core_module(stream-shower)", "plugins/CMakeLists.txt"),
        ("stream-shower", "frontend/FeatureToggles.hpp"),
        ("obs_browser_init_panel", "plugins/stream-shower/stream-shower.cpp"),
        ("stream_shower", "plugins/stream-shower/stream-shower.cpp"),
        ("StreamWatcherWindow", "plugins/stream-shower/stream-shower.cpp"),
        ("obs_frontend_add_tools_menu_item", "plugins/stream-shower/stream-shower.cpp"),
        ("openWatcherWindow", "plugins/stream-shower/stream-shower.cpp"),
        ("validChannelName", "plugins/stream-shower/stream-shower.cpp"),
    ):
        if needle not in read(rel):
            fail(f"verify: {needle!r} missing from {rel}")
    print("verify: nothing removed, all toggle code present")


def main():
    if ROOT is None:
        fail("usage: apply-toggle-patch.py <upstream-dir>")
    if not (ROOT / ".git").exists():
        fail(f"not an OBS checkout: {ROOT}")
    for rel in (
        "libobs/obs.h",
        "libobs/obs.c",
        "libobs/obs-internal.h",
        "libobs/obs-module.c",
        "libobs/obs-source.c",
        "frontend/plugin-manager/PluginManager.cpp",
        "frontend/settings/OBSBasicSettings.cpp",
        "frontend/settings/OBSBasicSettings.hpp",
        "frontend/widgets/OBSBasic.cpp",
        "frontend/widgets/OBSBasic.hpp",
        "frontend/widgets/OBSBasic_MainControls.cpp",
        "frontend/widgets/OBSBasic_Preview.cpp",
        "frontend/widgets/OBSBasic_Streaming.cpp",
        "frontend/widgets/OBSBasic_Recording.cpp",
        "frontend/widgets/OBSBasic_SceneItems.cpp",
        "frontend/widgets/OBSBasic_Updater.cpp",
        "frontend/widgets/OBSBasic_Profiles.cpp",
        "frontend/settings/OBSBasicSettings_Stream.cpp",
        "frontend/utility/SimpleOutput.cpp",
        "plugins/CMakeLists.txt",
    ):
        must_exist(rel)
    for rel, needle in (
        ("libobs/obs-module.c", "obs_add_disabled_feature"),
        ("frontend/settings/OBSBasicSettings.cpp", "OBSBasicSettings::BuildTogglesPage"),
        ("frontend/widgets/OBSBasic.cpp", "OBSBasic::ApplyEcoSettings"),
    ):
        if needle in read(rel):
            fail(f"{rel} already patched - refusing to run twice")

    patch_libobs()
    patch_hidden_sleep()
    patch_plugin_manager()
    patch_settings()
    patch_auto_restart()
    patch_obsbasic()
    patch_updater()
    patch_settings_crash_guards()
    patch_canvas_chatbox()
    patch_stream_shower()
    verify_no_removals()
    print("TOGGLE PATCH OK: official OBS 33.0.3 + Feature Toggles + canvas-chatbox + stream-shower, nothing removed")


if __name__ == "__main__":
    main()
