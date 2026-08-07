"""Tests for the plugin Web APIs (dynamic conversation-target picker).

These APIs let a plugin Page fetch the current platform group list and
write the chosen target back into the plugin config.  The tests reuse the
``loader_env`` fixture from ``test_astrbot_loader`` so the plugin is loaded
under AstrBot's ``data.plugins.<name>.main`` namespace shape, then call the
handler methods on an instance created via ``__new__`` (skipping
``__init__``, which would require the real ``Context.register_web_api``).
"""

import asyncio
import sys
import types
from types import SimpleNamespace

from test_astrbot_loader import PLUGIN_PKG

PLUGIN_MODULE = f"data.plugins.{PLUGIN_PKG}.main"


class _FakeMeta:
    def __init__(self, platform_id):
        self.id = platform_id


class _FakeClient:
    def __init__(self, groups=None, error=None):
        self._groups = groups or []
        self._error = error

    async def get_group_list(self):
        if self._error:
            raise self._error
        return self._groups


class _FakePlatform:
    def __init__(self, platform_id="qqab", client=None, meta_error=None):
        self._platform_id = platform_id
        self._client = client
        self._meta_error = meta_error

    def meta(self):
        if self._meta_error:
            raise self._meta_error
        return _FakeMeta(self._platform_id)

    def get_client(self):
        return self._client


class _FakeRequest:
    def __init__(self, payload):
        self._payload = payload

    async def json(self):
        return self._payload


class _FakeConfig(dict):
    def __init__(self, data):
        super().__init__(data)
        self.save_calls = []

    def save_config(self):
        self.save_calls.append(dict(self))


def _build_plugin(loader_env, config, platforms=(), payload=None):
    module = __import__(PLUGIN_MODULE, fromlist=["main"])
    plugin_cls = module.LivingMemoryExtPlugin
    plugin = plugin_cls.__new__(plugin_cls)
    plugin.config = _FakeConfig(config)
    plugin.context = SimpleNamespace(
        platform_manager=SimpleNamespace(platform_insts=list(platforms))
    )
    if payload is not None:
        web_mod = types.ModuleType("astrbot.api.web")
        web_mod.request = _FakeRequest(payload)
        sys.modules["astrbot.api.web"] = web_mod
    return plugin


def test_web_api_groups_lists_groups_from_platforms(loader_env):
    platforms = [
        _FakePlatform(
            "qqab",
            _FakeClient(
                [
                    {"group_id": 1102457938, "group_name": "记忆群"},
                    {"group_id": 987654321, "group_name": "摸鱼群"},
                ]
            ),
        ),
        _FakePlatform("qqofficial", _FakeClient([])),
        _FakePlatform("no_client"),
    ]
    plugin = _build_plugin(loader_env, {}, platforms)
    result = asyncio.run(plugin._web_api_groups())
    assert result["status"] == "ok"
    assert result["data"] == [
        {"platform_id": "qqab", "group_id": "1102457938", "group_name": "记忆群"},
        {"platform_id": "qqab", "group_id": "987654321", "group_name": "摸鱼群"},
    ]


def test_web_api_groups_skips_failed_platforms(loader_env):
    platforms = [
        _FakePlatform("boom", _FakeClient(error=RuntimeError("api down"))),
        _FakePlatform("meta_broken", meta_error=RuntimeError("meta down")),
    ]
    plugin = _build_plugin(loader_env, {}, platforms)
    result = asyncio.run(plugin._web_api_groups())
    assert result["status"] == "ok"
    assert result["data"] == []


def test_web_api_diary_rules_shape(loader_env):
    config = {
        "diary_digest": {
            "enabled": True,
            "rules": [
                {
                    "name": "测试规则",
                    "enabled": True,
                    "platform": "qqab",
                    "send_to": "1102457938",
                },
                {"name": "禁用规则", "enabled": False, "platform": "", "send_to": ""},
            ],
        }
    }
    plugin = _build_plugin(loader_env, config)
    result = asyncio.run(plugin._web_api_diary_rules())
    assert result["status"] == "ok"
    assert result["data"] == [
        {
            "index": 0,
            "name": "测试规则",
            "enabled": True,
            "platform": "qqab",
            "send_to": "1102457938",
        },
        {
            "index": 1,
            "name": "禁用规则",
            "enabled": False,
            "platform": "",
            "send_to": "",
        },
    ]


def test_web_api_diary_rules_missing_config(loader_env):
    plugin = _build_plugin(loader_env, {})
    result = asyncio.run(plugin._web_api_diary_rules())
    assert result == {"status": "ok", "data": []}


def test_web_api_save_diary_target_saves(loader_env):
    config = {
        "diary_digest": {
            "enabled": True,
            "rules": [
                {"name": "测试规则", "platform": "aiocqhttp", "send_to": "656678318"}
            ],
        }
    }
    plugin = _build_plugin(
        loader_env,
        config,
        payload={"rule_index": 0, "platform_id": "qqab", "group_id": "1102457938"},
    )
    result = asyncio.run(plugin._web_api_save_diary_target())
    assert result["status"] == "ok"
    rule = plugin.config["diary_digest"]["rules"][0]
    assert rule["platform"] == "qqab"
    assert rule["send_to"] == "1102457938"
    assert plugin.config.save_calls


def test_web_api_save_diary_target_default_platform(loader_env):
    config = {
        "diary_digest": {
            "enabled": True,
            "rules": [{"name": "测试规则", "platform": "", "send_to": ""}],
        }
    }
    plugin = _build_plugin(
        loader_env,
        config,
        payload={"rule_index": 0, "platform_id": "", "group_id": "123456"},
    )
    result = asyncio.run(plugin._web_api_save_diary_target())
    assert result["status"] == "ok"
    rule = plugin.config["diary_digest"]["rules"][0]
    assert rule["platform"] == "aiocqhttp"
    assert rule["send_to"] == "123456"


def test_web_api_save_diary_target_invalid_index(loader_env):
    config = {"diary_digest": {"enabled": True, "rules": [{"name": "测试规则"}]}}
    plugin = _build_plugin(
        loader_env,
        config,
        payload={"rule_index": 5, "platform_id": "qqab", "group_id": "1102457938"},
    )
    result = asyncio.run(plugin._web_api_save_diary_target())
    assert result["status"] == "error"
    assert "规则索引无效" in result["message"]


def test_web_api_save_diary_target_missing_diary(loader_env):
    plugin = _build_plugin(
        loader_env,
        {},
        payload={"rule_index": 0, "platform_id": "qqab", "group_id": "1102457938"},
    )
    result = asyncio.run(plugin._web_api_save_diary_target())
    assert result["status"] == "error"
    assert "diary_digest 配置缺失" in result["message"]
