#!/usr/bin/env python3
"""
Lumis 链接一键入库

流程: 解析+转写 → 逐字稿独立文件 → 主笔记（萃取+链接）→ 归档

用法:
  python lumis_ingest.py ingest "<链接>"
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from llm_extract import (
    ValueExtractionResult,
    llm_settings,
    looks_like_placeholder_title,
    run_value_extraction,
    tags_from_keywords,
    value_rating_from_section,
)
from transcript_utils import (
    build_chapter_outline,
    build_long_video_summary,
    core_points_heuristic,
    extract_action_items,
    extract_tools_table,
    format_chapter_table,
    format_tools_table,
    guess_content_category,
    guess_value_rating,
    infer_keywords,
    infer_keywords_long,
    is_long_video,
    pick_golden_quotes,
    read_transcript_sidecar,
    summary_from_text,
    transcript_duration_seconds,
    write_transcript_sidecar,
)

SKILL_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = SKILL_ROOT / "config.json"


def load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        print(f"错误: 配置文件不存在 {path}", file=sys.stderr)
        sys.exit(1)
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def ingest_settings(config: dict[str, Any]) -> dict[str, Any]:
    defaults = {
        "long_video_minutes": 10.0,
        "long_transcript_chars": 8000,
        "long_segment_count": 200,
        "value_extraction_prompt_short": "prompts/value_extraction_short.md",
        "value_extraction_prompt_long": "prompts/value_extraction_long.md",
        "llm_enabled": True,
        "llm_max_transcript_chars": 80000,
        "llm_timeout_seconds": 180,
        "llm_temperature": 0.3,
        "llm_max_tokens": 8192,
    }
    defaults.update(config.get("ingest", {}))
    return defaults


def resolve_path(base: Path, raw: str) -> Path:
    p = Path(raw)
    return p if p.is_absolute() else (base / p).resolve()


def find_python(video_skill_root: Path) -> Path:
    candidates = [
        video_skill_root.parent / "video-parser" / ".venv" / "Scripts" / "python.exe",
        video_skill_root.parent / "video-parser" / ".venv" / "bin" / "python",
        Path(sys.executable),
    ]
    for c in candidates:
        if c.exists():
            return c
    return Path(sys.executable)


def classify(data: dict[str, Any], config: dict[str, Any]) -> dict[str, str]:
    meta = data.get("metadata", {})
    author = (meta.get("author") or "").lower()

    for rule in config.get("routing_rules", []):
        if rule.get("default"):
            continue
        needles = [s.lower() for s in rule.get("author_contains", [])]
        if needles and any(n in author for n in needles):
            return {
                "category": rule["category"],
                "subfolder": rule["subfolder"],
                "reason": rule.get("reason", rule.get("name", "")),
            }

    for rule in config.get("routing_rules", []):
        if rule.get("default"):
            return {
                "category": rule["category"],
                "subfolder": rule["subfolder"],
                "reason": rule.get("reason", rule.get("name", "")),
            }

    return {
        "category": "03",
        "subfolder": "VideoNotes",
        "reason": "视频链接默认归档至对标账号库",
    }


def slug_from_title(title: str) -> str:
    s = re.sub(r'[\\/:*?"<>|]', "-", title).strip()
    return s[:80] if s else "untitled"


def platform_subfolder_index_path(
    lumis_root: Path, category: str, subfolder: str, config: dict[str, Any]
) -> Path | None:
    cat = config.get("categories", {}).get(category, {})
    rel = cat.get("path", "")
    if not rel:
        return None
    return lumis_root / rel / subfolder / "_content_index.md"


def ensure_subfolder_index(path: Path) -> None:
    if path.exists():
        return
    header = (
        "# 内容索引\n\n"
        "| 日期 | 标题 | 作者 | 分类 | 标签 | 笔记 |\n"
        "|------|------|------|------|------|------|\n"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(header, encoding="utf-8")


def append_subfolder_index(
    index_path: Path,
    *,
    date: str,
    title: str,
    author: str,
    category_label: str,
    tags: str,
    note_filename: str,
) -> None:
    ensure_subfolder_index(index_path)
    row = f"| {date} | {title} | {author} | {category_label} | {tags} | [[{note_filename}]] |"
    content = index_path.read_text(encoding="utf-8")
    if row.strip() in content:
        return
    if not content.endswith("\n"):
        content += "\n"
    index_path.write_text(content + row + "\n", encoding="utf-8")


def move_raw_json(
    raw_saved: str | None,
    lumis_root: Path,
    category: str,
    subfolder: str,
    config: dict[str, Any],
    fallback_src_dir: Path | None,
) -> str:
    if not raw_saved:
        return ""
    name = Path(raw_saved).name
    cat = config.get("categories", {}).get(category, {})
    dest_dir = lumis_root / cat.get("path", "") / subfolder / "_transcripts"
    dest_dir.mkdir(parents=True, exist_ok=True)

    src = Path(raw_saved)
    if not src.exists() and fallback_src_dir:
        alt = fallback_src_dir / name
        if alt.exists():
            src = alt

    if src.exists():
        dest = dest_dir / name
        dest.write_bytes(src.read_bytes())
        src.unlink(missing_ok=True)
    return name


def _format_quotes(quotes: list[str]) -> str:
    if quotes == ["无"]:
        return "无"
    return "\n".join(f"- 「{q}」" for q in quotes)


def _format_core_points(points: list[str]) -> str:
    return "\n".join(f"{i}. {p}" for i, p in enumerate(points, 1))


def _format_action_items(items: list[str]) -> str:
    if not items:
        return "无"
    return "\n".join(f"{i}. {t}" for i, t in enumerate(items, 1))


def _transcript_link(sidecar_name: str) -> str:
    if not sidecar_name:
        return "（转写未完成）"
    return f"[[_transcripts/{sidecar_name}]]"


def build_note_short(
    *,
    title: str,
    author: str,
    platform: str,
    source_url: str,
    route: dict[str, str],
    config: dict[str, Any],
    segments: list[dict[str, Any]],
    full_text: str,
    sidecar_name: str,
    meta: dict[str, Any],
    tr: dict[str, Any],
    media: dict[str, Any],
    raw_name: str,
) -> str:
    cat_cfg = config.get("categories", {}).get(route["category"], {})
    date = datetime.now().strftime("%Y-%m-%d")
    now = datetime.now(timezone.utc).isoformat()
    content_category = guess_content_category(title, full_text[:3000])
    keywords = infer_keywords(title, author, platform, segments)
    value_rating, value_block = guess_value_rating(content_category, False, True)
    tags_yaml = ", ".join(t.strip() for t in keywords.split("、") if t.strip())[:200]

    return f"""---
title: "{title}"
date: {date}
source_url: "{source_url}"
source_type: video
lumis_category: "{route['category']}"
lumis_subfolder: {route['subfolder']}
platform: {platform}
author: {author}
category: {content_category}
tags: [{tags_yaml}]
value_rating: {value_rating}
media_type: {media.get('media_type', 'video')}
transcript_note: "_transcripts/{sidecar_name}"
transcript_status: ok
created: {now}
---

# {title}

> 来源：[{platform}]({source_url}) · {author} · {date}
> 分类：{cat_cfg.get('label', route['category'])} / `{route['subfolder']}` — {route['reason']}

## 摘要

{summary_from_text(full_text)}

## 关键词

{keywords}

## 内容分类

{content_category}

## 核心观点

{_format_core_points(core_points_heuristic(segments, count=3))}

## 金句

{_format_quotes(pick_golden_quotes(segments, max_quotes=4))}

## 价值判断与入库建议

{value_block}

## 逐字稿

{_transcript_link(sidecar_name)}

---

## 元数据

| 字段 | 值 |
|------|-----|
| 平台 | {platform} |
| 作者 | {author} |
| 时长 | {transcript_duration_seconds(segments) / 60:.1f} 分钟 |
| 分段数 | {len(segments)} |
| 处理时间 | {meta.get('processed_at', '—')} |
| 转写任务 | {tr.get('task_id') or '—'} |
| 原始 JSON | [[_transcripts/{raw_name}]] |
"""


def build_note_long(
    *,
    title: str,
    author: str,
    platform: str,
    source_url: str,
    route: dict[str, str],
    config: dict[str, Any],
    segments: list[dict[str, Any]],
    full_text: str,
    sidecar_name: str,
    meta: dict[str, Any],
    tr: dict[str, Any],
    media: dict[str, Any],
    raw_name: str,
) -> str:
    cat_cfg = config.get("categories", {}).get(route["category"], {})
    date = datetime.now().strftime("%Y-%m-%d")
    now = datetime.now(timezone.utc).isoformat()
    content_category = guess_content_category(title, full_text[:5000])
    keywords = infer_keywords_long(title, author, platform, segments)
    chapters = build_chapter_outline(segments, chapter_count=6)
    actions = extract_action_items(segments)
    tools = extract_tools_table(segments, title)
    value_rating, value_block = guess_value_rating(content_category, True, True)
    tags_yaml = ", ".join(t.strip() for t in keywords.split("、") if t.strip())[:240]

    return f"""---
title: "{title}"
date: {date}
source_url: "{source_url}"
source_type: video
lumis_category: "{route['category']}"
lumis_subfolder: {route['subfolder']}
platform: {platform}
author: {author}
category: {content_category}
tags: [{tags_yaml}]
value_rating: {value_rating}
media_type: {media.get('media_type', 'video')}
transcript_note: "_transcripts/{sidecar_name}"
transcript_status: ok
created: {now}
---

# {title}

> 来源：[{platform}]({source_url}) · {author} · {date}
> 分类：{cat_cfg.get('label', route['category'])} / `{route['subfolder']}` — {route['reason']}

## 摘要

{build_long_video_summary(segments, full_text)}

## 关键词

{keywords}

## 内容分类

{content_category}

## 章节脉络

{format_chapter_table(chapters)}

## 核心观点

{_format_core_points(core_points_heuristic(segments, count=5))}

## 实操要点

{_format_action_items(actions)}

## 工具与概念

{format_tools_table(tools)}

## 金句

{_format_quotes(pick_golden_quotes(segments, max_quotes=6))}

## 价值判断与入库建议

{value_block}

## 逐字稿

{_transcript_link(sidecar_name)}

---

## 元数据

| 字段 | 值 |
|------|-----|
| 平台 | {platform} |
| 作者 | {author} |
| 时长 | {transcript_duration_seconds(segments) / 60:.1f} 分钟 |
| 分段数 | {len(segments)} |
| 处理时间 | {meta.get('processed_at', '—')} |
| 转写任务 | {tr.get('task_id') or '—'} |
| 原始 JSON | [[_transcripts/{raw_name}]] |
"""


def _escape_yaml(value: str) -> str:
    return value.replace('"', '\\"')


def build_note_llm(
    extraction: ValueExtractionResult,
    *,
    title: str,
    author: str,
    platform: str,
    source_url: str,
    route: dict[str, str],
    config: dict[str, Any],
    segments: list[dict[str, Any]],
    sidecar_name: str,
    meta: dict[str, Any],
    tr: dict[str, Any],
    media: dict[str, Any],
    raw_name: str,
) -> str:
    from llm_extract import SECTION_ORDER_LONG, SECTION_ORDER_SHORT

    cat_cfg = config.get("categories", {}).get(route["category"], {})
    date = datetime.now().strftime("%Y-%m-%d")
    now = datetime.now(timezone.utc).isoformat()
    sections = extraction.sections

    keywords = sections.get("关键词", infer_keywords(title, author, platform, segments))
    content_category = sections.get(
        "内容分类", guess_content_category(title, " ".join(sections.values())[:3000])
    )
    value_block = sections.get("价值判断与入库建议", "")
    value_rating = value_rating_from_section(value_block)
    tags_yaml = tags_from_keywords(keywords)

    order = SECTION_ORDER_LONG if extraction.long_video else SECTION_ORDER_SHORT
    body_chunks: list[str] = []
    for name in order:
        if name in sections and sections[name].strip():
            body_chunks.append(f"## {name}\n\n{sections[name].strip()}")

    if "逐字稿" not in sections:
        body_chunks.append(f"## 逐字稿\n\n{_transcript_link(sidecar_name)}")

    body = "\n\n".join(body_chunks)

    return f"""---
title: "{_escape_yaml(title)}"
date: {date}
source_url: "{source_url}"
source_type: video
lumis_category: "{route['category']}"
lumis_subfolder: {route['subfolder']}
platform: {platform}
author: {author}
category: {content_category}
tags: [{tags_yaml}]
value_rating: {value_rating}
media_type: {media.get('media_type', 'video')}
transcript_note: "_transcripts/{sidecar_name}"
transcript_status: ok
extraction: llm
created: {now}
---

# {title}

> 来源：[{platform}]({source_url}) · {author} · {date}
> 分类：{cat_cfg.get('label', route['category'])} / `{route['subfolder']}` — {route['reason']}

{body}

---

## 元数据

| 字段 | 值 |
|------|-----|
| 平台 | {platform} |
| 作者 | {author} |
| 时长 | {transcript_duration_seconds(segments) / 60:.1f} 分钟 |
| 分段数 | {len(segments)} |
| 处理时间 | {meta.get('processed_at', '—')} |
| 转写任务 | {tr.get('task_id') or '—'} |
| 萃取 | MiniMax LLM |
| 原始 JSON | [[_transcripts/{raw_name}]] |
"""


def build_note_pending(
    data: dict[str, Any],
    route: dict[str, str],
    config: dict[str, Any],
    *,
    err: str,
) -> str:
    meta = data.get("metadata", {})
    media = data.get("media", {})
    title = meta.get("title") or "未命名"
    author = meta.get("author") or ""
    platform = meta.get("platform") or ""
    source_url = data.get("source_url", "").split("?")[0]
    date = datetime.now().strftime("%Y-%m-%d")
    now = datetime.now(timezone.utc).isoformat()
    cat_cfg = config.get("categories", {}).get(route["category"], {})

    return f"""---
title: "{title}"
date: {date}
source_url: "{source_url}"
source_type: video
lumis_category: "{route['category']}"
lumis_subfolder: {route['subfolder']}
platform: {platform}
author: {author}
category: 案例拆解
tags: [{platform}, {author}]
value_rating: 仅存档
transcript_status: pending
created: {now}
---

# {title}

> 来源：[{platform}]({source_url}) · {author} · {date}

## 状态

⚠️ 逐字稿未完成：`{err or '转写失败'}`。请重新 ingest 同一链接。

## 逐字稿

（未完成）
"""


def run_extract(
    python: Path,
    video_processor: Path,
    video_config: Path,
    url: str,
    *,
    skip_transcribe: bool,
    work_dir: Path,
) -> dict[str, Any]:
    out = work_dir / "_ingest_extract.json"
    cmd = [
        str(python),
        str(video_processor),
        "--config",
        str(video_config),
        "extract",
        url,
        "--save-raw",
        "-o",
        str(out),
    ]
    if skip_transcribe:
        cmd.append("--skip-transcribe")

    proc = subprocess.run(cmd, cwd=str(video_processor.parent.parent))
    if not out.exists():
        return {"success": False, "source_url": url, "error": f"extract 失败 exit={proc.returncode}"}
    data = json.loads(out.read_text(encoding="utf-8"))
    out.unlink(missing_ok=True)
    return data


def run_archive(
    python: Path,
    archiver: Path,
    config: Path,
    note_path: Path,
    category: str,
    subfolder: str,
) -> dict[str, Any]:
    subprocess.run(
        [
            str(python),
            str(archiver),
            "--config",
            str(config),
            "archive",
            "--note",
            str(note_path),
            "--category",
            category,
            "--subfolder",
            subfolder,
        ],
        check=True,
        cwd=str(SKILL_ROOT),
    )
    return json.loads((SKILL_ROOT / "_last_archive.json").read_text(encoding="utf-8"))


def ingest_one(
    url: str,
    config: dict[str, Any],
    *,
    category: str | None = None,
    subfolder: str | None = None,
    skip_transcribe: bool = False,
) -> dict[str, Any]:
    settings = ingest_settings(config)
    vs = config.get("video_skill", {})
    video_skill_root = resolve_path(SKILL_ROOT, vs.get("root", "../video-to-knowledge-skill"))
    video_config = resolve_path(SKILL_ROOT, vs.get("config", "../video-to-knowledge-skill/config.json"))
    video_processor = video_skill_root / "scripts" / "video_processor.py"
    archiver = SKILL_ROOT / "scripts" / "content_archiver.py"
    archiver_config = SKILL_ROOT / "config.json"
    lumis_root = resolve_path(SKILL_ROOT, config.get("lumis_root", "../lumis"))
    python = find_python(video_skill_root)

    if not video_processor.exists():
        return {"success": False, "url": url, "error": f"找不到 {video_processor}"}

    data = run_extract(
        python, video_processor, video_config, url,
        skip_transcribe=skip_transcribe,
        work_dir=SKILL_ROOT,
    )

    if not data.get("metadata", {}).get("title") and not data.get("success"):
        return {"success": False, "url": url, "error": data.get("error", "解析失败"), "extract": data}

    route = classify(data, config)
    if category:
        route["category"] = category
    if subfolder:
        route["subfolder"] = subfolder

    video_cfg = json.loads(video_config.read_text(encoding="utf-8"))
    fallback_raw = Path(video_cfg.get("knowledge_base", {}).get("vault_path", "")) / "_transcripts"
    raw_name = move_raw_json(
        data.get("raw_saved"),
        lumis_root,
        route["category"],
        route["subfolder"],
        config,
        fallback_raw if fallback_raw.parent.exists() else None,
    )
    if raw_name:
        data["raw_saved"] = str(
            lumis_root
            / config["categories"][route["category"]]["path"]
            / route["subfolder"]
            / "_transcripts"
            / raw_name
        )

    tr = data.get("transcript", {})
    segments = tr.get("segments") or []
    full_text = tr.get("full_text") or ""
    meta = data.get("metadata", {})
    media = data.get("media", {})
    title = meta.get("title") or "未命名"
    author = meta.get("author") or ""
    platform = meta.get("platform") or ""
    source_url = data.get("source_url", "").split("?")[0]
    date_prefix = datetime.now().strftime("%Y-%m-%d")
    file_stem = f"{date_prefix}-{slug_from_title(title)}"
    sidecar_name = f"{file_stem}-transcript.md"

    cat_path = lumis_root / config["categories"][route["category"]]["path"] / route["subfolder"]
    transcripts_dir = cat_path / "_transcripts"

    transcript_ok = tr.get("success", False)
    err = data.get("error") or tr.get("error") or ""
    llm_used = False
    llm_error: str | None = None
    extraction: ValueExtractionResult | None = None

    if transcript_ok and segments:
        long = is_long_video(
            segments,
            full_text,
            min_minutes=float(settings["long_video_minutes"]),
            min_chars=int(settings["long_transcript_chars"]),
            min_segments=int(settings["long_segment_count"]),
        )
        preliminary_sidecar = f"{file_stem}-transcript.md"
        sidecar_name = preliminary_sidecar

        if llm_settings(config).get("enabled"):
            prompt_key = (
                "value_extraction_prompt_long" if long else "value_extraction_prompt_short"
            )
            prompt_path = resolve_path(SKILL_ROOT, settings[prompt_key])
            try:
                print(f"LLM 萃取中 ({llm_settings(config).get('model')})…", file=sys.stderr)
                extraction = run_value_extraction(
                    config=config,
                    prompt_path=prompt_path,
                    title="未命名" if looks_like_placeholder_title(title) else title,
                    author=author,
                    platform=platform,
                    source_url=source_url,
                    sidecar_name=preliminary_sidecar,
                    segments=segments,
                    full_text=full_text,
                    long_video=long,
                )
                if extraction.suggested_title:
                    title = extraction.suggested_title
                    file_stem = f"{date_prefix}-{slug_from_title(title)}"
                    sidecar_name = f"{file_stem}-transcript.md"
                llm_used = True
            except Exception as exc:
                llm_error = str(exc)
                print(f"LLM 萃取失败，回退规则模板: {exc}", file=sys.stderr)

        write_transcript_sidecar(
            transcripts_dir / sidecar_name,
            segments,
            title=title,
            source_url=source_url,
        )
        common = dict(
            title=title,
            author=author,
            platform=platform,
            source_url=source_url,
            route=route,
            config=config,
            segments=segments,
            full_text=full_text,
            sidecar_name=sidecar_name,
            meta=meta,
            tr=tr,
            media=media,
            raw_name=raw_name,
        )
        if extraction:
            llm_kwargs = {k: v for k, v in common.items() if k != "full_text"}
            note_text = build_note_llm(extraction, **llm_kwargs)
        elif long:
            note_text = build_note_long(**common)
        else:
            note_text = build_note_short(**common)
    else:
        sidecar_name = ""
        note_text = build_note_pending(data, route, config, err=err)
        long = False

    note_tmp = SKILL_ROOT / "_ingest_note.md"
    note_tmp.write_text(note_text, encoding="utf-8")

    try:
        archive_result = run_archive(
            python, archiver, archiver_config, note_tmp,
            route["category"], route["subfolder"],
        )
    finally:
        note_tmp.unlink(missing_ok=True)

    note_path = Path(archive_result["note_path"])
    content_category = guess_content_category(title, full_text[:3000])
    sub_idx = platform_subfolder_index_path(lumis_root, route["category"], route["subfolder"], config)
    if sub_idx:
        kw_source = (
            extraction.sections.get("关键词", "")
            if llm_used and extraction
            else infer_keywords(title, author, platform, segments)
        )
        append_subfolder_index(
            sub_idx,
            date=datetime.now().strftime("%Y-%m-%d"),
            title=title,
            author=author,
            category_label=content_category,
            tags=", ".join(t for t in re.split(r"[、,，]", kw_source)[:5] if t.strip()),
            note_filename=note_path.name,
        )

    return {
        "success": bool(data.get("success") or meta.get("title")),
        "url": url,
        "category": route["category"],
        "subfolder": route["subfolder"],
        "note_path": archive_result.get("note_path"),
        "relative_path": archive_result.get("relative_path"),
        "transcript_ok": transcript_ok,
        "long_video": long,
        "transcript_sidecar": sidecar_name or None,
        "llm_used": llm_used,
        "llm_error": llm_error,
        "error": err,
    }


def parse_note_frontmatter(note_text: str) -> dict[str, str]:
    if not note_text.startswith("---"):
        return {}
    parts = note_text.split("---", 2)
    if len(parts) < 3:
        return {}
    fields: dict[str, str] = {}
    for line in parts[1].splitlines():
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip().strip('"')
        if key:
            fields[key] = val
    return fields


def reextract_note(note_path: Path, config: dict[str, Any]) -> dict[str, Any]:
    """对已有笔记用 LLM 重新萃取（不重新转写）。"""
    settings = ingest_settings(config)
    note_path = note_path.resolve()
    if not note_path.exists():
        return {"success": False, "error": f"笔记不存在: {note_path}"}

    meta = parse_note_frontmatter(note_path.read_text(encoding="utf-8"))
    lumis_root = resolve_path(SKILL_ROOT, config.get("lumis_root", "../lumis"))
    category = meta.get("lumis_category", "03")
    subfolder = meta.get("lumis_subfolder", "VideoNotes")
    cat_path = lumis_root / config["categories"][category]["path"] / subfolder
    rel_sidecar = meta.get("transcript_note", "").replace("\\", "/").lstrip("/")
    sidecar_path = (cat_path / rel_sidecar) if rel_sidecar else None
    if not sidecar_path or not sidecar_path.exists():
        return {"success": False, "error": f"找不到逐字稿: {rel_sidecar}"}

    segments, sidecar_title, source_url = read_transcript_sidecar(sidecar_path)
    if not segments:
        return {"success": False, "error": "逐字稿为空"}

    title = meta.get("title") or sidecar_title or "未命名"
    author = meta.get("author", "")
    platform = meta.get("platform", "")
    full_text = " ".join(s.get("text", "") for s in segments)
    sidecar_name = sidecar_path.name
    long = is_long_video(
        segments,
        full_text,
        min_minutes=float(settings["long_video_minutes"]),
        min_chars=int(settings["long_transcript_chars"]),
        min_segments=int(settings["long_segment_count"]),
    )

    if not llm_settings(config).get("enabled"):
        return {"success": False, "error": "LLM 未启用，请配置 .env.local 中 LLM_API_KEY"}

    prompt_key = "value_extraction_prompt_long" if long else "value_extraction_prompt_short"
    prompt_path = resolve_path(SKILL_ROOT, settings[prompt_key])
    print(f"LLM 重新萃取: {note_path.name} ({llm_settings(config).get('model')})…", file=sys.stderr)

    extraction = run_value_extraction(
        config=config,
        prompt_path=prompt_path,
        title="未命名" if looks_like_placeholder_title(title) else title,
        author=author,
        platform=platform,
        source_url=source_url or meta.get("source_url", ""),
        sidecar_name=sidecar_name,
        segments=segments,
        full_text=full_text,
        long_video=long,
    )
    if extraction.suggested_title:
        title = extraction.suggested_title

    route = {
        "category": category,
        "subfolder": subfolder,
        "reason": "LLM 重新萃取",
    }
    note_text = build_note_llm(
        extraction,
        title=title,
        author=author,
        platform=platform,
        source_url=source_url or meta.get("source_url", ""),
        route=route,
        config=config,
        segments=segments,
        sidecar_name=sidecar_name,
        meta={"processed_at": datetime.now(timezone.utc).isoformat()},
        tr={"task_id": meta.get("transcript_note", "")},
        media={"media_type": meta.get("media_type", "video")},
        raw_name="",
    )

    new_name = f"{datetime.now().strftime('%Y-%m-%d')}-{slug_from_title(title)}.md"
    dest = cat_path / new_name
    if dest.resolve() != note_path.resolve():
        note_path.unlink(missing_ok=True)
    dest.write_text(note_text, encoding="utf-8")

    return {
        "success": True,
        "note_path": str(dest),
        "relative_path": f"{config['categories'][category]['path']}/{subfolder}/{dest.name}".replace("\\", "/"),
        "llm_used": True,
        "title": title,
    }


def cmd_routes(_args: argparse.Namespace, config: dict[str, Any]) -> int:
    print(json.dumps(config.get("routing_rules", []), ensure_ascii=False, indent=2))
    return 0


def cmd_ingest(args: argparse.Namespace, config: dict[str, Any]) -> int:
    results = []
    ok = True
    for url in args.urls:
        url = url.strip()
        if not url.startswith("http"):
            print(f"跳过无效链接: {url}", file=sys.stderr)
            ok = False
            continue
        print(f"处理: {url}", file=sys.stderr)
        result = ingest_one(
            url,
            config,
            category=args.category,
            subfolder=args.subfolder,
            skip_transcribe=args.skip_transcribe,
        )
        results.append(result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if not result.get("success"):
            ok = False
    return 0 if ok else 1


def cmd_reextract(args: argparse.Namespace, config: dict[str, Any]) -> int:
    ok = True
    for raw in args.notes:
        path = Path(raw.strip())
        print(f"重新萃取: {path}", file=sys.stderr)
        result = reextract_note(path, config)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if not result.get("success"):
            ok = False
    return 0 if ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Lumis 链接一键入库")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    sub = parser.add_subparsers(dest="command", required=True)

    p_ingest = sub.add_parser("ingest", help="解析链接并归档到 lumis")
    p_ingest.add_argument("urls", nargs="+", help="一个或多个链接")
    p_ingest.add_argument("--category", help="强制类别 01-07")
    p_ingest.add_argument("--subfolder", help="强制子目录")
    p_ingest.add_argument("--skip-transcribe", action="store_true", help="跳过转写")
    p_ingest.set_defaults(func=cmd_ingest)

    p_routes = sub.add_parser("routes", help="查看自动分类规则")
    p_routes.set_defaults(func=cmd_routes)

    p_reextract = sub.add_parser("reextract", help="对已有笔记用 LLM 重新萃取")
    p_reextract.add_argument("notes", nargs="+", help="笔记 .md 路径")
    p_reextract.set_defaults(func=cmd_reextract)

    args = parser.parse_args()
    config = load_config(Path(args.config))
    return args.func(args, config)


if __name__ == "__main__":
    sys.exit(main())
