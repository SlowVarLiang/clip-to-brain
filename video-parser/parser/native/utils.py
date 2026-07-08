import os

import httpx


def create_async_client(**kwargs) -> httpx.AsyncClient:
    proxy = os.getenv("PARSE_VIDEO_PROXY") or os.getenv("HTTP_PROXY") or os.getenv("HTTPS_PROXY")
    if proxy:
        kwargs["proxy"] = proxy
    return httpx.AsyncClient(**kwargs)
