import json
import re
import secrets
import string
from urllib.parse import parse_qs, urlparse

from .base import BaseParser, ImgInfo, VideoAuthor, VideoInfo
from .utils import create_async_client


class DouYin(BaseParser):
    async def parse_share_url(self, share_url: str) -> VideoInfo:
        parsed_url = urlparse(share_url)
        host = parsed_url.netloc

        if host in ["www.iesdouyin.com", "www.douyin.com"]:
            video_id = self._parse_video_id_from_path(share_url)
            if not video_id:
                raise ValueError("Failed to parse video ID from PC share URL")
            share_url = self._get_request_url_by_video_id(video_id)
        elif host == "v.douyin.com":
            video_id = await self._parse_app_share_url(share_url)
            if not video_id:
                raise ValueError("Failed to parse video ID from app share URL")
            share_url = self._get_request_url_by_video_id(video_id)
        else:
            raise ValueError(f"Douyin not support this host: {host}")

        async with create_async_client(follow_redirects=True) as client:
            response = await client.get(share_url, headers=self.get_default_headers())
            response.raise_for_status()

            is_note = self._is_note_content(response.text, share_url)
            json_data = None
            if is_note:
                json_data = await self._get_slides_info(video_id)

            if not json_data:
                pattern = re.compile(
                    r"window\._ROUTER_DATA\s*=\s*(.*?)\s*</script>",
                    flags=re.DOTALL,
                )
                find_res = pattern.search(response.text)
                if not find_res or not find_res.group(1):
                    raise ValueError("parse video json info from html fail")
                json_data = json.loads(find_res.group(1).strip())

            data = None
            if isinstance(json_data, dict) and "aweme_details" in json_data:
                if json_data["aweme_details"]:
                    data = json_data["aweme_details"][0]
            elif isinstance(json_data, dict) and "loaderData" in json_data:
                loader = json_data["loaderData"]
                original = None
                if "video_(id)/page" in loader:
                    original = loader["video_(id)/page"]["videoInfoRes"]
                elif "note_(id)/page" in loader:
                    original = loader["note_(id)/page"]["videoInfoRes"]
                else:
                    raise Exception("failed to parse Videos or Photo Gallery info from json")
                if not original["item_list"]:
                    msg = original["filter_list"][0]["detail_msg"] if original.get("filter_list") else "failed"
                    raise Exception(msg)
                data = original["item_list"][0]
            else:
                raise Exception("Unknown data structure")

            images = []
            if "images" in data and isinstance(data["images"], list):
                for img in data["images"]:
                    if img.get("url_list"):
                        image_url = self._get_no_webp_url(img["url_list"])
                        live_photo_url = ""
                        if img.get("video", {}).get("play_addr", {}).get("url_list"):
                            live_photo_url = img["video"]["play_addr"]["url_list"][0]
                        if image_url:
                            images.append(ImgInfo(url=image_url, live_photo_url=live_photo_url))

            video_url = ""
            music_url = ""
            if "video" in data and "play_addr" in data["video"]:
                if data["video"]["play_addr"].get("url_list"):
                    video_url = data["video"]["play_addr"]["url_list"][0].replace("playwm", "play")
                music_url = data["video"]["play_addr"].get("uri", "")

            if images:
                video_url = ""
            else:
                music_url = ""

            video_mp4_url = ""
            if video_url:
                video_mp4_url = await self.get_video_redirect_url(video_url)

            cover_url = ""
            if data.get("video", {}).get("cover", {}).get("url_list"):
                cover_url = self._get_no_webp_url(data["video"]["cover"]["url_list"])

            return VideoInfo(
                video_url=video_mp4_url,
                cover_url=cover_url,
                music_url=music_url,
                title=data.get("desc", ""),
                images=images,
                author=VideoAuthor(
                    uid=data.get("author", {}).get("sec_uid", ""),
                    name=data.get("author", {}).get("nickname", ""),
                    avatar=(data.get("author", {}).get("avatar_thumb", {}).get("url_list") or [""])[0],
                ),
            )

    async def get_video_redirect_url(self, video_url: str) -> str:
        async with create_async_client(follow_redirects=False) as client:
            response = await client.get(video_url, headers=self.get_default_headers())
            return response.headers.get("location") or video_url

    async def parse_video_id(self, video_id: str) -> VideoInfo:
        return await self.parse_share_url(self._get_request_url_by_video_id(video_id))

    def _get_request_url_by_video_id(self, video_id: str) -> str:
        return f"https://www.iesdouyin.com/share/video/{video_id}/"

    async def _parse_app_share_url(self, share_url: str) -> str:
        async with create_async_client(follow_redirects=False) as client:
            response = await client.get(share_url, headers=self.get_default_headers())
            location = response.headers.get("location", "")
            if not location or "ixigua.com" in location:
                return ""
            return self._parse_video_id_from_path(location)

    def _parse_video_id_from_path(self, url_path: str) -> str:
        if not url_path:
            return ""
        try:
            parsed = urlparse(url_path)
            query = parse_qs(parsed.query)
            if "modal_id" in query:
                return query["modal_id"][0]
            parts = parsed.path.strip("/").split("/")
            if parts:
                return parts[-1]
        except Exception:
            pass
        return ""

    def _get_no_webp_url(self, url_list: list) -> str:
        for url in url_list:
            if url and not url.endswith(".webp"):
                return url
        return url_list[0] if url_list else ""

    def _is_note_content(self, html_content: str, share_url: str) -> bool:
        try:
            match = re.search(
                r'<link[^>]*rel=["\']canonical["\'][^>]*href=["\']([^"\']+)["\']',
                html_content,
                re.IGNORECASE,
            )
            if match and "/note/" in match.group(1):
                return True
            if "/note/" in urlparse(share_url).path:
                return True
            if "note_" in html_content or "图文" in html_content:
                return True
        except Exception:
            pass
        return False

    async def _get_slides_info(self, video_id: str) -> dict | None:
        try:
            web_id = "75" + "".join(secrets.choice(string.digits) for _ in range(15))
            a_bogus = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(64))
            api_url = (
                f"https://www.iesdouyin.com/web/api/v2/aweme/slidesinfo/"
                f"?reflow_source=reflow_page&web_id={web_id}&device_id={web_id}"
                f"&aweme_ids=%5B{video_id}%5D&request_source=200&a_bogus={a_bogus}"
            )
            async with create_async_client() as client:
                response = await client.get(api_url, headers=self.get_default_headers())
                response.raise_for_status()
                data = response.json()
                return data if data.get("aweme_details") else None
        except Exception:
            return None
