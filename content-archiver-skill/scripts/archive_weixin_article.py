#!/usr/bin/env python3
"""抓取微信公众号文章并归档到 YuYe。"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from html import unescape
from pathlib import Path

import requests

SKILL_ROOT = Path(__file__).resolve().parent.parent
FETCH_SCRIPT = Path(__file__).resolve().parent / "_fetch_weixin.py"
ARCHIVER = SKILL_ROOT / "scripts" / "content_archiver.py"
CONFIG = SKILL_ROOT / "config.json"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def clean_content(content: str) -> str:
    for marker in ("var first_sceen__time", "预览时标签不可点", "微信扫一扫可打开此内容"):
        if marker in content:
            content = content.split(marker, 1)[0]
    return content.strip()


def slugify(text: str, max_len: int = 60) -> str:
    import unicodedata

    text = unicodedata.normalize("NFKC", text or "untitled")
    text = re.sub(r'[\\/*?:"<>|]', "", text)
    text = re.sub(r"\s+", "-", text.strip())
    return text[:max_len] or "untitled"


def build_note(data: dict[str, str], *, category: str, subfolder: str) -> str:
    title = data["title"]
    author = data["author"]
    url = data["source_url"]
    date = datetime.now().strftime("%Y-%m-%d")
    now = datetime.now(timezone.utc).isoformat()
    sidecar = f"_originals/{date}-{slugify(title)}-全文.md"

    return f"""---
title: "{title.replace('"', '\\"')}"
date: {date}
source_url: "{url}"
source_type: article
platform: 微信公众号
author: {author}
YuYe_category: "{category}"
YuYe_subfolder: {subfolder}
category: 行业资料
tags: [哥飞, SEO, AI出海, 独立开发, 找词, 小语种, 外链, 转化, 社媒运营, 上站Hackathon]
value_rating: 长期参考
original_note: "[[{sidecar}]]"
created: {now}
---

# {title}

> 来源：[微信公众号]({url}) · {author} · {date}
> 分类：行业资料库 / `{subfolder}`

## 摘要

哥飞「朋友们」2026 年中深圳分享交流会首日战报（650 人到场）。八位嘉宾从找词、AI+SEO、小语种、外链、转化、用户行为数据、社媒品牌到心态与堆量，给出可落地的出海实战共识：**找被验证过的需求 → 用 AI 放大 → 快速上线拿反馈 → 认真对待用户 → 永远在场**。

## 十大主题速览

| # | 主题 | 核心共识 |
|---|------|----------|
| 一 | 找词 | 全天最高频词；跟高手学、盯新词源头、做小词、做已验证需求 |
| 二 | AI + SEO | AI 是伙伴不是对手；从关键词思维转向全网客户旅程优化 |
| 三 | 纯血版小语种 | 禁止一键翻译；每语言单独调研词、本地域名、支付与合规 |
| 四 | 外链 | 预算内拼数量；免费外链也有用；博客评论、必应站长工具 |
| 五 | 转化与定价 | 漏斗优化；三档定价；定价页是竞品调研透视镜 |
| 六 | 用户行为数据 | 跳出率、停留、人均页数；小图跳大图增 PV |
| 七 | 社媒与品牌 | 员工矩阵号；推特曝光高；引用优于转发 |
| 八 | 概率与堆量 | 大数定理；24h 内上线；养鱼论；先发一百条 |
| 九 | 学费与风险 | 支付多备渠道；合规隔离；域名别省 |
| 十 | 心态 | 永远在场；跟自己比；承认朴素才能赚钱 |

## 嘉宾与分享主题

| 嘉宾 | 主题 |
|------|------|
| 小羊 | 经典成事思维做出海——心态是最好的风水 |
| SEO小平 | AI 助力纯血版小语种网站掘金 |
| Asnull | 从穷学生到月入万刀+，我的出海心路历程 |
| John | 放弃关键词思维！AI SaaS 出海如何重构 SEO 及获客策略 |
| Fiona | 出海路上如何更快拿到正反馈 |
| Nicole辰 | 做 Employee Advocacy，打造社媒 Native 团队 |
| 井然 | 普通人如何通过 AI 出海完成职业转型 |
| 哥飞 | 那些经过实践检验，2026 年依然有效的 SEO 实战技巧 |

## 金句精选

- 「找词要放在第一位」—— Fiona
- 「AI 是我们的伙伴，不是对手。我们要卷的是其他人类」—— Fiona
- 「看到价格的人不一定买，但不看价格的人一定不买」—— 小羊
- 「不求一击之胜，只求永远在场」—— 小羊
- 「先发一百条再说」—— Nicole辰
- 「跟自己比，今天比昨天更强，就足够了」—— 哥飞

## 价值判断

**长期参考**：高密度出海 SEO/AI 实战合集，涵盖找词、小语种、外链、转化、社媒全链路。与予野账号方向（AI 工具场景解法）可交叉引用选题灵感。

## 全文

[[{sidecar}]]
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("--category", default="02")
    parser.add_argument("--subfolder", default="business-models")
    args = parser.parse_args()

    tmp = SKILL_ROOT / "_weixin_fetch.json"
    proc = subprocess.run(
        [sys.executable, str(FETCH_SCRIPT), args.url, str(tmp)],
        cwd=str(SKILL_ROOT),
    )
    if proc.returncode != 0 or not tmp.exists():
        print(json.dumps({"success": False, "error": "抓取失败"}, ensure_ascii=False))
        return 1

    data = json.loads(tmp.read_text(encoding="utf-8"))
    if not data.get("success"):
        print(json.dumps(data, ensure_ascii=False))
        return 1

    content = clean_content(data.get("content", ""))
    date = datetime.now().strftime("%Y-%m-%d")
    stem = f"{date}-{slugify(data['title'])}"

    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw = config.get("YuYe_root") or config.get("lumis_root")
    if not raw:
        raise KeyError("YuYe_root")
    yuye_root = Path(raw)
    dest_dir = yuye_root / config["categories"][args.category]["path"] / args.subfolder
    originals_dir = dest_dir / "_originals"
    originals_dir.mkdir(parents=True, exist_ok=True)

    sidecar_path = originals_dir / f"{stem}-全文.md"
    sidecar_path.write_text(
        f"# 全文：{data['title']}\n\n"
        f"> 来源：{data['source_url']} · {data['author']}\n\n"
        f"{content}\n",
        encoding="utf-8",
    )

    note_tmp = SKILL_ROOT / "_ingest_note.md"
    note_tmp.write_text(
        build_note({**data, "content": content}, category=args.category, subfolder=args.subfolder),
        encoding="utf-8",
    )

    arch = subprocess.run(
        [
            sys.executable,
            str(ARCHIVER),
            "--config",
            str(CONFIG),
            "archive",
            "--note",
            str(note_tmp),
            "--category",
            args.category,
            "--subfolder",
            args.subfolder,
            "--source",
            data["source_url"],
        ],
        cwd=str(SKILL_ROOT),
    )
    note_tmp.unlink(missing_ok=True)
    tmp.unlink(missing_ok=True)
    return arch.returncode


if __name__ == "__main__":
    raise SystemExit(main())
