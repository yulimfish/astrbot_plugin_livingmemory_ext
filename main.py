"""Plugin entry for astrbot_plugin_livingmemory_ext (customized fork).

Extends the upstream LivingMemory plugin with a "memory diary" feature:
at a configured time each day, today's memories stored by the upstream
plugin are summarized into a diary and sent to the configured group chat.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register

# AstrBot loads plugins as `data.plugins.<plugin_dir>.main` (namespace package,
# plugin dir is NOT on sys.path), so intra-plugin imports must be relative —
# same style as the upstream LivingMemory plugin.
from .livingmemory_ext.diary_digest import (
    DiaryDigestScheduler,
    get_logger,
    merge_target_options,
)
from .livingmemory_ext.target_cache import (
    event_to_conversation,
    load_conversations,
    merge_conversation,
    save_conversations,
)

logger = get_logger("astrbot_plugin_livingmemory_ext")

PLUGIN_NAME = "LivingMemory Ext"
PLUGIN_AUTHOR = "yulimfish"
PLUGIN_VERSION = "0.1.1"
PLUGIN_REPO = "https://github.com/yulimfish/astrbot_plugin_livingmemory_ext"

# Config-schema paths to the rule `send_to` / `scope_target` fields whose
# `options` are injected at runtime with the live conversation-target list
# (drives the WebUI dropdown).
SCHEMA_SEND_TO_PATH = (
    "diary_digest",
    "items",
    "rules",
    "templates",
    "rule",
    "items",
    "send_to",
)
SCHEMA_SCOPE_TARGET_PATH = (
    "diary_digest",
    "items",
    "rules",
    "templates",
    "rule",
    "items",
    "scope_target",
)
SCHEMA_SYNC_START_DELAY = 5.0
SCHEMA_SYNC_INTERVAL = 600.0
QQOFFICIAL_TARGETS_FILE = "qqofficial_targets.json"


@register(
    PLUGIN_NAME,
    PLUGIN_AUTHOR,
    "定时总结当日长期记忆并以日记形式发送到指定群聊（上游 LivingMemory 定制化拓展）",
    PLUGIN_VERSION,
    PLUGIN_REPO,
)
class LivingMemoryExtPlugin(Star):
    def __init__(self, context: Context, config):
        super().__init__(context)
        self.config = config
        self._scheduler: DiaryDigestScheduler | None = None
        self._scheduler_start_task: asyncio.Task | None = None
        self._schema_sync_task: asyncio.Task | None = None
        self._target_cache_load_task: asyncio.Task | None = None
        self._target_cache_lock = asyncio.Lock()
        self._target_cache_loaded = False
        self._qqofficial_targets: list[dict[str, str]] = []
        try:
            self._target_cache_load_task = asyncio.create_task(
                self._load_qqofficial_targets()
            )
            self._schema_sync_task = asyncio.create_task(self._schema_options_loop())
        except RuntimeError as exc:
            logger.warning(
                "no running event loop, schema options sync disabled: %s", exc
            )
            self._schema_sync_task = None
        diary = config.get("diary_digest")
        if isinstance(diary, dict) and diary.get("enabled", False):
            self._scheduler = DiaryDigestScheduler(context, config)
            try:
                self._scheduler_start_task = asyncio.create_task(
                    self._scheduler.start()
                )
            except RuntimeError as exc:
                logger.warning(
                    "no running event loop, diary scheduler disabled: %s", exc
                )
                self._scheduler_start_task = None

    # -- dynamic conversation-target dropdown options (WebUI config panel) ---

    async def _schema_options_loop(self) -> None:
        """Periodically refresh the dropdown options in the config schema.

        The WebUI config panel serializes the in-memory ``config.schema`` on
        every fetch, so mutating its ``options``/``labels`` here makes the
        dropdown dynamic without touching any files.  The initial delay gives
        platform adapters time to connect after plugin load.
        """
        await asyncio.sleep(SCHEMA_SYNC_START_DELAY)
        await self._await_target_cache_load()
        while True:
            try:
                await self._sync_schema_options()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("failed to sync send_to options")
            await asyncio.sleep(SCHEMA_SYNC_INTERVAL)

    async def _sync_schema_options(self) -> None:
        """Inject the live conversation-target list into the rule schema."""
        schema = getattr(self.config, "schema", None)
        if not isinstance(schema, dict):
            return
        if self._normalize_legacy_send_to():
            try:
                self.config.save_config()
            except Exception as exc:  # noqa: BLE001 - persistence best effort
                logger.warning("failed to persist normalized send_to values: %s", exc)
        conversations = await self._list_conversations()
        conversations.extend(getattr(self, "_qqofficial_targets", []))
        self._inject_field_options(
            schema,
            SCHEMA_SEND_TO_PATH,
            self._configured_values("send_to"),
            conversations,
            kinds=("group",),
        )
        self._inject_field_options(
            schema,
            SCHEMA_SCOPE_TARGET_PATH,
            self._configured_values("scope_target"),
            conversations,
            kinds=("group", "friend"),
        )
        if conversations:
            logger.info(
                "synced %d conversation options into config schema",
                len(conversations),
            )
        else:
            logger.warning(
                "no conversations resolved from any platform; dropdown options "
                "will stay empty (check adapter connectivity / platform config)"
            )

    def _inject_field_options(
        self,
        schema: dict,
        path: tuple[str, ...],
        configured_values: list[str],
        conversations: list[dict],
        kinds: tuple[str, ...],
    ) -> None:
        """Inject ``options``/``labels`` for one rule field at ``path``."""
        field_schema = schema
        try:
            for key in path:
                field_schema = field_schema[key]
        except (KeyError, TypeError):
            return
        if not isinstance(field_schema, dict):
            return
        options, labels = merge_target_options(configured_values, conversations, kinds)
        field_schema["options"] = options
        field_schema["labels"] = labels

    # -- QQ Official observed-target cache ---------------------------------

    def _qqofficial_targets_path(self) -> Path:
        """Resolve the data/ path used for QQ Official group-openid targets."""
        try:
            from astrbot.api.star import StarTools

            return Path(StarTools.get_data_dir(PLUGIN_NAME)) / QQOFFICIAL_TARGETS_FILE
        except Exception:  # noqa: BLE001 - AstrBot runtime absent
            return Path("data") / QQOFFICIAL_TARGETS_FILE

    async def _load_qqofficial_targets(self) -> None:
        self._qqofficial_targets = await load_conversations(
            self._qqofficial_targets_path()
        )
        self._target_cache_loaded = True

    async def _await_target_cache_load(self) -> None:
        task = self._target_cache_load_task
        if task is not None and task is not asyncio.current_task():
            try:
                await task
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - cache must not break plugin
                logger.warning("failed to load QQ Official target cache: %s", exc)
        elif not self._target_cache_loaded:
            await self._load_qqofficial_targets()

    async def _save_qqofficial_targets(self) -> None:
        try:
            await save_conversations(
                self._qqofficial_targets_path(), self._qqofficial_targets
            )
        except Exception as exc:  # noqa: BLE001 - cache persistence is best effort
            logger.warning("failed to save QQ Official target cache: %s", exc)

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    @filter.platform_adapter_type(
        filter.PlatformAdapterType.QQOFFICIAL
        | filter.PlatformAdapterType.QQOFFICIAL_WEBHOOK
    )
    async def capture_qqofficial_target(self, event: AstrMessageEvent) -> None:
        """Remember QQ Official group-openids because its API cannot list groups."""
        try:
            await self._remember_qqofficial_target(event)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("failed to capture QQ Official conversation target")

    async def _remember_qqofficial_target(self, event: AstrMessageEvent) -> None:
        conversation = event_to_conversation(event)
        if conversation is None:
            return
        await self._await_target_cache_load()
        async with self._target_cache_lock:
            targets, changed = merge_conversation(
                self._qqofficial_targets, conversation
            )
            if not changed:
                return
            self._qqofficial_targets = targets
            await self._save_qqofficial_targets()
        await self._sync_schema_options()

    def _normalize_legacy_send_to(self) -> bool:
        """Rewrite legacy "bare group id + platform" rules into merged format.

        The WebUI config panel submits the form against the new schema, which
        no longer has a ``platform`` field — saving would silently drop the
        legacy value and the diary would fall back to the default platform.
        Normalize once at startup so persistence keeps working.
        """
        diary = self.config.get("diary_digest")
        rules = diary.get("rules") if isinstance(diary, dict) else None
        if not isinstance(rules, list):
            return False
        changed = False
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            send_to = str(rule.get("send_to") or "").strip()
            platform = str(rule.get("platform") or "").strip()
            if not send_to or ":" in send_to or not platform:
                continue
            rule["send_to"] = f"{platform}:{send_to}"
            rule.pop("platform", None)
            changed = True
        return changed

    def _configured_values(self, field: str) -> list[str]:
        """Existing non-empty values of a rule field across all rules."""
        diary = self.config.get("diary_digest")
        rules = diary.get("rules") if isinstance(diary, dict) else None
        if not isinstance(rules, list):
            return []
        return [
            str(rule.get(field) or "").strip()
            for rule in rules
            if isinstance(rule, dict)
        ]

    async def _list_conversations(self) -> list[dict]:
        """Enumerate conversations (groups + friends) of every connected platform.

        aiocqhttp (OneBot v11) exposes ``get_client().get_group_list()`` and
        ``get_client().get_friend_list()``; adapters without these APIs are
        skipped gracefully.
        """
        conversations: list[dict] = []
        platform_manager = getattr(self.context, "platform_manager", None)
        if platform_manager is None:
            return conversations
        for platform in platform_manager.platform_insts:
            try:
                platform_id = platform.meta().id
            except Exception as exc:  # noqa: BLE001
                logger.debug("cannot resolve platform id: %s", exc)
                continue
            try:
                client = platform.get_client()
            except Exception as exc:  # noqa: BLE001
                logger.debug("cannot get client for platform %s: %s", platform_id, exc)
                continue
            await self._append_client_conversations(
                conversations, platform_id, client, "get_group_list", "group"
            )
            await self._append_client_conversations(
                conversations, platform_id, client, "get_friend_list", "friend"
            )
        return conversations

    async def _append_client_conversations(
        self,
        conversations: list[dict],
        platform_id: str,
        client: Any,
        method_name: str,
        kind: str,
    ) -> None:
        """Append conversations returned by one client method, guarded."""
        method = getattr(client, method_name, None)
        if not callable(method):
            return
        try:
            items = await method()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "failed to list %s for platform %s: %s", kind, platform_id, exc
            )
            return
        for item in items:
            target_id = str(item.get("group_id", item.get("user_id", ""))).strip()
            if not target_id:
                continue
            display_name = str(item.get("group_name", item.get("nickname", ""))).strip()
            conversations.append(
                {
                    "platform_id": platform_id,
                    "target_id": target_id,
                    "display_name": display_name,
                    "kind": kind,
                }
            )

    async def terminate(self):
        """Shut down the background tasks on plugin unload."""
        if self._target_cache_load_task:
            self._target_cache_load_task.cancel()
            try:
                await self._target_cache_load_task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                logger.debug("QQ Official target-cache task interrupted")
            self._target_cache_load_task = None
        if self._schema_sync_task:
            self._schema_sync_task.cancel()
            try:
                await self._schema_sync_task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                logger.debug("schema options sync task interrupted")
            self._schema_sync_task = None
        if self._scheduler_start_task:
            try:
                await self._scheduler_start_task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                logger.debug("diary scheduler start task interrupted")
            self._scheduler_start_task = None
        if self._scheduler:
            await self._scheduler.stop()
            self._scheduler = None
