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
from .livingmemory_ext.diary_digest import DiaryDigestScheduler, get_logger

logger = get_logger("astrbot_plugin_livingmemory_ext")

PLUGIN_NAME = "LivingMemory Ext"
PLUGIN_AUTHOR = "yulimfish"
PLUGIN_VERSION = "0.1.1"
PLUGIN_REPO = "https://github.com/yulimfish/astrbot_plugin_livingmemory_ext"


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
        self._register_web_apis()
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

    def _register_web_apis(self) -> None:
        """Register plugin Web APIs consumed by the plugin Pages (WebUI workspace)."""
        self.context.register_web_api(
            "/astrbot_plugin_livingmemory_ext/groups",
            self._web_api_groups,
            ["GET"],
            "列出当前所有平台适配器可见的群聊列表",
        )
        self.context.register_web_api(
            "/astrbot_plugin_livingmemory_ext/diary_rules",
            self._web_api_diary_rules,
            ["GET"],
            "列出当前日记发送规则（含已配置的发送目标）",
        )
        self.context.register_web_api(
            "/astrbot_plugin_livingmemory_ext/save_diary_target",
            self._web_api_save_diary_target,
            ["POST"],
            "保存指定日记规则的发送目标（平台 + 群号）",
        )

    async def _web_api_groups(self) -> dict:
        """Enumerate groups visible to every connected platform adapter.

        aiocqhttp (OneBot v11) exposes ``get_client().get_group_list()``;
        adapters without a group-list API are skipped gracefully.
        """
        groups: list[dict] = []
        for platform in self.context.platform_manager.platform_insts:
            try:
                platform_id = platform.meta().id
            except Exception as exc:  # noqa: BLE001
                logger.debug("cannot resolve platform id: %s", exc)
                continue
            client = getattr(platform, "get_client", lambda: None)()
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
        return {"status": "ok", "data": groups}

    async def _web_api_diary_rules(self) -> dict:
        """Return the current diary rules (index, name, platform, send_to)."""
        diary = self.config.get("diary_digest") or {}
        rules = diary.get("rules") or []
        data = []
        for idx, rule in enumerate(rules):
            data.append(
                {
                    "index": idx,
                    "name": rule.get("name", ""),
                    "enabled": bool(rule.get("enabled", True)),
                    "platform": rule.get("platform", ""),
                    "send_to": rule.get("send_to", ""),
                }
            )
        return {"status": "ok", "data": data}

    async def _web_api_save_diary_target(self) -> dict:
        """Persist the selected platform + group into a rule's config."""
        from astrbot.api.web import request

        payload = await request.json()
        try:
            rule_index = int(payload.get("rule_index", -1))
        except (TypeError, ValueError):
            rule_index = -1
        platform_id = str(payload.get("platform_id", "")).strip()
        group_id = str(payload.get("group_id", "")).strip()

        diary = self.config.get("diary_digest")
        if not isinstance(diary, dict):
            return {"status": "error", "message": "diary_digest 配置缺失"}
        rules = diary.get("rules") or []
        if rule_index < 0 or rule_index >= len(rules):
            return {"status": "error", "message": "规则索引无效"}
        rules[rule_index]["platform"] = platform_id or "aiocqhttp"
        rules[rule_index]["send_to"] = group_id
        self.config.save_config()
        logger.info(
            "diary rule %d target saved: platform=%s group=%s",
            rule_index,
            rules[rule_index]["platform"],
            group_id,
        )
        return {
            "status": "ok",
            "message": "发送目标已保存，调度器下轮自动生效",
        }

    async def terminate(self):
        """Shut down the background scheduler on plugin unload."""
        if self._scheduler_start_task:
            try:
                await self._scheduler_start_task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                logger.debug("diary scheduler start task interrupted")
            self._scheduler_start_task = None
        if self._scheduler:
            await self._scheduler.stop()
            self._scheduler = None
