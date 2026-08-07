"""Plugin entry for astrbot_plugin_livingmemory_ext (customized fork).

Extends the upstream LivingMemory plugin with a "memory diary" feature:
at a configured time each day, today's memories stored by the upstream
plugin are summarized into a diary and sent to the configured group chat.
"""

from __future__ import annotations

import asyncio

from astrbot.api.star import Context, Star, register

# AstrBot loads plugins as `data.plugins.<plugin_dir>.main` (namespace package,
# plugin dir is NOT on sys.path), so intra-plugin imports must be relative —
# same style as the upstream LivingMemory plugin.
from .livingmemory_ext.diary_digest import (
    DiaryDigestScheduler,
    get_logger,
    merge_send_to_options,
)

logger = get_logger("astrbot_plugin_livingmemory_ext")

PLUGIN_NAME = "LivingMemory Ext"
PLUGIN_AUTHOR = "yulimfish"
PLUGIN_VERSION = "0.1.1"
PLUGIN_REPO = "https://github.com/yulimfish/astrbot_plugin_livingmemory_ext"

# Config-schema path to the rule `send_to` field whose `options` are injected
# at runtime with the live conversation-target list (drives the WebUI dropdown).
SCHEMA_SEND_TO_PATH = (
    "diary_digest",
    "items",
    "rules",
    "templates",
    "rule",
    "items",
    "send_to",
)
SCHEMA_SYNC_START_DELAY = 5.0
SCHEMA_SYNC_INTERVAL = 600.0


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
        try:
            self._schema_sync_task = asyncio.create_task(self._schema_options_loop())
        except RuntimeError as exc:
            logger.warning(
                "no running event loop, send_to options sync disabled: %s", exc
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

    # -- dynamic send_to dropdown options (WebUI config panel) ---------------

    async def _schema_options_loop(self) -> None:
        """Periodically refresh the send_to dropdown options in the config schema.

        The WebUI config panel serializes the in-memory ``config.schema`` on
        every fetch, so mutating its ``options``/``labels`` here makes the
        dropdown dynamic without touching any files.  The initial delay gives
        platform adapters time to connect after plugin load.
        """
        await asyncio.sleep(SCHEMA_SYNC_START_DELAY)
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
        send_to_schema = schema
        try:
            for key in SCHEMA_SEND_TO_PATH:
                send_to_schema = send_to_schema[key]
        except (KeyError, TypeError):
            return
        if not isinstance(send_to_schema, dict):
            return
        groups = await self._list_groups()
        options, labels = merge_send_to_options(
            self._configured_send_to_values(), groups
        )
        send_to_schema["options"] = options
        send_to_schema["labels"] = labels
        logger.info("synced %d send_to options into config schema", len(options))

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

    def _configured_send_to_values(self) -> list[str]:
        """Existing non-empty send_to values across all rules."""
        diary = self.config.get("diary_digest")
        rules = diary.get("rules") if isinstance(diary, dict) else None
        if not isinstance(rules, list):
            return []
        return [
            str(rule.get("send_to") or "").strip()
            for rule in rules
            if isinstance(rule, dict)
        ]

    async def _list_groups(self) -> list[dict]:
        """Enumerate groups visible to every connected platform adapter.

        aiocqhttp (OneBot v11) exposes ``get_client().get_group_list()``;
        adapters without a group-list API are skipped gracefully.
        """
        groups: list[dict] = []
        platform_manager = getattr(self.context, "platform_manager", None)
        if platform_manager is None:
            return groups
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
            get_group_list = getattr(client, "get_group_list", None)
            if not callable(get_group_list):
                continue
            try:
                group_list = await get_group_list()
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "failed to list groups for platform %s: %s", platform_id, exc
                )
                continue
            for group in group_list:
                group_id = str(group.get("group_id", "")).strip()
                if not group_id:
                    continue
                groups.append(
                    {
                        "platform_id": platform_id,
                        "group_id": group_id,
                        "group_name": str(group.get("group_name", "")).strip(),
                    }
                )
        return groups

    async def terminate(self):
        """Shut down the background tasks on plugin unload."""
        if self._schema_sync_task:
            self._schema_sync_task.cancel()
            try:
                await self._schema_sync_task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                logger.debug("send_to options sync task interrupted")
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
