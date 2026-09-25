# 🇬🇷 Greek Trends Telegram Bot

A zero-config Telegram bot that watches [Google Trends (Greece)](https://trends.google.com/trending?geo=GR),
classifies trending topics into categories, scores their momentum, and posts
formatted trend reports with related news straight to your chat — every 10
minutes, around the clock, via GitHub Actions.

Trends are deduplicated with a 24-hour cache (`seen.json`) so a topic is only
reported once per day. Daily usage statistics are accumulated in `stats.json`
and persisted to the repo, so you can review what the bot has been sending.

## Features

- **Live trending feed** — pulls Google Trends GR RSS every 10 minutes
- **Smart categories** — 15 Greek-aware categories (⚽ Sports, 🎵 Music, 🏛️ Politics,
  💰 Economy, 🛡️ Defense, 🌍 World, ⚠️ Emergency, 🏥 Health, 🔬 Tech/Science,
  ⚖️ Crime/Law, 🎓 Education, 🚆 Transport, 🌦️ Weather, 🧑‍🤝‍🧑 Society)
- **Trend score** — 0–100 composite score from search volume, source diversity
  and news coverage, rendered as a progress bar
- **Rich reports** — traffic, publish time, top sources, up to 5 related news
  links, and a thumbnail image when the feed provides one
- **Daily digest** — at 09:00 UTC: top-10 list, category breakdown, totals
- **Resilient** — bounded network timeouts, atomic state writes, graceful
  fallback from photo → text when Telegram rejects an image
- **Observable** — `python bot.py --stats` prints the last 7 days of activity
- **Configurable** — every knob is an environment variable; no source edits

## Requirements

- Python 3.10+
- A Telegram bot token from [@BotFather](https://t.me/BotFather)
- A chat ID to post into (your user chat, a group, or a channel)

## Setup

### 1. Create the bot

1. Message [@BotFather](https://t.me/BotFather) → `/newbot` → copy the token.
2. Message your new bot once (or add it to your group/channel) so it can see you.
3. Get your chat ID — e.g. call
   `curl https://api.telegram.org/bot<TOKEN>/getUpdates` and read
   `result[0].message.chat.id` (for groups it may be prefixed with `-`).

### 2. Configure GitHub Actions

Fork this repository, then in **Settings → Secrets and variables → Actions →
New repository secret**:

| Secret     | Value                              |
|------------|------------------------------------|
| `TELEGRAM_BOT_TOKEN` | your bot token            |
| `CHAT_ID`  | the target chat ID                 |

The `run-bot` workflow (`.github/workflows/run.yml`) runs the bot every 10
minutes and commits the updated `seen.json` / `stats.json` state back to the
repo automatically. That's it — no server, no cron, no cost.

### 3. Run locally (optional)

```bash
pip install -r requirements.txt
export TELEGRAM_BOT_TOKEN="your-token"
export CHAT_ID="your-chat-id"
python bot.py
```

## Configuration

All settings have sane defaults and are overridable via environment variables:

| Variable            | Default                     | Purpose                                        |
|---------------------|-----------------------------|------------------------------------------------|
| `TRENDS_URL`        | `https://trends.google.com/trending/rss?geo=GR` | RSS feed source          |
| `SEEN_FILE`         | `seen.json`                 | Dedup cache path                               |
| `STATS_FILE`        | `stats.json`                | Stats storage path                             |
| `TTL_SECONDS`       | `86400`                     | How long a topic stays "seen" (24h)            |
| `TRAFFIC_HIGH`      | `5000`                      | Traffic ≥ this ⇒ 🔥 HIGH PUBLIC INTEREST        |
| `TRAFFIC_MID`       | `100`                       | Traffic ≥ this ⇒ 📈 MODERATE TREND              |
| `MIN_TRAFFIC`       | `0`                         | Skip topics below this traffic (>0 to filter)  |
| `SEND_DELAY`        | `1.5`                       | Seconds between messages (Telegram flood limit)|
| `DIGEST_HOUR`       | `9`                         | UTC hour for the daily digest                  |
| `FETCH_TIMEOUT`     | `30`                        | Max seconds to wait for the feed               |

Invalid values (e.g. `TRAFFIC_HIGH=abc`) are rejected with a warning and the
default is used — a misconfigured variable can never break a run.

Invalid numeric values in `seen.json` / `stats.json` are tolerated (corrupt
state degrades to an empty cache).

## CLI

| Command                | What it does                                   |
|------------------------|------------------------------------------------|
| `python bot.py`        | Run one bot cycle (fetch, report, persist)     |
| `python bot.py --stats`| Print the last 7 days of recorded activity     |

Example `--stats` output:

```
Date         Topics    Searches  Top category
2026-08-12        9     128,500  ⚽ Sports
2026-08-13       11     204,300  🏛️ Politics
```

## How it works

1. Fetch the Google Trends GR RSS feed (bounded by `FETCH_TIMEOUT`).
2. For each new topic above `MIN_TRAFFIC`, compute:
   - **traffic** — parsed search volume (`1.5M+`, `500K+`, `500,000+` …)
   - **category** — keyword matching against ~15 Greek-aware keyword sets
   - **score** — `min(traffic/HIGH,1)×60 + min(sources/6,1)×20 + min(news/5,1)×20`
3. Send the report (photo + caption if an image is available, else text).
4. Mark the topic as seen (24h TTL) and update daily stats.
5. At `DIGEST_HOUR` UTC, send the daily digest for that run's topics.
6. Atomic-write `seen.json` / `stats.json`; the workflow commits and pushes them.

State files are committed by design — they carry the dedup cache and stats
between runs of the ephemeral GitHub-hosted runner.

## Project layout

```
bot.py                 # entire bot — config, analysis, formatting, sending
requirements.txt       # runtime dependencies
.github/workflows/run.yml  # 10-minute scheduled runner + state persistence
seen.json              # 24h dedup cache (committed by the bot itself)
stats.json             # daily activity stats (committed by the bot itself)
```

## Testing

```bash
pip install -r requirements.txt pytest
python -m pytest tests/ -v
```

The test suite is fully offline — the feed, the network and Telegram are all
mocked. It covers traffic parsing, category detection, scoring, markdown
escaping, state persistence, the digest, and an end-to-end bot run.

## License

MIT — see [LICENSE](LICENSE).