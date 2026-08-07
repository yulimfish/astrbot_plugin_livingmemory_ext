"""Simulate AstrBot's real plugin loader to guard the import style.

AstrBot loads plugins as `data.plugins.<plugin_dir>.main` (namespace package)
and does NOT put the plugin directory on sys.path.  Intra-plugin imports must
therefore be relative (`.livingmemory_ext.diary_digest`), same as upstream.
This test recreates that loading shape with a stubbed `astrbot` package and
fails if main.py ever regresses to an absolute top-level import.
"""

PLUGIN_PKG = "astrbot_plugin_livingmemory_ext"


def test_main_imports_under_astrbot_loader(loader_env):
    module = __import__(f"data.plugins.{PLUGIN_PKG}.main", fromlist=["main"])
    assert hasattr(module, "LivingMemoryExtPlugin")
    assert module.PLUGIN_VERSION == "0.1.1"
