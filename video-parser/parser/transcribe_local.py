"""本地转写 — faster-whisper + ffmpeg，输出格式与阿里云一致。"""

from __future__ import annotations

import asyncio
import gc
import os
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any

import httpx

from fastapi import HTTPException

from .transcribe import TranscribeResult, TranscriptSegment


def _setup_cuda_dll_path() -> None:
    """Windows：把 venv 内 nvidia-cublas-cu12 的 DLL 目录加入 PATH。"""
    if os.name != "nt":
        return
    try:
        import nvidia.cublas  # type: ignore[import-untyped]
    except ImportError:
        return
    pkg_root: Path | None = None
    if getattr(nvidia.cublas, "__file__", None):
        pkg_root = Path(nvidia.cublas.__file__).resolve().parent
    elif getattr(nvidia.cublas, "__path__", None):
        pkg_root = Path(nvidia.cublas.__path__[0])
    if not pkg_root:
        return
    bin_dir = pkg_root / "bin"
    if bin_dir.is_dir():
        os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")


def _ffmpeg_bin() -> str:
    custom = os.getenv("FFMPEG_PATH", "").strip()
    if custom and Path(custom).exists():
        return custom
    path = shutil.which("ffmpeg")
    if not path:
        raise RuntimeError(
            "未找到 ffmpeg。请安装后加入 PATH，或在 .env 设置 FFMPEG_PATH=完整路径"
        )
    return path


def _ffprobe_bin() -> str:
    ffmpeg = _ffmpeg_bin()
    probe = Path(ffmpeg).with_name("ffprobe.exe" if os.name == "nt" else "ffprobe")
    if probe.exists():
        return str(probe)
    path = shutil.which("ffprobe")
    if not path:
        raise RuntimeError("未找到 ffprobe，请与 ffmpeg 一并安装")
    return path


def _require_ffmpeg() -> str:
    return _ffmpeg_bin()


def _get_audio_duration(wav_path: Path) -> float:
    cmd = [
        _ffprobe_bin(),
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(wav_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "ffprobe 失败")[-800:])
    return float(proc.stdout.strip())


def _split_wav_chunks(
    wav_path: Path, chunk_sec: int, out_dir: Path
) -> list[tuple[Path, float]]:
    duration = _get_audio_duration(wav_path)
    ffmpeg = _require_ffmpeg()
    chunks: list[tuple[Path, float]] = []
    start = 0.0
    idx = 0
    while start < duration - 0.05:
        chunk_path = out_dir / f"chunk_{idx:03d}.wav"
        cmd = [
            ffmpeg,
            "-y",
            "-i",
            str(wav_path),
            "-ss",
            f"{start:.3f}",
            "-t",
            str(chunk_sec),
            "-acodec",
            "pcm_s16le",
            "-ar",
            "16000",
            "-ac",
            "1",
            str(chunk_path),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "ffmpeg 切分失败")[-800:]
            raise RuntimeError(err)
        chunks.append((chunk_path, start))
        start += chunk_sec
        idx += 1
    return chunks


async def _download_media(url: str, dest: Path) -> None:
    async with httpx.AsyncClient(follow_redirects=True, timeout=300) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        dest.write_bytes(resp.content)


def _extract_audio_wav(video_path: Path, wav_path: Path) -> None:
    ffmpeg = _require_ffmpeg()
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(video_path),
        "-vn",
        "-acodec",
        "pcm_s16le",
        "-ar",
        "16000",
        "-ac",
        "1",
        str(wav_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "ffmpeg 失败")[-800:]
        raise RuntimeError(err)


def _load_whisper_model() -> Any:
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError(
            "请安装 faster-whisper：pip install faster-whisper"
        ) from exc

    model_name = os.getenv("WHISPER_MODEL", "medium")
    device = os.getenv("WHISPER_DEVICE", "cuda")
    compute_type = os.getenv("WHISPER_COMPUTE_TYPE", "float16")
    if device in ("cuda", "gpu") and compute_type == "int8":
        compute_type = "float16"

    if device in ("cuda", "gpu", "auto"):
        _setup_cuda_dll_path()

    return WhisperModel(model_name, device=device, compute_type=compute_type)


def _transcribe_file(
    model: Any,
    wav_path: Path,
    *,
    offset_ms: int = 0,
) -> list[TranscriptSegment]:
    language = os.getenv("WHISPER_LANGUAGE", "zh") or None
    if language == "auto":
        language = None
    vad_filter = os.getenv("WHISPER_VAD_FILTER", "true").lower() in ("1", "true", "yes")

    segments_iter, _info = model.transcribe(
        str(wav_path),
        language=language,
        vad_filter=vad_filter,
        beam_size=int(os.getenv("WHISPER_BEAM_SIZE", "5")),
    )

    segments: list[TranscriptSegment] = []
    for seg in segments_iter:
        text = (seg.text or "").strip()
        if not text:
            continue
        begin_ms = int(seg.start * 1000) + offset_ms
        end_ms = int(seg.end * 1000) + offset_ms
        segments.append(TranscriptSegment(begin_ms=begin_ms, end_ms=end_ms, text=text))
    return segments


def _transcribe_wav(wav_path: Path) -> TranscribeResult:
    model_name = os.getenv("WHISPER_MODEL", "medium")
    language = os.getenv("WHISPER_LANGUAGE", "zh") or None
    if language == "auto":
        language = None

    chunk_sec = int(os.getenv("WHISPER_CHUNK_SECONDS", "600"))
    duration = _get_audio_duration(wav_path)

    all_segments: list[TranscriptSegment] = []
    if duration > chunk_sec + 1:
        with tempfile.TemporaryDirectory(prefix="v2k-asr-chunks-") as chunk_tmp:
            chunks = _split_wav_chunks(wav_path, chunk_sec, Path(chunk_tmp))
            for idx, (chunk_path, offset_sec) in enumerate(chunks, 1):
                model = _load_whisper_model()
                try:
                    all_segments.extend(
                        _transcribe_file(
                            model,
                            chunk_path,
                            offset_ms=int(offset_sec * 1000),
                        )
                    )
                finally:
                    del model
                    gc.collect()
    else:
        model = _load_whisper_model()
        try:
            all_segments = _transcribe_file(model, wav_path)
        finally:
            del model
            gc.collect()

    full_text = "".join(s.text for s in all_segments)
    task_id = f"local-{uuid.uuid4().hex[:16]}"
    lang = language or "unknown"
    return TranscribeResult(
        success=True,
        task_id=task_id,
        status=f"SUCCESS(local/{model_name}/{lang})",
        full_text=full_text,
        segments=all_segments,
    )


async def transcribe_video_url_local(video_url: str) -> TranscribeResult:
    if not video_url:
        return TranscribeResult(success=False, error="视频地址为空")

    from .security import validate_video_url

    try:
        validate_video_url(video_url)
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        return TranscribeResult(success=False, error=detail)
    except Exception as exc:
        return TranscribeResult(success=False, error=str(exc))

    try:
        with tempfile.TemporaryDirectory(prefix="v2k-local-asr-") as tmp:
            tmp_dir = Path(tmp)
            suffix = ".mp4"
            lower = video_url.lower()
            if ".mp3" in lower:
                suffix = ".mp3"
            elif ".m4a" in lower:
                suffix = ".m4a"

            media_path = tmp_dir / f"media{suffix}"
            wav_path = tmp_dir / "audio.wav"

            await _download_media(video_url, media_path)
            await asyncio.to_thread(_extract_audio_wav, media_path, wav_path)
            return await asyncio.to_thread(_transcribe_wav, wav_path)
    except Exception as exc:
        return TranscribeResult(success=False, error=str(exc))
