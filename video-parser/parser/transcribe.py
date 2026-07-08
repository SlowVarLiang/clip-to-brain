"""阿里云录音文件识别 — 视频 URL 转逐字稿。"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import uuid
from dataclasses import dataclass, field
from typing import Any

import httpx

# 任务状态缓存（生产环境建议换 Redis）
_task_cache: dict[str, dict[str, Any]] = {}


@dataclass
class TranscriptSegment:
    begin_ms: int
    end_ms: int
    text: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "begin_ms": self.begin_ms,
            "end_ms": self.end_ms,
            "begin_time": _format_ms(self.begin_ms),
            "end_time": _format_ms(self.end_ms),
            "text": self.text,
        }


@dataclass
class TranscribeResult:
    success: bool
    task_id: str = ""
    status: str = ""
    full_text: str = ""
    segments: list[TranscriptSegment] = field(default_factory=list)
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "task_id": self.task_id,
            "status": self.status,
            "full_text": self.full_text,
            "segments": [s.to_dict() for s in self.segments],
            "error": self.error,
        }


def _format_ms(ms: int) -> str:
    s, ms_rem = divmod(max(ms, 0), 1000)
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h:02d}:{m:02d}:{s:02d}.{ms_rem:03d}"
    return f"{m:02d}:{s:02d}.{ms_rem:03d}"


def _get_config() -> dict[str, str]:
    ak = os.getenv("ALIYUN_AK_ID") or os.getenv("ALIBABA_CLOUD_ACCESS_KEY_ID", "")
    sk = os.getenv("ALIYUN_AK_SECRET") or os.getenv("ALIBABA_CLOUD_ACCESS_KEY_SECRET", "")
    app_key = os.getenv("NLS_APP_KEY", "")
    region = os.getenv("ALIYUN_NLS_REGION", "cn-shanghai")
    if not ak or not sk or not app_key:
        raise ValueError(
            "请配置阿里云凭证：ALIYUN_AK_ID、ALIYUN_AK_SECRET、NLS_APP_KEY"
        )
    return {"ak": ak, "sk": sk, "app_key": app_key, "region": region}


def _parse_sentences(result_json: dict[str, Any]) -> tuple[str, list[TranscriptSegment]]:
    result = result_json.get("Result") or {}
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except json.JSONDecodeError:
            result = {}

    sentences = result.get("Sentences") or result.get("sentences") or []
    segments: list[TranscriptSegment] = []
    for item in sentences:
        text = (item.get("Text") or item.get("text") or "").strip()
        if not text:
            continue
        segments.append(
            TranscriptSegment(
                begin_ms=int(item.get("BeginTime") or item.get("begin_time") or 0),
                end_ms=int(item.get("EndTime") or item.get("end_time") or 0),
                text=text,
            )
        )
    full_text = "".join(s.text for s in segments)
    return full_text, segments


def _submit_and_poll(file_link: str) -> TranscribeResult:
    from aliyunsdkcore.acs_exception.exceptions import ClientException, ServerException
    from aliyunsdkcore.client import AcsClient
    from aliyunsdkcore.request import CommonRequest

    cfg = _get_config()
    region = cfg["region"]
    domain = f"filetrans.{region}.aliyuncs.com"

    client = AcsClient(cfg["ak"], cfg["sk"], region)

    post_req = CommonRequest()
    post_req.set_domain(domain)
    post_req.set_version("2018-08-17")
    post_req.set_product("nls-filetrans")
    post_req.set_action_name("SubmitTask")
    post_req.set_method("POST")

    task_body = json.dumps(
        {
            "appkey": cfg["app_key"],
            "file_link": file_link,
            "version": "4.0",
            "enable_words": False,
            "enable_sample_rate_adaptive": True,
        }
    )
    post_req.add_body_params("Task", task_body)

    try:
        post_resp = json.loads(client.do_action_with_exception(post_req))
    except (ServerException, ClientException) as exc:
        return TranscribeResult(success=False, error=str(exc))

    if post_resp.get("StatusText") != "SUCCESS":
        return TranscribeResult(
            success=False,
            error=post_resp.get("StatusText") or "提交识别任务失败",
        )

    task_id = post_resp.get("TaskId", "")
    if not task_id:
        return TranscribeResult(success=False, error="未返回 TaskId")

    get_req = CommonRequest()
    get_req.set_domain(domain)
    get_req.set_version("2018-08-17")
    get_req.set_product("nls-filetrans")
    get_req.set_action_name("GetTaskResult")
    get_req.set_method("GET")
    get_req.add_query_param("TaskId", task_id)

    import time

    poll_interval = int(os.getenv("NLS_POLL_INTERVAL", "5"))
    max_wait = int(os.getenv("NLS_MAX_WAIT", "3600"))
    elapsed = 0
    last_resp: dict[str, Any] = {}

    while elapsed < max_wait:
        try:
            last_resp = json.loads(client.do_action_with_exception(get_req))
        except (ServerException, ClientException) as exc:
            return TranscribeResult(success=False, task_id=task_id, error=str(exc))

        status = last_resp.get("StatusText", "")
        _task_cache[task_id] = {"status": status, "raw": last_resp}

        if status in ("RUNNING", "QUEUEING"):
            time.sleep(poll_interval)
            elapsed += poll_interval
            continue
        break

    status = last_resp.get("StatusText", "")
    if status == "SUCCESS":
        full_text, segments = _parse_sentences(last_resp)
        return TranscribeResult(
            success=True,
            task_id=task_id,
            status=status,
            full_text=full_text,
            segments=segments,
        )

    if status == "SUCCESS_WITH_NO_VALID_FRAGMENT":
        return TranscribeResult(
            success=True,
            task_id=task_id,
            status=status,
            full_text="",
            segments=[],
            error="识别完成但未检测到有效语音片段",
        )

    return TranscribeResult(
        success=False,
        task_id=task_id,
        status=status,
        error=status or "识别失败",
    )


async def _ensure_public_url(video_url: str) -> str:
    """确保阿里云可访问的文件 URL。优先 OSS，失败则尝试直链。"""
    bucket = os.getenv("ALIYUN_OSS_BUCKET", "").strip()
    if not bucket:
        return video_url

    try:
        return await _upload_to_oss(video_url, bucket)
    except Exception:
        return video_url


async def _upload_to_oss(video_url: str, bucket: str) -> str:
    import oss2

    cfg = _get_config()
    endpoint = os.getenv("ALIYUN_OSS_ENDPOINT", f"oss-{cfg['region']}.aliyuncs.com")
    prefix = os.getenv("ALIYUN_OSS_PREFIX", "video-transcribe").strip("/")

    auth = oss2.Auth(cfg["ak"], cfg["sk"])
    bucket_obj = oss2.Bucket(auth, endpoint, bucket)

    ext = ".mp4"
    if ".m3u8" in video_url:
        ext = ".m3u8"
    elif ".mp3" in video_url:
        ext = ".mp3"

    object_key = f"{prefix}/{uuid.uuid4().hex}{ext}"

    async with httpx.AsyncClient(follow_redirects=True, timeout=300) as client:
        resp = await client.get(video_url)
        resp.raise_for_status()
        data = resp.content

    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        tmp.write(data)
        tmp_path = tmp.name

    try:
        bucket_obj.put_object_from_file(object_key, tmp_path)
    finally:
        os.unlink(tmp_path)

    # 公共读 URL；私有桶需改为签名 URL
    if os.getenv("ALIYUN_OSS_PUBLIC", "true").lower() == "true":
        return f"https://{bucket}.{endpoint}/{object_key}"
    return bucket_obj.sign_url("GET", object_key, 3600)


async def transcribe_video_url(video_url: str) -> TranscribeResult:
    """将视频 URL 转为带时间戳的逐字稿。"""
    if not video_url:
        return TranscribeResult(success=False, error="视频地址为空")

    backend = os.getenv("TRANSCRIBE_BACKEND", "local").strip().lower()
    if backend in ("local", "whisper", "faster-whisper"):
        from .transcribe_local import transcribe_video_url_local

        return await transcribe_video_url_local(video_url)

    file_link = await _ensure_public_url(video_url)
    return await asyncio.to_thread(_submit_and_poll, file_link)


def get_task_status(task_id: str) -> dict[str, Any] | None:
    return _task_cache.get(task_id)
