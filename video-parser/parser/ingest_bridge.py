"""YuYe 一键入库桥接 — 供浏览器插件 / API 调用 content-archiver-skill。"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

_AUTOMEDIA_ROOT = Path(__file__).resolve().parent.parent.parent
_DEFAULT_CONFIG = _AUTOMEDIA_ROOT / "content-archiver-skill" / "config.json"
_SCRIPTS_DIR = _AUTOMEDIA_ROOT / "content-archiver-skill" / "scripts"


def ingest_config_path() -> Path:
    raw = os.getenv("INGEST_CONFIG", "").strip()
    return Path(raw) if raw else _DEFAULT_CONFIG


def _ensure_import_path() -> None:
    scripts = str(_SCRIPTS_DIR)
    if scripts not in sys.path:
        sys.path.insert(0, scripts)


def load_ingest_config(path: Path | None = None) -> dict[str, Any]:
    cfg_path = path or ingest_config_path()
    if not cfg_path.exists():
        raise FileNotFoundError(f"入库配置不存在: {cfg_path}")
    with cfg_path.open(encoding="utf-8") as f:
        return json.load(f)


def run_ingest_one(
    url: str,
    *,
    category: str | None = None,
    subfolder: str | None = None,
    skip_transcribe: bool = False,
    config_path: Path | None = None,
) -> dict[str, Any]:
    """同步执行单链接入库，返回 yuye_ingest.ingest_one 结果 dict。"""
    import importlib

    _ensure_import_path()
    import yuye_ingest  # noqa: WPS433

    importlib.reload(yuye_ingest)

    config = load_ingest_config(config_path)
    return yuye_ingest.ingest_one(
        url,
        config,
        category=category,
        subfolder=subfolder,
        skip_transcribe=skip_transcribe,
    )
