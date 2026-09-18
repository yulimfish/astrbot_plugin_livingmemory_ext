"""Shared fixtures for the astrbot_plugin_livingmemory_ext test suite."""

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

EVENT_STUB = """
class AstrMessageEvent:
    pass


class _EventMessageType:
    GROUP_MESSAGE = object()


class _PlatformAdapterType:
    QQOFFICIAL = 1
    QQOFFICIAL_WEBHOOK = 2


class _Filter:
    EventMessageType = _EventMessageType
    PlatformAdapterType = _PlatformAdapterType

    @staticmethod
    def event_message_type(*args, **kwargs):
        return lambda func: func

    @staticmethod
    def platform_adapter_type(*args, **kwargs):
        return lambda func: func


filter = _Filter()
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
    event_dir = api_dir / "event"
    event_dir.mkdir()
    (event_dir / "__init__.py").write_text(EVENT_STUB)

    sys.path.insert(0, str(tmp_path))
    yield tmp_path
    sys.path.remove(str(tmp_path))
    for name in list(sys.modules):
        if name.startswith(("data", "astrbot")):
            del sys.modules[name]
