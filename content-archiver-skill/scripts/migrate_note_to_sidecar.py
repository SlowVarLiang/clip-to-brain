"""一次性：从现有主笔记抽出逐字稿 → sidecar + 新格式主笔记。"""
from __future__ import annotations

import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from transcript_utils import (  # noqa: E402
    build_chapter_outline,
    extract_action_items,
    extract_tools_table,
    format_chapter_table,
    format_tools_table,
    transcript_duration_seconds,
    write_transcript_sidecar,
)

NOTE = Path(
    r"D:\0-CryptoLumis\5-automedia\lumis\03-benchmark-accounts\VideoNotes"
    r"\2026-07-06-零基礎30分鐘學會Codex-95%功能!【福利贈送】.md"
)
SIDECAR = NOTE.parent / "_transcripts" / "2026-07-06-零基礎30分鐘學會Codex-95%功能!【福利贈送】-transcript.md"

LINE_RE = re.compile(r"^- `\[(.+?) → (.+?)\]` (.+)$")


def parse_segments(text: str) -> list[dict]:
    segments = []
    for line in text.splitlines():
        m = LINE_RE.match(line.strip())
        if m:
            segments.append({"begin_time": m.group(1), "end_time": m.group(2), "text": m.group(3)})
    return segments


def extract_section(content: str, name: str) -> str:
    pat = rf"## {re.escape(name)}\n\n(.*?)(?=\n## |\Z)"
    m = re.search(pat, content, re.S)
    return m.group(1).strip() if m else ""


def main() -> None:
    raw = NOTE.read_text(encoding="utf-8")
    transcript_block = extract_section(raw, "逐字稿（带时间戳）")
    segments = parse_segments(transcript_block)
    if not segments:
        raise SystemExit("未解析到逐字稿行")

    write_transcript_sidecar(
        SIDECAR,
        segments,
        title="零基礎30分鐘學會Codex 95%功能！【福利贈送】",
        source_url="https://youtu.be/dMiV7Yx9yk4",
    )

    summary = extract_section(raw, "摘要")
    keywords = extract_section(raw, "关键词")
    category = extract_section(raw, "内容分类")
    core = extract_section(raw, "核心观点")
    quotes = extract_section(raw, "金句")
    value = extract_section(raw, "价值判断与入库建议")

    chapters = build_chapter_outline(segments, chapter_count=6)
    actions = extract_action_items(segments)
    tools = extract_tools_table(segments, "Codex")

    action_body = "\n".join(f"{i}. {t}" for i, t in enumerate(actions, 1)) if actions else "无"
    now = datetime.now(timezone.utc).isoformat()

    note = f"""---
title: "零基礎30分鐘學會Codex 95%功能！【福利贈送】"
date: 2026-07-06
source_url: "https://youtu.be/dMiV7Yx9yk4"
source_type: video
lumis_category: "03"
lumis_subfolder: VideoNotes
platform: YouTube
author: 李厂长来了
category: 教程方法论
tags: [Codex桌面端, agents.md, 计划模式, Computer Use, Skills, 工作流自动化, 李厂长来了]
value_rating: 长期参考
transcript_note: "_transcripts/{SIDECAR.name}"
transcript_status: ok
created: 2026-07-06T04:56:15.202820+00:00
updated: {now}
---

# 零基礎30分鐘學會Codex 95%功能！【福利贈送】

> 来源：[YouTube](https://youtu.be/dMiV7Yx9yk4) · 李厂长来了 · 2026-07-06
> 分类：对标账号库 / `VideoNotes` — 第三方视频/图文，对标拆解素材

## 摘要

{summary}

## 关键词

{keywords}

## 内容分类

{category}

## 章节脉络

{format_chapter_table(chapters)}

## 核心观点

{core}

## 实操要点

{action_body}

## 工具与概念

{format_tools_table(tools)}

## 金句

{quotes}

## 价值判断与入库建议

{value}

## 逐字稿

[[_transcripts/{SIDECAR.name}]]

---

## 元数据

| 字段 | 值 |
|------|-----|
| 平台 | YouTube |
| 作者 | 李厂长来了 |
| 时长 | {transcript_duration_seconds(segments) / 60:.1f} 分钟 |
| 分段数 | {len(segments)} |
| 转写任务 | local-0b488415622c4604 |
| 逐字稿 | [[_transcripts/{SIDECAR.name}]] |
"""
    NOTE.write_text(note, encoding="utf-8")
    print(f"sidecar: {SIDECAR}")
    print(f"note: {NOTE} ({len(segments)} segments)")


if __name__ == "__main__":
    main()
