"""Clip-to-Brain 用户 Profile 加载（开源自托管）。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore

SKILL_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PROFILES_DIR = SKILL_ROOT / "profiles"


@dataclass
class Profile:
    id: str
    label: str
    persona: str
    niche: str = ""
    platforms: list[str] | None = None
    remix_enabled: bool = True
    remix_max_angles: int = 3
    create_topic_card: bool = True
    topic_inbox: str = "04-viral-topics/_inbox"

    @property
    def remix_section(self) -> str:
        return f"{self.label}可写"


def _profiles_dir(config: dict[str, Any] | None) -> Path:
    clip = (config or {}).get("clip") or {}
    raw = clip.get("profiles_dir", "profiles")
    p = Path(raw)
    return p if p.is_absolute() else (SKILL_ROOT / p)


def _parse_profile(data: dict[str, Any]) -> Profile:
    remix = data.get("remix") or {}
    output = data.get("output") or {}
    return Profile(
        id=str(data.get("id") or "default-creator"),
        label=str(data.get("label") or "创作者"),
        persona=str(data.get("persona") or "内容创作者"),
        niche=str(data.get("niche") or ""),
        platforms=list(data.get("platforms") or []),
        remix_enabled=bool(remix.get("enabled", True)),
        remix_max_angles=int(remix.get("max_angles", 3)),
        create_topic_card=bool(output.get("create_topic_card", True)),
        topic_inbox=str(output.get("topic_inbox") or "04-viral-topics/_inbox"),
    )


def _builtin_default() -> Profile:
    return Profile(
        id="default-creator",
        label="创作者",
        persona="内容创作者，关注可落地的场景解法与选题灵感",
        niche="通用",
        platforms=["小红书", "视频号", "B站"],
    )


def list_profiles(config: dict[str, Any] | None = None) -> list[str]:
    directory = _profiles_dir(config)
    if not directory.exists():
        return ["default-creator"]
    ids = sorted(p.stem for p in directory.glob("*.yaml"))
    return ids or ["default-creator"]


def load_profile(name: str, config: dict[str, Any] | None = None) -> Profile:
    directory = _profiles_dir(config)
    key = (name or "").strip()

    # 兼容旧参数 予野YuYe → yuye profile
    aliases = {
        "予野YuYe": "yuye",
        "yuye": "yuye",
        "default": "default-creator",
        "creator": "default-creator",
    }
    key = aliases.get(key, key)

    if yaml is None:
        return _builtin_default()

    for stem in (key, key.replace("_", "-")):
        path = directory / f"{stem}.yaml"
        if path.exists():
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            return _parse_profile(data)

    if "予野" in name or "yuye" in name.lower():
        yuye = directory / "yuye.yaml"
        if yuye.exists():
            return _parse_profile(yaml.safe_load(yuye.read_text(encoding="utf-8")) or {})

    return _builtin_default()


def default_profile_name(config: dict[str, Any] | None = None) -> str:
    clip = (config or {}).get("clip") or {}
    return str(clip.get("default_profile") or "default-creator")
