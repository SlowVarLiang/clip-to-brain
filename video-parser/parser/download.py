"""媒体文件下载。"""

from __future__ import annotations

import os
import re
from pathlib import Path

import httpx

from .models import ParseResult


def _safe_filename(name: str, ext: str = "mp4") -> str:
    safe = re.sub(r'[\\/*?:"<>|]', "_", name).strip()[:80]
    return f"{safe or 'video'}.{ext}"


async def download_result(result: ParseResult, output_dir: str = "./downloads") -> list[str]:
    """下载解析结果中的视频/图片，返回本地文件路径列表。"""
    if not result.success:
        raise ValueError(result.error or "解析未成功，无法下载")

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    saved: list[str] = []

    async with httpx.AsyncClient(follow_redirects=True, timeout=120) as client:
        if result.video_url:
            ext = "mp4"
            if ".m3u8" in result.video_url:
                ext = "m3u8"
            fname = _safe_filename(result.title or "video", ext)
            path = out / fname
            resp = await client.get(result.video_url)
            resp.raise_for_status()
            path.write_bytes(resp.content)
            saved.append(str(path))

        if result.music_url:
            fname = _safe_filename((result.title or "music") + "_bgm", "mp3")
            path = out / fname
            resp = await client.get(result.music_url)
            resp.raise_for_status()
            path.write_bytes(resp.content)
            saved.append(str(path))

        for i, img_url in enumerate(result.images):
            ext = "jpg"
            if ".png" in img_url:
                ext = "png"
            elif ".webp" in img_url:
                ext = "webp"
            fname = _safe_filename(f"{result.title or 'image'}_{i + 1}", ext)
            path = out / fname
            resp = await client.get(img_url)
            resp.raise_for_status()
            path.write_bytes(resp.content)
            saved.append(str(path))

    return saved


def download_via_ytdlp(url: str, output_dir: str = "./downloads") -> str:
    """通过 yt-dlp 直接下载（适合 YouTube/TikTok 等）。"""
    from .ytdlp_backend import download

    return download(url, output_dir)
