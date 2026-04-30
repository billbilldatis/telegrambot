import feedparser
import json
import time
import requests
import os
import logging
from datetime import datetime, timezone
from collections import Counter
 
# -----------------------
# CONFIG
# -----------------------
URL = "https://trends.google.com/trending/rss?geo=GR"
BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]
SEEN_FILE = "seen.json"
STATS_FILE = "stats.json"
TTL_SECONDS = 86400        # 24 hours
TRAFFIC_HIGH = 20_00
TRAFFIC_MID = 5_00
MIN_TRAFFIC = 0            # Set > 0 to filter low-traffic topics
SEND_DELAY = 1.5           # Seconds between Telegram messages (avoid flood limits)
DIGEST_HOUR = 9            # Hour (UTC) to send daily digest (if run at this hour)
 
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)
 
# -----------------------
# CATEGORY DETECTION
# -----------------------
CATEGORIES = {
    "⚽ Sports": [
        "ολυμπιακός", "παοκ", "αεκ", "παναθηναϊκός", "τσιτσιπάς", "ucl",
        "champions league", "αθλητ", "ποδόσφαιρ", "μπάσκετ", "τένις",
        "γκολ", "νίκη", "αγώνας", "πρωτάθλημα", "fifa", "euro",
    ],
    "🎵 Music / Entertainment": [
        "eurovision", "τραγούδι", "μουσική", "συναυλία", "τηλεόραση",
        "σειρά", "ταινία", "netflix", "youtube", "tiktok", "instagram",
    ],
    "🏛️ Politics": [
        "κυβέρνηση", "βουλή", "πρωθυπουργός", "υπουργ", "εκλογ",
        "μητσοτάκης", "τσίπρας", "ανδρουλάκης", "πολιτικ", "νομοσχέδιο",
        "δήμος", "περιφέρεια",
    ],
    "💰 Economy": [
        "οικονομία", "χρηματιστήριο", "τράπεζα", "επιτόκιο", "πληθωρισμός",
        "αγορά", "επένδυση", "φόρος", "συντάξεις", "μισθός",
    ],
    "🛡️ Defense / Military": [
        "άμυνα", "στρατός", "ναυτικό", "αεροπορία", "nato", "όπλα",
        "πυραύλ", "militaire", "ασφάλεια", "απειλή",
    ],
    "🌍 World / International": [
        "τουρκία", "ρωσία", "αμερική", "ευρώπη", "ισραήλ", "ουκρανία",
        "διεθνής", "συνθήκη", "διπλωματία",
    ],
    "⚠️ Emergency / Disaster": [
        "σεισμός", "πυρκαγιά", "πλημμύρα", "ατύχημα", "τροχαίο",
        "έκτακτο", "θύμα", "νεκρός", "τραυματίας",
    ],
    "🏥 Health": [
        "υγεία", "νοσοκομείο", "εμβόλιο", "ιός", "ασθένεια",
        "covid", "καρκίνος", "ιατρ", "φάρμακο",
    ],
    "🔬 Technology / Science": [
        "τεχνολογία", "τεχνητή νοημοσύνη", "ai", "επιστήμη",
        "διάστημα", "nasa", "κλίμα", "περιβάλλον",
    ],
}
 
def detect_category(topic: str, news_items: list) -> str:
    text = (topic + " " + " ".join(n["title"] for n in news_items)).lower()
    for category, keywords in CATEGORIES.items():
        if any(kw in text for kw in keywords):
            return category
    return "📌 General"
 
# -----------------------
# TREND SCORE
# -----------------------
def trend_score(traffic: int, num_sources: int, num_news: int) -> int:
    """0-100 composite score based on traffic, source diversity, and coverage."""
    t_score = min(traffic / TRAFFIC_HIGH, 1.0) * 60
    s_score = min(num_sources / 6, 1.0) * 20
    n_score = min(num_news / 5, 1.0) * 20
    return round(t_score + s_score + n_score)
 
def score_bar(score: int) -> str:
    filled = score // 10
    return "█" * filled + "░" * (10 - filled) + f" {score}/100"
 
# -----------------------
# LOAD / SAVE
# -----------------------
def load_json(path: str) -> dict:
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
 
def save_json(path: str, data: dict) -> None:
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
 
def clean_seen(seen: dict) -> dict:
    now = time.time()
    cleaned = {k: v for k, v in seen.items() if now - v < TTL_SECONDS}
    removed = len(seen) - len(cleaned)
    if removed:
        log.info(f"Cleaned {removed} expired entries from seen cache.")
    return cleaned
 
# -----------------------
# PARSE TRAFFIC
# -----------------------
def parse_traffic(raw: str) -> int:
    try:
        raw = raw.strip().upper().replace(",", "")
        if "M" in raw:
            return int(float(raw.replace("M", "").replace("+", "")) * 1_000_000)
        if "K" in raw:
            return int(float(raw.replace("K", "").replace("+", "")) * 1_000)
        return int(raw.replace("+", ""))
    except (ValueError, AttributeError):
        return 0
 
# -----------------------
# ANALYSIS
# -----------------------
def analyze(traffic: int, news_items: list) -> tuple[list, list]:
    sources = list({n["source"] for n in news_items if n["source"]})


    if traffic >= TRAFFIC_HIGH:
        volume_label = "🔥 HIGH PUBLIC INTEREST"
    elif traffic >= TRAFFIC_MID:
        volume_label = "📈 MODERATE TREND"
    else:
        volume_label = "📉 LOW TREND"
 
    if len(sources) > 4:
        coverage_label = "🌐 WIDELY COVERED"
    elif len(sources) > 1:
        coverage_label = "📰 MODERATE COVERAGE"
    else:
        coverage_label = "🗞️ LIMITED COVERAGE"
 
    return [volume_label, coverage_label], sources
 
# -----------------------
# FORMAT MAIN MESSAGE
# -----------------------
def format_message(
    topic: str,
    traffic: int,
    published: str,
    analysis: list,
    sources: list,
    news_items: list,
    link: str,
    category: str,
    score: int,
    rank: int,
    total: int,
) -> str:
    try:
        dt = datetime.strptime(published, "%a, %d %b %Y %H:%M:%S %z")
        published_fmt = dt.strftime("%d %b %Y, %H:%M UTC")
    except (ValueError, TypeError):
        published_fmt = published or "Unknown"
 
    traffic_fmt = f"{traffic:,}" if traffic else "N/A"
    sources_text = ", ".join(sources) if sources else "N/A"
    news_lines = "\n".join(
        f"  • [{n['title']}]({n['url']})" if n.get("url") else f"  • {n['title']} ({n['source']})"
        for n in news_items[:5]
    ) or "  No related news."
 
    return (
        f"{category} | #{rank} of {total}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📊 *TREND REPORT*\n"
        f"🔎 *Topic:* {topic}\n"
        f"👥 *Traffic:* {traffic_fmt}\n"
        f"🕐 *Published:* {published_fmt}\n\n"
        f"*Trend Score:* `{score_bar(score)}`\n\n"
        f"*Analysis*\n"
        f"{chr(10).join(analysis)}\n\n"
        f"*Top Sources*\n"
        f"{sources_text}\n\n"
        f"*Related News*\n"
        f"{news_lines}\n\n"
        f"🔗 [View on Google Trends]({link})"
    )
 
# -----------------------
# DAILY DIGEST
# -----------------------
def format_digest(entries_data: list) -> str:
    if not entries_data:
        return ""
 
    top = sorted(entries_data, key=lambda x: x["traffic"], reverse=True)[:10]
    category_counts = Counter(e["category"] for e in entries_data)
    total_traffic = sum(e["traffic"] for e in entries_data)
 
    lines = ["📋 *DAILY DIGEST — Greece Trends*\n━━━━━━━━━━━━━━━━━━"]
    for i, e in enumerate(top, 1):
        lines.append(f"{i}. *{e['topic']}* — {e['traffic']:,} searches ({e['category']})")
 
    lines.append(f"\n📦 *Total topics sent:* {len(entries_data)}")
    lines.append(f"📊 *Total searches:* {total_traffic:,}")
    lines.append("\n*Categories breakdown:*")
    for cat, count in category_counts.most_common():
        lines.append(f"  {cat}: {count}")
 
    return "\n".join(lines)
 
# -----------------------
# TELEGRAM
# -----------------------
def send_text(msg: str, parse_mode: str = "Markdown") -> bool:
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={
                "chat_id": CHAT_ID,
                "text": msg[:4096],
                "parse_mode": parse_mode,
                "disable_web_page_preview": False,
            },
            timeout=10
        )
        resp.raise_for_status()
        return True
    except requests.RequestException as e:
        log.error(f"Telegram send failed: {e}")
        return False
 
def send_photo(image_url: str, caption: str) -> bool:
    """Send trend report with its thumbnail image."""
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
            json={
                "chat_id": CHAT_ID,
                "photo": image_url,
                "caption": caption[:1024],
                "parse_mode": "Markdown",
            },
            timeout=15
        )
        resp.raise_for_status()
        return True
    except requests.RequestException as e:
        log.warning(f"Photo send failed, falling back to text: {e}")
        return False
 
def send_entry(message: str, image_url: str | None) -> bool:
    """Try to send with image first; fall back to plain text."""
    if image_url:
        if send_photo(image_url, message[:1024]):
            return True
    return send_text(message)
 
# -----------------------
# STATS TRACKING
# -----------------------
def update_stats(stats: dict, entry_data: dict) -> dict:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if today not in stats:
        stats[today] = {"topics": 0, "total_traffic": 0, "categories": {}}
 
    day = stats[today]
    day["topics"] += 1
    day["total_traffic"] += entry_data["traffic"]
    cat = entry_data["category"]
    day["categories"][cat] = day["categories"].get(cat, 0) + 1
 
    # Keep only last 30 days
    all_days = sorted(stats.keys())
    return {k: stats[k] for k in all_days[-30:]}
 
# -----------------------
# MAIN
# -----------------------
def run() -> None:
    log.info("Fetching Google Trends feed...")
    feed = feedparser.parse(URL)
 
    if feed.bozo:
        log.warning(f"Feed parse warning: {feed.bozo_exception}")
 
    if not feed.entries:
        log.info("No entries in feed.")
        return
    seen = clean_seen(load_json(SEEN_FILE))
    stats = load_json(STATS_FILE)
 
    total_entries = len(feed.entries)
    new_count = 0
    digest_batch = []
 
    for rank, entry in enumerate(feed.entries, 1):
        topic = entry.get("title", "").strip()
        if not topic or topic in seen:
            continue
 
        traffic = parse_traffic(entry.get("ht_approx_traffic", "0"))
 
        if traffic < MIN_TRAFFIC:
            log.info(f"Skipping '{topic}' — traffic {traffic:,} below minimum.")
            continue
 
        news_items = [
            {
                "title": getattr(n, "title", "").strip(),
                "source": getattr(n, "ht_news_item_source", "").strip(),
                "url": getattr(n, "ht_news_item_url", "").strip(),
            }
            for n in entry.get("ht_news_item", [])
            if getattr(n, "title", "")
        ]
 
        # Extract thumbnail image
        image_url = None
        if hasattr(entry, "ht_picture"):
            image_url = entry.ht_picture
        elif hasattr(entry, "media_thumbnail") and entry.media_thumbnail:
            image_url = entry.media_thumbnail[0].get("url")
 
        analysis, sources = analyze(traffic, news_items)
        category = detect_category(topic, news_items)
        score = trend_score(traffic, len(sources), len(news_items))
 
        message = format_message(
            topic=topic,
            traffic=traffic,
            published=entry.get("published", ""),
            analysis=analysis,
            sources=sources,
            news_items=news_items,
            link=entry.get("link", ""),
            category=category,
            score=score,
            rank=rank,
            total=total_entries,
        )
 
        if send_entry(message, image_url):
            seen[topic] = time.time()
            new_count += 1
            entry_data = {"topic": topic, "traffic": traffic, "category": category}
            digest_batch.append(entry_data)
            stats = update_stats(stats, entry_data)
            log.info(f"[{rank}/{total_entries}] Sent: {topic} | {traffic:,} | {category} | score={score}")
            time.sleep(SEND_DELAY)
        else:
            log.warning(f"Failed to send '{topic}', will retry next run.")
 
    # Send daily digest at configured hour
    now_utc = datetime.now(timezone.utc)
    if now_utc.hour == DIGEST_HOUR and digest_batch:
        digest = format_digest(digest_batch)
        if digest:
            time.sleep(SEND_DELAY)
            send_text(digest)
            log.info("Daily digest sent.")
 
    save_json(SEEN_FILE, seen)
    save_json(STATS_FILE, stats)
    log.info(f"Done. {new_count} new trend(s) sent.")
 
if __name__ == "__main__":
    run()