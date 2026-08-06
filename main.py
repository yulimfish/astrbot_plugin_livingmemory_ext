"""Plugin entry for astrbot_plugin_livingmemory_ext (customized fork).

Extends the upstream LivingMemory plugin with a "memory diary" feature:
at a configured time each day, today's memories stored by the upstream
plugin are summarized into a diary and sent to the configured group chat.
"""

from __future__ import annotations

import asyncio
import logging

from astrbot.api.star import Context, Star, register

# AstrBot loads plugins as `data.plugins.<plugin_dir>.main` (namespace package,
# plugin dir is NOT on sys.path), so intra-plugin imports must be relative —
# same style as the upstream LivingMemory plugin.
from .livingmemory_ext.diary_digest import DiaryDigestScheduler

logger = logging.getLogger("livingmemory_ext")

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
