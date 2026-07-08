"""微信视频号 (weixin.qq.com/sph/) 解析器。"""

from __future__ import annotations

import json
import os
import secrets
import time
from urllib.parse import parse_qs, urlparse

import httpx

from .base import BaseParser, VideoAuthor, VideoInfo
from .utils import create_async_client

YUANBAO_PARSE_URL = "https://yuanbao.tencent.com/api/weixin/get_parse_result"
FEED_INFO_URL = "https://channels.weixin.qq.com/finder-preview/api/feed/get_feed_info"

PARSE_HEADERS = {
    "accept": "application/json, text/plain, */*",
    "content-type": "application/json",
    "origin": "https://yuanbao.tencent.com",
    "referer": "https://yuanbao.tencent.com/chat/naQivTmsDa/cf4d0079-ed1b-4c55-a3f3-2ca1379727d1",
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "x-source": "web",
    "x-language": "zh-CN",
}

FEED_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
    "Origin": "https://channels.weixin.qq.com",
    "User-Agent": PARSE_HEADERS["user-agent"],
}


def _generate_rid() -> str:
    ts = format(int(time.time()), "x")
    rand = secrets.token_hex(4)
    return f"{ts}-{rand}"


class WeiXinChannels(BaseParser):
    """解析微信视频号分享短链 https://weixin.qq.com/sph/xxx"""

    async def parse_share_url(self, share_url: str) -> VideoInfo:
        cookie = os.getenv("YUANBAO_COOKIE", "").strip()
        fallback_api = os.getenv("WX_SPH_API", "https://sph.litao.workers.dev/api/fetch_video_profile").strip()

        if cookie:
            try:
                return await self._parse_with_yuanbao(share_url, cookie)
            except Exception:
                if not fallback_api:
                    raise

        if fallback_api:
            return await self._parse_with_external_api(share_url, fallback_api)

        raise ValueError(
            "微信视频号解析需要配置 YUANBAO_COOKIE（推荐）或 WX_SPH_API。"
            "Cookie 获取方式：登录 https://yuanbao.tencent.com 后从浏览器复制 Cookie。"
        )

    async def _parse_with_yuanbao(self, share_url: str, cookie: str) -> VideoInfo:
        async with create_async_client(timeout=30) as client:
            resp = await client.post(
                YUANBAO_PARSE_URL,
                headers={**PARSE_HEADERS, "cookie": cookie},
                json={"type": "video_channel_url", "url": share_url, "scene": 1},
            )
            resp.raise_for_status()
            parse_data = resp.json().get("data") or {}
            export_id = parse_data.get("wx_export_id")
            if not export_id:
                raise ValueError("元宝 API 未返回 wx_export_id，请检查 Cookie 是否有效")

            general_token = ""
            eid = export_id
            playable = parse_data.get("playable_url") or ""
            if playable:
                qs = parse_qs(urlparse(playable).query)
                general_token = (qs.get("token") or [""])[0]
                eid = (qs.get("eid") or [export_id])[0]

            rid = _generate_rid()
            referer = (
                "https://channels.weixin.qq.com/finder-preview/pages/feed"
                f"?token={general_token}&eid={eid}"
            )
            feed_resp = await client.post(
                f"{FEED_INFO_URL}?_rid={rid}&_pageUrl=https:%2F%2Fchannels.weixin.qq.com%2Ffinder-preview%2Fpages%2Ffeed",
                headers={**FEED_HEADERS, "Referer": referer},
                json={"baseReq": {"generalToken": general_token}, "exportId": eid},
            )
            feed_resp.raise_for_status()
            return self._build_from_feed(feed_resp.json())

    async def _parse_with_external_api(self, share_url: str, api_url: str) -> VideoInfo:
        async with create_async_client(timeout=45) as client:
            resp = await client.post(api_url, json={"url": share_url})
            resp.raise_for_status()
            data = resp.json()
            if data.get("error"):
                raise ValueError(data["error"])
            return self._build_from_feed(data)

    def _build_from_feed(self, payload: dict) -> VideoInfo:
        root = payload.get("data") or payload
        feed = root.get("feedInfo") or root.get("object") or root
        author_info = root.get("authorInfo") or feed.get("contact") or {}

        video_url = ""
        for key in ("h264VideoInfo", "h265VideoInfo"):
            info = feed.get(key) or {}
            if info.get("videoUrl"):
                video_url = info["videoUrl"]
                break
        if not video_url:
            video_url = feed.get("videoUrl") or feed.get("video_url") or ""

        media = (feed.get("object_desc") or {}).get("media") or []
        if not video_url and media:
            video_url = media[0].get("url") or media[0].get("videoUrl") or ""

        title = feed.get("description") or feed.get("title") or ""
        cover = ""
        pics = feed.get("picInfo") or feed.get("pic_info") or []
        if pics:
            cover = pics[0].get("url") or pics[0].get("thumbUrl") or ""
        if not cover and media:
            cover = media[0].get("thumb_url") or media[0].get("coverUrl") or ""

        return VideoInfo(
            video_url=video_url,
            cover_url=cover,
            title=title.split("\n")[0][:200] if title else "",
            author=VideoAuthor(
                name=author_info.get("nickname") or author_info.get("nickName") or "",
                avatar=author_info.get("headImgUrl") or author_info.get("headUrl") or "",
            ),
        )

    async def parse_video_id(self, video_id: str) -> VideoInfo:
        raise NotImplementedError("请使用完整分享链接解析微信视频号")
