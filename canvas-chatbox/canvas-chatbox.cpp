/* Canvas Chatbox - OBS PS5 Lite
 *
 * A dock panel that sits BESIDE the canvas (in the OBS dock area, never
 * on top of the canvas and never inside the scene). The user types plain
 * words and the panel does it on the current scene/canvas directly:
 * add / remove / move / resize sources, set a colour background, or use
 * an image as a full-canvas background.
 *
 * Local only: no network, no external AI service, no background thread,
 * no timer. It only runs when the user hits Enter / Send, so it costs
 * nothing while streaming. Part of the 50% PC budget.
 *
 * Examples it handles:
 *   add my webcam bottom right
 *   add text hello world
 *   add image "C:\Users\ricky\Pictures\overlay.png"
 *   make the game bigger
 *   move the webcam to top left
 *   remove the text
 *   set background to black
 *   use this image as background
 */

#include <obs-module.h>
#include <obs-frontend-api.h>

#include <QWidget>
#include <QMainWindow>
#include <QDockWidget>
#include <QTimer>
#include <QMap>
#include <QVBoxLayout>
#include <QHBoxLayout>
#include <QPlainTextEdit>
#include <QLineEdit>
#include <QPushButton>
#include <QLabel>
#include <QRegularExpression>

#include <algorithm>
#include <cmath>
#include <string>
#include <vector>

OBS_DECLARE_MODULE()
OBS_MODULE_USE_DEFAULT_LOCALE("canvas-chatbox", "en-US")

namespace {

struct Kind {
	const char *key; /* word used to match */
	const char *id; /* obs source id */
	const char *name; /* default source name */
	const char *words; /* extra words that mean this kind */
};

/* Kinds the chatbox knows. Order matters: check webcam before camera etc. */
const Kind KINDS[] = {
	{"webcam", "dshow_input", "Webcam", "webcam cam camera"},
	{"game", "game_capture", "Game Capture", "game"},
	{"display", "monitor_capture", "Display Capture", "display screen monitor"},
	{"window", "window_capture", "Window Capture", "window"},
	{"browser", "browser_source", "Browser", "browser web website"},
	{"mic", "wasapi_input_capture", "Mic", "mic microphone"},
	{"text", "text_ft2_source", "Text", "text"},
	{"image", "image_source", "Image", "image picture photo"},
	{"color", "color_source", "Background", "color colour"},
	{"media", "ffmpeg_source", "Media", "media video clip"},
};

const Kind *findKind(const QString &lower)
{
	for (const Kind &k : KINDS) {
		if (lower.contains(k.key))
			return &k;
		QStringList words = QString(k.words).split(' ');
		for (const QString &w : words) {
			if (!w.isEmpty() && lower.contains(w))
				return &k;
		}
	}
	return nullptr;
}

bool canvasSize(uint32_t &cx, uint32_t &cy)
{
	struct obs_video_info ovi = {};
	if (obs_get_video_info(&ovi) && ovi.base_width > 0 && ovi.base_height > 0) {
		cx = ovi.base_width;
		cy = ovi.base_height;
		return true;
	}
	cx = 1280;
	cy = 720;
	return false;
}

uint32_t colorForName(const QString &lower, bool &ok)
{
	ok = true;
	if (lower.contains("black"))
		return 0xFF000000;
	if (lower.contains("white"))
		return 0xFFFFFFFF;
	if (lower.contains("red"))
		return 0xFFFF0000;
	if (lower.contains("green"))
		return 0xFF00FF00;
	if (lower.contains("blue"))
		return 0xFF0000FF;
	if (lower.contains("yellow"))
		return 0xFFFFFF00;
	if (lower.contains("purple"))
		return 0xFF800080;
	if (lower.contains("pink"))
		return 0xFFFFC0CB;
	if (lower.contains("orange"))
		return 0xFFFFA500;
	if (lower.contains("grey") || lower.contains("gray"))
		return 0xFF808080;
	ok = false;
	return 0xFF000000;
}

struct CollectCtx {
	std::vector<obs_sceneitem_t *> items;
};

bool collectCb(obs_scene_t *, obs_sceneitem_t *item, void *param)
{
	CollectCtx *ctx = (CollectCtx *)param;
	obs_sceneitem_addref(item);
	ctx->items.push_back(item);
	return true;
}

void releaseItems(std::vector<obs_sceneitem_t *> &items)
{
	for (obs_sceneitem_t *it : items)
		obs_sceneitem_release(it);
	items.clear();
}

QString sourceName(obs_sceneitem_t *item)
{
	obs_source_t *src = obs_sceneitem_get_source(item);
	if (!src)
		return QString();
	const char *name = obs_source_get_name(src);
	return name ? QString::fromUtf8(name) : QString();
}

QString sourceId(obs_sceneitem_t *item)
{
	obs_source_t *src = obs_sceneitem_get_source(item);
	if (!src)
		return QString();
	const char *id = obs_source_get_id(src);
	return id ? QString::fromUtf8(id) : QString();
}

/* Find an item in the current scene by source name (contains) or kind. */
obs_sceneitem_t *findItem(obs_scene_t *scene, const QString &lower)
{
	CollectCtx ctx;
	obs_scene_enum_items(scene, collectCb, &ctx);

	obs_sceneitem_t *found = nullptr;

	/* 1) name match: an item whose name appears in the command */
	for (obs_sceneitem_t *it : ctx.items) {
		QString name = sourceName(it).toLower();
		if (!name.isEmpty() && lower.contains(name)) {
			found = it;
			obs_sceneitem_addref(found);
			break;
		}
	}
	/* 2) kind match */
	if (!found) {
		const Kind *kind = findKind(lower);
		if (kind) {
			for (obs_sceneitem_t *it : ctx.items) {
				if (sourceId(it) == kind->id) {
					found = it;
					obs_sceneitem_addref(found);
					break;
				}
			}
		}
	}
	/* 3) "background" means the item named Background */
	if (!found && lower.contains("background")) {
		for (obs_sceneitem_t *it : ctx.items) {
			if (sourceName(it).toLower() == "background") {
				found = it;
				obs_sceneitem_addref(found);
				break;
			}
		}
	}
	releaseItems(ctx.items);
	return found;
}

void itemSize(obs_sceneitem_t *item, float &w, float &h)
{
	obs_source_t *src = obs_sceneitem_get_source(item);
	struct vec2 scale = {};
	obs_sceneitem_get_scale(item, &scale);
	uint32_t nw = src ? obs_source_get_width(src) : 0;
	uint32_t nh = src ? obs_source_get_height(src) : 0;
	if (nw == 0)
		nw = 640;
	if (nh == 0)
		nh = 360;
	w = (float)nw * (scale.x > 0.0f ? scale.x : 1.0f);
	h = (float)nh * (scale.y > 0.0f ? scale.y : 1.0f);
}

bool positionFor(const QString &lower, uint32_t cw, uint32_t ch, float w, float h,
		 struct vec2 &pos)
{
	if (lower.contains("bottom right")) {
		pos.x = (float)cw - w;
		pos.y = (float)ch - h;
	} else if (lower.contains("bottom left")) {
		pos.x = 0.0f;
		pos.y = (float)ch - h;
	} else if (lower.contains("top right")) {
		pos.x = (float)cw - w;
		pos.y = 0.0f;
	} else if (lower.contains("top left")) {
		pos.x = 0.0f;
		pos.y = 0.0f;
	} else if (lower.contains("bottom center") || lower.contains("bottom centre")) {
		pos.x = ((float)cw - w) / 2.0f;
		pos.y = (float)ch - h;
	} else if (lower.contains("top center") || lower.contains("top centre")) {
		pos.x = ((float)cw - w) / 2.0f;
		pos.y = 0.0f;
	} else if (lower.contains("center") || lower.contains("centre") ||
		   lower.contains("middle")) {
		pos.x = ((float)cw - w) / 2.0f;
		pos.y = ((float)ch - h) / 2.0f;
	} else {
		return false;
	}
	if (pos.x < 0.0f)
		pos.x = 0.0f;
	if (pos.y < 0.0f)
		pos.y = 0.0f;
	return true;
}

QString quotedPath(const QString &text)
{
	QRegularExpression re("\"([^\"]+)\"");
	QRegularExpressionMatch m = re.match(text);
	if (m.hasMatch())
		return m.captured(1);
	/* unquoted file token, e.g. C:\pics\bg.png */
	QRegularExpression re2("(\\S+\\.(png|jpg|jpeg|gif|bmp|webp|mp4|mov))",
			       QRegularExpression::CaseInsensitiveOption);
	QRegularExpressionMatch m2 = re2.match(text);
	if (m2.hasMatch())
		return m2.captured(1);
	return QString();
}

class CanvasChatbox : public QWidget {
	/* No Q_OBJECT on purpose: connects use lambdas, so no moc step is needed. */
	QPlainTextEdit *log = nullptr;
	QLineEdit *input = nullptr;

public:
	CanvasChatbox(QWidget *parent = nullptr) : QWidget(parent)
	{
		QVBoxLayout *layout = new QVBoxLayout(this);
		layout->setContentsMargins(6, 6, 6, 6);

		QLabel *title = new QLabel("Canvas Chatbox — type what to do, in plain words", this);
		title->setWordWrap(true);
		layout->addWidget(title);

		log = new QPlainTextEdit(this);
		log->setReadOnly(true);
		log->setMaximumBlockCount(200);
		log->setPlaceholderText("Try: add my webcam bottom right");
		layout->addWidget(log, 1);

		QLabel *hint = new QLabel(
			"Examples: add my webcam bottom right · make the game bigger · "
			"remove the text · set background to black · use this image as background",
			this);
		hint->setWordWrap(true);
		layout->addWidget(hint);

		QHBoxLayout *row = new QHBoxLayout();
		input = new QLineEdit(this);
		input->setPlaceholderText("Type what to do on the canvas…");
		row->addWidget(input, 1);
		QPushButton *send = new QPushButton("Send", this);
		row->addWidget(send);
		layout->addLayout(row);

		connect(send, &QPushButton::clicked, this, [this]() { onSend(); });
		connect(input, &QLineEdit::returnPressed, this, [this]() { onSend(); });

		reply("Hi — I live beside the canvas. Tell me what to do in plain words, "
		      "like \"add my webcam bottom right\" or \"set background to black\". "
		      "Type \"help\" to see everything I can do.");
	}

	void reply(const QString &text)
	{
		log->appendPlainText(text);
	}

private:
	void onSend()
	{
		QString text = input->text().trimmed();
		if (text.isEmpty())
			return;
		input->clear();
		log->appendPlainText(QString("> %1").arg(text));
		handleCommand(text);
	}

private:
	obs_scene_t *currentScene(obs_source_t **sceneSourceOut)
	{
		obs_source_t *sceneSource = obs_frontend_get_current_scene();
		if (!sceneSource)
			return nullptr;
		*sceneSourceOut = sceneSource;
		return obs_scene_from_source(sceneSource);
	}

	void handleCommand(const QString &text)
	{
		QString lower = text.toLower().trimmed();

		if (lower == "help" || lower.contains("what can you do") ||
		    lower.contains("what do you do")) {
			reply("I can do this on the canvas:\n"
			      "- add my webcam bottom right / add game / add display / add browser <url> / add mic / add text hello / add image \"C:\\path\\pic.png\"\n"
			      "- remove the text / remove the webcam\n"
			      "- move the webcam to top left / move the game left\n"
			      "- make the game bigger / make the webcam smaller / resize the image to 50%\n"
			      "- set background to black (black, white, red, green, blue, yellow, purple, pink, orange, grey)\n"
			      "- use this image as background (stretches an image to the full canvas)");
			return;
		}

		obs_source_t *sceneSource = nullptr;
		obs_scene_t *scene = currentScene(&sceneSource);
		if (!scene) {
			reply("No scene is open right now — open a scene first, then try again.");
			return;
		}

		if (lower.contains("background")) {
			doBackground(scene, text, lower);
		} else if (lower.startsWith("remove") || lower.startsWith("delete")) {
			doRemove(scene, lower);
		} else if (lower.startsWith("add")) {
			doAdd(scene, text, lower);
		} else if (lower.startsWith("move")) {
			doMove(scene, lower);
		} else if (lower.contains("bigger") || lower.contains("larger") ||
			   lower.contains("smaller") || lower.contains("resize") ||
			   lower.contains("big") || lower.contains("small")) {
			doResize(scene, lower);
		} else {
			reply("I didn't catch that. Try: add my webcam bottom right · "
			      "make the game bigger · remove the text · set background to black · "
			      "use this image as background. Type \"help\" for the full list.");
		}

		obs_source_release(sceneSource);
	}

	void doBackground(obs_scene_t *scene, const QString &text, const QString &lower)
	{
		uint32_t cw = 0, ch = 0;
		canvasSize(cw, ch);

		QString path = quotedPath(text);
		bool wantsImage = lower.contains("image") || lower.contains("picture") ||
				  lower.contains("photo") || !path.isEmpty();

		if (wantsImage) {
			if (!path.isEmpty()) {
				/* Use this exact file as the full-canvas background. */
				removeNamed(scene, "Background");
				obs_data_t *settings = obs_data_create();
				obs_data_set_string(settings, "file",
						    path.toUtf8().constData());
				obs_source_t *src = obs_source_create("image_source", "Background",
								      settings, nullptr);
				obs_data_release(settings);
				if (!src) {
					reply("I couldn't load that image file — check the path and try again.");
					return;
				}
				obs_sceneitem_t *item = obs_scene_add(scene, src);
				uint32_t nw = obs_source_get_width(src);
				uint32_t nh = obs_source_get_height(src);
				struct vec2 scale = {nw > 0 ? (float)cw / (float)nw : 1.0f,
						     nh > 0 ? (float)ch / (float)nh : 1.0f};
				struct vec2 pos = {0.0f, 0.0f};
				obs_sceneitem_set_scale(item, &scale);
				obs_sceneitem_set_pos(item, &pos);
				obs_sceneitem_set_order_position(item, 0);
				obs_sceneitem_release(item);
				obs_source_release(src);
				reply("Done — that image is now the background, full canvas.");
				return;
			}
			/* "use this image as background" - stretch an image already on the canvas. */
			obs_sceneitem_t *item = findItem(scene, "image");
			if (!item) {
				reply("There's no image on the canvas yet. Add one first, like: "
				      "add image \"C:\\path\\to\\image.png\" — then say: use this image as background.");
				return;
			}
			obs_source_t *src = obs_sceneitem_get_source(item);
			uint32_t nw = src ? obs_source_get_width(src) : 0;
			uint32_t nh = src ? obs_source_get_height(src) : 0;
			struct vec2 scale = {nw > 0 ? (float)cw / (float)nw : 1.0f,
					     nh > 0 ? (float)ch / (float)nh : 1.0f};
			struct vec2 pos = {0.0f, 0.0f};
			obs_sceneitem_set_scale(item, &scale);
			obs_sceneitem_set_pos(item, &pos);
			obs_sceneitem_set_order_position(item, 0);
			obs_sceneitem_release(item);
			reply("Done — the image is now the background, full canvas.");
			return;
		}

		bool ok = false;
		uint32_t color = colorForName(lower, ok);
		if (!ok) {
			reply("Which colour? Try: set background to black, white, red, green, "
			      "blue, yellow, purple, pink, orange or grey. Or: use this image as background.");
			return;
		}
		removeNamed(scene, "Background");
		obs_data_t *settings = obs_data_create();
		obs_data_set_int(settings, "color", (long long)color);
		obs_data_set_int(settings, "width", (long long)cw);
		obs_data_set_int(settings, "height", (long long)ch);
		obs_source_t *src = obs_source_create("color_source", "Background", settings, nullptr);
		obs_data_release(settings);
		if (!src) {
			reply("I couldn't make a colour background right now.");
			return;
		}
		obs_sceneitem_t *item = obs_scene_add(scene, src);
		struct vec2 pos = {0.0f, 0.0f};
		obs_sceneitem_set_pos(item, &pos);
		obs_sceneitem_set_order_position(item, 0);
		obs_sceneitem_release(item);
		obs_source_release(src);
		reply("Done — background set, full canvas.");
	}

	void removeNamed(obs_scene_t *scene, const char *name)
	{
		obs_sceneitem_t *item = obs_scene_find_source(scene, name);
		if (item) {
			obs_sceneitem_remove(item);
			obs_sceneitem_release(item);
		}
	}

	void doRemove(obs_scene_t *scene, const QString &lower)
	{
		obs_sceneitem_t *item = findItem(scene, lower);
		if (!item) {
			reply("I couldn't find that on the canvas — check the name and try again.");
			return;
		}
		QString name = sourceName(item);
		obs_sceneitem_remove(item);
		obs_sceneitem_release(item);
		reply(QString("Done — removed %1.").arg(name));
	}

	void doAdd(obs_scene_t *scene, const QString &text, const QString &lower)
	{
		uint32_t cw = 0, ch = 0;
		canvasSize(cw, ch);

		const Kind *kind = findKind(lower);
		if (!kind) {
			reply("Add what? I can add: webcam, game, display, window, browser, "
			      "mic, text, image, colour, media. Try: add my webcam bottom right.");
			return;
		}

		QString name = kind->name;
		/* Give repeats a different name so OBS doesn't clash. */
		obs_sceneitem_t *clash = obs_scene_find_source(scene, name.toUtf8().constData());
		if (clash) {
			obs_sceneitem_release(clash);
			static int n = 2;
			name = QString("%1 %2").arg(kind->name).arg(n++);
		}

		obs_data_t *settings = obs_data_create();
		QString path = quotedPath(text);
		if (QString(kind->id) == "image_source") {
			if (path.isEmpty()) {
				obs_data_release(settings);
				reply("Which image? Add it like this: add image \"C:\\path\\to\\image.png\"");
				return;
			}
			obs_data_set_string(settings, "file", path.toUtf8().constData());
		} else if (QString(kind->id) == "browser_source") {
			QRegularExpression urlRe("(https?://\\S+)");
			QRegularExpressionMatch m = urlRe.match(text);
			if (m.hasMatch())
				obs_data_set_string(settings, "url", m.captured(1).toUtf8().constData());
			obs_data_set_int(settings, "width", 1280);
			obs_data_set_int(settings, "height", 720);
		} else if (QString(kind->id) == "text_ft2_source") {
			QString words = path.isEmpty() ? QString() : path;
			if (words.isEmpty()) {
				/* text after "add text" */
				int idx = lower.indexOf("text") + 4;
				words = text.mid(idx).trimmed();
				words.remove('"');
			}
			if (words.isEmpty())
				words = "Text";
			obs_data_set_string(settings, "text", words.toUtf8().constData());
		} else if (QString(kind->id) == "ffmpeg_source") {
			if (path.isEmpty()) {
				obs_data_release(settings);
				reply("Which video? Add it like this: add media \"C:\\path\\to\\clip.mp4\"");
				return;
			}
			obs_data_set_string(settings, "local_file", path.toUtf8().constData());
			obs_data_set_bool(settings, "is_local_file", true);
		}

		obs_source_t *src = obs_source_create(kind->id, name.toUtf8().constData(), settings, nullptr);
		obs_data_release(settings);
		if (!src) {
			reply(QString("I couldn't add %1 right now.").arg(kind->name));
			return;
		}
		obs_sceneitem_t *item = obs_scene_add(scene, src);

		/* Size + place it. */
		float w = 0.0f, h = 0.0f;
		itemSize(item, w, h);
		struct vec2 pos = {0.0f, 0.0f};
		QString k = kind->key;
		if (k == "webcam") {
			/* Webcam: a third of the canvas wide, keeps its shape. */
			uint32_t nw = obs_source_get_width(src);
			uint32_t nh = obs_source_get_height(src);
			if (nw > 0 && nh > 0) {
				float targetW = (float)cw / 3.0f;
				struct vec2 scale = {targetW / (float)nw,
						     targetW / (float)nw};
				obs_sceneitem_set_scale(item, &scale);
				w = targetW;
				h = (float)nh * scale.y;
			}
			if (!positionFor(lower, cw, ch, w, h, pos)) {
				pos.x = (float)cw - w;
				pos.y = (float)ch - h; /* bottom right by default */
			}
		} else if (k == "text" || k == "image") {
			/* Shrink big images to fit the canvas. */
			if (w > (float)cw || h > (float)ch) {
				float s = std::min((float)cw / w, (float)ch / h);
				struct vec2 scale = {s, s};
				obs_sceneitem_set_scale(item, &scale);
				w *= s;
				h *= s;
			}
			if (!positionFor(lower, cw, ch, w, h, pos)) {
				pos.x = ((float)cw - w) / 2.0f;
				pos.y = ((float)ch - h) / 2.0f;
			}
		} else if (k == "mic") {
			/* Audio source: no picture on the canvas, it joins the mixer. */
			obs_sceneitem_release(item);
			obs_source_release(src);
			reply(QString("Done — added %1 to the mixer (it has its own slider).").arg(name));
			return;
		} else {
			/* game / display / window / browser / media: full canvas */
			pos.x = 0.0f;
			pos.y = 0.0f;
		}
		obs_sceneitem_set_pos(item, &pos);
		obs_sceneitem_release(item);
		obs_source_release(src);
		reply(QString("Done — added %1.").arg(name));
	}

	void doMove(obs_scene_t *scene, const QString &lower)
	{
		obs_sceneitem_t *item = findItem(scene, lower);
		if (!item) {
			reply("Move what? I couldn't find that on the canvas. Try: move the webcam to top left.");
			return;
		}
		uint32_t cw = 0, ch = 0;
		canvasSize(cw, ch);
		float w = 0.0f, h = 0.0f;
		itemSize(item, w, h);
		struct vec2 pos = {};
		obs_sceneitem_get_pos(item, &pos);
		QString name = sourceName(item);

		if (lower.contains("left") && !lower.contains("bottom") && !lower.contains("top"))
			pos.x -= 50.0f;
		else if (lower.contains("right") && !lower.contains("bottom") && !lower.contains("top"))
			pos.x += 50.0f;
		else if (lower.contains("up"))
			pos.y -= 50.0f;
		else if (lower.contains("down"))
			pos.y += 50.0f;
		else if (!positionFor(lower, cw, ch, w, h, pos)) {
			obs_sceneitem_release(item);
			reply("Move it where? Try: move the webcam to top left, bottom right, or center.");
			return;
		}
		if (pos.x < 0.0f)
			pos.x = 0.0f;
		if (pos.y < 0.0f)
			pos.y = 0.0f;
		if (pos.x > (float)cw - w)
			pos.x = std::max(0.0f, (float)cw - w);
		if (pos.y > (float)ch - h)
			pos.y = std::max(0.0f, (float)ch - h);
		obs_sceneitem_set_pos(item, &pos);
		obs_sceneitem_release(item);
		reply(QString("Done — moved %1.").arg(name));
	}

	void doResize(obs_scene_t *scene, const QString &lower)
	{
		obs_sceneitem_t *item = findItem(scene, lower);
		if (!item) {
			reply("Resize what? I couldn't find that on the canvas. Try: make the game bigger.");
			return;
		}
		uint32_t cw = 0, ch = 0;
		canvasSize(cw, ch);
		QString name = sourceName(item);
		struct vec2 scale = {};
		obs_sceneitem_get_scale(item, &scale);
		if (scale.x <= 0.0f)
			scale.x = 1.0f;
		if (scale.y <= 0.0f)
			scale.y = 1.0f;

		QRegularExpression pctRe("(\\d+)\\s*%");
		QRegularExpressionMatch m = pctRe.match(lower);
		if (m.hasMatch()) {
			/* Resize to a share of the canvas width, keeping shape. */
			obs_source_t *src = obs_sceneitem_get_source(item);
			uint32_t nw = src ? obs_source_get_width(src) : 0;
			if (nw == 0) {
				obs_sceneitem_release(item);
				reply("I can't measure that source yet — try again once it's showing on the canvas.");
				return;
			}
			float targetW = (float)cw * (m.captured(1).toFloat() / 100.0f);
			float s = targetW / (float)nw;
			scale.x = s;
			scale.y = s;
		} else if (lower.contains("bigger") || lower.contains("larger") ||
			   (lower.contains("big") && !lower.contains("small"))) {
			scale.x *= 1.25f;
			scale.y *= 1.25f;
		} else {
			scale.x *= 0.8f;
			scale.y *= 0.8f;
		}
		obs_sceneitem_set_scale(item, &scale);
		obs_sceneitem_release(item);
		reply(QString("Done — resized %1.").arg(name));
	}
};

/* ------------------------------------------------------------------ */
/* Style Chatbox - LEFT side dock. Live style/colour editor for the    */
/* streaming app itself, in real time, as you type, no restart.       */
/* Colours ONLY - it cannot add images (that is the Canvas Chatbox's   */
/* job, on the right). Every part gets its OWN separate colour:        */
/* background, text, buttons, panels, borders, mixer, scenes,         */
/* sources, controls, transitions, titles - each changed on its own,  */
/* never one colour for everything.                                    */
/*                                                                     */
/* Examples: "make the buttons red", "text white",                    */
/* "background dark grey", "mixer green", "reset style".              */
/*                                                                     */
/* How it works: each command builds one Qt stylesheet rule for just   */
/* that part and applies it to the OBS main window live. Rules are     */
/* kept per part, so changing the buttons never touches the text.      */
/* Nothing is sent anywhere, no network, no background thread - the    */
/* only work happens when you type (400 ms after you stop typing) or   */
/* hit Send.                                                           */
/* ------------------------------------------------------------------ */

struct StylePart {
	const char *key; /* word that names the part */
	const char *selector; /* Qt stylesheet, %1 = colour */
};

const StylePart STYLE_PARTS[] = {
	{"background",
	 "QMainWindow { background-color: %1; } QDockWidget { background-color: %1; }"},
	{"button", "QPushButton { background-color: %1; }"},
	{"text",
	 "QLabel, QLineEdit, QComboBox, QPushButton, QCheckBox, QRadioButton, "
	 "QSpinBox, QPlainTextEdit, QTreeWidget, QListWidget { color: %1; }"},
	{"panel", "QDockWidget { background-color: %1; } QFrame { background-color: %1; }"},
	{"border", "QDockWidget, QFrame { border: 1px solid %1; }"},
	{"mixer",
	 "QDockWidget#mixerDock { background-color: %1; } "
	 "QDockWidget#mixerDock QSlider::groove:vertical { background: %1; }"},
	{"scene", "#scenes { background-color: %1; }"},
	{"source", "#sources { background-color: %1; }"},
	{"control", "QDockWidget#controlsDock { background-color: %1; }"},
	{"transition", "QDockWidget#transitionsDock { background-color: %1; }"},
	{"title", "QDockWidget::title { background-color: %1; }"},
	{"header", "QDockWidget::title { background-color: %1; }"},
};

bool styleColourFor(const QString &lower, QString &hex)
{
	/* Hex first: #ff0000 */
	QRegularExpression hexRe("#([0-9a-fA-F]{6})");
	QRegularExpressionMatch hm = hexRe.match(lower);
	if (hm.hasMatch()) {
		hex = "#" + hm.captured(1).toUpper();
		return true;
	}
	/* Two-word shades first so "dark grey" beats "grey". */
	struct Named {
		const char *name;
		const char *hex;
	};
	static const Named NAMES[] = {
		{"dark grey", "#333333"}, {"dark gray", "#333333"},
		{"light grey", "#CCCCCC"}, {"light gray", "#CCCCCC"},
		{"dark red", "#8B0000"}, {"dark green", "#006400"},
		{"dark blue", "#00008B"}, {"light blue", "#ADD8E6"},
		{"light green", "#90EE90"}, {"black", "#000000"},
		{"white", "#FFFFFF"}, {"red", "#FF0000"},
		{"green", "#00FF00"}, {"blue", "#0000FF"},
		{"yellow", "#FFFF00"}, {"purple", "#800080"},
		{"pink", "#FFC0CB"}, {"orange", "#FFA500"},
		{"grey", "#808080"}, {"gray", "#808080"},
		{"cyan", "#00FFFF"}, {"magenta", "#FF00FF"},
		{"brown", "#A52A2A"}, {"gold", "#FFD700"},
		{"silver", "#C0C0C0"}, {"teal", "#008080"},
		{"navy", "#000080"}, {"lime", "#00FF00"},
		{"maroon", "#800000"}, {"olive", "#808000"},
		{"aqua", "#00FFFF"}, {"coral", "#FF7F50"},
		{"salmon", "#FA8072"}, {"beige", "#F5F5DC"},
	};
	for (const Named &n : NAMES) {
		if (lower.contains(n.name)) {
			hex = n.hex;
			return true;
		}
	}
	return false;
}

const StylePart *stylePartFor(const QString &lower)
{
	/* "preview"/"canvas" is not an app part - handled by the caller. */
	for (const StylePart &p : STYLE_PARTS) {
		if (lower.contains(p.key))
			return &p;
	}
	return nullptr;
}

class StyleChatbox : public QWidget {
	/* No Q_OBJECT on purpose: connects use lambdas, so no moc step is needed. */
	QPlainTextEdit *log = nullptr;
	QLineEdit *input = nullptr;
	QTimer *liveTimer = nullptr;
	QMap<QString, QString> rules; /* part key -> stylesheet rule */
	QString lastLive; /* last (part + colour) applied live, to avoid log spam */

public:
	StyleChatbox(QWidget *parent = nullptr) : QWidget(parent)
	{
		QVBoxLayout *layout = new QVBoxLayout(this);
		layout->setContentsMargins(6, 6, 6, 6);

		QLabel *title = new QLabel("Style Chatbox — colours for the app, live as you type", this);
		title->setWordWrap(true);
		layout->addWidget(title);

		log = new QPlainTextEdit(this);
		log->setReadOnly(true);
		log->setMaximumBlockCount(200);
		log->setPlaceholderText("Try: make the buttons red");
		layout->addWidget(log, 1);

		QLabel *hint = new QLabel(
			"Colours only, one part at a time — no images here. "
			"Examples: make the buttons red · text white · background dark grey · "
			"mixer green · scenes blue · reset style",
			this);
		hint->setWordWrap(true);
		layout->addWidget(hint);

		QHBoxLayout *row = new QHBoxLayout();
		input = new QLineEdit(this);
		input->setPlaceholderText("Type a colour change… e.g. make the buttons red");
		row->addWidget(input, 1);
		QPushButton *send = new QPushButton("Send", this);
		row->addWidget(send);
		layout->addLayout(row);

		liveTimer = new QTimer(this);
		liveTimer->setSingleShot(true);
		liveTimer->setInterval(400);
		connect(input, &QLineEdit::textChanged, this, [this]() { liveTimer->start(400); });
		connect(liveTimer, &QTimer::timeout, this, [this]() { tryApplyLive(); });
		connect(send, &QPushButton::clicked, this, [this]() { onSend(); });
		connect(input, &QLineEdit::returnPressed, this, [this]() { onSend(); });

		reply("Hi — I change the app's colours, live, one part at a time. "
		      "Try \"make the buttons red\" or \"text white\". "
		      "Type \"help\" for every part, or \"reset style\" to go back to normal. "
		      "I can't add images — that's the Canvas Chatbox on the right.");
	}

	void reply(const QString &text)
	{
		log->appendPlainText(text);
	}

private:
	void applyRules()
	{
		void *mw = obs_frontend_get_main_window();
		if (!mw)
			return;
		QMainWindow *main = (QMainWindow *)mw;
		QString sheet;
		for (auto it = rules.begin(); it != rules.end(); ++it)
			sheet += it.value() + "\n";
		main->setStyleSheet(sheet);
	}

	/* Parse "part + colour" out of a line. Returns false if it is not a
	 * colour command (help/reset/preview are handled by the caller). */
	bool parse(const QString &lower, const StylePart **partOut, QString &hexOut)
	{
		const StylePart *part = stylePartFor(lower);
		if (!part)
			return false;
		QString hex;
		if (!styleColourFor(lower, hex))
			return false;
		*partOut = part;
		hexOut = hex;
		return true;
	}

	void tryApplyLive()
	{
		QString text = input->text().trimmed();
		if (text.isEmpty())
			return;
		QString lower = text.toLower();
		if (lower.contains("reset") || lower.contains("help") ||
		    lower.contains("preview") || lower.contains("canvas"))
			return;
		const StylePart *part = nullptr;
		QString hex;
		if (!parse(lower, &part, hex))
			return;
		QString key = QString("%1=%2").arg(part->key, hex);
		if (key == lastLive)
			return;
		lastLive = key;
		rules[part->key] = QString(part->selector).arg(hex);
		applyRules();
		log->appendPlainText(QString("Live: %1 → %2").arg(part->key, hex));
	}

	void onSend()
	{
		liveTimer->stop();
		QString text = input->text().trimmed();
		if (text.isEmpty())
			return;
		input->clear();
		lastLive.clear();
		log->appendPlainText(QString("> %1").arg(text));
		QString lower = text.toLower();

		if (lower.contains("help") || lower.contains("what can you do")) {
			reply("One part at a time, colours only:\n"
			      "- background, text, buttons, panels, borders\n"
			      "- mixer, scenes, sources, controls, transitions, titles\n"
			      "Say it like: make the buttons red · text white · background dark grey · "
			      "mixer green · scenes blue · borders yellow.\n"
			      "Colours: black, white, red, green, blue, yellow, purple, pink, orange, "
			      "grey, dark grey, light grey, dark/light red/green/blue, cyan, gold, "
			      "or a hex like #FF0000.\n"
			      "\"reset style\" puts everything back to normal.\n"
			      "The canvas video itself can't be recoloured here — for the stream "
			      "background use the Canvas Chatbox on the right.");
			return;
		}
		if (lower.contains("reset")) {
			rules.clear();
			applyRules();
			reply("Done — all colours reset to normal.");
			return;
		}
		if (lower.contains("preview") || lower.contains("canvas")) {
			reply("The preview shows the canvas video, so I can't recolour it here. "
			      "For the stream background, use the Canvas Chatbox on the right — "
			      "say \"set background to black\" there.");
			return;
		}
		if (lower.contains("everything") || lower.contains(" all ") ||
		    lower.endsWith(" all")) {
			reply("I change one part at a time, never everything at once — "
			      "which part? background, text, buttons, panels, borders, mixer, "
			      "scenes, sources, controls, transitions or titles?");
			return;
		}
		const StylePart *part = nullptr;
		QString hex;
		if (!parse(lower, &part, hex)) {
			reply("I need a part and a colour — try: make the buttons red. "
			      "Parts: background, text, buttons, panels, borders, mixer, scenes, "
			      "sources, controls, transitions, titles. Type \"help\" for colours.");
			return;
		}
		rules[part->key] = QString(part->selector).arg(hex);
		applyRules();
		reply(QString("Done — %1 is now %2.").arg(part->key, hex));
	}
};

} // namespace

static QWidget *chatboxWidget = nullptr;
static QWidget *styleWidget = nullptr;

/* OBS puts plugin docks on the right, floating and hidden, by default.
 * Pin a dock to a side instead: un-float it, move it to the area, show it.
 * First run only - after that OBS remembers where the user put the dock. */
static void placeDock(const char *id, Qt::DockWidgetArea area)
{
	void *mw = obs_frontend_get_main_window();
	if (!mw)
		return;
	QMainWindow *main = (QMainWindow *)mw;
	QDockWidget *dock = main->findChild<QDockWidget *>(QString::fromUtf8(id));
	if (!dock)
		return;
	dock->setFloating(false);
	main->addDockWidget(area, dock);
	dock->setVisible(true);
}

bool obs_module_load(void)
{
	/* Canvas Chatbox: docked BESIDE the canvas on the RIGHT, in the OBS
	 * dock area - never on top of the canvas and never inside the scene. */
	chatboxWidget = new CanvasChatbox();
	if (!obs_frontend_add_dock_by_id("canvas-chatbox", "Canvas Chatbox",
					 (void *)chatboxWidget)) {
		blog(LOG_WARNING, "Canvas Chatbox: could not add the dock beside the canvas");
		delete chatboxWidget;
		chatboxWidget = nullptr;
		return false;
	}
	placeDock("canvas-chatbox", Qt::RightDockWidgetArea);

	/* Style Chatbox: docked on the LEFT side, live app colours only. */
	styleWidget = new StyleChatbox();
	if (!obs_frontend_add_dock_by_id("style-chatbox", "Style Chatbox",
					 (void *)styleWidget)) {
		blog(LOG_WARNING, "Style Chatbox: could not add the dock on the left");
		delete styleWidget;
		styleWidget = nullptr;
	} else {
		placeDock("style-chatbox", Qt::LeftDockWidgetArea);
	}
	blog(LOG_INFO, "Canvas Chatbox loaded (right of canvas) + Style Chatbox loaded (left side)");
	return true;
}

void obs_module_unload(void)
{
	/* The docks own the widgets once they are added; nothing to free here. */
	chatboxWidget = nullptr;
	styleWidget = nullptr;
}
