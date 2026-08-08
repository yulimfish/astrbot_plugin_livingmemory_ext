"""Tests for the merged send_to dropdown: value parsing and schema injection.

The WebUI config panel serializes the in-memory ``config.schema`` on every
fetch; the plugin refreshes its ``send_to`` field's ``options``/``labels``
from the live platform group list, so the panel renders a dynamic dropdown
(displaying group names, storing ``platform:group_id``).
"""

import asyncio
from types import SimpleNamespace

from test_astrbot_loader import PLUGIN_PKG

PLUGIN_MODULE = f"data.plugins.{PLUGIN_PKG}.main"
DIARY_MODULE = f"data.plugins.{PLUGIN_PKG}.livingmemory_ext.diary_digest"


def _diary(loader_env):
    return __import__(DIARY_MODULE, fromlist=["diary_digest"])


# -- pure parsing helpers ---------------------------------------------------


def test_parse_send_to_bare_group_id(loader_env):
    parse_send_to = _diary(loader_env).parse_send_to
    assert parse_send_to("123456") == ("aiocqhttp", "123456")
    assert parse_send_to(" 123456 ") == ("aiocqhttp", "123456")
    assert parse_send_to("123456", "qqab") == ("qqab", "123456")


def test_parse_send_to_merged_format(loader_env):
    parse_send_to = _diary(loader_env).parse_send_to
    assert parse_send_to("qqab:1102457938") == ("qqab", "1102457938")
    assert parse_send_to("qqofficial:123456") == ("qqofficial", "123456")


def test_parse_send_to_legacy_umo(loader_env):
    parse_send_to = _diary(loader_env).parse_send_to
    assert parse_send_to("qqab:GroupMessage:1102457938") == ("qqab", "1102457938")
    assert parse_send_to("aiocqhttp:FriendMessage:42") == ("aiocqhttp", "42")


def test_parse_send_to_empty(loader_env):
    parse_send_to = _diary(loader_env).parse_send_to
    assert parse_send_to("") == ("aiocqhttp", "")
    assert parse_send_to(None) == ("aiocqhttp", "")
    assert parse_send_to("   ") == ("aiocqhttp", "")


def test_parse_send_to_trailing_colon(loader_env):
    parse_send_to = _diary(loader_env).parse_send_to
    assert parse_send_to("qqab:") == ("qqab", "")


def test_build_target_umo_formats(loader_env):
    build_target_umo = _diary(loader_env).build_target_umo
    assert build_target_umo({"send_to": "qqab:1102457938"}) == (
        "qqab:GroupMessage:1102457938"
    )
    assert build_target_umo({"send_to": "1102457938"}) == (
        "aiocqhttp:GroupMessage:1102457938"
    )
    assert build_target_umo({"send_to": "1102457938", "platform": "qqab"}) == (
        "qqab:GroupMessage:1102457938"
    )
    assert build_target_umo({"send_to": "qqab:GroupMessage:1102457938"}) == (
        "qqab:GroupMessage:1102457938"
    )
    assert build_target_umo({"send_to": ""}) == ""


# -- option merging ---------------------------------------------------------


def test_merge_target_options_configured_values_first(loader_env):
    merge_target_options = _diary(loader_env).merge_target_options
    conversations = [
        {
            "platform_id": "qqab",
            "target_id": "1102457938",
            "display_name": "记忆群",
            "kind": "group",
        },
        {
            "platform_id": "qqab",
            "target_id": "987654321",
            "display_name": "摸鱼群",
            "kind": "group",
        },
    ]
    options, labels = merge_target_options(["qqab:1102457938"], conversations)
    assert options == ["qqab:1102457938", "qqab:987654321"]
    assert labels == ["1102457938 [qqab]", "摸鱼群 (987654321) [qqab]"]


def test_merge_target_options_friends_and_kinds(loader_env):
    merge_target_options = _diary(loader_env).merge_target_options
    conversations = [
        {
            "platform_id": "qqab",
            "target_id": "10001",
            "display_name": "小明",
            "kind": "friend",
        },
        {
            "platform_id": "qqab",
            "target_id": "20002",
            "display_name": "摸鱼群",
            "kind": "group",
        },
    ]
    options, labels = merge_target_options([], conversations, kinds=("friend",))
    assert options == ["qqab:10001"]
    assert labels == ["[好友] 小明 (10001) [qqab]"]


def test_merge_target_options_friend_without_name(loader_env):
    merge_target_options = _diary(loader_env).merge_target_options
    conversations = [
        {
            "platform_id": "qqab",
            "target_id": "10001",
            "display_name": "",
            "kind": "friend",
        }
    ]
    options, labels = merge_target_options([], conversations, kinds=("group", "friend"))
    assert options == ["qqab:10001"]
    assert labels == ["[好友] 10001 [qqab]"]


def test_merge_target_options_deduplicates(loader_env):
    merge_target_options = _diary(loader_env).merge_target_options
    conversations = [
        {
            "platform_id": "qqab",
            "target_id": "1102457938",
            "display_name": "记忆群",
            "kind": "group",
        }
    ]
    options, _ = merge_target_options(["qqab:1102457938"], conversations)
    assert options == ["qqab:1102457938"]


def test_merge_target_options_skips_broken_entries(loader_env):
    merge_target_options = _diary(loader_env).merge_target_options
    conversations = [
        {
            "platform_id": "qqab",
            "target_id": "",
            "display_name": "无目标",
            "kind": "group",
        },
        {
            "platform_id": "",
            "target_id": "123",
            "display_name": "无平台",
            "kind": "group",
        },
    ]
    options, _ = merge_target_options([], conversations)
    assert options == []


def test_merge_target_options_legacy_value_kept(loader_env):
    merge_target_options = _diary(loader_env).merge_target_options
    options, labels = merge_target_options(["123456"], [])
    assert options == ["123456"]
    assert labels == ["123456 [aiocqhttp]"]


# -- scope target resolution -------------------------------------------------


def test_build_rule_scope_like(loader_env):
    build_rule_scope_like = _diary(loader_env).build_rule_scope_like
    assert build_rule_scope_like({"scope": "all"}) is None
    assert (
        build_rule_scope_like({"scope": "group", "scope_target": "123"})
        == "%:GroupMessage:123%"
    )
    assert (
        build_rule_scope_like(
            {"scope": "group", "scope_target": "123", "send_to": "qqab:456"}
        )
        == "%:GroupMessage:123%"
    )
    assert (
        build_rule_scope_like({"scope": "friend", "scope_target": "qqab:999"})
        == "%:FriendMessage:999%"
    )
    assert build_rule_scope_like({"scope": "group", "scope_target": ""}) is None


# -- schema injection -------------------------------------------------------


class _FakeMeta:
    def __init__(self, platform_id):
        self.id = platform_id


class _FakeClient:
    def __init__(self, groups=None, friends=None):
        self._groups = groups or []
        self._friends = friends or []

    async def get_group_list(self):
        return self._groups

    async def get_friend_list(self):
        return self._friends


class _FakePlatform:
    def __init__(
        self,
        platform_id="qqab",
        groups=None,
        friends=None,
        meta_error=None,
        client_error=None,
    ):
        self._platform_id = platform_id
        self._client = _FakeClient(groups, friends)
        self._meta_error = meta_error
        self._client_error = client_error

    def meta(self):
        if self._meta_error:
            raise self._meta_error
        return _FakeMeta(self._platform_id)

    def get_client(self):
        if self._client_error:
            raise self._client_error
        return self._client


class _FakeConfig(dict):
    def __init__(self, data, schema):
        super().__init__(data)
        self.schema = schema
        self.save_calls = 0

    def save_config(self):
        self.save_calls += 1


def _build_plugin(loader_env, schema, platforms=()):
    module = __import__(PLUGIN_MODULE, fromlist=["main"])
    plugin_cls = module.LivingMemoryExtPlugin
    plugin = plugin_cls.__new__(plugin_cls)
    plugin.config = _FakeConfig({}, schema)
    plugin.context = SimpleNamespace(
        platform_manager=SimpleNamespace(platform_insts=list(platforms))
    )
    return plugin


def test_list_conversations_aggregates_platforms(loader_env):
    plugin = _build_plugin(
        loader_env,
        {},
        platforms=[
            _FakePlatform(
                "qqab",
                groups=[
                    {"group_id": 1102457938, "group_name": "记忆群"},
                    {"group_id": 987654321, "group_name": "摸鱼群"},
                ],
                friends=[{"user_id": 10001, "nickname": "小明"}],
            ),
            _FakePlatform("qqofficial", []),
        ],
    )
    conversations = asyncio.run(plugin._list_conversations())
    assert conversations == [
        {
            "platform_id": "qqab",
            "target_id": "1102457938",
            "display_name": "记忆群",
            "kind": "group",
        },
        {
            "platform_id": "qqab",
            "target_id": "987654321",
            "display_name": "摸鱼群",
            "kind": "group",
        },
        {
            "platform_id": "qqab",
            "target_id": "10001",
            "display_name": "小明",
            "kind": "friend",
        },
    ]


def test_sync_schema_options_injects_dropdowns(loader_env):
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
    plugin = _build_plugin(
        loader_env,
        schema,
        platforms=[
            _FakePlatform(
                "qqab",
                groups=[{"group_id": 1102457938, "group_name": "记忆群"}],
                friends=[{"user_id": 10001, "nickname": "小明"}],
            )
        ],
    )
    asyncio.run(plugin._sync_schema_options())
    items = schema["diary_digest"]["items"]["rules"]["templates"]["rule"]["items"]
    assert items["send_to"]["options"] == ["qqab:1102457938"]
    assert items["send_to"]["labels"] == ["记忆群 (1102457938) [qqab]"]
    assert items["scope_target"]["options"] == ["qqab:1102457938", "qqab:10001"]
    assert items["scope_target"]["labels"] == [
        "记忆群 (1102457938) [qqab]",
        "[好友] 小明 (10001) [qqab]",
    ]


def test_sync_schema_options_merges_configured_values(loader_env):
    schema = {
        "diary_digest": {
            "items": {
                "rules": {
                    "templates": {
                        "rule": {
                            "items": {"send_to": {"type": "string", "options": []}}
                        }
                    }
                }
            }
        }
    }
    plugin = _build_plugin(loader_env, schema)
    plugin.config["diary_digest"] = {
        "rules": [{"send_to": "qqab:1102457938"}, {"send_to": ""}]
    }
    asyncio.run(plugin._sync_schema_options())
    send_to = schema["diary_digest"]["items"]["rules"]["templates"]["rule"]["items"][
        "send_to"
    ]
    assert send_to["options"] == ["qqab:1102457938"]
    assert send_to["labels"] == ["1102457938 [qqab]"]


def test_sync_schema_options_ignores_missing_schema(loader_env):
    plugin = _build_plugin(loader_env, {})
    assert asyncio.run(plugin._sync_schema_options()) is None


def test_sync_schema_options_schema_path_missing(loader_env):
    schema = {"diary_digest": {"items": {"rules": {}}}}
    plugin = _build_plugin(loader_env, schema)
    assert asyncio.run(plugin._sync_schema_options()) is None


def test_sync_schema_options_send_to_not_dict(loader_env):
    schema = {
        "diary_digest": {
            "items": {
                "rules": {"templates": {"rule": {"items": {"send_to": "not-a-dict"}}}}
            }
        }
    }
    plugin = _build_plugin(loader_env, schema)
    assert asyncio.run(plugin._sync_schema_options()) is None


def test_list_conversations_skips_broken_platforms(loader_env):
    plugin = _build_plugin(
        loader_env,
        {},
        platforms=[
            _FakePlatform("boom", meta_error=RuntimeError("meta down")),
            _FakePlatform("no_client", client_error=RuntimeError("client down")),
            _FakePlatform(
                "qqab",
                groups=[{"group_id": 1102457938, "group_name": "记忆群"}],
            ),
        ],
    )
    conversations = asyncio.run(plugin._list_conversations())
    assert conversations == [
        {
            "platform_id": "qqab",
            "target_id": "1102457938",
            "display_name": "记忆群",
            "kind": "group",
        }
    ]


def test_normalize_legacy_send_to_merges_platform(loader_env):
    plugin = _build_plugin(loader_env, {})
    plugin.config["diary_digest"] = {
        "rules": [
            {"name": "旧规则", "send_to": "1102457938", "platform": "qqab"},
            {"name": "新规则", "send_to": "qqab:987654321"},
            {"name": "纯群号默认平台", "send_to": "123456", "platform": ""},
            {"name": "空目标", "send_to": "", "platform": "qqab"},
        ]
    }
    assert plugin._normalize_legacy_send_to() is True
    rules = plugin.config["diary_digest"]["rules"]
    assert rules[0] == {"name": "旧规则", "send_to": "qqab:1102457938"}
    assert rules[1] == {"name": "新规则", "send_to": "qqab:987654321"}
    assert rules[2] == {
        "name": "纯群号默认平台",
        "send_to": "123456",
        "platform": "",
    }
    assert rules[3] == {"name": "空目标", "send_to": "", "platform": "qqab"}


def test_normalize_legacy_send_to_is_idempotent(loader_env):
    plugin = _build_plugin(loader_env, {})
    plugin.config["diary_digest"] = {
        "rules": [{"name": "旧规则", "send_to": "1102457938", "platform": "qqab"}]
    }
    plugin._normalize_legacy_send_to()
    assert plugin._normalize_legacy_send_to() is False
    assert plugin.config["diary_digest"]["rules"][0]["send_to"] == "qqab:1102457938"


def test_sync_schema_options_persists_normalized_values(loader_env):
    schema = {
        "diary_digest": {
            "items": {
                "rules": {
                    "templates": {
                        "rule": {
                            "items": {"send_to": {"type": "string", "options": []}}
                        }
                    }
                }
            }
        }
    }
    plugin = _build_plugin(loader_env, schema)
    plugin.config["diary_digest"] = {
        "rules": [{"name": "旧规则", "send_to": "1102457938", "platform": "qqab"}]
    }
    asyncio.run(plugin._sync_schema_options())
    assert plugin.config.save_calls == 1
    assert plugin.config["diary_digest"]["rules"][0]["send_to"] == "qqab:1102457938"
    send_to = schema["diary_digest"]["items"]["rules"]["templates"]["rule"]["items"][
        "send_to"
    ]
    assert send_to["options"] == ["qqab:1102457938"]
