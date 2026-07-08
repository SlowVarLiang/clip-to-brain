#!/usr/bin/env python3
"""选题 → 予野六页图文脚手架。完整规范见 lumis/04-viral-topics/tool-tutorials/_six-page-carousel-spec.md"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

STYLE_SUFFIX = (
    "Xiaohongshu carousel slide, vertical 3:4 ratio 1080x1440, minimalist notebook aesthetic, "
    "off-white warm paper background #F5F3EF, dark forest green #2D4A3E accent, muted navy #1E3A5F, "
    "clean modern Chinese sans-serif typography, subtle paper grain, calm professional mood, "
    "plenty of whitespace, no neon, no purple-blue AI cliché, no robot brain imagery, "
    'footer "予野YuYe" and page number'
)

PAGE_TYPES = [
    ("封面页", "钩子标题 + 身份标签予野YuYe + 页码 1/6"),
    ("核心观点页", "1–3 个观点，建立共鸣或结论"),
    ("方法论页", "3–5 步框架 / 对比表 / 流程图"),
    ("案例页", "真实经历一幕 或 Before/After"),
    ("行动建议页", "今天就能做的 3 条"),
    ("CTA转化页", "收藏 + 关注 + 下篇预告 +「慢慢来，才更快」"),
]

BANNED = ("震惊", "保姆级", "为所欲为", "第二大脑", "一文看懂", "AI时代", "炸裂", "精通")


def topic_type_hint(title: str) -> str:
    if any(k in title for k in ("转行", "国企", "土木", "企划", "ALL IN")):
        return "转行手记"
    if "vs" in title.lower() or "区别" in title or "对比" in title:
        return "工具对比"
    if "第" in title and "天" in title:
        return "亲测记录"
    if "坑" in title:
        return "避坑清单"
    if "企划" in title or "调研" in title:
        return "职场场景"
    if "慢慢来" in title or "日更" in title:
        return "签名篇"
    if "Obsidian" in title or "笔记库" in title:
        return "工作流"
    return "工具亲测"


def scaffold(title: str, topic_type: str = "", next_topic: str = "") -> dict:
    t = topic_type or topic_type_hint(title)
    pages = []
    for i, (ptype, hint) in enumerate(PAGE_TYPES, 1):
        prompt = f"Slide {i}/6, {ptype}, topic: {title}, type hint: {hint}, {STYLE_SUFFIX}"
        pages.append(
            {
                "page": i,
                "type": ptype,
                "hint": hint,
                "on_image_copy": f"【待填】{title} — {ptype}",
                "image_prompt": prompt,
            }
        )
    if next_topic and pages:
        pages[-1]["on_image_copy"] = (
            f"收藏这条\n关注我 @予野YuYe\n下篇：{next_topic}\n慢慢来，才更快"
        )
    return {
        "xiaohongshu_title": title[:20],
        "topic_type": t,
        "caption": f"【待填正文】\n\n慢慢来，才更快。",
        "tags": ["#予野YuYe", "#图文笔记", f"#{t}"],
        "pages": pages,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def to_markdown(data: dict) -> str:
    lines = [
        f"# {data['xiaohongshu_title']}",
        "",
        f"**类型**：{data['topic_type']}",
        "",
        "## 正文",
        "",
        data["caption"],
        "",
        f"**标签**：{' '.join(data['tags'])}",
        "",
        "## 六页",
        "",
        "| 页 | 类型 | 图上文案 | 生图 Prompt |",
        "|----|------|----------|-------------|",
    ]
    for p in data["pages"]:
        copy = p["on_image_copy"].replace("\n", "<br>")
        pr = p["image_prompt"][:80] + "…"
        lines.append(f"| P{p['page']} | {p['type']} | {copy} | {pr} |")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description="选题 → 予野六页图文脚手架")
    ap.add_argument("title", help="选题标题")
    ap.add_argument("--type", default="", help="选题类型（转行手记/工具对比/…）")
    ap.add_argument("--next", default="", help="下篇预告标题")
    ap.add_argument("--format", choices=("json", "md"), default="md")
    args = ap.parse_args()

    for w in BANNED:
        if w in args.title:
            print(f"警告: 标题含禁用词「{w}」", file=sys.stderr)

    data = scaffold(args.title, args.type, args.next)
    if args.format == "json":
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(to_markdown(data))


if __name__ == "__main__":
    main()
