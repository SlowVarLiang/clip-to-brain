import json
import re

import fake_useragent

from .base import BaseParser, ImgInfo, VideoAuthor, VideoInfo
from .utils import create_async_client


class KuaiShou(BaseParser):
    async def parse_share_url(self, share_url: str) -> VideoInfo:
        user_agent = fake_useragent.UserAgent(os="iOS").random

        async with create_async_client(follow_redirects=False) as client:
            share_response = await client.get(
                share_url,
                headers={"User-Agent": user_agent, "Referer": "https://v.kuaishou.com/"},
            )
            location_url = share_response.headers.get("location", "")
            if not location_url:
                raise Exception("failed to get location url from share url")
            location_url = location_url.replace("/fw/long-video/", "/fw/photo/")

        async with create_async_client(follow_redirects=True) as client:
            response = await client.get(
                location_url,
                headers=share_response.headers,
                cookies=share_response.cookies,
            )
            match = re.search(r"window.INIT_STATE\s*=\s*(.*?) ", response.text)
            if not match:
                raise Exception("failed to parse video JSON info from HTML")

            json_data = json.loads(match.group(1).strip())
            photo_data = {}
            for item in json_data.values():
                if "result" in item and "photo" in item:
                    photo_data = item
                    break

            if not photo_data:
                raise Exception("failed to parse photo info from INIT_STATE")
            if photo_data["result"] != 1:
                raise Exception(f"获取作品信息失败: result={photo_data['result']}")

            data = photo_data["photo"]
            video_url = ""
            if data.get("mainMvUrls"):
                video_url = data["mainMvUrls"][0]["url"]

            atlas = data.get("ext_params", {}).get("atlas", {})
            cdn_list = atlas.get("cdn", [])
            atlas_list = atlas.get("list", [])
            images = []
            if cdn_list and atlas_list:
                for atlas_item in atlas_list:
                    images.append(ImgInfo(url=f"https://{cdn_list[0]}/{atlas_item}"))

            return VideoInfo(
                video_url=video_url,
                cover_url=data["coverUrls"][0]["url"],
                title=data["caption"],
                author=VideoAuthor(name=data["userName"], avatar=data["headUrl"]),
                images=images,
            )

    async def parse_video_id(self, video_id: str) -> VideoInfo:
        raise NotImplementedError("快手暂不支持直接解析视频ID")
