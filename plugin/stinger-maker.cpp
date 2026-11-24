/* Stinger Maker - OBS plugin (works on any OBS 28-33)
 *
 * Adds "Stinger Maker" to the Scene Transitions + dropdown, and a
 * Tools > Stinger Maker menu item.
 *
 * Simple version of a complicated transition maker: no timeline, no
 * video file, no rendering wait. Pick a style, two colours, some text,
 * a duration and a transition point - the transition draws the
 * animation live, in real time, while OBS switches scenes.
 *
 * How it works:
 *  - A real OBS transition source ("stinger_maker",
 *    OBS_SOURCE_TYPE_TRANSITION). OBS calls its video_render callback
 *    with t = 0..1 over the transition duration, and gives it the two
 *    scene textures (A = old scene, B = new scene).
 *  - The render is done by one small shader (data/stinger_maker.effect)
 *    with five styles: Wipe, Slide, Zoom, Glitch, Neon. Scene A shows
 *    before the transition point, scene B after it, with a colour bar
 *    at the wipe edge.
 *  - The text is rendered once with Qt (QImage/QPainter) into a
 *    texture and drawn centred, slamming in around the transition
 *    point. No font files, no external assets.
 *  - Sound: there is a Sound on/off property, but this version ships
 *    NO sound - there is no audio file bundled and no tone is
 *    synthesised. The property is stored and labelled as not in this
 *    version. Do not claim otherwise.
 *
 * Version adaptation:
 *  - Only stable libobs APIs used since OBS 28: obs_register_source
 *    with OBS_SOURCE_TYPE_TRANSITION, obs_transition_video_render /
 *    obs_transition_audio_render, gs_effect_create_from_file,
 *    obs_properties_*, obs_frontend_add_tools_menu_item,
 *    obs_frontend_set_current_transition,
 *    obs_frontend_set_transition_duration, obs_source_create_private.
 *  - obs_module_load logs obs_get_version() and loads on any version;
 *    nothing here needs an OBS 33-only API.
 *  - No FFmpeg, no libx264, no VLC, no datachannel, no external DLLs
 *    beyond obs.dll, the OBS frontend API and Qt6 (Widgets + Gui),
 *    which OBS already ships.
 */

#include <obs-module.h>
#include <obs-frontend-api.h>
#include <graphics/vec2.h>
#include <graphics/vec4.h>

#include <QDialog>
#include <QWidget>
#include <QMainWindow>
#include <QVBoxLayout>
#include <QHBoxLayout>
#include <QFormLayout>
#include <QComboBox>
#include <QPushButton>
#include <QLineEdit>
#include <QSlider>
#include <QCheckBox>
#include <QLabel>
#include <QTimer>
#include <QPainter>
#include <QImage>
#include <QFont>
#include <QColorDialog>
#include <QColor>

#include <cmath>
#include <cstring>
#include <string>

OBS_DECLARE_MODULE()
OBS_MODULE_USE_DEFAULT_LOCALE("stinger-maker", "en-US")

#define S_STYLE "style"
#define S_COLOR1 "color1"
#define S_COLOR2 "color2"
#define S_TEXT "text"
#define S_DURATION "duration"
#define S_POINT "point"
#define S_SOUND "sound"

enum StingerStyle {
	STYLE_WIPE = 0,
	STYLE_SLIDE = 1,
	STYLE_ZOOM = 2,
	STYLE_GLITCH = 3,
	STYLE_NEON = 4,
};

static float clampf(float v, float lo, float hi)
{
	return v < lo ? lo : (v > hi ? hi : v);
}

static float easeOutBack(float t)
{
	/* Small overshoot so the text slams in instead of sliding in. */
	float c1 = 1.70158f;
	float c3 = c1 + 1.0f;
	t = clampf(t, 0.0f, 1.0f);
	return 1.0f + c3 * powf(t - 1.0f, 3.0f) + c1 * powf(t - 1.0f, 2.0f);
}

static void colorToVec4(uint32_t c, struct vec4 *v)
{
	/* OBS colour properties store 0xAARRGGBB. */
	float r = (float)((c >> 16) & 0xFF) / 255.0f;
	float g = (float)((c >> 8) & 0xFF) / 255.0f;
	float b = (float)(c & 0xFF) / 255.0f;
	vec4_set(v, r, g, b, 1.0f);
}

/* ------------------------------------------------------------------ */
/* Transition source                                                   */
/* ------------------------------------------------------------------ */

struct stinger_info {
	obs_source_t *source;

	gs_effect_t *effect;
	gs_eparam_t *a_param;
	gs_eparam_t *b_param;
	gs_eparam_t *progress_param;
	gs_eparam_t *point_param;
	gs_eparam_t *style_param;
	gs_eparam_t *color1_param;
	gs_eparam_t *color2_param;

	int style;
	struct vec4 color1;
	struct vec4 color2;
	float point; /* 0..1, default 0.5 */
	int duration_ms; /* stored; OBS drives t, see update() */
	bool sound; /* stored only - no sound in this version */

	std::string text;
	gs_texture_t *text_tex;
	uint32_t text_w;
	uint32_t text_h;
	bool text_dirty;
};

static const char *stinger_get_name(void *type_data)
{
	(void)type_data;
	return obs_module_text("StingerMaker");
}

/* Render the text into a texture. Must run on the graphics thread -
 * it is only ever called from the video render callback. */
static void stinger_rebuild_text(struct stinger_info *s)
{
	if (s->text_tex) {
		gs_texture_destroy(s->text_tex);
		s->text_tex = nullptr;
	}
	s->text_w = 0;
	s->text_h = 0;
	s->text_dirty = false;

	if (s->text.empty())
		return;

	const int W = 1024;
	const int H = 256;
	QImage img(W, H, QImage::Format_ARGB32);
	img.fill(Qt::transparent);
	QPainter p(&img);
	p.setRenderHint(QPainter::Antialiasing);
	QFont font("Arial", 96, QFont::Bold);
	p.setFont(font);
	QString qtext = QString::fromUtf8(s->text.c_str());
	/* Black outline so white text reads on any scene. */
	p.setPen(QColor(0, 0, 0, 255));
	for (int dx = -4; dx <= 4; dx += 4) {
		for (int dy = -4; dy <= 4; dy += 4) {
			if (dx == 0 && dy == 0)
				continue;
			p.drawText(QRect(dx, dy, W, H), Qt::AlignCenter, qtext);
		}
	}
	p.setPen(QColor(255, 255, 255, 255));
	p.drawText(QRect(0, 0, W, H), Qt::AlignCenter, qtext);
	p.end();

	/* QImage ARGB32 is BGRA in memory on little-endian, which is
	 * exactly GS_BGRA. */
	const uint8_t *bits = img.constBits();
	s->text_tex = gs_texture_create(W, H, GS_BGRA, 1, &bits, 0);
	if (s->text_tex) {
		s->text_w = W;
		s->text_h = H;
	}
}

static void stinger_update(void *data, obs_data_t *settings)
{
	struct stinger_info *s = (struct stinger_info *)data;
	const char *style = obs_data_get_string(settings, S_STYLE);
	if (!style)
		style = "wipe";
	if (strcmp(style, "slide") == 0)
		s->style = STYLE_SLIDE;
	else if (strcmp(style, "zoom") == 0)
		s->style = STYLE_ZOOM;
	else if (strcmp(style, "glitch") == 0)
		s->style = STYLE_GLITCH;
	else if (strcmp(style, "neon") == 0)
		s->style = STYLE_NEON;
	else
		s->style = STYLE_WIPE;

	uint32_t c1 = (uint32_t)obs_data_get_int(settings, S_COLOR1);
	uint32_t c2 = (uint32_t)obs_data_get_int(settings, S_COLOR2);
	colorToVec4(c1 ? c1 : 0xFF8000FF, &s->color1);
	colorToVec4(c2 ? c2 : 0xFF00C8FF, &s->color2);

	const char *text = obs_data_get_string(settings, S_TEXT);
	std::string newText = text ? text : "";
	if (newText != s->text) {
		s->text = newText;
		s->text_dirty = true;
	}

	s->duration_ms = (int)obs_data_get_int(settings, S_DURATION);
	if (s->duration_ms <= 0)
		s->duration_ms = 1000;
	s->point = (float)obs_data_get_int(settings, S_POINT) / 100.0f;
	if (s->point < 0.05f)
		s->point = 0.05f;
	if (s->point > 0.95f)
		s->point = 0.95f;
	s->sound = obs_data_get_bool(settings, S_SOUND);
	/* Sound is stored only: this version ships no sound. */
}

static void *stinger_create(obs_data_t *settings, obs_source_t *source)
{
	struct stinger_info *s = (struct stinger_info *)bzalloc(sizeof(*s));
	s->source = source;
	s->style = STYLE_WIPE;
	s->point = 0.5f;
	s->duration_ms = 1000;
	s->sound = false;
	s->text_tex = nullptr;
	s->text_dirty = false;
	vec4_set(&s->color1, 0.5f, 0.0f, 1.0f, 1.0f);
	vec4_set(&s->color2, 0.0f, 0.78f, 1.0f, 1.0f);

	char *file = obs_module_file("stinger_maker.effect");
	obs_enter_graphics();
	s->effect = file ? gs_effect_create_from_file(file, nullptr) : nullptr;
	obs_leave_graphics();
	bfree(file);

	if (!s->effect) {
		blog(LOG_ERROR, "Stinger Maker: could not load stinger_maker.effect");
		bfree(s);
		return nullptr;
	}
	s->a_param = gs_effect_get_param_by_name(s->effect, "tex_a");
	s->b_param = gs_effect_get_param_by_name(s->effect, "tex_b");
	s->progress_param = gs_effect_get_param_by_name(s->effect, "progress");
	s->point_param = gs_effect_get_param_by_name(s->effect, "point");
	s->style_param = gs_effect_get_param_by_name(s->effect, "style");
	s->color1_param = gs_effect_get_param_by_name(s->effect, "color1");
	s->color2_param = gs_effect_get_param_by_name(s->effect, "color2");

	obs_source_update(source, settings);
	return s;
}

static void stinger_destroy(void *data)
{
	struct stinger_info *s = (struct stinger_info *)data;
	if (s->text_tex) {
		obs_enter_graphics();
		gs_texture_destroy(s->text_tex);
		obs_leave_graphics();
	}
	bfree(s);
}

static void stinger_callback(void *data, gs_texture_t *a, gs_texture_t *b, float t, uint32_t cx, uint32_t cy)
{
	struct stinger_info *s = (struct stinger_info *)data;
	if (!s->effect)
		return;

	if (s->text_dirty)
		stinger_rebuild_text(s);

	const bool previous = gs_framebuffer_srgb_enabled();
	gs_enable_framebuffer_srgb(true);

	if (a)
		gs_effect_set_texture_srgb(s->a_param, a);
	if (b)
		gs_effect_set_texture_srgb(s->b_param, b);
	gs_effect_set_float(s->progress_param, t);
	gs_effect_set_float(s->point_param, s->point);
	gs_effect_set_int(s->style_param, s->style);
	gs_effect_set_vec4(s->color1_param, &s->color1);
	gs_effect_set_vec4(s->color2_param, &s->color2);

	while (gs_effect_loop(s->effect, "Stinger"))
		gs_draw_sprite(nullptr, 0, cx, cy);

	/* Text slam: appears around the transition point, scales up
	 * with a little overshoot, then settles. */
	if (s->text_tex && s->text_w > 0) {
		float tt = clampf((t - s->point * 0.5f) / 0.35f, 0.0f, 1.0f);
		if (tt > 0.0f) {
			float scale = 0.75f + 0.35f * easeOutBack(tt);
			float tw = (float)s->text_w * scale * 0.9f;
			float th = (float)s->text_h * scale * 0.9f;
			if (tw > (float)cx * 0.9f) {
				float k = ((float)cx * 0.9f) / tw;
				tw *= k;
				th *= k;
			}
			float x = ((float)cx - tw) / 2.0f;
			float y = ((float)cy - th) / 2.0f;
			gs_effect_t *def = obs_get_base_effect(OBS_EFFECT_DEFAULT);
			gs_effect_set_texture_srgb(gs_effect_get_param_by_name(def, "image"),
						   s->text_tex);
			gs_matrix_push();
			gs_matrix_translate3f(x, y, 0.0f);
			while (gs_effect_loop(def, "Draw"))
				gs_draw_sprite(s->text_tex, 0, (uint32_t)tw, (uint32_t)th);
			gs_matrix_pop();
		}
	}

	gs_enable_framebuffer_srgb(previous);
}

static void stinger_video_render(void *data, gs_effect_t *effect)
{
	struct stinger_info *s = (struct stinger_info *)data;
	(void)effect;
	obs_transition_video_render(s->source, stinger_callback);
}

static float mix_a(void *data, float t)
{
	(void)data;
	return 1.0f - t;
}

static float mix_b(void *data, float t)
{
	(void)data;
	return t;
}

static bool stinger_audio_render(void *data, uint64_t *ts_out, struct obs_source_audio_mix *audio,
				 uint32_t mixers, size_t channels, size_t sample_rate)
{
	struct stinger_info *s = (struct stinger_info *)data;
	return obs_transition_audio_render(s->source, ts_out, audio, mixers, channels, sample_rate, mix_a,
					   mix_b);
}

static obs_properties_t *stinger_properties(void *data)
{
	(void)data;
	obs_properties_t *ppts = obs_properties_create();
	obs_property_t *p;

	p = obs_properties_add_list(ppts, S_STYLE, obs_module_text("Style"), OBS_COMBO_TYPE_LIST,
				    OBS_COMBO_FORMAT_STRING);
	obs_property_list_add_string(p, obs_module_text("Style.Wipe"), "wipe");
	obs_property_list_add_string(p, obs_module_text("Style.Slide"), "slide");
	obs_property_list_add_string(p, obs_module_text("Style.Zoom"), "zoom");
	obs_property_list_add_string(p, obs_module_text("Style.Glitch"), "glitch");
	obs_property_list_add_string(p, obs_module_text("Style.Neon"), "neon");

	obs_properties_add_color(ppts, S_COLOR1, obs_module_text("Color1"));
	obs_properties_add_color(ppts, S_COLOR2, obs_module_text("Color2"));
	obs_properties_add_text(ppts, S_TEXT, obs_module_text("Text"), OBS_TEXT_DEFAULT);

	p = obs_properties_add_list(ppts, S_DURATION, obs_module_text("Duration"), OBS_COMBO_TYPE_LIST,
				    OBS_COMBO_FORMAT_INT);
	obs_property_list_add_int(p, obs_module_text("Duration.0.5s"), 500);
	obs_property_list_add_int(p, obs_module_text("Duration.1s"), 1000);
	obs_property_list_add_int(p, obs_module_text("Duration.1.5s"), 1500);
	obs_property_list_add_int(p, obs_module_text("Duration.2s"), 2000);

	obs_properties_add_int_slider(ppts, S_POINT, obs_module_text("Point"), 5, 95, 5);
	obs_properties_add_bool(ppts, S_SOUND, obs_module_text("Sound"));

	obs_properties_add_text(ppts, "note", obs_module_text("Note"), OBS_TEXT_INFO);
	return ppts;
}

static void stinger_defaults(obs_data_t *settings)
{
	obs_data_set_default_string(settings, S_STYLE, "wipe");
	obs_data_set_default_int(settings, S_COLOR1, 0xFF8000FF);
	obs_data_set_default_int(settings, S_COLOR2, 0xFF00C8FF);
	obs_data_set_default_string(settings, S_TEXT, "official_robust_clan");
	obs_data_set_default_int(settings, S_DURATION, 1000);
	obs_data_set_default_int(settings, S_POINT, 50);
	obs_data_set_default_bool(settings, S_SOUND, false);
}

static enum gs_color_space stinger_video_get_color_space(void *data, size_t count,
							 const enum gs_color_space *preferred_spaces)
{
	(void)count;
	(void)preferred_spaces;
	struct stinger_info *s = (struct stinger_info *)data;
	return obs_transition_video_get_color_space(s->source);
}

static struct obs_source_info stinger_transition = {
	.id = "stinger_maker",
	.type = OBS_SOURCE_TYPE_TRANSITION,
	.output_flags = OBS_SOURCE_VIDEO,
	.get_name = stinger_get_name,
	.create = stinger_create,
	.destroy = stinger_destroy,
	.get_defaults = stinger_defaults,
	.get_properties = stinger_properties,
	.update = stinger_update,
	.video_render = stinger_video_render,
	.audio_render = stinger_audio_render,
	.video_get_color_space = stinger_video_get_color_space,
};

/* ------------------------------------------------------------------ */
/* Tools > Stinger Maker dialog                                        */
/* ------------------------------------------------------------------ */

class PreviewWidget : public QWidget {
public:
	int style = 0;
	QColor c1 = QColor(128, 0, 255);
	QColor c2 = QColor(0, 200, 255);
	QString text = "official_robust_clan";
	float progress = 0.0f;

	explicit PreviewWidget(QWidget *parent = nullptr) : QWidget(parent)
	{
		setMinimumHeight(180);
	}

protected:
	void paintEvent(QPaintEvent *) override
	{
		QPainter p(this);
		int w = width();
		int h = height();
		/* Scene A: dark, Scene B: lighter, so the switch reads. */
		p.fillRect(0, 0, w, h, QColor(30, 30, 40));
		float edge = progress;
		if (style == 2 || style == 3) {
			/* Zoom / Glitch: crossfade. */
			p.setOpacity(progress);
			p.fillRect(0, 0, w, h, QColor(60, 60, 90));
			p.setOpacity(1.0);
		} else {
			int x = (int)(edge * w);
			p.fillRect(0, 0, x, h, QColor(60, 60, 90));
			/* Colour bar at the edge. */
			QColor bar = c1;
			if (progress > 0.5f)
				bar = c2;
			p.fillRect(x - 4, 0, 8, h, bar);
			if (style == 4) {
				p.setOpacity(0.35);
				p.fillRect(x - 24, 0, 48, h, c2);
				p.setOpacity(1.0);
			}
		}
		if (!text.isEmpty() && progress > 0.25f) {
			float tt = (progress - 0.25f) / 0.35f;
			if (tt > 1.0f)
				tt = 1.0f;
			QFont f("Arial", (int)(18 + 14 * tt), QFont::Bold);
			p.setFont(f);
			p.setPen(Qt::black);
			p.drawText(QRect(2, 2, w, h), Qt::AlignCenter, text);
			p.setPen(Qt::white);
			p.drawText(QRect(0, 0, w, h), Qt::AlignCenter, text);
		}
	}
};

static QString styleKeyFromIndex(int i)
{
	switch (i) {
	case 1:
		return "slide";
	case 2:
		return "zoom";
	case 3:
		return "glitch";
	case 4:
		return "neon";
	default:
		return "wipe";
	}
}

class StingerMakerDialog : public QDialog {
	QComboBox *styleBox = nullptr;
	QPushButton *color1Btn = nullptr;
	QPushButton *color2Btn = nullptr;
	QLineEdit *textEdit = nullptr;
	QComboBox *durationBox = nullptr;
	QSlider *pointSlider = nullptr;
	QCheckBox *soundBox = nullptr;
	QLabel *status = nullptr;
	PreviewWidget *preview = nullptr;
	QTimer *anim = nullptr;
	QColor color1 = QColor(128, 0, 255);
	QColor color2 = QColor(0, 200, 255);
	float progress = 0.0f;

public:
	explicit StingerMakerDialog(QWidget *parent = nullptr) : QDialog(parent)
	{
		setWindowTitle("Stinger Maker");
		setMinimumWidth(420);
		QVBoxLayout *layout = new QVBoxLayout(this);

		preview = new PreviewWidget(this);
		layout->addWidget(preview);

		QFormLayout *form = new QFormLayout();
		styleBox = new QComboBox(this);
		styleBox->addItems({"Wipe", "Slide", "Zoom", "Glitch", "Neon"});
		form->addRow("Style:", styleBox);

		color1Btn = new QPushButton("Pick colour 1", this);
		color2Btn = new QPushButton("Pick colour 2", this);
		form->addRow("Colour 1:", color1Btn);
		form->addRow("Colour 2:", color2Btn);

		textEdit = new QLineEdit("official_robust_clan", this);
		form->addRow("Text:", textEdit);

		durationBox = new QComboBox(this);
		durationBox->addItems({"0.5 seconds", "1 second", "1.5 seconds", "2 seconds"});
		durationBox->setCurrentIndex(1);
		form->addRow("Duration:", durationBox);

		pointSlider = new QSlider(Qt::Horizontal, this);
		pointSlider->setRange(5, 95);
		pointSlider->setValue(50);
		form->addRow("Transition point %:", pointSlider);

		soundBox = new QCheckBox("Sound (not in this version — no sound yet)", this);
		soundBox->setChecked(false);
		form->addRow("", soundBox);
		layout->addLayout(form);

		status = new QLabel("Pick a style and colours — the preview loops above. "
				    "\"Use This Stinger Now\" makes it your current transition.",
				    this);
		status->setWordWrap(true);
		layout->addWidget(status);

		QHBoxLayout *row = new QHBoxLayout();
		QPushButton *useBtn = new QPushButton("Use This Stinger Now", this);
		QPushButton *closeBtn = new QPushButton("Close", this);
		row->addWidget(useBtn, 1);
		row->addWidget(closeBtn);
		layout->addLayout(row);

		anim = new QTimer(this);
		anim->setInterval(33);
		connect(anim, &QTimer::timeout, this, [this]() {
			progress += 0.02f;
			if (progress > 1.0f)
				progress = 0.0f;
			preview->progress = progress;
			preview->update();
		});
		anim->start();

		connect(styleBox, QOverload<int>::of(&QComboBox::currentIndexChanged), this,
			[this](int i) { preview->style = i; });
		connect(color1Btn, &QPushButton::clicked, this, [this]() {
			QColor c = QColorDialog::getColor(color1, this, "Colour 1");
			if (c.isValid()) {
				color1 = c;
				preview->c1 = c;
			}
		});
		connect(color2Btn, &QPushButton::clicked, this, [this]() {
			QColor c = QColorDialog::getColor(color2, this, "Colour 2");
			if (c.isValid()) {
				color2 = c;
				preview->c2 = c;
			}
		});
		connect(textEdit, &QLineEdit::textChanged, this,
			[this](const QString &t) { preview->text = t; });
		connect(useBtn, &QPushButton::clicked, this, [this]() { onUse(); });
		connect(closeBtn, &QPushButton::clicked, this, [this]() { accept(); });
	}

private:
	void onUse()
	{
		int durations[] = {500, 1000, 1500, 2000};
		int ms = durations[durationBox->currentIndex()];
		uint32_t col1 = (uint32_t)((0xFF << 24) | (color1.red() << 16) | (color1.green() << 8) |
					   color1.blue());
		uint32_t col2 = (uint32_t)((0xFF << 24) | (color2.red() << 16) | (color2.green() << 8) |
					   color2.blue());
		obs_data_t *settings = obs_data_create();
		obs_data_set_string(settings, S_STYLE, styleKeyFromIndex(styleBox->currentIndex())
							       .toUtf8()
							       .constData());
		obs_data_set_int(settings, S_COLOR1, (long long)col1);
		obs_data_set_int(settings, S_COLOR2, (long long)col2);
		obs_data_set_string(settings, S_TEXT, textEdit->text().toUtf8().constData());
		obs_data_set_int(settings, S_DURATION, ms);
		obs_data_set_int(settings, S_POINT, pointSlider->value());
		obs_data_set_bool(settings, S_SOUND, soundBox->isChecked());

		obs_source_t *src = obs_source_create_private("stinger_maker", "Stinger Maker", settings);
		obs_data_release(settings);
		if (!src) {
			status->setText("Could not make the stinger — is the plugin loaded?");
			return;
		}
		obs_frontend_set_current_transition(src);
		obs_frontend_set_transition_duration(ms);
		obs_source_release(src);
		status->setText("Done — this stinger is now your current transition. Press "
				"Transition in OBS to play it. To keep it in the list, add it via "
				"Scene Transitions + > Stinger Maker with the same settings.");
	}
};

static void openStingerMaker(void *private_data)
{
	(void)private_data;
	void *mw = obs_frontend_get_main_window();
	QWidget *parent = mw ? (QWidget *)mw : nullptr;
	StingerMakerDialog dlg(parent);
	dlg.exec();
}

bool obs_module_load(void)
{
	uint32_t v = obs_get_version();
	int major = (int)((v >> 24) & 0xFF);
	int minor = (int)((v >> 16) & 0xFF);
	int patch = (int)(v & 0xFFFF);
	blog(LOG_INFO, "Stinger Maker: loading on OBS %d.%d.%d", major, minor, patch);

	obs_register_source(&stinger_transition);
	obs_frontend_add_tools_menu_item("Stinger Maker", openStingerMaker, nullptr);
	blog(LOG_INFO, "Stinger Maker loaded: Scene Transitions + > Stinger Maker, and Tools > Stinger Maker");
	return true;
}

void obs_module_unload(void) {}
