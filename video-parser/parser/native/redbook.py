import re

import fake_useragent
import yaml

from .base import BaseParser, ImgInfo, VideoAuthor, VideoInfo
from .utils import create_async_client


class RedBook(BaseParser):
    async def parse_share_url(self, share_url: str) -> VideoInfo:
        headers = {"User-Agent": fake_useragent.UserAgent(os=["windows"]).random}
        async with create_async_client(follow_redirects=True) as client:
            response = await client.get(share_url, headers=headers)
            response.raise_for_status()

            match = re.search(
                r"window\.__INITIAL_STATE__\s*=\s*(.*?)\s*</script>",
                response.text,
                re.DOTALL,
            )
            if not match:
                raise ValueError("parse video json info from html fail")

            json_data = yaml.safe_load(match.group(1))
            note_id = json_data["note"]["currentNoteId"]
            if note_id == "undefined":
                raise Exception("parse fail: note id in response is undefined")

            data = json_data["note"]["noteDetailMap"][note_id]["note"]

            video_url = ""
            h264 = data.get("video", {}).get("media", {}).get("stream", {}).get("h264", [])
            if h264:
                video_url = h264[0].get("masterUrl", "")

            images = []
            if not video_url:
                for img_item in data["imageList"]:
                    image_id = img_item["urlDefault"].split("/")[-1].split("!")[0]
                    spectrum = "spectrum/" if "spectrum" in img_item["urlDefault"] else ""
                    new_url = f"https://ci.xiaohongshu.com/notes_pre_post/{spectrum}{image_id}?imageView2/format/jpg"
                    img_info = ImgInfo(url=new_url)
                    if "notes_pre_post" not in img_item["urlDefault"]:
                        img_info.url = img_item["urlDefault"]
                    if img_item.get("livePhoto") and img_item.get("stream", {}).get("h264"):
                        img_info.live_photo_url = img_item["stream"]["h264"][0]["masterUrl"]
                    images.append(img_info)

            return VideoInfo(
                video_url=video_url,
                cover_url=data["imageList"][0]["urlDefault"],
                title=data["title"],
                images=images,
                author=VideoAuthor(
                    uid=data["user"]["userId"],
                    name=data["user"]["nickname"],
                    avatar=data["user"]["avatar"],
                ),
            )

    async def parse_video_id(self, video_id: str) -> VideoInfo:
        raise NotImplementedError("小红书暂不支持直接解析视频ID")
