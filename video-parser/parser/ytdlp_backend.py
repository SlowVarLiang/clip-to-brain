"""yt-dlp 后端 — 覆盖 YouTube / TikTok / 知乎 等 1800+ 站点。"""

from __future__ import annotations

import os
from typing import Any

import yt_dlp


def _base_opts() -> dict[str, Any]:
    opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "format": "best",
        "socket_timeout": 30,
        "nocheckcertificate": True,
    }
    proxy = os.getenv("HTTP_PROXY") or os.getenv("HTTPS_PROXY")
    if proxy:
        opts["proxy"] = proxy
    return opts


def extract_info(url: str) -> dict[str, Any]:
    opts = _base_opts()
    with yt_dlp.YoutubeDL(opts) as ydl:
        return ydl.extract_info(url, download=False)


def download(url: str, output_dir: str, filename: str | None = None) -> str:
    outtmpl = os.path.join(output_dir, filename or "%(title).80s.%(ext)s")
    opts = _base_opts()
    opts.update({"skip_download": False, "outtmpl": outtmpl})
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        return ydl.prepare_filename(info)
