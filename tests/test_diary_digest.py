import asyncio
import json
import sqlite3
from datetime import datetime, timedelta

from livingmemory_ext.diary_digest import (
    DiaryDigestScheduler,
    build_scope_like,
    build_target_umo,
    fetch_day_memories,
    is_due,
    parse_hhmm,
    seconds_until_next_run,
    today_range,
)

SCHEMA = """
CREATE TABLE documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id TEXT NOT NULL,
    text TEXT NOT NULL,
    metadata TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def _make_db(path, rows):
    conn = sqlite3.connect(path)
    conn.execute(SCHEMA)
    for doc_id, text, meta in rows:
        conn.execute(
            "INSERT INTO documents (doc_id, text, metadata, created_at, updated_at) "
            "VALUES (?, ?, ?, datetime('now'), datetime('now'))",
            (doc_id, text, json.dumps(meta)),
        )
    conn.commit()
    conn.close()


def test_parse_hhmm():
    assert parse_hhmm("22:00") == (22, 0)
    assert parse_hhmm("9:05") == (9, 5)
    assert parse_hhmm(" 23:59 ") == (23, 59)
    assert parse_hhmm("25:00") is None
    assert parse_hhmm("22:60") is None
    assert parse_hhmm("abc") is None
    assert parse_hhmm("") is None
    assert parse_hhmm(None) is None
    assert parse_hhmm(2200) is None


def test_seconds_until_next_run():
    now = datetime(2026, 8, 7, 20, 0, 0)
    later_today = seconds_until_next_run("22:00", now)
    assert 7199 < later_today <= 7200
    earlier = seconds_until_next_run("08:00", now)
    assert 43199 < earlier <= 43200


def test_today_range():
    start_ts, end_ts = today_range(datetime(2026, 8, 7, 15, 30, 0))
    start_dt = datetime.fromtimestamp(start_ts)
    end_dt = datetime.fromtimestamp(end_ts)
    assert start_dt.hour == 0 and start_dt.minute == 0
    assert end_dt.hour == 15 and end_dt.minute == 30
    assert start_ts <= end_ts


def test_is_due():
    now = datetime(2026, 8, 7, 22, 30, 0)
    rule = {"time": "22:00"}
    assert is_due(rule, now) is True
    assert is_due(rule, now, "2026-08-07") is False
    assert is_due(rule, now, "2026-08-06") is True
    early = datetime(2026, 8, 7, 21, 0, 0)
    assert is_due(rule, early) is False
    assert is_due({"time": "bad"}, now) is False
    assert is_due({}, now) is False


def test_rule_key_stable():
    assert DiaryDigestScheduler._rule_key({"__template_key": "rule_1"}) == "rule_1"
    fallback = DiaryDigestScheduler._rule_key(
        {
            "name": "A",
            "scope": "group",
            "platform": "aiocqhttp",
            "scope_target": "123",
            "time": "22:00",
        }
    )
    assert "custom|A|group|aiocqhttp|123|22:00" == fallback
    assert fallback == DiaryDigestScheduler._rule_key(
        {
            "name": "A",
            "scope": "group",
            "platform": "aiocqhttp",
            "scope_target": "123",
            "time": "22:00",
        }
    )


def test_state_roundtrip(tmp_path):
    path = tmp_path / "diary_last_run.json"
    scheduler = DiaryDigestScheduler(None, {})
    asyncio.run(scheduler._load_last_run(path))
    assert scheduler._last_run == {}
    scheduler._last_run = {"rule_1": "2026-08-07"}
    asyncio.run(scheduler._save_last_run(path))
    scheduler._last_run = {}
    asyncio.run(scheduler._load_last_run(path))
    assert scheduler._last_run == {"rule_1": "2026-08-07"}


def test_state_corrupted(tmp_path):
    path = tmp_path / "diary_last_run.json"
    path.write_text("{not json")
    scheduler = DiaryDigestScheduler(None, {})
    asyncio.run(scheduler._load_last_run(path))
    assert scheduler._last_run == {}


def test_build_scope_like():
    assert build_scope_like("all", "aiocqhttp", "") is None
    assert build_scope_like("", "aiocqhttp", "") is None
    assert (
        build_scope_like("group", "aiocqhttp", "123") == "aiocqhttp:GroupMessage:123%"
    )
    assert (
        build_scope_like("friend", "telegram", "999") == "telegram:PrivateMessage:999%"
    )
    assert build_scope_like("group", "aiocqhttp", "") is None
    assert build_scope_like("unknown", "aiocqhttp", "1") is None


def test_build_target_umo():
    assert build_target_umo({"send_to": "123456"}) == "aiocqhttp:GroupMessage:123456"
    assert (
        build_target_umo({"send_to": "123456", "platform": "telegram"})
        == "telegram:GroupMessage:123456"
    )
    assert (
        build_target_umo({"send_to": "aiocqhttp:GroupMessage:123"})
        == "aiocqhttp:GroupMessage:123"
    )
    assert build_target_umo({"send_to": ""}) == ""
    assert build_target_umo({"send_to": "  "}) == ""


def test_fetch_day_memories(tmp_path):
    now = datetime.now()
    start_ts, end_ts = today_range(now)
    yesterday_ts = (now - timedelta(days=1)).timestamp()
    today_ts = now.timestamp() - 60

    db = tmp_path / "livingmemory.db"
    _make_db(
        db,
        [
            (
                "m1",
                "早上和群友讨论了新插件",
                {
                    "create_time": today_ts,
                    "session_id": "aiocqhttp:GroupMessage:123",
                    "status": "active",
                },
            ),
            (
                "m2",
                "下午完成了代码",
                {
                    "create_time": today_ts,
                    "session_id": "aiocqhttp:GroupMessage:456",
                    "status": "active",
                },
            ),
            (
                "m3",
                "归档的记忆",
                {
                    "create_time": today_ts,
                    "session_id": "aiocqhttp:GroupMessage:123",
                    "status": "archived",
                },
            ),
            (
                "m4",
                "昨天的记忆",
                {
                    "create_time": yesterday_ts,
                    "session_id": "aiocqhttp:GroupMessage:123",
                    "status": "active",
                },
            ),
        ],
    )

    all_rows = asyncio.run(fetch_day_memories(db, start_ts, end_ts))
    assert [r["text"] for r in all_rows] == ["早上和群友讨论了新插件", "下午完成了代码"]

    group_rows = asyncio.run(
        fetch_day_memories(db, start_ts, end_ts, "aiocqhttp:GroupMessage:123%")
    )
    assert [r["text"] for r in group_rows] == ["早上和群友讨论了新插件"]

    missing = asyncio.run(fetch_day_memories(tmp_path / "nope.db", start_ts, end_ts))
    assert missing == []


def test_fetch_from_wal_db_with_open_writer(tmp_path):
    """Read-only read while the writer connection stays open (WAL, not checkpointed)."""
    db = tmp_path / "wal.db"
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute(SCHEMA)
    ts = datetime.now().timestamp() - 60
    conn.execute(
        "INSERT INTO documents (doc_id, text, metadata, created_at, updated_at) "
        "VALUES (?, ?, ?, datetime('now'), datetime('now'))",
        (
            "m1",
            "WAL 模式下的记忆",
            json.dumps(
                {
                    "create_time": ts,
                    "session_id": "aiocqhttp:GroupMessage:123",
                    "status": "active",
                }
            ),
        ),
    )
    conn.commit()
    start_ts, end_ts = today_range(datetime.now())
    try:
        rows = asyncio.run(fetch_day_memories(db, start_ts, end_ts))
        assert [r["text"] for r in rows] == ["WAL 模式下的记忆"]
    finally:
        conn.close()
