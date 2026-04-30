import feedparser
import json
import time
import requests
import os
URL = "https://trends.google.com/trending/rss?geo=GR"

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]

SEEN_FILE = "seen.json"


# -----------------------
# LOAD / SAVE
# -----------------------
def load_seen():
    try:
        with open(SEEN_FILE, "r") as f:
            return json.load(f)
    except:
        return {}


def save_seen(data):
    with open(SEEN_FILE, "w") as f:
        json.dump(data, f)


# -----------------------
# CLEAN OLD (24h)
# -----------------------
def clean_seen(seen):
    now = time.time()
    return {k: v for k, v in seen.items() if now - v < 86400}


# -----------------------
# PARSE TRAFFIC
# -----------------------
def parse_traffic(t):
    try:
        t = t.replace("K+", "000").replace("M+", "000000")
        return int(t)
    except:
        return 0


# -----------------------
# ANALYSIS
# -----------------------
def analyze(topic, traffic, news_items):
    sources = [n["source"] for n in news_items if n["source"]]
    unique_sources = list(set(sources))

    analysis = []

    if traffic > 100000:
        analysis.append("HIGH PUBLIC INTEREST")
    elif traffic > 20000:
        analysis.append("MODERATE TREND")
    else:
        analysis.append("LOW TREND")

    if len(unique_sources) > 3:
        analysis.append("WIDELY COVERED")
    else:
        analysis.append("LIMITED COVERAGE")

    return analysis, unique_sources


# -----------------------
# TELEGRAM
# -----------------------
def send(msg):
    requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        json={"chat_id": CHAT_ID, "text": msg[:4000]}
    )


# -----------------------
# MAIN
# -----------------------
def run():
    feed = feedparser.parse(URL)

    seen = load_seen()
    seen = clean_seen(seen)

    for entry in feed.entries:
        topic = entry.title

        if topic in seen:
            continue

        traffic = parse_traffic(entry.get("ht_approx_traffic", "0"))

        news_items = [
            {
                "title": n.title,
                "source": getattr(n, "ht_news_item_source", ""),
                "url": getattr(n, "ht_news_item_url", "")
            }
            for n in entry.get("ht_news_item", [])
        ]

        analysis, sources = analyze(topic, traffic, news_items)

        news_text = "\n".join(
            [f"- {n['title']} ({n['source']})" for n in news_items]
        )

        sources_text = ", ".join(sources) if sources else "N/A"

        message = f"""
📊 TREND REPORT

Topic: {topic}
Traffic: {traffic}
Time: {entry.published}

--- Analysis ---
{", ".join(analysis)}

--- Top Sources ---
{sources_text}

--- Related News ---
{news_text}

Link:
{entry.link}
"""

        send(message)

        seen[topic] = time.time()

    save_seen(seen)


if __name__ == "__main__":
    run()