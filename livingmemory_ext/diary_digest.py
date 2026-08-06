"""Memory diary digest: schedule, fetch, summarize and send daily memories.

The plugin reads the memory database written by the upstream
`astrbot_plugin_livingmemory` plugin (read-only), summarizes today's
memories with the configured LLM provider, and sends the diary to the
target group chat at the configured time. Multiple rules (scope + time +
send target) are supported.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import aiofiles
import aiosqlite

logger = logging.getLogger("livingmemory_ext.diary_digest")

UPSTREAM_PLUGIN_NAME = "astrbot_plugin_livingmemory"
UPSTREAM_DB_FILE = "livingmemory.db"
PLUGIN_NAME = "astrbot_plugin_livingmemory_ext"
STATE_FILE = "diary_last_run.json"

GROUP_UMO_KEY = "GroupMessage"
PRIVATE_UMO_KEY = "PrivateMessage"
DEFAULT_PLATFORM = "aiocqhttp"

# Keep in sync with the "diary_digest.prompt" default in _conf_schema.json:
# the schema ships the same built-in prompt for first-time installs.
DEFAULT_DIARY_PROMPT = (
    "你正在把用户今天的长期记忆整理成一篇日记。"
    "这是一篇日记，请以第一人称、自然温暖的笔触记录今天发生的重要事情、"
    "遇见的人、情绪变化与感悟，写成连贯的段落而不是分条列举。"
    "写作时请融入你当前的 AstrBot 人设的性格与语气。"
    "请直接输出日记正文，不要输出任何额外说明。"
)

_MEMORY_QUERY_SQL = """
SELECT text, metadata FROM documents
WHERE CAST(json_extract(metadata, '$.create_time') AS REAL) BETWEEN ? AND ?
  AND COALESCE(json_extract(metadata, '$.status'), 'active') = 'active'
  {scope_filter}
ORDER BY CAST(json_extract(metadata, '$.create_time') AS REAL) ASC
"""

REQUIRED_COLUMNS = frozenset({"text", "metadata"})


# ---------------------------------------------------------------------------
# Pure helpers (unit-testable without an AstrBot runtime)
# ---------------------------------------------------------------------------


def parse_hhmm(value: Any) -> tuple[int, int] | None:
    """Parse an 'HH:MM' string into (hour, minute), or None if invalid."""
    if not isinstance(value, str):
        return None
    parts = value.strip().split(":")
    if len(parts) != 2:
        return None
    try:
        hour, minute = int(parts[0]), int(parts[1])
    except ValueError:
        return None
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return hour, minute


def seconds_until_next_run(time_str: str, now: datetime | None = None) -> float:
    """Seconds until the next occurrence of the HH:MM time (next day if passed)."""
    now = now or datetime.now()
    parsed = parse_hhmm(time_str)
    if parsed is None:
        return 24 * 3600.0
    hour, minute = parsed
    next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    delta = (next_run - now).total_seconds()
    if delta <= 0:
        delta += 24 * 3600.0
    return delta


def is_due(rule: dict, now: datetime, last_run_date: str | None = None) -> bool:
    """True if the rule's HH:MM target has passed today and it has not run today."""
    parsed = parse_hhmm(rule.get("time") or "")
    if parsed is None:
        return False
    hour, minute = parsed
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if now < target:
        return False
    return (last_run_date or "") != now.date().isoformat()


def today_range(now: datetime | None = None) -> tuple[float, float]:
    """Epoch timestamp range [start of today, now) in local time."""
    now = now or datetime.now()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return start.timestamp(), now.timestamp()


def build_scope_like(scope: str, platform: str, target: str) -> str | None:
    """SQL LIKE pattern for the session_id scope filter, or None for 'all'."""
    scope = (scope or "all").strip().lower()
    target = (target or "").strip()
    if scope == "all":
        return None
    if scope == "group":
        if not target:
            return None
        return f"{platform}:{GROUP_UMO_KEY}:{target}%"
    if scope == "friend":
        if not target:
            return None
        return f"{platform}:{PRIVATE_UMO_KEY}:{target}%"
    return None


def build_target_umo(rule: dict) -> str:
    """Unified message origin of the diary's send target (group chat)."""
    send_to = (rule.get("send_to") or "").strip()
    if not send_to:
        return ""
    if ":" in send_to:
        return send_to
    platform = (rule.get("platform") or DEFAULT_PLATFORM).strip()
    return f"{platform}:{GROUP_UMO_KEY}:{send_to}"


async def fetch_day_memories(
    db_path: Path,
    start_ts: float,
    end_ts: float,
    scope_like: str | None = None,
) -> list[dict]:
    """Fetch today's active memories from the upstream database (read-only)."""
    if not Path(db_path).exists():
        return []
    sql = _MEMORY_QUERY_SQL.format(
        scope_filter="AND json_extract(metadata, '$.session_id') LIKE ?"
        if scope_like
        else ""
    )
    params: list = [start_ts, end_ts]
    if scope_like:
        params.append(scope_like)
    try:
        uri = f"{Path(db_path).resolve().as_uri()}?mode=ro"
        async with aiosqlite.connect(uri, uri=True) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA busy_timeout = 5000")
            problem = await _validate_schema(db)
            if problem:
                logger.error(
                    "[DiaryDigest] upstream memory database schema mismatch at %s: %s; "
                    "upstream LivingMemory may have been upgraded — diary skipped",
                    db_path,
                    problem,
                )
                return []
            cursor = await db.execute(sql, params)
            rows = await cursor.fetchall()
            await cursor.close()
        return [dict(row) for row in rows]
    except Exception as exc:  # noqa: BLE001 - degrade gracefully
        logger.error(
            "[DiaryDigest] failed to fetch day memories from %s: %s", db_path, exc
        )
        return []


async def _validate_schema(db) -> str | None:
    """Return a description of a missing table/columns, or None if usable."""
    tables = await db.execute_fetchall(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='documents'"
    )
    if not tables:
        return "table 'documents' not found"
    columns = await db.execute_fetchall("PRAGMA table_info(documents)")
    names = {row["name"] for row in columns}
    missing = REQUIRED_COLUMNS - names
    if missing:
        return f"missing columns: {', '.join(sorted(missing))}"
    return None


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------


class DiaryDigestScheduler:
    """Background scheduler running every enabled diary rule at its time."""

    def __init__(self, context: Any, config: dict):
        self.context = context
        self.config = config
        self._running = False
        self._stopped = False
        self._task: asyncio.Task | None = None
        self._run_tasks: set[asyncio.Task] = set()
        self._last_run: dict[str, str] = {}

    # -- lifecycle ----------------------------------------------------------

    async def start(self) -> None:
        if self._running or self._stopped:
            return
        self._running = True
        await self._load_last_run()
        self._task = asyncio.create_task(self._scheduler_loop())
        logger.info("[DiaryDigest] scheduler started")

    async def stop(self) -> None:
        logger.info("[DiaryDigest] scheduler stopping")
        self._running = False
        self._stopped = True
        for task in list(self._run_tasks):
            task.cancel()
        if self._run_tasks:
            await asyncio.gather(*self._run_tasks, return_exceptions=True)
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            except Exception:  # pragma: no cover - defensive  # noqa: BLE001
                logger.debug("[DiaryDigest] diary scheduler task stopped with error")
            self._task = None

    # -- internals ----------------------------------------------------------

    def _diary_config(self) -> dict:
        diary = self.config.get("diary_digest")
        return diary if isinstance(diary, dict) else {}

    def _rules(self) -> list[dict]:
        rules = self._diary_config().get("rules") or []
        return [
            rule
            for rule in rules
            if isinstance(rule, dict) and rule.get("enabled", True)
        ]

    async def _scheduler_loop(self) -> None:
        while self._running:
            try:
                rules = self._rules()
                if not rules:
                    await asyncio.sleep(3600)
                    continue
                now = datetime.now()
                wait = 24 * 3600.0
                changed = False
                occurrences: dict[str, int] = {}
                for rule in rules:
                    time_str = rule.get("time") or ""
                    if parse_hhmm(time_str) is None:
                        logger.warning(
                            "[DiaryDigest] diary rule %s has invalid time %r, skipped",
                            rule.get("name") or "unnamed",
                            time_str,
                        )
                        continue
                    key = self._rule_key(rule)
                    nth = occurrences.get(key, 0)
                    occurrences[key] = nth + 1
                    if nth:
                        key = f"{key}#{nth}"
                    if is_due(rule, now, self._last_run.get(key)):
                        self._spawn_run(rule)
                        self._last_run[key] = now.date().isoformat()
                        changed = True
                    wait = min(wait, seconds_until_next_run(time_str, now))
                if changed:
                    await self._save_last_run()
                await asyncio.sleep(max(1.0, wait))
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("[DiaryDigest] diary scheduler loop error")
                await asyncio.sleep(3600)

    @staticmethod
    def _rule_key(rule: dict) -> str:
        """Stable per-rule identity, persisted across plugin reloads."""
        template_key = str(rule.get("__template_key") or "").strip()
        if template_key:
            return template_key
        name = rule.get("name") or ""
        scope = rule.get("scope") or ""
        platform = rule.get("platform") or ""
        target = rule.get("scope_target") or ""
        time_str = rule.get("time") or ""
        return f"custom|{name}|{scope}|{platform}|{target}|{time_str}"

    def _spawn_run(self, rule: dict) -> None:
        task = asyncio.create_task(self._safe_run(rule))
        self._run_tasks.add(task)
        task.add_done_callback(self._run_tasks.discard)

    def _state_path(self) -> Path:
        """Last-run state file lives in the plugin data dir (data/)."""
        try:
            from astrbot.api.star import StarTools

            return Path(StarTools.get_data_dir(PLUGIN_NAME)) / STATE_FILE
        except Exception:  # pragma: no cover - astrbot unavailable  # noqa: BLE001
            logger.warning(
                "[DiaryDigest] cannot resolve plugin data dir, falling back to ./data"
            )
            return Path("data") / STATE_FILE

    async def _load_last_run(self, path: Path | None = None) -> None:
        path = path or self._state_path()
        try:
            async with aiofiles.open(path, "r", encoding="utf-8") as f:
                raw = await f.read()
            data = json.loads(raw)
            self._last_run = {
                str(key): str(value)
                for key, value in data.items()
                if isinstance(value, str)
            }
        except FileNotFoundError:
            pass
        except Exception as exc:  # noqa: BLE001
            logger.warning("[DiaryDigest] failed to load diary last-run state: %s", exc)

    async def _save_last_run(self, path: Path | None = None) -> None:
        path = path or self._state_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            async with aiofiles.open(path, "w", encoding="utf-8") as f:
                await f.write(json.dumps(self._last_run, ensure_ascii=False, indent=2))
        except Exception as exc:  # noqa: BLE001
            logger.warning("[DiaryDigest] failed to save diary last-run state: %s", exc)

    async def _safe_run(self, rule: dict) -> None:
        """Run one rule with full error isolation."""
        name = rule.get("name") or "unnamed"
        try:
            await self._run_rule(rule)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("[DiaryDigest] diary rule %s failed", name)

    async def _run_rule(self, rule: dict) -> None:
        name = rule.get("name") or "unnamed"
        if not build_target_umo(rule):
            logger.warning(
                "[DiaryDigest] diary rule %s has empty send target, skip", name
            )
            return
        logger.info("[DiaryDigest] running diary rule: %s", name)
        memories = await self._fetch_memories(rule)
        if not memories:
            logger.info("[DiaryDigest] no memories found for diary rule %s, skip", name)
            return
        diary = await self._summarize(rule, memories)
        if not diary:
            logger.warning(
                "[DiaryDigest] diary summary empty for rule %s, skip send", name
            )
            return
        await self._send(rule, diary)

    async def _fetch_memories(self, rule: dict) -> list[dict]:
        db_path = self._resolve_db_path()
        logger.info("[DiaryDigest] reading memories from %s", db_path)
        scope_like = build_scope_like(
            rule.get("scope") or "all",
            (rule.get("platform") or DEFAULT_PLATFORM).strip(),
            rule.get("scope_target") or "",
        )
        if scope_like is None and (rule.get("scope") or "all") != "all":
            logger.warning(
                "[DiaryDigest] diary rule %s has invalid scope target, skip",
                rule.get("name") or "unnamed",
            )
            return []
        start_ts, end_ts = today_range()
        memories = await fetch_day_memories(db_path, start_ts, end_ts, scope_like)
        logger.info(
            "[DiaryDigest] fetched %d memories for rule %s",
            len(memories),
            rule.get("name") or "unnamed",
        )
        return memories

    def _resolve_db_path(self) -> Path:
        configured = (self._diary_config().get("memory_db_path") or "").strip()
        if configured:
            return Path(configured)
        try:
            from astrbot.api.star import StarTools

            base = StarTools.get_data_dir(UPSTREAM_PLUGIN_NAME)
            return Path(base) / UPSTREAM_DB_FILE
        except Exception as exc:  # noqa: BLE001
            logger.warning("[DiaryDigest] cannot resolve upstream data dir: %s", exc)
            return Path(UPSTREAM_DB_FILE)

    async def _summarize(self, rule: dict, memories: list[dict]) -> str:
        diary_cfg = self._diary_config()
        prompt = (diary_cfg.get("prompt") or "").strip() or DEFAULT_DIARY_PROMPT
        persona_prompt = await self._get_persona_prompt(rule)
        system_prompt = prompt
        if persona_prompt:
            system_prompt = f"{prompt}\n\n当前 AstrBot 人设：\n{persona_prompt}"

        lines = []
        for index, memory in enumerate(memories, 1):
            text = (memory.get("text") or "").strip()
            if not text:
                continue
            meta = self._safe_load_json(memory.get("metadata"))
            time_str = ""
            create_time = meta.get("create_time")
            if isinstance(create_time, (int, float)):
                try:
                    time_str = datetime.fromtimestamp(create_time).strftime("%H:%M")
                except (OSError, ValueError, OverflowError):
                    time_str = ""
            lines.append(f"{index}. [{time_str}] {text}")
        if not lines:
            return ""
        memory_text = "\n".join(lines)
        today = datetime.now().strftime("%Y-%m-%d")
        user_prompt = (
            f"以下是今天（{today}）收集到的记忆：\n\n{memory_text}\n\n"
            "请根据这些记忆写一篇日记。"
        )
        provider = self._get_provider(diary_cfg.get("llm_provider_id") or "")
        if provider is None:
            logger.warning(
                "[DiaryDigest] no LLM provider available for diary rule %s",
                rule.get("name"),
            )
            return ""
        try:
            resp = await provider.text_chat(
                prompt=user_prompt, system_prompt=system_prompt
            )
            return str(getattr(resp, "completion_text", "") or "").strip()
        except Exception:
            logger.exception("[DiaryDigest] LLM summarize failed")
            return ""

    @staticmethod
    def _safe_load_json(raw: Any) -> dict:
        if isinstance(raw, dict):
            return raw
        try:
            loaded = json.loads(raw or "{}")
            return loaded if isinstance(loaded, dict) else {}
        except (json.JSONDecodeError, TypeError, ValueError):
            return {}

    def _get_provider(self, provider_id: str):
        if provider_id:
            try:
                provider = self.context.get_provider_by_id(provider_id)
                if provider is not None:
                    return provider
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "[DiaryDigest] provider %s unavailable: %s", provider_id, exc
                )
        try:
            return self.context.get_using_provider()
        except Exception as exc:  # noqa: BLE001
            logger.warning("[DiaryDigest] cannot get using provider: %s", exc)
            return None

    async def _get_persona_prompt(self, rule: dict) -> str:
        """Inject the current AstrBot persona system prompt, if resolvable."""
        try:
            persona_manager = getattr(self.context, "persona_manager", None)
            if persona_manager is None:
                return ""
            umo = build_target_umo(rule)
            default = await persona_manager.get_default_persona_v3(umo=umo)
            if isinstance(default, dict):
                persona_id = default.get("name")
            else:
                persona_id = getattr(default, "name", None)
            if not persona_id:
                return ""
            persona = await persona_manager.get_persona(persona_id)
            return str(getattr(persona, "system_prompt", "") or "")
        except Exception as exc:  # noqa: BLE001
            logger.debug("[DiaryDigest] failed to resolve persona prompt: %s", exc)
            return ""

    async def _send(self, rule: dict, diary: str) -> None:
        umo = build_target_umo(rule)
        if not umo:
            logger.warning(
                "[DiaryDigest] diary rule %s has empty send target, skip",
                rule.get("name") or "unnamed",
            )
            return
        try:
            from astrbot.api.event import MessageChain

            await self.context.send_message(umo, MessageChain().message(diary))
            logger.info("[DiaryDigest] diary sent to %s", umo)
        except Exception:
            logger.exception("[DiaryDigest] failed to send diary to %s", umo)
