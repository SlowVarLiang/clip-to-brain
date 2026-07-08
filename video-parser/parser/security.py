"""API 安全：URL 校验、限流。"""

from __future__ import annotations

import ipaddress
import os
import time
from collections import defaultdict
from urllib.parse import urlparse

from fastapi import HTTPException, Request

from .accounts import Account

# 转写下载允许的 CDN 域名后缀（逗号分隔，可追加）
_DEFAULT_VIDEO_SUFFIXES = (
    "xhscdn.com",
    "douyin.com",
    "douyinvod.com",
    "ixigua.com",
    "bdxiguastatic.com",
    "bilibili.com",
    "hdslb.com",
    "bilivideo.com",
    "qq.com",
    "qpic.cn",
    "qlogo.cn",
    "weixin.qq.com",
    "bytecdn.cn",
    "byteimg.com",
    "tiktokcdn.com",
    "tiktokv.com",
    "googlevideo.com",
    "youtube.com",
    "ytimg.com",
)


def _video_suffixes() -> tuple[str, ...]:
    raw = os.getenv("ALLOWED_VIDEO_HOSTS", "").strip()
    if raw:
        return tuple(s.strip().lower() for s in raw.split(",") if s.strip())
    return _DEFAULT_VIDEO_SUFFIXES


def _is_private_host(host: str) -> bool:
    host = host.lower().strip(".")
    if not host or host in ("localhost", "0.0.0.0"):
        return True
    if host.endswith(".local") or host.endswith(".internal"):
        return True
    # 纯 IP
    try:
        ip = ipaddress.ip_address(host.split(":")[0])
        return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
    except ValueError:
        return False


def validate_video_url(url: str) -> None:
    """转写前校验 video_url，防 SSRF。"""
    if not url or not url.strip():
        raise HTTPException(status_code=400, detail="video_url 为空")

    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(status_code=400, detail="仅允许 http/https 视频地址")

    host = (parsed.hostname or "").lower()
    if _is_private_host(host):
        raise HTTPException(status_code=403, detail="不允许访问内网或本地地址")

    mode = os.getenv("TRANSCRIBE_URL_MODE", "cdn").strip().lower()
    if mode in ("any", "open", "off"):
        return

    suffixes = _video_suffixes()
    if not any(host == s or host.endswith("." + s) for s in suffixes):
        raise HTTPException(
            status_code=403,
            detail=f"视频域名不在白名单（{host}）。可在 ALLOWED_VIDEO_HOSTS 追加。",
        )


class RateLimiter:
    def __init__(self, max_requests: int, window_sec: int = 60) -> None:
        self.max_requests = max_requests
        self.window_sec = window_sec
        self._hits: dict[str, list[float]] = defaultdict(list)

    def check(self, client_key: str, *, max_requests: int | None = None) -> None:
        limit = max_requests if max_requests is not None else self.max_requests
        if limit <= 0:
            return
        now = time.time()
        window_start = now - self.window_sec
        hits = [t for t in self._hits[client_key] if t > window_start]
        if len(hits) >= limit:
            raise HTTPException(status_code=429, detail="请求过于频繁，请稍后再试")
        hits.append(now)
        self._hits[client_key] = hits


def account_rate_limit(account: Account, limiter: RateLimiter) -> None:
    """按账户限流；未单独配置时使用全局默认。"""
    per_account = account.rate_limit_per_minute
    global_default = int(os.getenv("RATE_LIMIT_PER_MINUTE", "30"))
    limit = per_account if per_account > 0 else global_default
    limiter.check(f"acct:{account.id}", max_requests=limit)


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def make_rate_limiter() -> RateLimiter:
    limit = int(os.getenv("RATE_LIMIT_PER_MINUTE", "30"))
    return RateLimiter(max_requests=limit, window_sec=60)
