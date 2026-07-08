#!/usr/bin/env python3
"""
视频内容知识化 — 内容获取与归档脚本

用法:
  python video_processor.py extract "<链接或分享文案>"
  python video_processor.py extract "<链接>" --output result.json
  python video_processor.py archive --note note.md --meta result.json
  python video_processor.py pipeline "<链接>" --note note.md
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SKILL_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = SKILL_ROOT / "config.json"


def load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        print(f"错误: 配置文件不存在 {path}", file=sys.stderr)
        print(f"请复制 config_template.json 为 config.json 并填写路径", file=sys.stderr)
        sys.exit(1)
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def apply_config(config: dict[str, Any]) -> Path:
    """将 config 写入环境变量，并返回 video-parser 根目录。"""
    vp_root = Path(config.get("video_parser_root", "../video-parser"))
    if not vp_root.is_absolute():
        vp_root = (SKILL_ROOT / vp_root).resolve()

    env_file = config.get("env_file")
    if env_file:
        env_path = Path(env_file)
        if not env_path.is_absolute():
            env_path = (SKILL_ROOT / env_path).resolve()
        if env_path.exists():
            try:
                from dotenv import load_dotenv

                load_dotenv(env_path, override=False)
            except ImportError:
                pass

    ali = config.get("aliyun", {})
    if ali.get("ak_id"):
        os.environ["ALIYUN_AK_ID"] = ali["ak_id"]
    if ali.get("ak_secret"):
        os.environ["ALIYUN_AK_SECRET"] = ali["ak_secret"]
    if ali.get("app_key"):
        os.environ["NLS_APP_KEY"] = ali["app_key"]
    if ali.get("region"):
        os.environ["ALIYUN_NLS_REGION"] = ali["region"]
    if ali.get("poll_interval"):
        os.environ["NLS_POLL_INTERVAL"] = str(ali["poll_interval"])
    if ali.get("max_wait"):
        os.environ["NLS_MAX_WAIT"] = str(ali["max_wait"])

    oss = config.get("oss", {})
    if oss.get("bucket"):
        os.environ["ALIYUN_OSS_BUCKET"] = oss["bucket"]
    if oss.get("endpoint"):
        os.environ["ALIYUN_OSS_ENDPOINT"] = oss["endpoint"]
    if oss.get("prefix"):
        os.environ["ALIYUN_OSS_PREFIX"] = oss["prefix"]
    if "public" in oss:
        os.environ["ALIYUN_OSS_PUBLIC"] = str(oss["public"]).lower()

    wx = config.get("weixin", {})
    if wx.get("yuanbao_cookie"):
        os.environ["YUANBAO_COOKIE"] = wx["yuanbao_cookie"]
    if wx.get("sph_api"):
        os.environ["WX_SPH_API"] = wx["sph_api"]

    proxy = config.get("proxy", {})
    if proxy.get("http"):
        os.environ["HTTP_PROXY"] = proxy["http"]
    if proxy.get("https"):
        os.environ["HTTPS_PROXY"] = proxy["https"]

    if str(vp_root) not in sys.path:
        sys.path.insert(0, str(vp_root))
    return vp_root


def slugify(text: str, max_len: int = 60) -> str:
    text = unicodedata.normalize("NFKC", text or "untitled")
    text = re.sub(r'[\\/*?:"<>|]', "", text)
    text = re.sub(r"\s+", "-", text.strip())
    return text[:max_len] or "untitled"


async def extract_content(url_or_text: str, *, skip_transcribe: bool = False) -> dict[str, Any]:
    from parser.unified import extract_urls, parse_text, parse_url
    from parser.transcribe import transcribe_video_url

    urls = extract_urls(url_or_text)
    target = urls[0] if urls else url_or_text.strip()

    if urls:
        results = await parse_text(url_or_text)
        parse = results[0]
    else:
        parse = await parse_url(target)

    out: dict[str, Any] = {
        "success": parse.success,
        "source_url": parse.raw_url or target,
        "error": parse.error,
        "media": {
            "video_url": parse.video_url,
            "cover_url": parse.cover_url,
            "music_url": parse.music_url,
            "images": parse.images,
            "media_type": parse.media_type,
        },
        "metadata": {
            "platform": parse.platform,
            "title": parse.title,
            "author": parse.author,
            "backend": parse.backend,
            "processed_at": datetime.now(timezone.utc).isoformat(),
        },
        "transcript": {"success": False, "full_text": "", "segments": []},
    }

    if not parse.success:
        return out

    if skip_transcribe or parse.media_type == "images":
        out["transcript"]["skipped"] = True
        out["transcript"]["reason"] = "图集内容或无 transcribe 请求"
        return out

    if not parse.video_url:
        out["transcript"]["skipped"] = True
        out["transcript"]["reason"] = "无视频地址"
        return out

    tr = await transcribe_video_url(parse.video_url)
    out["transcript"] = {
        "success": tr.success,
        "full_text": tr.full_text,
        "segments": [s.to_dict() for s in tr.segments],
        "task_id": tr.task_id,
        "status": tr.status,
        "error": tr.error,
    }
    out["success"] = parse.success and tr.success
    if not tr.success:
        out["error"] = tr.error or "转写失败"
    return out


def save_transcript_raw(data: dict[str, Any], config: dict[str, Any]) -> Path | None:
    kb = config.get("knowledge_base", {})
    vault = Path(kb.get("vault_path", "./vault"))
    sub = kb.get("transcript_subdir", "_transcripts")
    vault.mkdir(parents=True, exist_ok=True)
    (vault / sub).mkdir(parents=True, exist_ok=True)

    title = data.get("metadata", {}).get("title", "untitled")
    date = datetime.now().strftime("%Y-%m-%d")
    fname = f"{date}-{slugify(title)}-raw.json"
    path = vault / sub / fname
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def archive_note(note_path: Path, meta_path: Path | None, config: dict[str, Any]) -> dict[str, Any]:
    kb = config.get("knowledge_base", {})
    vault = Path(kb.get("vault_path", "./vault"))
    vault.mkdir(parents=True, exist_ok=True)

    note_content = note_path.read_text(encoding="utf-8")
    meta: dict[str, Any] = {}
    if meta_path and meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))

    metadata = meta.get("metadata", {})
    title = _extract_frontmatter(note_content, "title") or metadata.get("title", "未命名")
    platform = metadata.get("platform", "")
    author = metadata.get("author", "")
    category = _extract_frontmatter(note_content, "category") or ""
    tags = _extract_frontmatter(note_content, "tags") or ""

    date = datetime.now().strftime("%Y-%m-%d")
    dest_name = f"{date}-{slugify(title)}.md"
    dest = vault / dest_name
    dest.write_text(note_content, encoding="utf-8")

    index_file = kb.get("index_file", "_content_index.md")
    index_path = vault / index_file
    _ensure_index(index_path)
    row = f"| {date} | {title} | {platform} | {author} | {category} | {tags} | [[{dest_name}]] |"
    _append_index_row(index_path, row)

    return {
        "success": True,
        "note_path": str(dest),
        "index_path": str(index_path),
    }


def _extract_frontmatter(content: str, key: str) -> str:
    if not content.startswith("---"):
        return ""
    parts = content.split("---", 2)
    if len(parts) < 3:
        return ""
    for line in parts[1].splitlines():
        if line.strip().startswith(f"{key}:"):
            return line.split(":", 1)[1].strip().strip('"').strip("'")
    return ""


def _ensure_index(path: Path) -> None:
    if path.exists():
        return
    header = (
        "# 内容索引总表\n\n"
        "| 日期 | 标题 | 平台 | 作者 | 分类 | 标签 | 笔记 |\n"
        "|------|------|------|------|------|------|------|\n"
    )
    path.write_text(header, encoding="utf-8")


def _append_index_row(path: Path, row: str) -> None:
    content = path.read_text(encoding="utf-8")
    if row.strip() in content:
        return
    if not content.endswith("\n"):
        content += "\n"
    path.write_text(content + row + "\n", encoding="utf-8")


def cmd_extract(args: argparse.Namespace, config: dict[str, Any]) -> int:
    apply_config(config)
    data = asyncio.run(extract_content(args.input, skip_transcribe=args.skip_transcribe))

    if args.save_raw:
        raw_path = save_transcript_raw(data, config)
        if raw_path:
            data["raw_saved"] = str(raw_path)

    text = json.dumps(data, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(args.output)
    else:
        print(text)
    return 0 if data.get("success") else 1


def cmd_archive(args: argparse.Namespace, config: dict[str, Any]) -> int:
    result = archive_note(Path(args.note), Path(args.meta) if args.meta else None, config)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("success") else 1


def cmd_pipeline(args: argparse.Namespace, config: dict[str, Any]) -> int:
    apply_config(config)
    data = asyncio.run(extract_content(args.input, skip_transcribe=args.skip_transcribe))
    raw_path = save_transcript_raw(data, config)
    payload = {"extract": data, "raw_path": str(raw_path) if raw_path else None}
    if args.output:
        Path(args.output).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if data.get("success") else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="视频内容知识化处理器")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="config.json 路径")
    sub = parser.add_subparsers(dest="command", required=True)

    p_extract = sub.add_parser("extract", help="解析链接 + 转写逐字稿")
    p_extract.add_argument("input", help="视频/图文分享链接或含链接文案")
    p_extract.add_argument("--output", "-o", help="输出 JSON 文件")
    p_extract.add_argument("--skip-transcribe", action="store_true")
    p_extract.add_argument("--save-raw", action="store_true", help="保存原始 JSON 到知识库")
    p_extract.set_defaults(func=cmd_extract)

    p_archive = sub.add_parser("archive", help="归档 Markdown 笔记并更新索引")
    p_archive.add_argument("--note", required=True, help="Markdown 笔记路径")
    p_archive.add_argument("--meta", help="extract 输出的 JSON（可选）")
    p_archive.set_defaults(func=cmd_archive)

    p_pipe = sub.add_parser("pipeline", help="extract + 保存 raw JSON")
    p_pipe.add_argument("input", help="分享链接")
    p_pipe.add_argument("--output", "-o", help="输出 pipeline JSON")
    p_pipe.add_argument("--skip-transcribe", action="store_true")
    p_pipe.set_defaults(func=cmd_pipeline)

    args = parser.parse_args()
    config = load_config(Path(args.config))
    return args.func(args, config)


if __name__ == "__main__":
    sys.exit(main())
