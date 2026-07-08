#!/usr/bin/env python3
"""予野六页竖图 · GPT Image 2 定型流程。

P1–P6：整页 generate，无 IP / 无人物。
"""
from __future__ import annotations

import argparse
import base64
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

from yuye_image2_prompts import build_prompt, set_theme, get_theme, STYLE_PREFIX, STYLE_NEGATIVE

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = (
    REPO_ROOT
    / "YuYe/04-viral-topics/tool-tutorials/output"
    / "2026-07-06-topic01-guoqi-all-in-ai-route-a"
)

MODEL = "openai/gpt-image-2"
SIZE = "1024x1536"
DEFAULT_QUALITY = "low"

GLOBAL_PREFIX = STYLE_PREFIX
NEGATIVE = STYLE_NEGATIVE


PAGES: list[dict[str, str]] = [
    {
        "file": "page-01-封面页.jpg",
        "name": "P1 封面",
        "prompt": GLOBAL_PREFIX
        + "封面页 layout："
        "上半区居中超大藏青粗体标题三行「国企5年」「我为什么」「ALL IN AI」，"
        "下方居中橙红色副标题「稳定·转型·一篇讲透」+ 短橙线，"
        "下半区左右分栏——左侧三行圆形线框图标+说明，右侧线框金字塔（中间层藏青），"
        "对称平衡，无人物，无IP，纯信息图，"
        "底部细灰线，左下角页脚「予野YuYe·转行手记 1/6」。"
        + NEGATIVE,
    },
    {
        "file": "page-02-核心观点页.jpg",
        "name": "P2 核心观点",
        "prompt": GLOBAL_PREFIX
        + "内页 layout："
        "左上橙红实心标签「写在前面：为什么写这条」白字，"
        "右上灰色页码「02/06」，"
        "主体为4条左对齐列表，每条前橙红圆点："
        "稳定但闷/土木企划写材料/AI是新手艺/不劝裸辞只讲权衡。"
        "大行距留白，底部虚线分割，无人物，纯信息图。"
        + NEGATIVE,
    },
    {
        "file": "page-03-方法论页.jpg",
        "name": "P3 方法论",
        "prompt": GLOBAL_PREFIX
        + "内页 layout："
        "左上橙标「第一步：我怎么做决定」，右上 03/06，"
        "4条橙点 bullet list，底部4步时间轴色块（列清单/小号试跑/存钱垫/再跳槽），"
        "底部虚线，无人物。"
        + NEGATIVE,
    },
    {
        "file": "page-04-案例页.jpg",
        "name": "P4 案例",
        "prompt": GLOBAL_PREFIX
        + "内页 layout："
        "左上橙标「真实一幕：离职前夜」，右上 04/06，"
        "中部大号藏青故事文字块，下方3条橙点，"
        "右下角极淡建筑线稿水印，安静克制，无人物。"
        + NEGATIVE,
    },
    {
        "file": "page-05-行动建议页.jpg",
        "name": "P5 行动",
        "prompt": GLOBAL_PREFIX
        + "内页 layout："
        "左上橙标「给犹豫的人：3条建议」，右上 05/06，"
        "4条橙点建议，最后一条浅红提醒框，底部虚线，无人物。"
        + NEGATIVE,
    },
    {
        "file": "page-06-CTA转化页.jpg",
        "name": "P6 CTA",
        "prompt": GLOBAL_PREFIX
        + "CTA转化页 layout，无人物："
        "居中藏青大标题「转行决策 完整清单」，"
        "橙红引导语「收藏这条·犹豫时翻出来看」，"
        "向下橙色箭头+剪贴板清单图标（三个橙勾），"
        "左下「慢慢来，才更快」，右上 06/06，底部淡藏青波浪。"
        + NEGATIVE,
    },
]


def load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    for p in (REPO_ROOT / ".env.local", REPO_ROOT / ".env"):
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
            elif line.startswith("sk-"):
                env.setdefault("IMAGE_API_KEY", line)
    return env


def generate_one(api_key: str, api_base: str, prompt: str, quality: str) -> bytes:
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": MODEL,
        "prompt": prompt,
        "size": SIZE,
        "quality": quality,
        "n": 1,
        "response_format": "b64_json",
    }
    resp = requests.post(
        f"{api_base.rstrip('/')}/images/generations",
        headers=headers,
        json=payload,
        timeout=300,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:500]}")
    data = resp.json()
    item = data["data"][0]
    if "b64_json" in item:
        return base64.b64decode(item["b64_json"])
    if "url" in item:
        r2 = requests.get(item["url"], timeout=120)
        r2.raise_for_status()
        return r2.content
    raise RuntimeError(f"unexpected response: {json.dumps(data)[:300]}")


def load_pages(out_dir: Path) -> tuple[list[dict[str, str]], str]:
    cfg = out_dir / "pages.json"
    if cfg.exists():
        data = json.loads(cfg.read_text(encoding="utf-8"))
        theme = data.get("theme", "data-white")
        set_theme(theme)
        return data["pages"], theme
    set_theme("data-white")
    return PAGES, "data-white"


def main() -> int:
    ap = argparse.ArgumentParser(description="予野六页 · GPT Image 2 定型生成")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--quality", default=DEFAULT_QUALITY, choices=("low", "medium", "high"))
    ap.add_argument("--page", type=int, nargs="*", help="只生成指定页 1-6")
    args = ap.parse_args()

    env = load_env()
    api_key = env.get("IMAGE_API_KEY", "")
    api_base = env.get("IMAGE_API_BASE", "https://api.ofox.ai/v1")
    if not api_key:
        print("缺少 IMAGE_API_KEY", file=sys.stderr)
        return 1

    args.out.mkdir(parents=True, exist_ok=True)
    pages, theme = load_pages(args.out)
    targets = pages
    if args.page:
        targets = [pages[i - 1] for i in args.page if 1 <= i <= len(pages)]

    manifest: list[dict] = []
    for i, page in enumerate(targets, 1):
        print(f"[{page['file']}] {page['name']} quality={args.quality}")
        try:
            prompt = build_prompt(page)
            raw = generate_one(api_key, api_base, prompt, args.quality)
            out = args.out / page["file"]
            out.write_bytes(raw)
            print(f"  -> {out} ({len(raw)//1024} KB)")
            manifest.append({"file": page["file"], "status": "ok", "bytes": len(raw)})
        except Exception as e:
            print(f"  FAIL: {e}", file=sys.stderr)
            manifest.append({"file": page["file"], "status": "error", "error": str(e)})

    meta = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "workflow": "image2-v2",
        "theme": theme,
        "model": MODEL,
        "quality": args.quality,
        "size": SIZE,
        "cover_ip": False,
        "inner_ip": False,
        "pages": manifest,
    }
    (args.out / "manifest.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
