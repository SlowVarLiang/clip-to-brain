"""Clip-to-Brain 桥接 — 供 API / 插件调用 content-archiver-skill/scripts/clip.py。"""

from __future__ import annotations

import importlib
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

_AUTOMEDIA_ROOT = Path(__file__).resolve().parent.parent.parent
_DEFAULT_CONFIG = _AUTOMEDIA_ROOT / "content-archiver-skill" / "config.json"
_SCRIPTS_DIR = _AUTOMEDIA_ROOT / "content-archiver-skill" / "scripts"


def clip_config_path() -> Path:
    import os

    raw = os.getenv("INGEST_CONFIG", "").strip()
    return Path(raw) if raw else _DEFAULT_CONFIG


def _ensure_import_path() -> None:
    scripts = str(_SCRIPTS_DIR)
    if scripts not in sys.path:
        sys.path.insert(0, scripts)


def load_clip_config(path: Path | None = None) -> dict[str, Any]:
    cfg_path = path or clip_config_path()
    if not cfg_path.exists():
        raise FileNotFoundError(f"入库配置不存在: {cfg_path}")
    with cfg_path.open(encoding="utf-8") as f:
        return json.load(f)


def run_clip_one(
    raw_input: str,
    *,
    profile: str | None = None,
    account: str | None = None,
    category: str | None = None,
    subfolder: str | None = None,
    title: str | None = None,
    config_path: Path | None = None,
) -> dict[str, Any]:
    """同步执行 clip，返回 ClipResult 字典。"""
    _ensure_import_path()
    import clip  # noqa: WPS433

    importlib.reload(clip)

    config = load_clip_config(config_path)
    pid = profile or account
    result = clip.clip(
        raw_input,
        config,
        profile_id=pid,
        category=category,
        subfolder=subfolder,
        title=title,
        create_topic=True,
    )
    return clip.result_to_dict(result)


def yuye_root_from_config(config: dict[str, Any]) -> Path:
    skill = _AUTOMEDIA_ROOT / "content-archiver-skill"
    raw = config.get("YuYe_root") or config.get("lumis_root", "../vault")
    root = Path(raw)
    return root if root.is_absolute() else (skill / root).resolve()


def run_clip_stats(*, days: int = 7, config_path: Path | None = None) -> dict[str, Any]:
    _ensure_import_path()
    import clip_stats  # noqa: WPS433

    config = load_clip_config(config_path)
    return clip_stats.collect_stats(yuye_root_from_config(config), days=days)


def run_clip_profiles(*, config_path: Path | None = None) -> dict[str, Any]:
    _ensure_import_path()
    from profile_loader import default_profile_name, list_profiles, load_profile  # noqa: WPS433

    config = load_clip_config(config_path)
    default = default_profile_name(config)
    obs = config.get("obsidian") or {}
    profiles = []
    for pid in list_profiles(config):
        p = load_profile(pid, config)
        profiles.append(
            {
                "id": pid,
                "label": p.label,
                "persona": p.persona,
                "niche": p.niche,
                "default": pid == default,
                "create_topic_card": p.create_topic_card,
            }
        )
    return {
        "default_profile": default,
        "vault_name": obs.get("vault_name") or "YuYe",
        "YuYe_root": str(yuye_root_from_config(config)),
        "profiles": profiles,
    }


def clip_dashboard_path() -> Path:
    return _AUTOMEDIA_ROOT / "content-archiver-skill" / "web" / "clip-dashboard.html"
