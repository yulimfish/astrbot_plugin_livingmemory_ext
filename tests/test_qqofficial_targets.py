"""Tests for QQ Official group-openid target discovery and caching."""

import asyncio
from pathlib import Path
from types import SimpleNamespace

from test_astrbot_loader import PLUGIN_PKG

PLUGIN_MODULE = f"data.plugins.{PLUGIN_PKG}.main"
TARGETS_MODULE = f"data.plugins.{PLUGIN_PKG}.livingmemory_ext.target_cache"
METADATA_PATH = Path(__file__).parent.parent / "metadata.yaml"


def _targets(loader_env):
    return __import__(TARGETS_MODULE, fromlist=["target_cache"])


def _event(
    platform_id="qq-main",
    platform_name="qq_official",
    group_openid="group-openid-123",
    group_name="官方机器人测试群",
):
    return SimpleNamespace(
        get_platform_id=lambda: platform_id,
        get_platform_name=lambda: platform_name,
        get_group_id=lambda: group_openid,
        message_obj=SimpleNamespace(
            group=SimpleNamespace(group_name=group_name),
        ),
    )


def test_qqofficial_event_uses_instance_id_and_group_openid(loader_env):
    event_to_conversation = _targets(loader_env).event_to_conversation

    assert event_to_conversation(_event()) == {
        "platform_id": "qq-main",
        "target_id": "group-openid-123",
        "display_name": "官方机器人测试群",
        "kind": "group",
    }


def test_metadata_declares_qqofficial_adapters():
    metadata = METADATA_PATH.read_text(encoding="utf-8")

    assert "  - qq_official\n" in metadata
    assert "  - qq_official_webhook\n" in metadata


def test_qqofficial_event_ignores_private_and_other_platforms(loader_env):
    event_to_conversation = _targets(loader_env).event_to_conversation

    assert event_to_conversation(_event(platform_name="aiocqhttp")) is None
    assert event_to_conversation(_event(group_openid="")) is None


def test_merge_conversation_updates_name_without_duplicate(loader_env):
    merge_conversation = _targets(loader_env).merge_conversation
    old = {
        "platform_id": "qq-main",
        "target_id": "group-openid-123",
        "display_name": "",
        "kind": "group",
    }
    updated = {**old, "display_name": "官方机器人测试群"}

    conversations, changed = merge_conversation([old], updated)

    assert changed is True
    assert conversations == [updated]
    conversations, changed = merge_conversation(conversations, updated)
    assert changed is False
    assert conversations == [updated]


def test_target_cache_roundtrip(loader_env, tmp_path):
    cache = _targets(loader_env)
    path = tmp_path / "qqofficial_targets.json"
    conversations = [
        {
            "platform_id": "qq-main",
            "target_id": "group-openid-123",
            "display_name": "官方机器人测试群",
            "kind": "group",
        }
    ]

    asyncio.run(cache.save_conversations(path, conversations))

    assert asyncio.run(cache.load_conversations(path)) == conversations


def test_target_cache_ignores_corrupted_file(loader_env, tmp_path):
    cache = _targets(loader_env)
    path = tmp_path / "qqofficial_targets.json"
    path.write_text("{invalid json", encoding="utf-8")

    assert asyncio.run(cache.load_conversations(path)) == []


def test_qqofficial_target_updates_dropdown_immediately(loader_env):
    module = __import__(PLUGIN_MODULE, fromlist=["main"])
    plugin = module.LivingMemoryExtPlugin.__new__(module.LivingMemoryExtPlugin)
    plugin._qqofficial_targets = []
    plugin._target_cache_loaded = True
    plugin._target_cache_load_task = None

    async def _save_targets():
        return None

    plugin._save_qqofficial_targets = _save_targets

    schema = {
        "diary_digest": {
            "items": {
                "rules": {
                    "templates": {
                        "rule": {
                            "items": {
                                "send_to": {"type": "string", "options": []},
                                "scope_target": {"type": "string", "options": []},
                            }
                        }
                    }
                }
            }
        }
    }
    plugin.config = {"diary_digest": {"rules": []}}
    plugin.context = SimpleNamespace(
        platform_manager=SimpleNamespace(platform_insts=[]),
    )
    plugin.config = SimpleNamespace(
        schema=schema,
        get=lambda key, default=None: {"diary_digest": {"rules": []}}.get(key, default),
    )

    async def _remember_target():
        plugin._target_cache_lock = asyncio.Lock()
        await plugin._remember_qqofficial_target(_event())

    asyncio.run(_remember_target())

    items = schema["diary_digest"]["items"]["rules"]["templates"]["rule"]["items"]
    assert items["send_to"]["options"] == ["qq-main:group-openid-123"]
    assert items["send_to"]["labels"] == [
        "官方机器人测试群 (group-openid-123) [qq-main]"
    ]
