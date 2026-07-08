"""统一解析入口 — 自动识别平台，native 优先，yt-dlp 兜底。"""

from __future__ import annotations

import re

from .models import ParseResult
from .native.registry import get_native_parser
from .platforms import PlatformInfo, detect_platform
from .ytdlp_backend import extract_info

URL_PATTERN = re.compile(
    r"https?://[^\s<>\"']+|"
    r"(?:v\.douyin|v\.kuaishou|xhslink|b23)\.[^\s<>\"']+"
)


def extract_urls(text: str) -> list[str]:
    found = URL_PATTERN.findall(text.strip())
    seen: set[str] = set()
    result: list[str] = []
    for url in found:
        if not url.startswith("http"):
            url = "https://" + url
        if url not in seen:
            seen.add(url)
            result.append(url)
    return result


async def _parse_native(url: str, platform: PlatformInfo) -> ParseResult:
    parser = get_native_parser(url)
    if not parser:
        raise ValueError("无可用原生解析器")
    info = await parser.parse_share_url(url)
    return ParseResult.from_native(info, platform.name, url)


def _parse_ytdlp(url: str, platform: PlatformInfo | None) -> ParseResult:
    name = platform.name if platform else "通用"
    try:
        info = extract_info(url)
        return ParseResult.from_ytdlp(info, name, url)
    except Exception as exc:
        return ParseResult.fail(url, str(exc), name)


async def parse_url(url: str) -> ParseResult:
    url = url.strip()
    if not url.startswith("http"):
        url = "https://" + url

    platform = detect_platform(url)
    platform_name = platform.name if platform else "未知"
    backend = platform.backend if platform else "ytdlp"
    has_native = get_native_parser(url) is not None

    if has_native and backend in ("native", "both"):
        try:
            return await _parse_native(url, platform or PlatformInfo(platform_name, (), "native"))
        except Exception as native_err:
            if backend == "native":
                return ParseResult.fail(url, f"原生解析失败: {native_err}", platform_name)

    result = _parse_ytdlp(url, platform)
    if not result.success and has_native:
        result.error = f"所有解析方式均失败。最后错误: {result.error}"
    return result


async def parse_text(text: str) -> list[ParseResult]:
    urls = extract_urls(text)
    if not urls:
        return [ParseResult.fail(text, "未检测到有效链接")]
    return [await parse_url(url) for url in urls]
