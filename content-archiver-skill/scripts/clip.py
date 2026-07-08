#!/usr/bin/env python3
"""
Clip-to-Brain 统一入口：粘贴链接或文字 → Obsidian 结构化笔记 + 回执

用法:
  python clip.py "<url 或文字>"
  python clip.py "<url>" --account 予野YuYe
  python clip.py --file article.txt --category 04 --subfolder methodology
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import re
import subprocess
import sys
import urllib.parse
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from content_archiver import archive_note, load_config
from llm_extract import (
    SECTION_ORDER_SHORT,
    chat_completion,
    llm_settings,
    tags_from_keywords,
    value_rating_from_section,
)
from lumis_ingest import ingest_one, slug_from_title
from profile_loader import Profile, default_profile_name, list_profiles, load_profile

SKILL_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = SKILL_ROOT / "config.json"
FETCH_WEIXIN = Path(__file__).resolve().parent / "_fetch_weixin.py"
ARTICLE_PROMPT = SKILL_ROOT / "prompts" / "value_extraction_article.md"

URL_RE = re.compile(
    r"https?://[^\s<>\"']+|"
    r"(?:v\.douyin|v\.kuaishou|xhslink|b23)\.[^\s<>\"']+",
    re.I,
)


@dataclass
class ClipResult:
    success: bool
    kind: str = ""
    title: str = ""
    author: str = ""
    platform: str = ""
    note_path: str = ""
    relative_path: str = ""
    value_rating: str = ""
    category: str = ""
    subfolder: str = ""
    remix_angles: list[str] = field(default_factory=list)
    sections: dict[str, str] = field(default_factory=dict)
    topic_path: str = ""
    error: str = ""
    next_step: str = ""
    llm_used: bool = False


def resolve_path(base: Path, raw: str) -> Path:
    p = Path(raw)
    return p if p.is_absolute() else (base / p).resolve()


def obsidian_vault_name(config: dict[str, Any]) -> str:
    obs = config.get("obsidian") or {}
    return obs.get("vault_name") or "lumis"


def open_in_obsidian(config: dict[str, Any], relative_path: str) -> bool:
    if not relative_path:
        return False
    vault = obsidian_vault_name(config)
    file_param = relative_path.replace("\\", "/")
    uri = f"obsidian://open?vault={urllib.parse.quote(vault)}&file={urllib.parse.quote(file_param)}"
    try:
        if sys.platform == "win32":
            os.startfile(uri)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.run(["open", uri], check=False)
        else:
            subprocess.run(["xdg-open", uri], check=False)
        return True
    except Exception as exc:
        print(f"无法打开 Obsidian: {exc}", file=sys.stderr)
        return False


def extract_first_url(text: str) -> str | None:
    m = URL_RE.search(text.strip())
    if not m:
        return None
    url = m.group(0)
    return url if url.startswith("http") else f"https://{url}"


def normalize_input(raw: str) -> str:
    s = raw.strip()
    s = re.sub(r"^(归档|clip|入库|brain\s+clip)\s+", "", s, flags=re.I)
    return s.strip()


def detect_kind(raw: str) -> tuple[str, str]:
    text = normalize_input(raw)
    url = extract_first_url(text)
    if url:
        low = url.lower()
        if "mp.weixin.qq.com" in low:
            return "weixin", url
        if any(p in low for p in ("fe.xiaohongshu.com/ditto", "xiaohongshu.com/crown")):
            return "h5", url
        return "video", url
    if text.startswith("http"):
        return "video", text.split()[0]
    if len(text) >= 80:
        return "text", text
    if text.startswith("#") or "\n" in text:
        return "text", text
    return "invalid", text


def validate_xhs_url(url: str) -> str | None:
    low = url.lower()
    if "xiaohongshu.com/discovery/item" in low and "xsec_token" not in low:
        return "小红书分享链须含 xsec_token，请从 App 重新复制完整分享链接"
    return None


def resolve_profile(name: str | None, config: dict[str, Any]) -> Profile:
    key = name or default_profile_name(config)
    return load_profile(key, config)


def platform_label_from_url(url: str) -> str:
    low = url.lower()
    if "xiaohongshu" in low or "xhslink" in low or "xhs.cn" in low:
        return "小红书"
    if "weixin.qq.com/sph" in low or "channels.weixin.qq.com" in low:
        return "微信视频号"
    if "mp.weixin.qq.com" in low:
        return "微信公众号"
    if "bilibili" in low or "b23.tv" in low:
        return "B站"
    if "douyin" in low or "iesdouyin" in low:
        return "抖音"
    if "youtube" in low or "youtu.be" in low:
        return "YouTube"
    if "kuaishou" in low:
        return "快手"
    return "视频"


def result_to_dict(result: ClipResult) -> dict[str, Any]:
    return {
        "success": result.success,
        "kind": result.kind,
        "title": result.title,
        "author": result.author,
        "platform": result.platform,
        "note_path": result.note_path,
        "relative_path": result.relative_path,
        "value_rating": result.value_rating,
        "category": result.category,
        "subfolder": result.subfolder,
        "remix_angles": result.remix_angles,
        "topic_path": result.topic_path,
        "llm_used": result.llm_used,
        "error": result.error,
        "next_step": result.next_step,
    }


def append_remix_to_note(note_path: str, angles: list[str], label: str) -> None:
    if not angles or not note_path:
        return
    p = Path(note_path)
    if not p.exists():
        return
    text = p.read_text(encoding="utf-8")
    heading = f"## {label}可写"
    if heading in text:
        return
    block = heading + "\n\n" + "\n".join(f"- {a}" for a in angles)
    if "## 元数据" in text:
        text = text.replace("## 元数据", block + "\n\n## 元数据", 1)
    else:
        text = text.rstrip() + "\n\n" + block + "\n"
    p.write_text(text, encoding="utf-8")


def append_next_steps_to_note(note_path: str, topic_rel: str) -> None:
    if not note_path:
        return
    p = Path(note_path)
    if not p.exists():
        return
    text = p.read_text(encoding="utf-8")
    if "## 下一步" in text:
        return
    lines = ["## 下一步", "", "- 选题模板：[[04-viral-topics/_template]]"]
    if topic_rel:
        lines.insert(2, f"- 选题卡：[[{topic_rel}]]")
    block = "\n".join(lines)
    if "## 元数据" in text:
        text = text.replace("## 元数据", block + "\n\n## 元数据", 1)
    elif re.search(r"## .+可写", text):
        m = re.search(r"(## .+可写\n\n(?:- .+\n?)+)", text)
        if m:
            text = text[: m.end()] + "\n\n" + block + text[m.end() :]
        else:
            text = text.rstrip() + "\n\n" + block + "\n"
    else:
        text = text.rstrip() + "\n\n" + block + "\n"
    p.write_text(text, encoding="utf-8")


def create_topic_stub(
    config: dict[str, Any],
    result: ClipResult,
    source_rel: str,
    profile: Profile,
) -> str | None:
    if not profile.create_topic_card:
        return None
    if result.value_rating not in ("可二创", "长期参考") or not result.remix_angles:
        return None

    lumis_root = resolve_path(SKILL_ROOT, config.get("lumis_root", "../lumis"))
    inbox = lumis_root / profile.topic_inbox.replace("\\", "/")
    inbox.mkdir(parents=True, exist_ok=True)

    date = datetime.now().strftime("%Y-%m-%d")
    primary = result.remix_angles[0]
    fname = f"{date}-{slugify(primary)}.md"
    dest = inbox / fname
    n = 2
    while dest.exists():
        dest = inbox / f"{date}-{slugify(primary)}-{n}.md"
        n += 1

    variants = "\n".join(f"{i}. {a}" for i, a in enumerate(result.remix_angles[:3], 1))
    summary = (result.sections.get("摘要") or "")[:300]
    safe_title = primary.replace('"', '\\"')

    dest.write_text(
        f"""---
title: "{safe_title}"
direction: 工具教程
platform: 小红书
status: 待写
source_note: "[[{source_rel}]]"
tags: []
---

# {primary}

> Clip-to-Brain 自动生成 · 来源：[[{source_rel}]]

## 标题变体

{variants}

## 目标人群

<!-- {profile.niche or '目标读者'} -->

## 核心承诺

{summary or "（从来源笔记摘要填入）"}

## 内容骨架

1. **开头钩子**：
2. **价值交付**：
3. **结尾 CTA**：

## 验证依据

- 对标来源：[[{source_rel}]]

## 需要的素材来源

- [[{source_rel}]]
- [[04-viral-topics/_template]]
""",
        encoding="utf-8",
    )
    rel = dest.relative_to(lumis_root).as_posix()
    _append_inbox_index(inbox / "_content_index.md", dest.name, primary, source_rel)
    return rel


def _append_inbox_index(index_path: Path, filename: str, title: str, source_rel: str) -> None:
    if not index_path.parent.exists():
        return
    header = (
        "# 选题收件箱\n\n"
        "| 日期 | 标题 | 来源 | 选题卡 |\n"
        "|------|------|------|--------|\n"
    )
    if not index_path.exists():
        index_path.write_text(header, encoding="utf-8")
    date = datetime.now().strftime("%Y-%m-%d")
    row = f"| {date} | {title[:40]} | [[{source_rel}]] | [[{filename}]] |"
    content = index_path.read_text(encoding="utf-8")
    if row.strip() not in content:
        if not content.endswith("\n"):
            content += "\n"
        index_path.write_text(content + row + "\n", encoding="utf-8")


def slugify(text: str, max_len: int = 60) -> str:
    import unicodedata

    text = unicodedata.normalize("NFKC", text or "untitled")
    text = re.sub(r'[\\/*?:"<>|]', "", text)
    text = re.sub(r"\s+", "-", text.strip())
    return text[:max_len] or "untitled"


def parse_sections(markdown: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    pattern = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
    matches = list(pattern.finditer(markdown))
    for i, match in enumerate(matches):
        name = match.group(1).strip()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(markdown)
        sections[name] = markdown[start:end].strip()
    return sections


def run_article_extraction(
    config: dict[str, Any],
    *,
    title: str,
    author: str,
    platform: str,
    source_url: str,
    sidecar_link: str,
    body: str,
) -> tuple[dict[str, str], str | None, bool]:
    settings = llm_settings(config)
    if not settings["enabled"]:
        return {}, None, False

    system = ARTICLE_PROMPT.read_text(encoding="utf-8")
    max_chars = settings["max_transcript_chars"]
    content = body if len(body) <= max_chars else body[:max_chars] + "\n\n…（正文过长，已截断）"
    user = f"""请根据以下文章信息生成主笔记正文（Markdown，从 `## 摘要` 开始）。

# 元信息
- 标题：{title or "未命名"}
- 作者：{author or "未知"}
- 平台：{platform or "未知"}
- 链接：{source_url or "—"}
- 全文文件：{sidecar_link}

# 正文
{content}

# 输出约束
1. 严格按系统提示中的章节顺序输出，使用 `## 章节名`。
2. **不要**输出 YAML frontmatter，**不要**输出 `# 一级标题`。
3. `## 全文` 只写一行链接：`[[{sidecar_link}]]`
"""
    raw = chat_completion(system=system, user=user, settings=settings)
    suggested = None
    m = re.search(r"^建议标题[：:]\s*(.+)$", raw, re.MULTILINE)
    if m:
        suggested = m.group(1).strip().strip("\"'「」")[:80]
    return parse_sections(raw), suggested, True


def build_article_note(
    *,
    title: str,
    author: str,
    platform: str,
    source_url: str,
    route: dict[str, str],
    config: dict[str, Any],
    sections: dict[str, str],
    sidecar_rel: str,
    llm_used: bool,
) -> str:
    cat_cfg = config.get("categories", {}).get(route["category"], {})
    date = datetime.now().strftime("%Y-%m-%d")
    now = datetime.now(timezone.utc).isoformat()
    keywords = sections.get("关键词", "")
    content_category = sections.get("内容分类", "教程方法论")
    value_block = sections.get("价值判断与入库建议", "")
    value_rating = value_rating_from_section(value_block)
    tags_yaml = tags_from_keywords(keywords)

    order = list(SECTION_ORDER_SHORT[:3]) + ["实操要点"] + list(SECTION_ORDER_SHORT[3:])
    body_chunks: list[str] = []
    for name in order:
        if name in sections and sections[name].strip():
            body_chunks.append(f"## {name}\n\n{sections[name].strip()}")
    if "全文" not in sections:
        body_chunks.append(f"## 全文\n\n[[{sidecar_rel}]]")

    extraction_tag = "llm" if llm_used else "rule"
    safe_title = title.replace('"', '\\"')
    return f"""---
title: "{safe_title}"
date: {date}
source_url: "{source_url}"
source_type: article
lumis_category: "{route['category']}"
lumis_subfolder: {route['subfolder']}
platform: {platform}
author: {author}
category: {content_category}
tags: [{tags_yaml}]
value_rating: {value_rating}
original_note: "[[{sidecar_rel}]]"
extraction: {extraction_tag}
created: {now}
---

# {title}

> 来源：[{platform}]({source_url}) · {author} · {date}
> 分类：{cat_cfg.get('label', route['category'])} / `{route['subfolder']}` — {route.get('reason', '')}

{chr(10).join(body_chunks)}
"""


def fallback_article_sections(title: str, body: str) -> dict[str, str]:
    from transcript_utils import guess_content_category, summary_from_text

    preview = body[:3000]
    return {
        "摘要": summary_from_text(body, max_sentences=3),
        "关键词": "、".join(re.findall(r"[\u4e00-\u9fff]{2,6}", title + preview)[:8]) or "待补充",
        "内容分类": guess_content_category(title, preview),
        "核心观点": "1. （LLM 未启用，请手动补充核心观点）",
        "实操要点": "无",
        "金句": "无",
        "价值判断与入库建议": "**仅存档** — 自动归档，待人工补萃取。",
        "全文": "",
    }


def fetch_weixin(url: str) -> dict[str, Any]:
    tmp = SKILL_ROOT / "_clip_weixin.json"
    proc = subprocess.run(
        [sys.executable, str(FETCH_WEIXIN), url, str(tmp)],
        cwd=str(SKILL_ROOT),
    )
    try:
        if proc.returncode != 0 or not tmp.exists():
            return {"success": False, "error": "微信公众号抓取失败"}
        return json.loads(tmp.read_text(encoding="utf-8"))
    finally:
        tmp.unlink(missing_ok=True)


def clean_weixin_content(content: str) -> str:
    for marker in ("var first_sceen__time", "预览时标签不可点", "微信扫一扫可打开此内容"):
        if marker in content:
            content = content.split(marker, 1)[0]
    return content.strip()


def default_text_route(title: str, body: str) -> dict[str, str]:
    from transcript_utils import guess_content_category

    cat = guess_content_category(title, body[:2000])
    if cat in ("行业观察", "案例拆解"):
        return {"category": "02", "subfolder": "industry-news", "reason": "行业/案例类文本"}
    if cat == "教程方法论":
        return {"category": "04", "subfolder": "methodology", "reason": "可复用方法论文本"}
    return {"category": "04", "subfolder": "methodology", "reason": "纯文本默认归档至方法论库"}


def infer_text_title(text: str, explicit: str | None = None) -> str:
    if explicit:
        return explicit.strip()
    lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
    if not lines:
        return "未命名"
    first = lines[0]
    if first.startswith("#"):
        return first.lstrip("#").strip()[:80]
    if len(first) <= 60 and len(lines) > 1:
        return first[:80]
    return first[:40] + ("…" if len(first) > 40 else "")


def ingest_article_body(
    *,
    config: dict[str, Any],
    title: str,
    author: str,
    platform: str,
    source_url: str,
    body: str,
    category: str | None,
    subfolder: str | None,
) -> ClipResult:
    route = default_text_route(title, body)
    if category:
        route["category"] = category
    if subfolder:
        route["subfolder"] = subfolder

    lumis_root = resolve_path(SKILL_ROOT, config.get("lumis_root", "../lumis"))
    cat_path = lumis_root / config["categories"][route["category"]]["path"] / route["subfolder"]
    originals_dir = cat_path / "_originals"
    originals_dir.mkdir(parents=True, exist_ok=True)

    date = datetime.now().strftime("%Y-%m-%d")
    stem = f"{date}-{slugify(title)}"
    sidecar_name = f"{stem}-全文.md"
    sidecar_rel = f"_originals/{sidecar_name}"
    sidecar_path = originals_dir / sidecar_name
    sidecar_path.write_text(
        f"# 全文：{title}\n\n"
        f"> 来源：{source_url or '粘贴文本'} · {author or '—'}\n\n"
        f"{body}\n",
        encoding="utf-8",
    )

    print(f"萃取中…（{platform} · {author or '未知'}）", file=sys.stderr)
    sections, suggested, llm_used = run_article_extraction(
        config,
        title=title,
        author=author,
        platform=platform,
        source_url=source_url,
        sidecar_link=sidecar_rel,
        body=body,
    )
    if suggested:
        title = suggested
        stem = f"{date}-{slugify(title)}"
        sidecar_name = f"{stem}-全文.md"
        new_rel = f"_originals/{sidecar_name}"
        new_path = originals_dir / sidecar_name
        if new_path.resolve() != sidecar_path.resolve():
            sidecar_path.rename(new_path)
            sidecar_rel = new_rel
            sidecar_path = new_path
        sections["全文"] = f"[[{sidecar_rel}]]"

    if not sections:
        sections = fallback_article_sections(title, body)
        sections["全文"] = f"[[{sidecar_rel}]]"
        llm_used = False

    note_tmp = SKILL_ROOT / "_clip_note.md"
    note_tmp.write_text(
        build_article_note(
            title=title,
            author=author,
            platform=platform,
            source_url=source_url,
            route=route,
            config=config,
            sections=sections,
            sidecar_rel=sidecar_rel,
            llm_used=llm_used,
        ),
        encoding="utf-8",
    )
    try:
        archive = archive_note(
            note_tmp,
            route["category"],
            route["subfolder"],
            config,
            source=source_url,
        )
    finally:
        note_tmp.unlink(missing_ok=True)

    rating = value_rating_from_section(sections.get("价值判断与入库建议", ""))
    return ClipResult(
        success=True,
        kind="article",
        title=title,
        author=author,
        platform=platform,
        note_path=archive["note_path"],
        relative_path=archive["relative_path"],
        value_rating=rating,
        category=route["category"],
        subfolder=route["subfolder"],
        llm_used=llm_used,
        sections=sections,
    )


def ingest_weixin(url: str, config: dict[str, Any], category: str | None, subfolder: str | None) -> ClipResult:
    print("解析中…（微信公众号）", file=sys.stderr)
    data = fetch_weixin(url)
    if not data.get("success"):
        return ClipResult(
            success=False,
            kind="weixin",
            error=data.get("error", "抓取失败"),
            next_step="确认链接可公开访问，或稍后重试",
        )

    body = clean_weixin_content(data.get("content", ""))
    route_cat = category or "02"
    route_sub = subfolder or "business-models"
    result = ingest_article_body(
        config=config,
        title=data.get("title") or "未命名",
        author=data.get("author") or "",
        platform="微信公众号",
        source_url=data.get("source_url", url),
        body=body,
        category=route_cat,
        subfolder=route_sub,
    )
    result.kind = "weixin"
    return result


def ingest_text(text: str, config: dict[str, Any], category: str | None, subfolder: str | None, title: str | None) -> ClipResult:
    body = text.strip()
    inferred_title = infer_text_title(body, title)
    print(f"处理纯文本…（{len(body)} 字）", file=sys.stderr)
    result = ingest_article_body(
        config=config,
        title=inferred_title,
        author="",
        platform="粘贴文本",
        source_url="",
        body=body,
        category=category,
        subfolder=subfolder,
    )
    result.kind = "text"
    return result


def ingest_video(url: str, config: dict[str, Any], category: str | None, subfolder: str | None) -> ClipResult:
    hint = validate_xhs_url(url)
    if hint:
        return ClipResult(success=False, kind="video", error=hint, next_step="从 App 分享 → 复制链接（含 xsec_token）")

    print(f"解析中…（{platform_label_from_url(url)}）", file=sys.stderr)
    with contextlib.redirect_stdout(io.StringIO()):
        raw = ingest_one(url, config, category=category, subfolder=subfolder)
    if not raw.get("success"):
        err = raw.get("error", "解析或转写失败")
        next_step = "检查链接是否有效；小红书请用带 token 的分享链"
        if "ffmpeg" in err.lower():
            next_step = "安装 ffmpeg 并加入 PATH 后重试"
        return ClipResult(success=False, kind="video", error=err, next_step=next_step)

    note_path = raw.get("note_path", "")
    meta = _read_note_fields(note_path) if note_path else {}
    return ClipResult(
        success=True,
        kind="video",
        title=meta.get("title", ""),
        author=meta.get("author", ""),
        platform=meta.get("platform", ""),
        note_path=note_path,
        relative_path=raw.get("relative_path", ""),
        value_rating=meta.get("value_rating", "仅存档"),
        category=raw.get("category", ""),
        subfolder=raw.get("subfolder", ""),
        llm_used=bool(raw.get("llm_used")),
        sections=_sections_from_note(note_path),
    )


def _read_note_fields(path: str) -> dict[str, str]:
    if not path or not Path(path).exists():
        return {}
    text = Path(path).read_text(encoding="utf-8")
    fields: dict[str, str] = {}
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            for line in parts[1].splitlines():
                if ":" in line:
                    k, _, v = line.partition(":")
                    fields[k.strip()] = v.strip().strip('"')
    m = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    if m and "title" not in fields:
        fields["title"] = m.group(1).strip()
    return fields


def _sections_from_note(path: str) -> dict[str, str]:
    if not path or not Path(path).exists():
        return {}
    text = Path(path).read_text(encoding="utf-8")
    if text.startswith("---"):
        parts = text.split("---", 2)
        body = parts[2] if len(parts) >= 3 else text
    else:
        body = text
    return parse_sections(body)


def suggest_remix_angles(
    config: dict[str, Any],
    profile: Profile,
    title: str,
    sections: dict[str, str],
) -> list[str]:
    core = sections.get("核心观点", "")
    summary = sections.get("摘要", "")
    if not profile.remix_enabled or not (core or summary):
        return []

    settings = llm_settings(config)
    if settings["enabled"]:
        prompt = f"""你是{profile.label}的小红书选题顾问（{profile.persona}）。
根据已入库内容，给出 {profile.remix_max_angles} 条「{profile.remix_section}」的小红书标题角度。
要求：场景解法视角、口语化、可点击、每条不超过 28 字。
只输出编号列表（1. 2. 3.），不要解释。

标题：{title}
摘要：{summary}
核心观点：
{core}
"""
        try:
            raw = chat_completion(system="你是资深内容策划。", user=prompt, settings=settings)
            angles = re.findall(r"^\s*\d+[.、)\]]\s*(.+)$", raw, re.MULTILINE)
            cleaned = [a.strip().strip("\"'「」") for a in angles if a.strip()]
            if len(cleaned) >= 2:
                return cleaned[: profile.remix_max_angles]
        except Exception as exc:
            print(f"二创角度生成跳过: {exc}", file=sys.stderr)

    points = re.findall(r"^\d+\.\s*(.+)$", core, re.MULTILINE)
    if not points:
        points = [ln.strip("- •") for ln in summary.splitlines() if ln.strip()][:3]
    hooks = ["亲测", "不会写代码也能", "对比", "4步搞定", "踩坑总结"]
    angles: list[str] = []
    for i, p in enumerate(points[: profile.remix_max_angles]):
        hook = hooks[i % len(hooks)]
        short = p[:22] + ("…" if len(p) > 22 else "")
        angles.append(f"{hook}：{short}")
    return angles


def clip(
    raw_input: str,
    config: dict[str, Any],
    *,
    profile_id: str | None = None,
    account: str | None = None,
    category: str | None = None,
    subfolder: str | None = None,
    title: str | None = None,
    create_topic: bool = True,
) -> ClipResult:
    profile = resolve_profile(profile_id or account, config)
    kind, payload = detect_kind(raw_input)
    if kind == "invalid":
        return ClipResult(
            success=False,
            error="输入无效：请粘贴 http 链接，或至少 80 字的正文",
            next_step="示例：python clip.py \"https://www.xiaohongshu.com/...\"",
        )
    if kind == "h5":
        return ClipResult(
            success=False,
            kind="h5",
            error="H5 长图页请先用 h5_image_pipeline.py 处理",
            next_step=f"python scripts/h5_image_pipeline.py pipeline \"{payload}\"",
        )
    if kind == "weixin":
        result = ingest_weixin(payload, config, category, subfolder)
    elif kind == "video":
        result = ingest_video(payload, config, category, subfolder)
    else:
        result = ingest_text(payload, config, category, subfolder, title)

    sections = result.sections
    if result.success:
        result.remix_angles = suggest_remix_angles(config, profile, result.title, sections)
        if result.note_path and result.remix_angles:
            append_remix_to_note(result.note_path, result.remix_angles, profile.label)
        if create_topic and profile.create_topic_card and result.relative_path:
            topic_rel = create_topic_stub(config, result, result.relative_path, profile)
            if topic_rel:
                result.topic_path = topic_rel
                append_next_steps_to_note(result.note_path, topic_rel)
    return result


def print_receipt(result: ClipResult, profile: Profile) -> None:
    if not result.success:
        print("❌ 归档失败")
        if result.error:
            print(f"原因：{result.error}")
        if result.next_step:
            print(f"下一步：{result.next_step}")
        return

    print("✅ 已入库")
    if result.relative_path:
        print(f"📁 {result.relative_path}")
    elif result.note_path:
        print(f"📁 {result.note_path}")
    if result.title:
        meta = " · ".join(x for x in (result.platform, result.author) if x)
        extra = f"（{meta}）" if meta else ""
        print(f"📄 {result.title}{extra}")
    if result.value_rating:
        print(f"⭐ 评级：{result.value_rating}")
    if result.remix_angles:
        print(f"💡 {profile.remix_section}：")
        for angle in result.remix_angles:
            print(f"   - {angle}")
    if result.topic_path:
        print(f"📝 选题卡：{result.topic_path}")


def cmd_clip(args: argparse.Namespace, config: dict[str, Any]) -> int:
    raw = args.input or ""
    if args.file:
        file_path = Path(args.file)
        if file_path.exists() and file_path.is_file():
            raw = file_path.read_text(encoding="utf-8")
        elif not raw:
            raw = args.file  # PowerShell 误绑时，把 --file 值当链接/文字
    if not raw or not raw.strip():
        print("错误: 需要链接或文字输入", file=sys.stderr)
        return 1

    profile = resolve_profile(args.profile or args.account, config)

    result = clip(
        raw,
        config,
        profile_id=profile.id,
        category=args.category,
        subfolder=args.subfolder,
        title=args.title,
        create_topic=not args.no_topic,
    )
    print_receipt(result, profile)

    if result.success and args.open:
        opened = open_in_obsidian(config, result.relative_path)
        if result.topic_path:
            open_in_obsidian(config, result.topic_path)
        elif not opened:
            print("提示：Obsidian 未打开，请确认 vault 名称为 lumis", file=sys.stderr)

    payload = result_to_dict(result)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if result.success else 1


def cmd_reextract(args: argparse.Namespace, config: dict[str, Any]) -> int:
    from lumis_ingest import reextract_note

    profile = resolve_profile(args.profile or args.account, config)
    ok = True
    for raw in args.reextract:
        path = Path(raw.strip())
        print(f"重新萃取: {path.name}", file=sys.stderr)
        with contextlib.redirect_stdout(io.StringIO()):
            raw_result = reextract_note(path, config)
        if not raw_result.get("success"):
            print(f"❌ {raw_result.get('error', '失败')}")
            ok = False
            continue
        note_path = raw_result["note_path"]
        sections = _sections_from_note(note_path)
        title = raw_result.get("title") or path.stem
        angles = suggest_remix_angles(config, profile, title, sections)
        append_remix_to_note(note_path, angles, profile.label)
        meta = _read_note_fields(note_path)
        result = ClipResult(
            success=True,
            kind="reextract",
            title=title,
            author=meta.get("author", ""),
            platform=meta.get("platform", ""),
            note_path=note_path,
            relative_path=raw_result.get("relative_path", ""),
            value_rating=meta.get("value_rating", ""),
            remix_angles=angles,
            sections=sections,
            llm_used=True,
        )
        print_receipt(result, profile)
    return 0 if ok else 1


def cmd_stats(args: argparse.Namespace, config: dict[str, Any]) -> int:
    from clip_stats import collect_stats

    lumis_root = resolve_path(SKILL_ROOT, config.get("lumis_root", "../lumis"))
    data = collect_stats(lumis_root, days=getattr(args, "days", 1) or 1)
    s = data["summary"]
    days = data["days"]
    if days <= 1:
        print(
            f"📊 今日归档 {s['today_total']} 条 · "
            f"可二创 {s['today_remixable']} 条 · "
            f"长期参考 {s['today_long_ref']} 条"
        )
    else:
        print(
            f"📊 近{days}日 {s['period_total']} 条 · "
            f"今日 {s['today_total']} · "
            f"可二创 {s['today_remixable']} · "
            f"长期参考 {s['today_long_ref']}"
        )
    for item in data["items"][:12]:
        print(f"   · [{item['value_rating']}] {item['title'][:48]}")
        print(f"     {item['relative_path']}")
    if getattr(args, "json", False):
        print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


def cmd_list_profiles(_args: argparse.Namespace, config: dict[str, Any]) -> int:
    default = default_profile_name(config)
    print("可用 Profile：")
    for pid in list_profiles(config):
        p = load_profile(pid, config)
        mark = " (默认)" if pid == default else ""
        print(f"  · {pid}{mark} — {p.label}：{p.persona[:48]}…")
    return 0


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = argparse.ArgumentParser(description="Clip-to-Brain：链接/文字 → Obsidian 笔记")
    parser.add_argument("input", nargs="?", help="URL 或正文（可带前缀「归档」）")
    parser.add_argument("--file", help="从文件读取正文")
    parser.add_argument("--profile", help="创作者 profile（见 profiles/*.yaml）")
    parser.add_argument("--account", help="同 --profile（兼容旧参数）")
    parser.add_argument("--category", help="强制类别 01-07")
    parser.add_argument("--subfolder", help="强制子目录")
    parser.add_argument("--title", help="纯文本时指定标题")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--json", action="store_true", help="额外输出 JSON")
    parser.add_argument("--stats", action="store_true", help="今日归档统计")
    parser.add_argument("--reextract", nargs="+", metavar="NOTE", help="对已有笔记重新 LLM 萃取")
    parser.add_argument("--no-topic", action="store_true", help="不自动生成选题卡")
    parser.add_argument("--open", action="store_true", help="完成后在 Obsidian 打开笔记（及选题卡）")
    parser.add_argument("--days", type=int, default=1, help="--stats 统计天数")
    parser.add_argument("--list-profiles", action="store_true", help="列出可用 profile")
    args = parser.parse_args()

    config = load_config(Path(args.config))

    if args.list_profiles:
        return cmd_list_profiles(args, config)
    if args.stats:
        return cmd_stats(args, config)
    if args.reextract:
        return cmd_reextract(args, config)

    if not args.input and not args.file:
        parser.error("需要 input、--file、--stats 或 --reextract")

    return cmd_clip(args, config)


if __name__ == "__main__":
    sys.exit(main())
