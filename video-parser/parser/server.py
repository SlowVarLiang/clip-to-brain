"""HTTP API 服务 — 视频解析 + 逐字稿转写。"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

load_dotenv()

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
API_KEY = os.getenv("API_KEY", "").strip()
REQUIRE_API_KEY = os.getenv("REQUIRE_API_KEY", "false").strip().lower() in ("1", "true", "yes")
DOCS_ENABLED = os.getenv("DOCS_ENABLED", "false").strip().lower() in ("1", "true", "yes")
SERVE_WEB_UI = os.getenv("SERVE_WEB_UI", "false").strip().lower() in ("1", "true", "yes")

from .accounts import Account, AccountStore  # noqa: E402
from .security import account_rate_limit, make_rate_limiter, validate_video_url  # noqa: E402
from .transcribe import TranscribeResult, transcribe_video_url  # noqa: E402
from .unified import parse_text, parse_url  # noqa: E402

_rate_limiter = make_rate_limiter()
_account_store = AccountStore(legacy_api_key=API_KEY)

app = FastAPI(
    title="视频去水印 & 逐字稿 API",
    description="支持 80+ 平台解析 + 本地 Whisper 转写",
    version="1.4.0",
    docs_url="/docs" if DOCS_ENABLED else None,
    redoc_url="/redoc" if DOCS_ENABLED else None,
    openapi_url="/openapi.json" if DOCS_ENABLED else None,
)

_cors = os.getenv("CORS_ORIGINS", "").strip()
_extension_cors = os.getenv("EXTENSION_CORS", "true").strip().lower() in ("1", "true", "yes")
if _cors or _extension_cors:
    _origins = [o.strip() for o in _cors.split(",") if o.strip()]
    if "*" in _origins:
        _origins = ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_origins or [],
        allow_origin_regex=r"chrome-extension://.*" if _extension_cors else None,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "X-API-Key"],
    )

_transcribe_jobs: dict[str, dict] = {}
_ingest_jobs: dict[str, dict] = {}
_clip_jobs: dict[str, dict] = {}


def _ensure_configured() -> None:
    if REQUIRE_API_KEY and not _account_store.has_any_key():
        raise HTTPException(status_code=503, detail="服务未配置 API Key（.env 或 accounts.json）")


def get_account(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> Account:
    _ensure_configured()
    if not REQUIRE_API_KEY and not x_api_key:
        return Account(id="anonymous", name="anonymous", api_key_hash="", enabled=True)
    return _account_store.require_account(x_api_key)


def rate_limit_account(account: Account = Depends(get_account)) -> Account:
    account_rate_limit(account, _rate_limiter)
    return account


class ParseRequest(BaseModel):
    url: str | None = None
    text: str | None = None


class TranscribeRequest(BaseModel):
    video_url: str


class PipelineRequest(BaseModel):
    url: str | None = None
    text: str | None = None
    skip_transcribe: bool = False


class IngestRequest(BaseModel):
    url: str
    category: str | None = None
    subfolder: str | None = None
    skip_transcribe: bool = False


class ClipRequest(BaseModel):
    url: str | None = None
    text: str | None = None
    input: str | None = None
    profile: str | None = None
    account: str | None = None  # 兼容旧字段
    category: str | None = None
    subfolder: str | None = None
    title: str | None = None


async def _transcribe_checked(video_url: str) -> TranscribeResult:
    validate_video_url(video_url)
    return await transcribe_video_url(video_url)


def _record_transcribe_if_ok(account: Account, result: TranscribeResult) -> None:
    if result.success:
        _account_store.record_transcribe_usage(account)


@app.get("/")
async def index():
    if not SERVE_WEB_UI:
        return JSONResponse({"status": "ok", "message": "video-parser API"})
    index_file = WEB_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"status": "ok"}


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "auth_required": REQUIRE_API_KEY and _account_store.has_any_key(),
    }


@app.get("/account/me")
async def account_me(account: Account = Depends(rate_limit_account)):
    """查询当前 Key 对应账户信息与本月用量。"""
    return {"success": True, "account": account.public_info()}


@app.get("/api", dependencies=[Depends(rate_limit_account)])
async def api_root():
    return {
        "name": "视频去水印 & 逐字稿 API",
        "endpoints": {
            "health": "GET /health",
            "account": "GET /account/me",
            "pipeline": "POST /pipeline",
            "ingest": "POST /ingest",
            "ingest_status": "GET /ingest/{job_id}",
            "clip": "POST /clip",
            "clip_stats": "GET /clip/stats",
            "clip_dashboard": "GET /clip/dashboard",
            "clip_status": "GET /clip/{job_id}",
            "bot_feishu": "POST /bot/feishu",
            "bot_telegram": "POST /bot/telegram",
            "parse": "GET/POST /parse",
            "transcribe_sync": "POST /transcribe/sync",
        },
    }


@app.get("/platforms", dependencies=[Depends(rate_limit_account)])
async def platforms():
    from .platforms import PLATFORMS

    return [{"name": p.name, "backend": p.backend} for p in PLATFORMS]


@app.get("/parse", dependencies=[Depends(rate_limit_account)])
async def parse_get(url: str = Query(..., description="视频/图集分享链接")):
    result = await parse_url(url)
    return JSONResponse(result.to_dict())


@app.post("/parse", dependencies=[Depends(rate_limit_account)])
async def parse_post(body: ParseRequest):
    if body.text:
        results = await parse_text(body.text)
        return JSONResponse([r.to_dict() for r in results])
    if body.url:
        result = await parse_url(body.url)
        return JSONResponse(result.to_dict())
    return JSONResponse({"success": False, "error": "请提供 url 或 text 参数"}, status_code=400)


@app.post("/pipeline", dependencies=[Depends(rate_limit_account)])
async def pipeline_post(body: PipelineRequest, account: Account = Depends(get_account)):
    """一键：解析链接 → 转写逐字稿。"""
    if body.text:
        results = await parse_text(body.text)
        parse_data = results[0].to_dict() if results else {"success": False, "error": "无链接"}
    elif body.url:
        parse_data = (await parse_url(body.url)).to_dict()
    else:
        return JSONResponse({"success": False, "error": "请提供 url 或 text"}, status_code=400)

    out: dict = {"success": parse_data.get("success", False), "parse": parse_data, "transcript": None}
    if not parse_data.get("success"):
        out["error"] = parse_data.get("error", "解析失败")
        return JSONResponse(out)

    if body.skip_transcribe or parse_data.get("media_type") == "images":
        out["transcript"] = {"success": False, "reason": "skip_transcribe or images"}
        return JSONResponse(out)

    video_url = parse_data.get("video_url") or ""
    if not video_url:
        out["transcript"] = {"success": False, "error": "无 video_url"}
        return JSONResponse(out)

    _account_store.check_quota(account)

    try:
        tr = await _transcribe_checked(video_url)
    except HTTPException as exc:
        out["transcript"] = {"success": False, "error": exc.detail}
        out["error"] = str(exc.detail)
        return JSONResponse(out, status_code=exc.status_code)

    _record_transcribe_if_ok(account, tr)
    out["transcript"] = tr.to_dict()
    out["success"] = tr.success
    if not tr.success:
        out["error"] = tr.error
    return JSONResponse(out)


async def _run_transcribe_job(job_id: str, video_url: str, account: Account) -> None:
    _transcribe_jobs[job_id] = {"status": "RUNNING", "result": None}
    try:
        validate_video_url(video_url)
        _account_store.check_quota(account)
        result = await transcribe_video_url(video_url)
        _record_transcribe_if_ok(account, result)
        _transcribe_jobs[job_id] = {
            "status": "SUCCESS" if result.success else "FAILED",
            "result": result.to_dict(),
        }
    except HTTPException as exc:
        _transcribe_jobs[job_id] = {
            "status": "FAILED",
            "result": TranscribeResult(success=False, error=str(exc.detail)).to_dict(),
        }
    except Exception as exc:
        _transcribe_jobs[job_id] = {
            "status": "FAILED",
            "result": TranscribeResult(success=False, error=str(exc)).to_dict(),
        }


@app.post("/transcribe", dependencies=[Depends(rate_limit_account)])
async def transcribe_post(
    body: TranscribeRequest,
    background_tasks: BackgroundTasks,
    account: Account = Depends(get_account),
):
    if not body.video_url:
        return JSONResponse({"success": False, "error": "video_url 不能为空"}, status_code=400)
    validate_video_url(body.video_url)
    job_id = uuid.uuid4().hex
    _transcribe_jobs[job_id] = {"status": "QUEUEING", "result": None}
    background_tasks.add_task(_run_transcribe_job, job_id, body.video_url, account)
    return JSONResponse({"success": True, "job_id": job_id, "status": "QUEUEING"})


@app.get("/transcribe/{job_id}", dependencies=[Depends(get_account)])
async def transcribe_status(job_id: str):
    job = _transcribe_jobs.get(job_id)
    if not job:
        return JSONResponse({"success": False, "error": "任务不存在或已过期"}, status_code=404)
    return JSONResponse({"success": True, "job_id": job_id, **job})


def _run_ingest_job(job_id: str, body: IngestRequest) -> None:
    from .ingest_bridge import run_ingest_one

    _ingest_jobs[job_id] = {"status": "RUNNING", "result": None}
    try:
        result = run_ingest_one(
            body.url,
            category=body.category,
            subfolder=body.subfolder,
            skip_transcribe=body.skip_transcribe,
        )
        _ingest_jobs[job_id] = {
            "status": "SUCCESS" if result.get("success") else "FAILED",
            "result": result,
        }
    except FileNotFoundError as exc:
        _ingest_jobs[job_id] = {
            "status": "FAILED",
            "result": {"success": False, "url": body.url, "error": str(exc)},
        }
    except Exception as exc:
        _ingest_jobs[job_id] = {
            "status": "FAILED",
            "result": {"success": False, "url": body.url, "error": str(exc)},
        }


@app.post("/ingest", dependencies=[Depends(rate_limit_account)])
async def ingest_post(
    body: IngestRequest,
    background_tasks: BackgroundTasks,
    account: Account = Depends(get_account),
):
    """一键入库 YuYe：解析 → 转写 → 主笔记 + 逐字稿 sidecar。"""
    if not body.url.strip().startswith("http"):
        return JSONResponse({"success": False, "error": "url 必须以 http 开头"}, status_code=400)
    job_id = uuid.uuid4().hex
    _ingest_jobs[job_id] = {"status": "QUEUEING", "result": None}
    background_tasks.add_task(_run_ingest_job, job_id, body)
    return JSONResponse({"success": True, "job_id": job_id, "status": "QUEUEING"})


@app.get("/ingest/{job_id}", dependencies=[Depends(get_account)])
async def ingest_status(job_id: str):
    job = _ingest_jobs.get(job_id)
    if not job:
        return JSONResponse({"success": False, "error": "任务不存在或已过期"}, status_code=404)
    return JSONResponse({"success": True, "job_id": job_id, **job})


@app.post("/ingest/sync", dependencies=[Depends(rate_limit_account)])
async def ingest_sync(body: IngestRequest, account: Account = Depends(get_account)):
    """同步入库（长视频可能超时，插件请用 POST /ingest + 轮询）。"""
    if not body.url.strip().startswith("http"):
        return JSONResponse({"success": False, "error": "url 必须以 http 开头"}, status_code=400)
    from .ingest_bridge import run_ingest_one

    try:
        result = run_ingest_one(
            body.url,
            category=body.category,
            subfolder=body.subfolder,
            skip_transcribe=body.skip_transcribe,
        )
    except FileNotFoundError as exc:
        return JSONResponse({"success": False, "error": str(exc)}, status_code=503)
    except Exception as exc:
        return JSONResponse({"success": False, "error": str(exc)}, status_code=500)
    return JSONResponse(result)


def _clip_raw_input(body: ClipRequest) -> str:
    raw = (body.input or body.url or body.text or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="请提供 url、text 或 input")
    return raw


def _run_clip_job(job_id: str, body: ClipRequest) -> None:
    from .clip_bridge import run_clip_one

    _clip_jobs[job_id] = {"status": "RUNNING", "result": None}
    try:
        result = run_clip_one(
            _clip_raw_input(body),
            profile=body.profile or body.account,
            category=body.category,
            subfolder=body.subfolder,
            title=body.title,
        )
        _clip_jobs[job_id] = {
            "status": "SUCCESS" if result.get("success") else "FAILED",
            "result": result,
        }
    except FileNotFoundError as exc:
        _clip_jobs[job_id] = {
            "status": "FAILED",
            "result": {"success": False, "error": str(exc)},
        }
    except HTTPException as exc:
        _clip_jobs[job_id] = {
            "status": "FAILED",
            "result": {"success": False, "error": str(exc.detail)},
        }
    except Exception as exc:
        _clip_jobs[job_id] = {
            "status": "FAILED",
            "result": {"success": False, "error": str(exc)},
        }


@app.post("/clip", dependencies=[Depends(rate_limit_account)])
async def clip_post(
    body: ClipRequest,
    background_tasks: BackgroundTasks,
    account: Account = Depends(get_account),
):
    """Clip-to-Brain：链接/文字 → 结构化笔记 + 二创角度（异步）。"""
    _clip_raw_input(body)
    job_id = uuid.uuid4().hex
    _clip_jobs[job_id] = {"status": "QUEUEING", "result": None}
    background_tasks.add_task(_run_clip_job, job_id, body)
    return JSONResponse({"success": True, "job_id": job_id, "status": "QUEUEING"})


@app.get("/clip/stats")
async def clip_stats_get(days: int = Query(7, ge=1, le=90)):
    from .clip_bridge import run_clip_stats

    try:
        return JSONResponse(run_clip_stats(days=days))
    except FileNotFoundError as exc:
        return JSONResponse({"success": False, "error": str(exc)}, status_code=503)


@app.get("/clip/dashboard")
async def clip_dashboard():
    from .clip_bridge import clip_dashboard_path

    path = clip_dashboard_path()
    if not path.exists():
        return JSONResponse({"success": False, "error": "dashboard 未安装"}, status_code=404)
    return FileResponse(path)


@app.post("/bot/feishu")
async def bot_feishu(request: Request):
    import sys
    from pathlib import Path

    scripts = Path(__file__).resolve().parent.parent.parent / "content-archiver-skill" / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    import clip_bot  # noqa: WPS433

    body = await request.json()
    return JSONResponse(clip_bot.handle_feishu_event(body))


@app.post("/bot/telegram")
async def bot_telegram(request: Request):
    import sys
    from pathlib import Path

    scripts = Path(__file__).resolve().parent.parent.parent / "content-archiver-skill" / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    import clip_bot  # noqa: WPS433

    body = await request.json()
    return JSONResponse(clip_bot.handle_telegram_update(body))


@app.get("/clip/{job_id}", dependencies=[Depends(get_account)])
async def clip_status(job_id: str):
    job = _clip_jobs.get(job_id)
    if not job:
        return JSONResponse({"success": False, "error": "任务不存在或已过期"}, status_code=404)
    return JSONResponse({"success": True, "job_id": job_id, **job})


@app.post("/clip/sync", dependencies=[Depends(rate_limit_account)])
async def clip_sync(body: ClipRequest, account: Account = Depends(get_account)):
    """同步 Clip（长视频可能超时，插件请用 POST /clip + 轮询）。"""
    from .clip_bridge import run_clip_one

    try:
        result = run_clip_one(
            _clip_raw_input(body),
            profile=body.profile or body.account,
            category=body.category,
            subfolder=body.subfolder,
            title=body.title,
        )
    except FileNotFoundError as exc:
        return JSONResponse({"success": False, "error": str(exc)}, status_code=503)
    except HTTPException as exc:
        return JSONResponse({"success": False, "error": str(exc.detail)}, status_code=exc.status_code)
    except Exception as exc:
        return JSONResponse({"success": False, "error": str(exc)}, status_code=500)
    return JSONResponse(result)


@app.post("/transcribe/sync", dependencies=[Depends(rate_limit_account)])
async def transcribe_sync(body: TranscribeRequest, account: Account = Depends(get_account)):
    if not body.video_url:
        return JSONResponse({"success": False, "error": "video_url 不能为空"}, status_code=400)
    _account_store.check_quota(account)
    result = await _transcribe_checked(body.video_url)
    _record_transcribe_if_ok(account, result)
    return JSONResponse(result.to_dict())


if SERVE_WEB_UI and WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")


def run_server():
    import uvicorn

    if REQUIRE_API_KEY and not _account_store.has_any_key():
        print(
            "错误: 已启用 REQUIRE_API_KEY 但未配置密钥。"
            "请在 .env 设置 API_KEY，或用 scripts/manage_accounts.py add 创建客户账户。",
            file=sys.stderr,
        )
        sys.exit(1)

    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "8765"))
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run_server()
