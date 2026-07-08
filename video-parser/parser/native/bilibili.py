import json
from urllib.parse import urlparse

from .base import BaseParser, VideoAuthor, VideoInfo
from .utils import create_async_client


class BiliBili(BaseParser):
    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )

    def get_default_headers(self) -> dict:
        return {"User-Agent": self.USER_AGENT, "Referer": "https://www.bilibili.com/"}

    async def parse_share_url(self, share_url: str) -> VideoInfo:
        bvid = await self._get_bvid_from_url(share_url)
        return await self.parse_video_id(bvid)

    async def parse_video_id(self, video_id: str) -> VideoInfo:
        view_api = f"https://api.bilibili.com/x/web-interface/view?bvid={video_id}"
        view_resp = json.loads(await self._send_bili_request(view_api))
        if view_resp.get("code") != 0 or not view_resp.get("data", {}).get("pages"):
            raise ValueError(view_resp.get("message", "无法获取该视频"))

        data = view_resp["data"]
        cid = data["pages"][0]["cid"]
        play_api = (
            f"https://api.bilibili.com/x/player/playurl?"
            f"otype=json&fnver=0&fnval=0&qn=80&bvid={video_id}&cid={cid}&platform=html5"
        )
        play_resp = json.loads(await self._send_bili_request(play_api))
        if play_resp.get("code") != 0:
            raise ValueError(play_resp.get("message", "B站API返回错误"))

        durl = play_resp.get("data", {}).get("durl") or []
        if not durl:
            raise ValueError("无法获取该视频播放链接")

        owner = data.get("owner", {})
        return VideoInfo(
            title=data.get("title", ""),
            video_url=durl[0].get("url", ""),
            cover_url=data.get("pic", ""),
            author=VideoAuthor(
                uid=str(owner.get("mid", "")),
                name=owner.get("name", ""),
                avatar=owner.get("face", ""),
            ),
        )

    async def _get_bvid_from_url(self, raw_url: str) -> str:
        parsed = urlparse(raw_url)
        if "b23.tv" in parsed.netloc:
            async with create_async_client(follow_redirects=False) as client:
                resp = await client.get(raw_url, headers=self.get_default_headers())
                location = resp.headers.get("location")
                if not location:
                    raise ValueError("无法从b23.tv获取重定向链接")
                return await self._get_bvid_from_url(location)

        if "bilibili.com" in parsed.netloc:
            parts = parsed.path.strip("/").split("/")
            if len(parts) >= 2 and parts[0] == "video" and parts[1].startswith("BV"):
                return parts[1]
        raise ValueError("不是有效的B站视频链接")

    async def _send_bili_request(self, api_url: str) -> str:
        async with create_async_client() as client:
            response = await client.get(api_url, headers=self.get_default_headers())
            if response.status_code != 200:
                raise ValueError(f"HTTP请求失败, 状态码: {response.status_code}")
            return response.text
