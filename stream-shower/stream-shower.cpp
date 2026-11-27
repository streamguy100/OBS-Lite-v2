/* Stream Shower + Browser Watcher - OBS Toggle
 *
 * Two parts that work as one:
 *
 * 1) "Stream Shower" source. Add it to a scene and it shows a Twitch
 *    or Kick stream fullscreen, no chat panel, in the stream itself.
 *    You put in up to 10 links, in order, and a timer per link
 *    (default 10 minutes). It plays link 1, then auto-switches to
 *    link 2, and so on, then loops back to link 1. A link can ONLY
 *    be twitch.tv/<streamer name> or kick.com/<streamer name>
 *    (v4, 2026-11-26 — like a Browser Source, but locked to those
 *    two: any other link, site or format is rejected and does not
 *    load), or just a channel name (kaicenat) - plain names use the
 *    default platform picked in the properties.
 *
 * 2) "Stream Watcher" pop-out window (v4, 2026-11-26: was a dock,
 *    top left — now a separate window, still inside OBS). Open it
 *    from Tools > Stream Watcher, or the "Open Stream Watcher"
 *    button in the source properties. It shows the EXACT same stream
 *    the source is showing, at the same time, so you can watch it
 *    while you stream. When the source auto-switches, the window
 *    switches with it. It also has Prev / Next buttons, and a
 *    countdown showing which link is playing and when it switches.
 *    Closing the window only hides it — its 1-second timer keeps
 *    running, so the source keeps auto-switching while it is closed.
 *
 * Extras (sir asked for all five):
 *   - Skip if offline: the next link is checked before it plays; if
 *     it is offline the shower skips it and plays the next live one.
 *     Checks use the OFFICIAL APIs only — Kick's public
 *     api/v2/channels (no login) and Twitch Helix /streams (needs a
 *     Twitch Client ID + token in the source properties). No page
 *     scraping. A link whose live status cannot be checked is never
 *     skipped on a guess.
 *   - Offline-screen watch (sir, 2026-11-25): the Watcher window also
 *     watches the player IT is showing for the official Twitch /
 *     Kick offline screen, and when that screen shows, it triggers
 *     the same skip. This is the path that works WITHOUT Helix
 *     credentials: a Twitch link with no credentials can still be
 *     skipped once its offline screen is actually seen. The probe
 *     is DOM / JS inside the Watcher window's own player page — it looks for
 *     the offline text AND for the absence of a playing <video>,
 *     and reports back by setting document.title (the only return
 *     channel the OBS browser-panel API gives: executeJavaScript is
 *     fire-and-forget, titleChanged is the signal). The offline
 *     screen must be present for ~3 seconds straight before it
 *     skips, so a brief buffering / loading screen never
 *     false-triggers. Either trigger (API says offline OR offline
 *     screen seen) causes the same skip.
 *   - Next / Previous buttons in the dock.
 *   - Countdown in the dock (link number + channel + time left).
 *   - Channel name only (see above).
 *   - Saved lists: save more than one Top 10 list (e.g. a GTA list
 *     and a main list) and switch between them without retyping.
 *
 * Safe versions (sir, 2026-11-24):
 *   - The Shower source is MUTED by default — other streams' audio
 *     never goes out to viewers unless sir turns on "Play audio from
 *     the current stream", which unmutes only the link playing now.
 *     The Watcher window (his own monitoring) is not muted.
 *   - Auto-switch happens ONLY on sir's timer, and only to a link
 *     already checked live. It never auto-plays a stream the second
 *     it goes live, and never jumps to an unchecked link.
 *   - The source properties carry a note: only show streams you have
 *     permission to rebroadcast / co-stream with.
 *
 * How it works: the source owns a private child browser_source (the
 * same trick OBS's own Stinger transition uses for its video file)
 * and renders it fullscreen. The dock is a CEF browser widget from
 * OBS's own browser-panels API (the same API OBS's BrowserDock uses),
 * pointed at the same player URL. One shared playlist state drives
 * both, and the Watcher window's 1-second timer is the switcher: it counts
 * down, switches, and re-checks offline status. The dock timer runs
 * even when the dock is hidden, so switching works while streaming.
 *
 * Honest limits:
 *   - Twitch / Kick players are the official embeds
 *     (player.twitch.tv, player.kick.com). Twitch embeds need a
 *     "parent" host; this build uses parent=localhost, which is the
 *     standard OBS browser-source value. If Twitch ever shows a
 *     "refused to connect" page, that is the embed parent check, not
 *     the shower.
 *   - Offline detection uses official APIs only. Kick's public
 *     api/v2/channels needs no login. Twitch Helix needs a Client ID
 *     + access token (paste them in the source properties; get them
 *     from dev.twitch.tv) — without them, Twitch links cannot be
 *     checked, so they are treated as "check unavailable": they
 *     still play on sir's timer, they are just never auto-skipped
 *     by the API path. The OFFLINE-SCREEN watch is the path that
 *     works without credentials: it watches the dock's own player
 *     for the official Twitch / Kick offline screen and skips when
 *     it is seen for ~3 seconds straight. It watches the Watcher
 *     dock's player (same URL as the source's private browser) —
 *     the source's private browser_source has no JS API OBS exposes
 *     to a plugin, so the dock is the only place the page can be
 *     probed. If Twitch / Kick change their offline screen layout
 *     or wording, the probe's text match may need updating; the API
 *     check keeps working regardless. If OBS / CEF throttles the
 *     dock while it is hidden, the screen watch may be delayed —
 *     the API check still runs on its own timer.
 *     Login-gated / subscriber-only streams need the user signed in
 *     inside OBS's browser (cookies are shared with the CEF browser,
 *     same as any Browser Source).
 *   - One Stream Shower source per scene collection is the supported
 *     setup: the window follows the most recently created source.
 */

#include <obs-module.h>
#include <obs-frontend-api.h>

#include <browser-panel.hpp>

#include <QWidget>
#include <QMainWindow>
#include <QTimer>
#include <QDateTime>
#include <QLabel>
#include <QPushButton>
#include <QHBoxLayout>
#include <QVBoxLayout>
#include <QCloseEvent>
#include <QNetworkAccessManager>
#include <QNetworkRequest>
#include <QNetworkReply>

#include <algorithm>
#include <cstring>
#include <map>
#include <mutex>
#include <string>
#include <vector>

OBS_DECLARE_MODULE()
OBS_MODULE_USE_DEFAULT_LOCALE("stream-shower", "en-US")

namespace {

const int MAX_LINKS = 10;
const int DEFAULT_MINUTES = 10;
const int SHOWER_WIDTH = 1920;
const int SHOWER_HEIGHT = 1080;

/* ------------------------------------------------------------------ */
/* Shared playlist state (source + dock read/write this, under lock)   */
/* ------------------------------------------------------------------ */

struct ShowerEntry {
	QString platform; /* "twitch" or "kick" */
	QString channel;
	QString url; /* full link as typed, for display */
	int minutes = DEFAULT_MINUTES;
};

struct LiveCache {
	/* UNKNOWN: never checked. LIVE / OFFLINE: definite official-API
	 * result. NO_CHECK: this link cannot be checked (Twitch without
	 * Helix credentials) — it is never auto-skipped, it just plays
	 * on the timer. */
	enum class Status { UNKNOWN, LIVE, OFFLINE, NO_CHECK };
	Status status = Status::UNKNOWN;
	qint64 checkedMs = 0;
};

struct ShowerState {
	std::mutex mutex;
	std::vector<ShowerEntry> entries;
	int current = 0;
	double elapsed = 0.0; /* seconds on the current link */
	bool needsApply = false; /* URL changed, dock must push it */
	bool audioOn = false; /* false = Shower muted (default) */
	bool screenWatch = true; /* watch the dock player for the official offline screen */
	QString twitchClientId; /* optional, for Helix live checks */
	QString twitchToken; /* optional, for Helix live checks */
	std::map<QString, LiveCache> liveCache; /* "twitch:name" -> result */
	obs_weak_source_t *browserWeak = nullptr; /* child browser source */
};

static ShowerState g_state;

/* The Stream Watcher pop-out window lives below; the source
 * properties button calls this to open it. */
void openWatcherWindow();

/* Offline-screen probe (DOM / JS, run inside the Watcher dock's
 * player page — the window and the source show the same player URL).
 *
 * Why this route: the OBS browser-panel API gives executeJavaScript
 * (fire-and-forget, no return value) and a titleChanged signal, and
 * nothing else. So the probe reports back by setting document.title
 * to "SHOWER:<state>:<n>", with a counter so the title changes on
 * every probe and titleChanged fires every time. The dock parses it.
 *
 * Detection is two signals at once, so neither alone can lie:
 *   - the page text contains "offline" (the official Twitch / Kick
 *     offline screen says the channel is offline), AND
 *   - there is NO playing <video> (readyState >= 2, currentTime > 0,
 *     not paused, not ended).
 * A live stream has a playing video, so it reads LIVE even if the
 * word "offline" appears somewhere in the page text. A loading /
 * buffering stream has no playing video yet but also no offline
 * text, so it reads UNKNOWN — never a skip. Only offline-text AND
 * no playing video reads OFFLINE. The dock debounces that for ~3
 * seconds before it skips. */
static const char *kOfflineProbeJs = R"JS(
(function(){
  // Probe reports document.title as SHOWER:OFFLINE:<n>, SHOWER:LIVE:<n> or SHOWER:UNKNOWN:<n>
  try{
    var txt = (document.body ? document.body.innerText : '') || '';
    var off = /offline/i.test(txt);
    var live = false;
    var vs = document.querySelectorAll('video');
    for (var i = 0; i < vs.length; i++) {
      var v = vs[i];
      if (v && v.readyState >= 2 && v.currentTime > 0 && !v.paused && !v.ended) { live = true; break; }
    }
    var state = (!live && off) ? 'OFFLINE' : (live ? 'LIVE' : 'UNKNOWN');
    window.__showerProbeN = (window.__showerProbeN || 0) + 1;
    document.title = 'SHOWER:' + state + ':' + window.__showerProbeN;
  }catch(e){}
})();
)JS";

const int SCREEN_OFFLINE_DEBOUNCE_TICKS = 3; /* ~3 seconds at the 1s dock tick */

QString cacheKey(const ShowerEntry &e)
{
	return e.platform + ":" + e.channel.toLower();
}

/* Can this entry's live status be checked at all? Kick: yes, public
 * API. Twitch: only with Helix credentials in the properties.
 * The Locked version assumes g_state.mutex is already held (calling
 * the locking version from inside advanceToNext would deadlock). */
bool entryCanCheckLocked(const ShowerEntry &e)
{
	if (e.platform == "kick")
		return true;
	return !g_state.twitchClientId.isEmpty() && !g_state.twitchToken.isEmpty();
}

bool entryCanCheck(const ShowerEntry &e)
{
	std::lock_guard<std::mutex> lock(g_state.mutex);
	return entryCanCheckLocked(e);
}

/* Display / skip-if-offline helper: true unless a FRESH check said
 * offline. Unknown or uncheckable = live (never skip on a guess). */
bool entryIsLive(const ShowerEntry &e)
{
	std::lock_guard<std::mutex> lock(g_state.mutex);
	auto it = g_state.liveCache.find(cacheKey(e));
	if (it == g_state.liveCache.end())
		return true;
	qint64 now = QDateTime::currentMSecsSinceEpoch();
	if (now - it->second.checkedMs > 120000)
		return true;
	return it->second.status != LiveCache::Status::OFFLINE;
}

/* Parse one typed link into platform + channel. STRICT (v4):
 * ONLY twitch.tv/<name> or kick.com/<name> are accepted as links,
 * plus the matching official embed forms (player.twitch.tv/?channel=
 * and player.kick.com/<name>), plus a plain channel name. ANY other
 * URL / domain / format (youtube.com, twitch.tv/videos/..., a clip
 * link, a link with an extra path after the name, a link to any other
 * site) is REJECTED and returns false — the link is skipped and never
 * loads. Plain names use the default platform. Returns false for an
 * empty / unusable / rejected link. */
static bool validChannelName(const QString &c)
{
	/* Twitch / Kick names: letters, digits, underscore, 1-25 chars. */
	if (c.isEmpty() || c.size() > 25)
		return false;
	for (QChar ch : c) {
		if (!ch.isLetterOrNumber() && ch != '_')
			return false;
	}
	return true;
}

/* One path segment after a host, e.g. "kaicenat" from
 * "twitch.tv/kaicenat" (trailing slash / ?query allowed). Empty if
 * there is no segment, or more than one segment (e.g. videos/123). */
static QString singlePathSegment(QString rest)
{
	int cut = rest.indexOf('?');
	if (cut >= 0)
		rest = rest.left(cut);
	cut = rest.indexOf('#');
	if (cut >= 0)
		rest = rest.left(cut);
	/* Embed URLs carry extra params after the name
	 * (?channel=name&parent=...), so cut at '&' too. */
	cut = rest.indexOf('&');
	if (cut >= 0)
		rest = rest.left(cut);
	while (rest.endsWith('/'))
		rest.chop(1);
	if (rest.isEmpty() || rest.contains('/'))
		return QString();
	return rest.trimmed();
}

bool parseEntry(const QString &raw, const QString &defaultPlatform, ShowerEntry &out)
{
	QString text = raw.trimmed();
	if (text.isEmpty())
		return false;
	QString lower = text.toLower();
	out.url = text;
	out.minutes = DEFAULT_MINUTES;

	/* Strip scheme + www. so twitch.tv/name, https://twitch.tv/name
	 * and www.twitch.tv/name all match the same way. */
	QString noScheme = lower;
	if (noScheme.startsWith("https://"))
		noScheme = noScheme.mid(8);
	else if (noScheme.startsWith("http://"))
		noScheme = noScheme.mid(7);
	if (noScheme.startsWith("www."))
		noScheme = noScheme.mid(4);

	if (noScheme.startsWith("twitch.tv/")) {
		out.platform = "twitch";
		out.channel = singlePathSegment(noScheme.mid(10));
	} else if (noScheme.startsWith("kick.com/")) {
		out.platform = "kick";
		out.channel = singlePathSegment(noScheme.mid(9));
	} else if (noScheme.startsWith("player.twitch.tv/") || noScheme.startsWith("player.twitch.tv?")) {
		/* Official Twitch embed: ...?channel=name */
		out.platform = "twitch";
		int idx = noScheme.indexOf("channel=");
		if (idx < 0)
			return false;
		out.channel = singlePathSegment(noScheme.mid(idx + 8));
	} else if (noScheme.startsWith("player.kick.com/")) {
		out.platform = "kick";
		out.channel = singlePathSegment(noScheme.mid(16));
	} else if (noScheme.startsWith("twitch.tv") || noScheme.startsWith("kick.com") ||
		   noScheme.contains("://") || noScheme.contains('.') || noScheme.contains('/')) {
		/* Looks like a link, but not twitch.tv/<name> or
		 * kick.com/<name> — rejected. This is the v4 lock: no
		 * other site, no videos/clips page, no extra path. */
		return false;
	} else {
		/* Plain channel name (or @name). */
		out.platform = defaultPlatform.isEmpty() ? "twitch" : defaultPlatform;
		out.channel = text;
		if (out.channel.startsWith('@'))
			out.channel = out.channel.mid(1);
		out.channel = out.channel.trimmed();
	}
	out.channel = out.channel.trimmed();
	if (!validChannelName(out.channel))
		return false;
	return true;
}

QString playerUrl(const ShowerEntry &e, bool muted)
{
	if (e.platform == "kick")
		return QString("https://player.kick.com/%1%2")
			.arg(e.channel, muted ? "?muted=true" : "?muted=false");
	/* Twitch embed. parent=localhost is the standard OBS value. */
	return QString("https://player.twitch.tv/?channel=%1&parent=localhost&autoplay=true&muted=%2")
		.arg(e.channel, muted ? "true" : "false");
}

QString displayName(const ShowerEntry &e)
{
	return QString("%1 (%2)").arg(e.channel, e.platform);
}

/* Push the current entry's URL into the child browser source. Runs on
 * the UI thread (dock timer / source update). The source is MUTED by
 * default (audioOn=false): the player URL is muted AND the source
 * volume is 0, so other streams' audio never goes out to viewers
 * unless sir turns "Play audio from the current stream" on. */
void applyUrlToBrowser()
{
	obs_weak_source_t *weak = nullptr;
	bool audioOn = false;
	{
		std::lock_guard<std::mutex> lock(g_state.mutex);
		weak = g_state.browserWeak;
		audioOn = g_state.audioOn;
		g_state.needsApply = false;
	}
	if (!weak)
		return;
	obs_source_t *browser = obs_weak_source_get_source(weak);
	if (!browser)
		return;
	ShowerEntry entry;
	{
		std::lock_guard<std::mutex> lock(g_state.mutex);
		if (g_state.entries.empty() || g_state.current < 0 ||
		    g_state.current >= (int)g_state.entries.size()) {
			obs_source_release(browser);
			return;
		}
		entry = g_state.entries[(size_t)g_state.current];
	}
	obs_data_t *settings = obs_source_get_settings(browser);
	obs_data_set_string(settings, "url", playerUrl(entry, !audioOn).toUtf8().constData());
	obs_data_set_int(settings, "width", SHOWER_WIDTH);
	obs_data_set_int(settings, "height", SHOWER_HEIGHT);
	obs_source_update(browser, settings);
	obs_data_release(settings);
	obs_source_set_volume(browser, audioOn ? 1.0f : 0.0f);
	obs_source_release(browser);
}

/* Advance to the next entry in order. Auto-switch only lands on a
 * link already checked LIVE (fresh official-API result), or on a link
 * that cannot be checked at all (Twitch without Helix credentials —
 * it just plays on the timer). An unchecked-but-checkable link is
 * skipped this time: the dock checks upcoming links every 30s, so it
 * is eligible on the next loop. It never auto-plays a stream the
 * second it goes live — switching happens only on sir's timer, to a
 * link already verified live. If every other entry is ineligible,
 * stay put rather than looping on offline screens. */
void advanceToNext()
{
	std::lock_guard<std::mutex> lock(g_state.mutex);
	if (g_state.entries.empty())
		return;
	int n = (int)g_state.entries.size();
	qint64 now = QDateTime::currentMSecsSinceEpoch();
	for (int step = 1; step <= n; step++) {
		int idx = (g_state.current + step) % n;
		const ShowerEntry &cand = g_state.entries[(size_t)idx];
		bool eligible = false;
		auto it = g_state.liveCache.find(cacheKey(cand));
		if (it != g_state.liveCache.end() && now - it->second.checkedMs <= 120000) {
			eligible = it->second.status == LiveCache::Status::LIVE ||
				   it->second.status == LiveCache::Status::NO_CHECK;
		} else {
			/* Never checked, or stale: only eligible if it
			 * cannot be checked at all. */
			eligible = !entryCanCheckLocked(cand);
		}
		if (eligible || step == n) {
			g_state.current = idx;
			g_state.elapsed = 0.0;
			g_state.needsApply = true;
			return;
		}
	}
}

void jumpTo(int idx)
{
	std::lock_guard<std::mutex> lock(g_state.mutex);
	if (g_state.entries.empty())
		return;
	int n = (int)g_state.entries.size();
	idx = ((idx % n) + n) % n;
	g_state.current = idx;
	g_state.elapsed = 0.0;
	g_state.needsApply = true;
}

/* ------------------------------------------------------------------ */
/* Saved lists (stored in the source settings as an obs_data_array)    */
/* ------------------------------------------------------------------ */

void readSlots(obs_data_t *settings, std::vector<ShowerEntry> &entries, QString &defPlatform)
{
	const char *dp = obs_data_get_string(settings, "default_platform");
	defPlatform = dp ? QString::fromUtf8(dp) : "twitch";
	if (defPlatform != "kick")
		defPlatform = "twitch";
	entries.clear();
	for (int i = 1; i <= MAX_LINKS; i++) {
		QString linkKey = QString("link%1").arg(i);
		QString minKey = QString("minutes%1").arg(i);
		const char *raw = obs_data_get_string(settings, linkKey.toUtf8().constData());
		ShowerEntry e;
		if (!raw || !parseEntry(QString::fromUtf8(raw), defPlatform, e))
			continue;
		long long mins = obs_data_get_int(settings, minKey.toUtf8().constData());
		e.minutes = (int)std::max<long long>(1, std::min<long long>(180, mins > 0 ? mins : DEFAULT_MINUTES));
		e.url = QString::fromUtf8(raw);
		entries.push_back(e);
	}
}

void writeSlots(obs_data_t *settings, const std::vector<ShowerEntry> &entries)
{
	for (int i = 1; i <= MAX_LINKS; i++) {
		QString linkKey = QString("link%1").arg(i);
		QString minKey = QString("minutes%1").arg(i);
		if (i <= (int)entries.size()) {
			obs_data_set_string(settings, linkKey.toUtf8().constData(),
					    entries[(size_t)i - 1].url.toUtf8().constData());
			obs_data_set_int(settings, minKey.toUtf8().constData(),
					 entries[(size_t)i - 1].minutes);
		} else {
			obs_data_set_string(settings, linkKey.toUtf8().constData(), "");
			obs_data_set_int(settings, minKey.toUtf8().constData(), DEFAULT_MINUTES);
		}
	}
}

} // namespace

namespace {

/* ------------------------------------------------------------------ */
/* Stream Shower source                                              */
/* ------------------------------------------------------------------ */

struct ShowerData {
	obs_source_t *source = nullptr;
	obs_source_t *browser = nullptr; /* private child browser_source */
};

void showerApplySettings(ShowerData *d, obs_data_t *settings)
{
	std::vector<ShowerEntry> entries;
	QString defPlatform;
	readSlots(settings, entries, defPlatform);
	const char *cid = obs_data_get_string(settings, "twitch_client_id");
	const char *tok = obs_data_get_string(settings, "twitch_token");
	bool audioOn = obs_data_get_bool(settings, "audio_on");
	bool screenWatch = obs_data_get_bool(settings, "screen_watch");
	{
		std::lock_guard<std::mutex> lock(g_state.mutex);
		g_state.entries = entries;
		g_state.audioOn = audioOn;
		g_state.screenWatch = screenWatch;
		g_state.twitchClientId = cid ? QString::fromUtf8(cid) : QString();
		g_state.twitchToken = tok ? QString::fromUtf8(tok) : QString();
		if (g_state.current >= (int)g_state.entries.size())
			g_state.current = 0;
		if (g_state.entries.empty())
			g_state.current = 0;
		g_state.elapsed = 0.0;
		g_state.needsApply = true;
	}
	if (d->browser)
		applyUrlToBrowser();
}

static const char *shower_get_name(void *)
{
	return "Stream Shower (Twitch / Kick)";
}

static void *shower_create(obs_data_t *settings, obs_source_t *source)
{
	ShowerData *d = new ShowerData();
	d->source = source;

	/* Private child browser source, same trick as OBS's Stinger
	 * transition uses for its video file: created, never added to a
	 * scene, rendered by the parent. */
	obs_data_t *bsettings = obs_data_create();
	obs_data_set_string(bsettings, "url", "https://player.twitch.tv/?channel=kaicenat&parent=localhost&autoplay=true&muted=true");
	obs_data_set_int(bsettings, "width", SHOWER_WIDTH);
	obs_data_set_int(bsettings, "height", SHOWER_HEIGHT);
	obs_data_set_int(bsettings, "fps", 30);
	obs_data_set_bool(bsettings, "fps_custom", true);
	obs_data_set_bool(bsettings, "shutdown", false);
	d->browser = obs_source_create_private("browser_source", "Stream Shower (internal browser)",
					       bsettings);
	obs_data_release(bsettings);

	{
		std::lock_guard<std::mutex> lock(g_state.mutex);
		if (g_state.browserWeak)
			obs_weak_source_release(g_state.browserWeak);
		g_state.browserWeak = d->browser ? obs_source_get_weak_source(d->browser) : nullptr;
	}
	showerApplySettings(d, settings);
	blog(LOG_INFO, "Stream Shower: source created");
	return d;
}

static void shower_destroy(void *data)
{
	ShowerData *d = (ShowerData *)data;
	{
		std::lock_guard<std::mutex> lock(g_state.mutex);
		if (g_state.browserWeak) {
			obs_weak_source_release(g_state.browserWeak);
			g_state.browserWeak = nullptr;
		}
		g_state.entries.clear();
		g_state.current = 0;
		g_state.elapsed = 0.0;
	}
	if (d->browser)
		obs_source_release(d->browser);
	delete d;
}

static uint32_t shower_get_width(void *)
{
	return SHOWER_WIDTH;
}

static uint32_t shower_get_height(void *)
{
	return SHOWER_HEIGHT;
}

static void shower_update(void *data, obs_data_t *settings)
{
	showerApplySettings((ShowerData *)data, settings);
}

static void shower_get_defaults(obs_data_t *settings)
{
	for (int i = 1; i <= MAX_LINKS; i++) {
		QString minKey = QString("minutes%1").arg(i);
		obs_data_set_default_int(settings, minKey.toUtf8().constData(), DEFAULT_MINUTES);
	}
	obs_data_set_default_string(settings, "default_platform", "twitch");
	/* Muted by default: other streams' audio never goes out to
	 * viewers unless sir turns "Play audio from the current stream" on. */
	obs_data_set_default_bool(settings, "audio_on", false);
	/* Offline-screen watch on by default: it is the skip path that
	 * works without Twitch Helix credentials. */
	obs_data_set_default_bool(settings, "screen_watch", true);
}

static void shower_video_render(void *data, gs_effect_t *)
{
	ShowerData *d = (ShowerData *)data;
	if (d->browser)
		obs_source_video_render(d->browser);
}

/* --- saved lists: load a saved list into the 10 slots --- */
static bool savedListChanged(void *priv, obs_properties_t *, obs_property_t *, obs_data_t *settings)
{
	ShowerData *d = (ShowerData *)priv;
	(void)d;
	const char *name = obs_data_get_string(settings, "saved_list");
	if (!name || !*name)
		return false;
	obs_data_array_t *arr = obs_data_get_array(settings, "saved_lists");
	if (!arr)
		return false;
	size_t count = obs_data_array_count(arr);
	for (size_t i = 0; i < count; i++) {
		obs_data_t *item = obs_data_array_item(arr, i);
		if (!item)
			continue;
		const char *itemName = obs_data_get_string(item, "name");
		if (itemName && strcmp(itemName, name) == 0) {
			std::vector<ShowerEntry> entries;
			for (int s = 1; s <= MAX_LINKS; s++) {
				QString linkKey = QString("link%1").arg(s);
				QString minKey = QString("minutes%1").arg(s);
				const char *raw = obs_data_get_string(item, linkKey.toUtf8().constData());
				if (raw && *raw) {
					ShowerEntry e;
					e.url = QString::fromUtf8(raw);
					e.minutes = (int)obs_data_get_int(item, minKey.toUtf8().constData());
					if (e.minutes <= 0)
						e.minutes = DEFAULT_MINUTES;
					entries.push_back(e);
				}
			}
			writeSlots(settings, entries);
			obs_data_release(item);
			obs_data_array_release(arr);
			return true; /* refresh the properties dialog */
		}
		obs_data_release(item);
	}
	obs_data_array_release(arr);
	return false;
}

static bool saveListClicked(obs_properties_t *, obs_property_t *, void *priv)
{
	ShowerData *d = (ShowerData *)priv;
	if (!d || !d->source)
		return false;
	obs_data_t *settings = obs_source_get_settings(d->source);
	const char *name = obs_data_get_string(settings, "list_name");
	QString listName = (name && *name) ? QString::fromUtf8(name) : QString();
	std::vector<ShowerEntry> entries;
	QString defPlatform;
	readSlots(settings, entries, defPlatform);
	if (entries.empty()) {
		obs_data_release(settings);
		return false;
	}
	obs_data_array_t *arr = obs_data_get_array(settings, "saved_lists");
	if (!arr)
		arr = obs_data_array_create();
	/* Replace a list with the same name, or append a new one. */
	bool replaced = false;
	size_t count = obs_data_array_count(arr);
	for (size_t i = 0; i < count; i++) {
		obs_data_t *item = obs_data_array_item(arr, i);
		if (!item)
			continue;
		const char *itemName = obs_data_get_string(item, "name");
		if (listName.isEmpty()) {
			/* No name typed: replace the first list, or fall
			 * through to append below. */
			obs_data_release(item);
			continue;
		}
		if (itemName && listName == QString::fromUtf8(itemName)) {
			obs_data_t *fresh = obs_data_create();
			obs_data_set_string(fresh, "name", listName.toUtf8().constData());
			for (int s = 1; s <= MAX_LINKS; s++) {
				QString linkKey = QString("link%1").arg(s);
				QString minKey = QString("minutes%1").arg(s);
				const char *raw = obs_data_get_string(settings, linkKey.toUtf8().constData());
				obs_data_set_string(fresh, linkKey.toUtf8().constData(), raw ? raw : "");
				obs_data_set_int(fresh, minKey.toUtf8().constData(),
						 obs_data_get_int(settings, minKey.toUtf8().constData()));
			}
			obs_data_array_erase(arr, i);
			obs_data_array_insert(arr, i, fresh);
			obs_data_release(fresh);
			replaced = true;
			obs_data_release(item);
			break;
		}
		obs_data_release(item);
	}
	if (!replaced) {
		if (listName.isEmpty())
			listName = QString("List %1").arg(count + 1);
		obs_data_t *fresh = obs_data_create();
		obs_data_set_string(fresh, "name", listName.toUtf8().constData());
		for (int s = 1; s <= MAX_LINKS; s++) {
			QString linkKey = QString("link%1").arg(s);
			QString minKey = QString("minutes%1").arg(s);
			const char *raw = obs_data_get_string(settings, linkKey.toUtf8().constData());
			obs_data_set_string(fresh, linkKey.toUtf8().constData(), raw ? raw : "");
			obs_data_set_int(fresh, minKey.toUtf8().constData(),
					 obs_data_get_int(settings, minKey.toUtf8().constData()));
		}
		obs_data_array_push_back(arr, fresh);
		obs_data_release(fresh);
	}
	obs_data_set_array(settings, "saved_lists", arr);
	obs_data_array_release(arr);
	obs_data_set_string(settings, "saved_list", listName.toUtf8().constData());
	obs_source_update(d->source, settings);
	obs_data_release(settings);
	blog(LOG_INFO, "Stream Shower: saved list '%s'", listName.toUtf8().constData());
	return true;
}

static bool deleteListClicked(obs_properties_t *, obs_property_t *, void *priv)
{
	ShowerData *d = (ShowerData *)priv;
	if (!d || !d->source)
		return false;
	obs_data_t *settings = obs_source_get_settings(d->source);
	const char *name = obs_data_get_string(settings, "list_name");
	if (!name || !*name) {
		obs_data_release(settings);
		return false;
	}
	obs_data_array_t *arr = obs_data_get_array(settings, "saved_lists");
	if (!arr) {
		obs_data_release(settings);
		return false;
	}
	size_t count = obs_data_array_count(arr);
	for (size_t i = 0; i < count; i++) {
		obs_data_t *item = obs_data_array_item(arr, i);
		if (!item)
			continue;
		const char *itemName = obs_data_get_string(item, "name");
		bool match = itemName && strcmp(itemName, name) == 0;
		obs_data_release(item);
		if (match) {
			obs_data_array_erase(arr, i);
			break;
		}
	}
	obs_data_set_array(settings, "saved_lists", arr);
	obs_data_array_release(arr);
	obs_data_set_string(settings, "saved_list", "");
	obs_source_update(d->source, settings);
	obs_data_release(settings);
	return true;
}

static bool openWatcherClicked(obs_properties_t *, obs_property_t *, void *)
{
	openWatcherWindow();
	return true;
}

static obs_properties_t *shower_get_properties(void *data)
{
	ShowerData *d = (ShowerData *)data;
	obs_properties_t *props = obs_properties_create();
	obs_properties_set_flags(props, OBS_PROPERTIES_DEFER_UPDATE);

	obs_property_t *info = obs_properties_add_text(
		props, "info", "Stream Shower — up to 10 links, in order. "
			       "ONLY twitch.tv/<streamer name> or kick.com/<streamer name> "
			       "are accepted — like a Browser Source, but locked to "
			       "those two. Any other link, site or format is rejected "
			       "and will not play. Or just type a channel name "
			       "(kaicenat). Empty links are skipped. "
			       "Only show streams you have permission to rebroadcast / "
			       "co-stream with. The Shower is MUTED by default — turn on "
			       "'Play audio from the current stream' below to unmute only "
			       "the link playing now. 'Watch for the offline screen' "
			       "below also skips a link when the official Twitch / Kick "
			       "offline screen shows for ~3 seconds — that is the skip "
			       "that works even without Twitch Helix credentials. "
			       "Open the Stream Watcher window from Tools > Stream "
			       "Watcher, or the button below.",
		OBS_TEXT_INFO);
	(void)info;

	obs_properties_add_button2(props, "open_watcher", "Open Stream Watcher",
				   openWatcherClicked, d);

	obs_properties_add_bool(props, "screen_watch",
				"Watch for the offline screen (skip when the official Twitch / Kick offline screen shows for ~3 seconds)");

	obs_properties_add_bool(props, "audio_on",
				"Play audio from the current stream (unmute this link only — off = muted)");

	obs_properties_add_text(props, "twitch_client_id",
				"Twitch Client ID (optional — for Helix live checks, from dev.twitch.tv)",
				OBS_TEXT_DEFAULT);
	obs_properties_add_text(props, "twitch_token",
				"Twitch access token (optional — for Helix live checks)",
				OBS_TEXT_PASSWORD);

	for (int i = 1; i <= MAX_LINKS; i++) {
		QString linkKey = QString("link%1").arg(i);
		QString linkLabel = QString("Stream link %1").arg(i);
		obs_properties_add_text(props, linkKey.toUtf8().constData(), linkLabel.toUtf8().constData(),
					OBS_TEXT_DEFAULT);
		QString minKey = QString("minutes%1").arg(i);
		QString minLabel = QString("Minutes on link %1").arg(i);
		obs_properties_add_int(props, minKey.toUtf8().constData(), minLabel.toUtf8().constData(),
				       1, 180, 1);
	}

	obs_property_t *plat = obs_properties_add_list(props, "default_platform",
						       "Default platform for plain channel names",
						       OBS_COMBO_TYPE_LIST, OBS_COMBO_FORMAT_STRING);
	obs_property_list_add_string(plat, "Twitch", "twitch");
	obs_property_list_add_string(plat, "Kick", "kick");

	/* Saved lists. */
	obs_property_t *saved = obs_properties_add_list(props, "saved_list", "Saved list (load one)",
							OBS_COMBO_TYPE_LIST, OBS_COMBO_FORMAT_STRING);
	obs_property_list_add_string(saved, "(none)", "");
	obs_data_t *settings = d && d->source ? obs_source_get_settings(d->source) : nullptr;
	if (settings) {
		obs_data_array_t *arr = obs_data_get_array(settings, "saved_lists");
		if (arr) {
			size_t count = obs_data_array_count(arr);
			for (size_t i = 0; i < count; i++) {
				obs_data_t *item = obs_data_array_item(arr, i);
				if (!item)
					continue;
				const char *itemName = obs_data_get_string(item, "name");
				if (itemName && *itemName)
					obs_property_list_add_string(saved, itemName, itemName);
				obs_data_release(item);
			}
			obs_data_array_release(arr);
		}
		obs_data_release(settings);
	}
	obs_property_set_modified_callback2(saved, savedListChanged, d);

	obs_properties_add_text(props, "list_name", "List name (for Save / Delete)",
				OBS_TEXT_DEFAULT);
	obs_properties_add_button2(props, "save_list", "Save this list", saveListClicked, d);
	obs_properties_add_button2(props, "delete_list", "Delete named list", deleteListClicked, d);

	return props;
}

} // namespace

namespace {

/* ------------------------------------------------------------------ */
/* Stream Watcher pop-out window (v4: was a dock, top left)          */
/* ------------------------------------------------------------------ */
/* A separate top-level window, still inside OBS and still part of
 * this same stream-shower.dll — no separate .exe, no new file. It
 * shows the exact same stream the source is showing, in sync. It is
 * created once at module load and kept HIDDEN: its 1-second timer
 * keeps running while it is hidden, so the source keeps
 * auto-switching (and the offline-screen probe keeps running) even
 * when the window is closed. Closing the window only hides it
 * (closeEvent below); Tools > Stream Watcher or the button in the
 * source properties opens it again. */

class StreamWatcherWindow : public QWidget {
	/* No Q_OBJECT on purpose: connects use lambdas, so no moc step
	 * is needed (same as the chatbox docks). */
	QLabel *status = nullptr;
	QPushButton *prevBtn = nullptr;
	QPushButton *nextBtn = nullptr;
	QTimer *timer = nullptr;
	QNetworkAccessManager *nam = nullptr;
	QCefWidget *web = nullptr;
	QCef *cef = nullptr;
	int tickCount = 0;
	/* Offline-screen watch state: the probe reports back through
	 * document.title ("SHOWER:OFFLINE/LIVE/UNKNOWN:<n>"). Ticks
	 * count consecutive 1-second probes that reported OFFLINE for
	 * the entry named in screenKey; at 3 the dock skips. */
	int screenOfflineTicks = 0;
	QString screenKey; /* "twitch:name" the ticks belong to */

public:
	StreamWatcherWindow(QWidget *parent = nullptr) : QWidget(parent)
	{
		setWindowTitle("Stream Watcher");
		setWindowFlags(Qt::Window);
		resize(960, 640);
		QVBoxLayout *layout = new QVBoxLayout(this);
		layout->setContentsMargins(6, 6, 6, 6);

		status = new QLabel("Stream Watcher — add links in the Stream Shower source properties", this);
		status->setWordWrap(true);
		layout->addWidget(status);

		QHBoxLayout *row = new QHBoxLayout();
		prevBtn = new QPushButton("◀ Prev", this);
		nextBtn = new QPushButton("Next ▶", this);
		row->addWidget(prevBtn);
		row->addWidget(nextBtn);
		layout->addLayout(row);

		/* The video itself: OBS's own CEF browser widget, the same
		 * API OBS's BrowserDock uses. It shows the same player URL
		 * the Stream Shower source is showing. */
		cef = obs_browser_init_panel();
		if (cef) {
			if (!cef->initialized())
				cef->init_browser();
			std::string startUrl;
			{
				std::lock_guard<std::mutex> lock(g_state.mutex);
				if (!g_state.entries.empty())
					startUrl = playerUrl(g_state.entries[(size_t)g_state.current], false)
							   .toStdString();
			}
			if (startUrl.empty())
				startUrl = "https://player.twitch.tv/?channel=kaicenat&parent=localhost&autoplay=true&muted=false";
			web = cef->create_widget(this, startUrl);
			/* Offline-screen probe, two ways in: as the startup
			 * script it runs on every page load, and the 1-second
			 * tick below re-runs it while the stream is playing,
			 * so a stream that goes offline mid-play is caught
			 * without a reload. The probe reports back through
			 * document.title — see onPageTitle(). */
			web->setStartupScript(kOfflineProbeJs);
			connect(web, &QCefWidget::titleChanged, this,
				[this](const QString &title) { onPageTitle(title); });
		}
		if (web) {
			layout->addWidget(web, 1);
		} else {
			QLabel *fallback = new QLabel(
				"Browser view is not available (OBS browser panels are off), "
				"but the Stream Shower source still shows the stream in "
				"your output. Use Prev / Next below to switch links.",
				this);
			fallback->setWordWrap(true);
			layout->addWidget(fallback, 1);
		}

		nam = new QNetworkAccessManager(this);

		timer = new QTimer(this);
		timer->setInterval(1000);
		connect(timer, &QTimer::timeout, this, [this]() { onTick(); });
		connect(prevBtn, &QPushButton::clicked, this, [this]() { onJump(-1); });
		connect(nextBtn, &QPushButton::clicked, this, [this]() { onJump(1); });
		timer->start();
		onTick();
	}

protected:
	/* Closing the window only hides it — the timer (and the
	 * source's auto-switching) must keep running while it is
	 * closed, so the window is never deleted here. */
	void closeEvent(QCloseEvent *event) override
	{
		event->ignore();
		hide();
	}

private:
	void setWebUrl(const QString &url)
	{
		if (web)
			web->setURL(url.toStdString());
	}

	void refreshStatus()
	{
		std::vector<ShowerEntry> entries;
		int current = 0;
		double elapsed = 0.0;
		{
			std::lock_guard<std::mutex> lock(g_state.mutex);
			entries = g_state.entries;
			current = g_state.current;
			elapsed = g_state.elapsed;
		}
		if (entries.empty() || current < 0 || current >= (int)entries.size()) {
			status->setText("Stream Watcher — no streams set. Add links in the "
					"Stream Shower source properties.");
			return;
		}
		const ShowerEntry &e = entries[(size_t)current];
		int total = std::max(1, e.minutes * 60);
		int left = std::max(0, total - (int)elapsed);
		QString liveNote;
		if (!entryIsLive(e))
			liveNote = " — offline, will skip";
		else if (screenOfflineTicks > 0)
			liveNote = QString(" — offline screen seen (%1/3)").arg(screenOfflineTicks);
		status->setText(QString("Now: #%1 %2 — switches in %3:%4%5")
					.arg(current + 1)
					.arg(displayName(e))
					.arg(left / 60)
					.arg(left % 60, 2, 10, QChar('0'))
					.arg(liveNote));
	}

	/* The offline-screen probe reports back through the page title:
	 * "SHOWER:OFFLINE:<n>" / "SHOWER:LIVE:<n>" / "SHOWER:UNKNOWN:<n>".
	 * Anything else is the player's own title — ignore it.
	 * OFFLINE ticks only count while the same entry is still playing;
	 * a switch (timer, Prev/Next, API skip) resets them. LIVE is a
	 * definite observation of a playing video, so it is cached LIVE
	 * the same way the API result is — that also feeds the
	 * skip-if-offline check. UNKNOWN (loading / buffering) resets
	 * the count but never skips. At 3 straight OFFLINE ticks (~3s)
	 * the dock skips, exactly like the API path: the entry is cached
	 * OFFLINE and advanceToNext() lands on the next live link. */
	void onPageTitle(const QString &title)
	{
		if (!title.startsWith("SHOWER:"))
			return;
		QStringList parts = title.split(':');
		if (parts.size() < 2)
			return;
		QString state = parts[1];
		ShowerEntry current;
		bool haveCurrent = false;
		{
			std::lock_guard<std::mutex> lock(g_state.mutex);
			if (!g_state.entries.empty() && g_state.current >= 0 &&
			    g_state.current < (int)g_state.entries.size()) {
				current = g_state.entries[(size_t)g_state.current];
				haveCurrent = true;
			}
		}
		if (!haveCurrent)
			return;
		QString key = cacheKey(current);
		if (state == "LIVE") {
			screenOfflineTicks = 0;
			std::lock_guard<std::mutex> lock(g_state.mutex);
			g_state.liveCache[key] = LiveCache{
				LiveCache::Status::LIVE,
				QDateTime::currentMSecsSinceEpoch()};
			return;
		}
		if (state != "OFFLINE") {
			/* UNKNOWN: loading / buffering — reset, never skip. */
			screenOfflineTicks = 0;
			return;
		}
		if (screenKey != key) {
			screenKey = key;
			screenOfflineTicks = 0;
		}
		screenOfflineTicks++;
		if (screenOfflineTicks >= SCREEN_OFFLINE_DEBOUNCE_TICKS)
			skipCurrentForOfflineScreen(key);
	}

	void skipCurrentForOfflineScreen(const QString &key)
	{
		{
			std::lock_guard<std::mutex> lock(g_state.mutex);
			g_state.liveCache[key] = LiveCache{
				LiveCache::Status::OFFLINE,
				QDateTime::currentMSecsSinceEpoch()};
		}
		blog(LOG_INFO, "Stream Shower: offline screen seen for %s, skipping to next link",
		     key.toUtf8().constData());
		screenOfflineTicks = 0;
		screenKey.clear();
		advanceToNext();
		applyUrlToBrowser();
		{
			std::lock_guard<std::mutex> lock(g_state.mutex);
			if (!g_state.entries.empty())
				setWebUrl(playerUrl(g_state.entries[(size_t)g_state.current], false));
		}
		refreshStatus();
	}

	void onJump(int dir)
	{
		int target = 0;
		{
			std::lock_guard<std::mutex> lock(g_state.mutex);
			target = g_state.current + dir;
		}
		screenOfflineTicks = 0;
		screenKey.clear();
		jumpTo(target);
		applyUrlToBrowser();
		{
			std::lock_guard<std::mutex> lock(g_state.mutex);
			if (!g_state.entries.empty())
				setWebUrl(playerUrl(g_state.entries[(size_t)g_state.current], false));
		}
		refreshStatus();
	}

	void onTick()
	{
		tickCount++;
		bool switched = false;
		bool needApply = false;
		bool screenWatch = true;
		{
			std::lock_guard<std::mutex> lock(g_state.mutex);
			needApply = g_state.needsApply;
			screenWatch = g_state.screenWatch;
			if (!g_state.entries.empty()) {
				g_state.elapsed += 1.0;
				const ShowerEntry &e = g_state.entries[(size_t)g_state.current];
				if (g_state.elapsed >= (double)std::max(1, e.minutes * 60)) {
					/* Advance outside this lock below
					 * (advanceToNext takes the lock). */
					switched = true;
				}
			}
		}
		if (switched) {
			screenOfflineTicks = 0;
			screenKey.clear();
			advanceToNext();
			applyUrlToBrowser();
			std::lock_guard<std::mutex> lock(g_state.mutex);
			if (!g_state.entries.empty())
				setWebUrl(playerUrl(g_state.entries[(size_t)g_state.current], false));
		} else if (needApply) {
			screenOfflineTicks = 0;
			screenKey.clear();
			applyUrlToBrowser();
			std::lock_guard<std::mutex> lock(g_state.mutex);
			if (!g_state.entries.empty())
				setWebUrl(playerUrl(g_state.entries[(size_t)g_state.current], false));
		}
		/* Offline-screen probe, once a second, in the dock's own
		 * player (same URL the source is showing). The probe sets
		 * document.title; the dock reads it back in onPageTitle().
		 * Runs even when the dock is hidden — the timer keeps
		 * ticking. Skipped only if sir turned the watch off. */
		if (screenWatch && web)
			web->executeJavaScript(kOfflineProbeJs);
		refreshStatus();
		/* Offline pre-check every 30 seconds: the next two links, so
		 * the auto-switch can skip an offline one without a pause. */
		if (tickCount % 30 == 0)
			checkUpcoming();
	}

	void checkUpcoming()
	{
		std::vector<ShowerEntry> entries;
		int current = 0;
		{
			std::lock_guard<std::mutex> lock(g_state.mutex);
			entries = g_state.entries;
			current = g_state.current;
		}
		if (entries.empty())
			return;
		int n = (int)entries.size();
		for (int step = 1; step <= 2 && step < n; step++) {
			ShowerEntry e = entries[(size_t)((current + step) % n)];
			qint64 now = QDateTime::currentMSecsSinceEpoch();
			{
				std::lock_guard<std::mutex> lock(g_state.mutex);
				auto it = g_state.liveCache.find(cacheKey(e));
				if (it != g_state.liveCache.end() && now - it->second.checkedMs < 120000)
					continue; /* fresh cache, skip */
			}
			checkOneLive(e);
		}
	}

	/* Best-effort offline check, OFFICIAL APIs only — no page
	 * scraping. Kick: public api/v2/channels (no login). Twitch:
	 * Helix /streams, which needs a Client ID + access token from
	 * the source properties; without them the link is cached
	 * NO_CHECK (never auto-skipped, just plays on the timer).
	 * Only a definite result is cached; anything unclear is left
	 * uncached so it is checked again. */
	void checkOneLive(const ShowerEntry &e)
	{
		QString clientId, token;
		if (e.platform == "twitch") {
			std::lock_guard<std::mutex> lock(g_state.mutex);
			clientId = g_state.twitchClientId;
			token = g_state.twitchToken;
			if (clientId.isEmpty() || token.isEmpty()) {
				g_state.liveCache[cacheKey(e)] =
					LiveCache{LiveCache::Status::NO_CHECK,
						  QDateTime::currentMSecsSinceEpoch()};
				return; /* cannot check — never skip it */
			}
		}
		QNetworkRequest req;
		if (e.platform == "kick") {
			req.setUrl(QUrl(QString("https://kick.com/api/v2/channels/%1").arg(e.channel)));
		} else {
			req.setUrl(QUrl(QString("https://api.twitch.tv/helix/streams?user_login=%1")
						.arg(e.channel.toLower())));
			req.setRawHeader("Client-Id", clientId.toUtf8());
			req.setRawHeader("Authorization",
					 QString("Bearer %1").arg(token).toUtf8());
		}
		req.setRawHeader("User-Agent", "OBS-Stream-Shower/1.0");
		QNetworkReply *reply = nam->get(req);
		QString key = cacheKey(e);
		QString platform = e.platform;
		connect(reply, &QNetworkReply::finished, reply, [reply, key, platform]() {
			bool definite = false;
			bool live = true;
			if (reply->error() == QNetworkReply::NoError) {
				QByteArray body = reply->readAll();
				obs_data_t *json = obs_data_create_from_json(body.constData());
				if (json) {
					if (platform == "kick") {
						/* Kick: "livestream" is null when offline. */
						obs_data_t *stream = obs_data_get_obj(json, "livestream");
						definite = true;
						live = stream != nullptr;
						if (stream)
							obs_data_release(stream);
					} else {
						/* Helix: "data" array is empty when offline. */
						obs_data_array_t *data = obs_data_get_array(json, "data");
						if (data) {
							definite = true;
							live = obs_data_array_count(data) > 0;
							obs_data_array_release(data);
						}
					}
					obs_data_release(json);
				}
			}
			if (definite) {
				std::lock_guard<std::mutex> lock(g_state.mutex);
				g_state.liveCache[key] = LiveCache{
					live ? LiveCache::Status::LIVE : LiveCache::Status::OFFLINE,
					QDateTime::currentMSecsSinceEpoch()};
				blog(LOG_INFO, "Stream Shower: %s is %s",
				     key.toUtf8().constData(), live ? "LIVE" : "offline");
			}
			reply->deleteLater();
		});
	}
};

static QWidget *watcherWindow = nullptr;

void openWatcherWindow()
{
	if (!watcherWindow)
		watcherWindow = new StreamWatcherWindow();
	watcherWindow->show();
	watcherWindow->raise();
	watcherWindow->activateWindow();
}

/* Tools menu entry: added once OBS has finished loading, so the
 * main window (and its Tools menu) exists. Adding it in
 * obs_module_load directly would be too early — the main window is
 * not built yet at that point. */
static bool toolsMenuAdded = false;

static void onFrontendEvent(enum obs_frontend_event event, void *)
{
	if (event != OBS_FRONTEND_EVENT_FINISHED_LOADING || toolsMenuAdded)
		return;
	toolsMenuAdded = true;
	obs_frontend_add_tools_menu_item("Stream Watcher", [](void *) { openWatcherWindow(); },
					 nullptr);
}

} // namespace

bool obs_module_load(void)
{
	/* Stream Shower source. Field-by-field init (OBS builds C++
	 * plugins at C++17 — designated initializers are rejected). */
	static struct obs_source_info info;
	memset(&info, 0, sizeof(info));
	info.id = "stream_shower";
	info.type = OBS_SOURCE_TYPE_INPUT;
	info.output_flags = OBS_SOURCE_VIDEO;
	info.get_name = shower_get_name;
	info.create = shower_create;
	info.destroy = shower_destroy;
	info.get_width = shower_get_width;
	info.get_height = shower_get_height;
	info.get_defaults = shower_get_defaults;
	info.get_properties = shower_get_properties;
	info.update = shower_update;
	info.video_render = shower_video_render;
	info.icon_type = OBS_ICON_TYPE_BROWSER;
	obs_register_source(&info);

	/* Stream Watcher pop-out window. Created now, kept HIDDEN —
	 * its 1-second timer is the switcher, and it must keep running
	 * even when the window is closed, so the source keeps
	 * auto-switching. Open it from Tools > Stream Watcher (added
	 * when OBS finishes loading) or the "Open Stream Watcher"
	 * button in the source properties. No dock is registered any
	 * more in v4. */
	watcherWindow = new StreamWatcherWindow();
	obs_frontend_add_event_callback(onFrontendEvent, nullptr);
	blog(LOG_INFO, "Stream Shower loaded (source + Watcher window, Tools > Stream Watcher)");
	return true;
}

void obs_module_unload(void)
{
	watcherWindow = nullptr;
}
