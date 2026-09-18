"""Persistent conversation targets discovered from QQ Official events."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import aiofiles

QQ_OFFICIAL_PLATFORM_NAMES = frozenset({"qq_official", "qq_official_webhook"})


def event_to_conversation(event: Any) -> dict[str, str] | None:
    """Build a group target from a QQ Official inbound event.

    QQ Official exposes a ``group_openid`` (or a guild ``channel_id``) as the
    AstrBot event group id.  It cannot enumerate all groups through its client
    API, so observed event targets are the reliable source for the dropdown.
    """
    try:
        platform_name = str(event.get_platform_name() or "").strip()
        platform_id = str(event.get_platform_id() or "").strip()
        target_id = str(event.get_group_id() or "").strip()
    except Exception:  # noqa: BLE001 - event adapters are third-party inputs
        return None
    if (
        platform_name not in QQ_OFFICIAL_PLATFORM_NAMES
        or not platform_id
        or not target_id
    ):
        return None
    group = getattr(getattr(event, "message_obj", None), "group", None)
    display_name = str(getattr(group, "group_name", "") or "").strip()
    return {
        "platform_id": platform_id,
        "target_id": target_id,
        "display_name": display_name,
        "kind": "group",
    }


def merge_conversation(
    conversations: list[dict[str, str]], conversation: dict[str, str]
) -> tuple[list[dict[str, str]], bool]:
    """Add or refresh one conversation while preserving dropdown order."""
    result = [item.copy() for item in conversations]
    for index, item in enumerate(result):
        if (
            item.get("platform_id") == conversation["platform_id"]
            and item.get("target_id") == conversation["target_id"]
            and item.get("kind") == conversation["kind"]
        ):
            if item == conversation:
                return result, False
            result[index] = conversation.copy()
            return result, True
    result.append(conversation.copy())
    return result, True


async def load_conversations(path: Path) -> list[dict[str, str]]:
    """Read valid cached QQ Official targets, returning an empty list on errors."""
    try:
        async with aiofiles.open(path, "r", encoding="utf-8") as file:
            raw = json.loads(await file.read())
    except (FileNotFoundError, json.JSONDecodeError, OSError, TypeError, ValueError):
        return []
    if not isinstance(raw, list):
        return []

    conversations: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        platform_id = str(item.get("platform_id") or "").strip()
        target_id = str(item.get("target_id") or "").strip()
        if not platform_id or not target_id:
            continue
        conversation = {
            "platform_id": platform_id,
            "target_id": target_id,
            "display_name": str(item.get("display_name") or "").strip(),
            "kind": "group",
        }
        conversations, _ = merge_conversation(conversations, conversation)
    return conversations


async def save_conversations(path: Path, conversations: list[dict[str, str]]) -> None:
    """Persist discovered targets under the plugin data directory."""
    path.parent.mkdir(parents=True, exist_ok=True)
    async with aiofiles.open(path, "w", encoding="utf-8") as file:
        await file.write(json.dumps(conversations, ensure_ascii=False, indent=2))
