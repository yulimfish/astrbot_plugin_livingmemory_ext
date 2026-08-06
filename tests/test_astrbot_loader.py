"""Simulate AstrBot's real plugin loader to guard the import style.

AstrBot loads plugins as `data.plugins.<plugin_dir>.main` (namespace package)
and does NOT put the plugin directory on sys.path.  Intra-plugin imports must
therefore be relative (`.livingmemory_ext.diary_digest`), same as upstream.
This test recreates that loading shape with a stubbed `astrbot` package and
fails if main.py ever regresses to an absolute top-level import.
"""

import shutil
import sys
from pathlib import Path

import pytest

PLUGIN_DIR = Path(__file__).resolve().parent.parent
PLUGIN_PKG = "astrbot_plugin_livingmemory_ext"

STAR_STUB = """
class Star:
    def __init__(self, context):
        self.context = context


class Context:
    pass


class StarTools:
    @staticmethod
    def get_data_dir(plugin_name: str) -> str:
        return f"/tmp/astrbot-data/{plugin_name}"


def register(*args, **kwargs):
    def decorator(cls):
        return cls

    return decorator
"""


@pytest.fixture
def loader_env(tmp_path):
    """Recreate AstrBot's `data.plugins.<dir>.main` loading shape."""
    plugin_path = tmp_path / "data" / "plugins" / PLUGIN_PKG
    plugin_path.mkdir(parents=True)
    shutil.copy2(PLUGIN_DIR / "main.py", plugin_path / "main.py")
    shutil.copytree(PLUGIN_DIR / "livingmemory_ext", plugin_path / "livingmemory_ext")

    api_dir = tmp_path / "astrbot" / "api"
    api_dir.mkdir(parents=True)
    (api_dir / "__init__.py").write_text("")
    (api_dir / "star.py").write_text(STAR_STUB)

    sys.path.insert(0, str(tmp_path))
    yield tmp_path
    sys.path.remove(str(tmp_path))
    for name in list(sys.modules):
        if name.startswith(("data", "astrbot")):
            del sys.modules[name]


def test_main_imports_under_astrbot_loader(loader_env):
    module = __import__(f"data.plugins.{PLUGIN_PKG}.main", fromlist=["main"])
    assert hasattr(module, "LivingMemoryExtPlugin")
    assert module.PLUGIN_VERSION == "0.1.1"
