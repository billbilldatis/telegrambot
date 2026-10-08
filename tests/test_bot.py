"""Offline test suite for the Greek Trends Telegram bot.

Everything network- or Telegram-related is mocked; no test touches the
network. Run with:  python -m pytest tests/ -v
"""

import json
import time as time_mod
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

import bot


# ---------------------------------------------------------------------------
# Markdown escaping — THE regression tests. Raw feed text containing a stray
# ``*`` / ``_`` / ``[`` / backtick previously produced malformed Telegram
# markup: the API rejected the message (HTTP 400), the topic was never marked
# as seen, and it was retried on every run forever.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "raw,expected",
    [
        ("plain text", "plain text"),
        ("a * star", r"a \* star"),
        ("under_score", r"under\_score"),
        ("bracket [x]", r"bracket \[x\]"),
        ("tick `x`", r"tick \`x\`"),
        ("back\\slash", r"back\\slash"),
        ("", ""),
        ("mixed * _ [ ] `", r"mixed \* \_ \[ \] \`"),
    ],
)
def test_escape_md(raw, expected):
    assert bot.escape_md(raw) == expected


def test_escape_md_url():
    assert bot.escape_md_url("https://a.com/x)") == "https://a.com/x%29"
    assert bot.escape_md_url("https://a.com/a\\b") == "https://a.com/a%5Cb"
    assert bot.escape_md_url("https://trends.google.com/?geo=GR&days=1") == (
        "https://trends.google.com/?geo=GR&days=1"
    )


def test_format_message_escapes_topic_and_news():
    msg = bot.format_message(
        topic="Σεισμός * στην Κρήτη [LIVE]",
        traffic=120_000,
        published_raw="",
        published_parsed=None,
        analysis=["📈 MODERATE TREND", "🌐 WIDELY COVERED"],
        sources=["news.gr"],
        news_items=[
            {"title": "Τι έγινε (αναλυτικά)", "source": "in.gr", "url": "https://www.in.gr/?a=1)"},
            {"title": "No url here", "source": "ert.gr", "url": ""},
        ],
        link="https://trends.google.com/trends/trending?geo=GR&days=1",
        category="⚠️ Emergency / Disaster",
        score=77,
        rank=1,
        total=20,
    )
    assert r"*Topic:* Σεισμός \* στην Κρήτη \[LIVE\]" in msg
    assert r"[Τι έγινε (αναλυτικά)](https://www.in.gr/?a=1%29)" in msg
    assert "https://trends.google.com/trends/trending?geo=GR&days=1" in msg
    # Raw markup must never appear unescaped in the body.
    assert "Σεισμός * στην" not in msg
    assert "`score_bar`" not in msg


def test_format_message_published_from_parsed():
    parsed = time_mod.struct_time((2026, 8, 18, 9, 30, 0, 1, 230, 0))
    msg = bot.format_message(
        topic="T", traffic=1, published_raw="Tue, 18 Aug 2026 09:30:00 GMT",
        published_parsed=parsed, analysis=[], sources=[], news_items=[],
        link="", category="📌 General", score=0, rank=1, total=1,
    )
    assert "18 Aug 2026, 09:30 UTC" in msg


def test_format_message_published_fallback_raw():
    msg = bot.format_message(
        topic="T", traffic=1, published_raw="Tue, 18 Aug 2026 09:30:00 GMT",
        published_parsed=None, analysis=[], sources=[], news_items=[],
        link="", category="📌 General", score=0, rank=1, total=1,
    )
    assert "Tue, 18 Aug 2026 09:30:00 GMT" in msg


# ---------------------------------------------------------------------------
# Traffic parsing
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "raw,expected",
    [
        ("500K+", 500_000),
        ("1.5M+", 1_500_000),
        ("500,000+", 500_000),
        ("500000+", 500_000),
        ("0", 0),
        ("100", 100),
        ("2K", 2_000),
        ("", 0),
        ("garbage", 0),
        ("NaN", 0),
    ],
)
def test_parse_traffic(raw, expected):
    assert bot.parse_traffic(raw) == expected


def test_parse_traffic_case_insensitive():
    assert bot.parse_traffic("500k+") == 500_000
    assert bot.parse_traffic("1.5m+") == 1_500_000


# ---------------------------------------------------------------------------
# Category detection
# ---------------------------------------------------------------------------
def test_detect_category_known():
    items = [{"title": "Νίκη του ΠΑΟΚ στο ντέρμπι", "source": "x", "url": ""}]
    assert bot.detect_category("ΟΣΦΠ", items) == "⚽ Sports"


def test_detect_category_case_insensitive():
    items = [{"title": "", "source": "", "url": ""}]
    assert bot.detect_category("EURO 2024", items) == "⚽ Sports"


def test_detect_category_news_title_counted():
    items = [{"title": "Τεχνητή νοημοσύνη αλλάζει τα πάντα", "source": "x", "url": ""}]
    assert bot.detect_category("άγνωστο θέμα", items) == "🔬 Technology / Science"


def test_detect_category_fallback():
    items = [{"title": "", "source": "", "url": ""}]
    assert bot.detect_category("qwzxvbnm", items) == "📌 General"


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------
def test_trend_score_max():
    assert bot.trend_score(10_000_000, 10, 10) == 100


def test_trend_score_zero():
    assert bot.trend_score(0, 0, 0) == 0


def test_trend_score_partial():
    # 60% traffic (5000/5000), 1/6 sources, 1/5 news -> 60 + 3 + 4 = 67
    assert 60 <= bot.trend_score(5_000, 1, 1) <= 70


def test_score_bar():
    assert bot.score_bar(0) == "░" * 10 + " 0/100"
    assert bot.score_bar(100) == "█" * 10 + " 100/100"
    assert bot.score_bar(50) == "█" * 5 + "░" * 5 + " 50/100"


# ---------------------------------------------------------------------------
# State persistence
# ---------------------------------------------------------------------------
def test_load_json_missing(tmp_path):
    assert bot.load_json(str(tmp_path / "nope.json")) == {}


def test_load_json_corrupt(tmp_path):
    p = tmp_path / "corrupt.json"
    p.write_text("{not json")
    assert bot.load_json(str(p)) == {}


def test_load_json_valid(tmp_path):
    p = tmp_path / "ok.json"
    p.write_text('{"a": 1}')
    assert bot.load_json(str(p)) == {"a": 1}


def test_save_json_atomic(tmp_path):
    p = tmp_path / "state.json"
    bot.save_json(str(p), {"topic": "Ελλάδα", "t": 1.5})
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data == {"topic": "Ελλάδα", "t": 1.5}
    # No temp file may be left behind.
    assert not (tmp_path / "state.json.tmp").exists()


def test_clean_seen_removes_expired():
    now = 1_000_000.0
    seen = {
        "fresh": now - 100,               # 100s old — keep
        "old": now - bot.TTL_SECONDS - 1,  # expired — drop
        "boundary": now - bot.TTL_SECONDS,  # age == TTL — drop (strict <)
    }
    with _fake_time(now):
        cleaned = bot.clean_seen(seen)
    assert set(cleaned) == {"fresh"}


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------
def test_update_stats_creates_and_increments_day(monkeypatch):
    monkeypatch.setattr(bot, "_now_utc", lambda: datetime(2026, 8, 18, 9, 0, 0, tzinfo=timezone.utc))
    stats = {}
    stats = bot.update_stats(stats, {"topic": "a", "traffic": 100, "category": "🏛️ Politics"})
    stats = bot.update_stats(stats, {"topic": "b", "traffic": 50, "category": "🏛️ Politics"})
    day = stats["2026-08-18"]
    assert day["topics"] == 2
    assert day["total_traffic"] == 150
    assert day["categories"] == {"🏛️ Politics": 2}


def test_update_stats_trims_to_30_days(monkeypatch):
    monkeypatch.setattr(bot, "_now_utc", lambda: datetime(2026, 8, 31, 9, 0, 0, tzinfo=timezone.utc))
    stats = {}
    for day_offset in range(40):
        stats[f"day-{day_offset:02d}"] = {"topics": 0, "total_traffic": 0, "categories": {}}
        stats = bot.update_stats(stats, {"topic": str(day_offset), "traffic": 1, "category": "x"})
    assert len(stats) == 30
    assert "day-39" in stats
    assert "day-09" not in stats


def test_format_digest():
    entries = [
        {"topic": "a", "traffic": 10, "category": "X"},
        {"topic": "b * bold", "traffic": 500, "category": "Y"},
        {"topic": "c", "traffic": 50, "category": "X"},
    ]
    digest = bot.format_digest(entries)
    assert "1. *b \\* bold* — 500 searches (Y)" in digest
    assert "*Total topics sent:* 3" in digest
    assert "*Total searches:* 560" in digest
    assert "X: 2" in digest


def test_format_digest_empty():
    assert bot.format_digest([]) == ""


# ---------------------------------------------------------------------------
# Feed fetch (network mocked)
# ---------------------------------------------------------------------------
def test_fetch_feed_success(monkeypatch):
    class FakeResp:
        content = b"<rss/>"
        def raise_for_status(self):
            return None
    calls = {}
    def fake_get(url, timeout, headers):
        calls["url"], calls["timeout"], calls["headers"] = url, timeout, headers
        return FakeResp()
    monkeypatch.setattr(bot.requests, "get", fake_get)
    assert bot.fetch_feed() == b"<rss/>"
    assert calls["url"] == bot.URL
    assert calls["timeout"] == bot.FETCH_TIMEOUT
    assert bot.USER_AGENT in calls["headers"]["User-Agent"]


def test_fetch_feed_raises(monkeypatch):
    def boom(*a, **k):
        raise bot.requests.RequestException("down")
    monkeypatch.setattr(bot.requests, "get", boom)
    with pytest.raises(bot.requests.RequestException):
        bot.fetch_feed()


# ---------------------------------------------------------------------------
# End-to-end run() — feed + Telegram fully mocked
# ---------------------------------------------------------------------------
class _FakeEntry(dict):
    """Dict with attribute access, mimicking feedparser's FeedParserDict."""

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name) from None

    def __setattr__(self, name, value):
        self[name] = value


def _fake_entry(title, traffic, seen_age=None, with_url=True):
    return _FakeEntry(
        title=title,
        ht_approx_traffic=str(traffic),
        published="Tue, 18 Aug 2026 09:30:00 GMT",
        published_parsed=time_mod.struct_time((2026, 8, 18, 9, 30, 0, 1, 230, 0)),
        link="https://trends.google.com/trends/trending?geo=GR",
        ht_news_item=[
            _FakeEntry(
                title=f"news about {title}",
                source="in.gr",
                url=f"https://in.gr/{title.replace(' ', '-')}" if with_url else "",
            )
        ],
        ht_picture="https://example.com/img.jpg",
    )


def _fake_feed(*entries):
    return SimpleNamespace(bozo=False, bozo_exception=None, entries=list(entries))


@pytest.fixture
def run_env(tmp_path, monkeypatch):
    """Isolate the bot's mutable global state for a full run()."""
    monkeypatch.setattr(bot, "SEEN_FILE", str(tmp_path / "seen.json"))
    monkeypatch.setattr(bot, "STATS_FILE", str(tmp_path / "stats.json"))
    monkeypatch.setattr(bot, "DIGEST_HOUR", 99)  # never fires during tests
    monkeypatch.setattr(bot.time, "sleep", lambda s: None)
    monkeypatch.setattr(bot, "BOT_TOKEN", "test-token")
    monkeypatch.setattr(bot, "CHAT_ID", "-100")
    sent = []
    monkeypatch.setattr(bot, "send_entry", lambda msg, img: sent.append((msg, img)) or True)
    monkeypatch.setattr(bot, "fetch_feed", lambda: b"<rss/>")
    return sent


def test_run_sends_only_new_entries_and_persists(run_env, tmp_path, monkeypatch):
    seen_path = bot.SEEN_FILE
    stats_path = bot.STATS_FILE
    seen = {f"old topic {i}": time_mod.time() - 100 for i in range(3)}
    bot.save_json(seen_path, seen)

    feed = _fake_feed(
        _fake_entry("old topic 0", 20_000),      # already seen → skip
        _fake_entry("low traffic", 10),          # below MIN_TRAFFIC? MIN=0, so sent
        _fake_entry("Νέο θέμα * με αστερίσκο", 75_000),  # fresh + markup chars
    )
    monkeypatch.setattr(bot.feedparser, "parse", lambda content: feed)

    bot.run()

    assert len(run_env) == 2  # "old topic 0" is already seen → skipped
    topics = [m[0] for m in run_env]
    assert any(r"*Topic:* Νέο θέμα \* με αστερίσκο" in m for m in topics)

    persisted = bot.load_json(seen_path)
    assert "Νέο θέμα * με αστερίσκο" in persisted
    assert "low traffic" in persisted
    assert "old topic 0" in persisted  # TTL not expired

    stats = bot.load_json(stats_path)
    assert stats
    today = list(stats.keys())[-1]
    assert stats[today]["topics"] == 2


def test_run_respects_min_traffic(run_env, monkeypatch):
    monkeypatch.setattr(bot, "MIN_TRAFFIC", 50_000)
    feed = _fake_feed(
        _fake_entry("small fry", 1_000),
        _fake_entry("big story", 200_000),
    )
    monkeypatch.setattr(bot.feedparser, "parse", lambda content: feed)
    bot.run()
    assert len(run_env) == 1
    assert "*Topic:* big story" in run_env[0][0]
    assert "small fry" not in bot.load_json(bot.SEEN_FILE)


def test_run_does_not_duplicate_after_send_failure(run_env, tmp_path, monkeypatch):
    """A failed send must leave the topic unseen so the next run retries it."""
    sent = []

    def flaky_send(msg, img):
        sent.append(msg)
        return False  # always fails

    monkeypatch.setattr(bot, "send_entry", flaky_send)
    feed = _fake_feed(_fake_entry("retry me", 60_000))
    monkeypatch.setattr(bot.feedparser, "parse", lambda content: feed)
    bot.run()
    assert len(sent) == 1
    assert bot.load_json(bot.SEEN_FILE) == {}  # nothing marked seen


def test_run_feed_failure_is_safe(run_env, monkeypatch):
    def fail_fetch():
        raise bot.requests.RequestException("network down")
    monkeypatch.setattr(bot, "fetch_feed", fail_fetch)
    monkeypatch.setattr(bot.feedparser, "parse", lambda c: None)
    bot.run()  # must not raise
    assert run_env == []
    assert not __import__("os").path.exists(bot.SEEN_FILE)


def test_run_empty_feed(run_env, monkeypatch):
    monkeypatch.setattr(bot.feedparser, "parse", lambda content: _fake_feed())
    bot.run()
    assert run_env == []


def test_run_skips_duplicate_topics_in_same_batch(run_env, monkeypatch):
    feed = _fake_feed(
        _fake_entry("same topic", 100_000),
        _fake_entry("same topic", 100_000),
    )
    monkeypatch.setattr(bot.feedparser, "parse", lambda content: feed)
    bot.run()
    assert len(run_env) == 1  # second occurrence skipped within the run


def test_run_requires_secrets(monkeypatch):
    monkeypatch.setattr(bot, "BOT_TOKEN", "")
    monkeypatch.setattr(bot, "CHAT_ID", "")
    called = []
    monkeypatch.setattr(bot, "fetch_feed", lambda: called.append(1) or b"")
    bot.run()
    assert called == []  # fetch never attempted without secrets


def test_run_stats_flag_works_without_secrets(tmp_path, monkeypatch, capsys):
    bot.save_json(str(tmp_path / "stats.json"), {"2026-08-18": {"topics": 3, "total_traffic": 9_000, "categories": {"x": 3}}})
    monkeypatch.setattr(bot, "STATS_FILE", str(tmp_path / "stats.json"))
    monkeypatch.setattr(bot, "BOT_TOKEN", "")
    monkeypatch.setattr(bot, "CHAT_ID", "")
    monkeypatch.setattr(bot.sys, "argv", ["bot.py", "--stats"])
    bot.run()
    assert "2026-08-18" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# CLI + helpers
# ---------------------------------------------------------------------------
def test_print_stats_empty(capsys):
    bot.print_stats({})
    out = capsys.readouterr().out
    assert "No stats recorded yet" in out


def test_print_stats_renders(capsys):
    stats = {
        "2026-08-12": {"topics": 9, "total_traffic": 128_500, "categories": {"⚽ Sports": 5}},
        "2026-08-13": {"topics": 11, "total_traffic": 204_300, "categories": {"🏛️ Politics": 6}},
    }
    bot.print_stats(stats)
    out = capsys.readouterr().out
    assert "2026-08-13" in out
    assert "128,500" in out
    assert "⚽ Sports" in out


def test_env_int_helpers(monkeypatch):
    assert bot._env_int("GHOSTIX_UNSET", 5) == 5
    monkeypatch.setenv("GHOSTIX_INT", "42")
    assert bot._env_int("GHOSTIX_INT", 5) == 42
    monkeypatch.setenv("GHOSTIX_BAD", "abc")
    assert bot._env_int("GHOSTIX_BAD", 5) == 5


def test_env_float_helper(monkeypatch):
    assert bot._env_float("GHOSTIX_FLOAT_UNSET", 1.5) == 1.5
    monkeypatch.setenv("GHOSTIX_FLOAT", "2.25")
    assert bot._env_float("GHOSTIX_FLOAT", 1.5) == 2.25


def test_version():
    assert bot.__version__ == "1.1.0"


import contextlib


@contextlib.contextmanager
def _fake_time(fixed):
    original = bot.time.time
    bot.time.time = lambda: fixed
    try:
        yield
    finally:
        bot.time.time = original