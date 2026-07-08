"""统一解析结果模型。"""

from __future__ import annotations

import dataclasses
from typing import Any


@dataclasses.dataclass
class ParseResult:
    success: bool
    platform: str
    title: str = ""
    author: str = ""
    cover_url: str = ""
    video_url: str = ""
    music_url: str = ""
    images: list[str] = dataclasses.field(default_factory=list)
    media_type: str = "video"  # video | images | livephoto
    backend: str = ""  # native | ytdlp
    raw_url: str = ""
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_native(cls, info: Any, platform: str, raw_url: str) -> ParseResult:
        images = [img.url for img in (info.images or []) if img.url]
        media_type = "images" if images and not info.video_url else "video"
        if images and info.video_url:
            media_type = "livephoto"
        return cls(
            success=True,
            platform=platform,
            title=info.title or "",
            author=(info.author.name if info.author else "") or "",
            cover_url=info.cover_url or "",
            video_url=info.video_url or "",
            music_url=info.music_url or "",
            images=images,
            media_type=media_type,
            backend="native",
            raw_url=raw_url,
        )

    @classmethod
    def from_ytdlp(cls, info: dict[str, Any], platform: str, raw_url: str) -> ParseResult:
        video_url = info.get("url") or ""
        if not video_url and info.get("formats"):
            formats = info["formats"]
            best = max(formats, key=lambda f: f.get("height") or 0)
            video_url = best.get("url") or ""

        images: list[str] = []
        if info.get("thumbnails"):
            cover = info["thumbnails"][-1].get("url", "")
        else:
            cover = info.get("thumbnail") or ""

        return cls(
            success=bool(video_url),
            platform=platform,
            title=info.get("title") or "",
            author=info.get("uploader") or info.get("channel") or "",
            cover_url=cover,
            video_url=video_url,
            media_type="video",
            backend="ytdlp",
            raw_url=raw_url,
            error="" if video_url else "未找到可下载的视频地址",
        )

    @classmethod
    def fail(cls, raw_url: str, error: str, platform: str = "未知") -> ParseResult:
        return cls(success=False, platform=platform, raw_url=raw_url, error=error)
