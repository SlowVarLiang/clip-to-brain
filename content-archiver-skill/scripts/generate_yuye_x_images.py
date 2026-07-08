#!/usr/bin/env python3
"""予野 X 平台配图 · GPT Image 2（16:9 横版）。"""
from __future__ import annotations

import argparse
import base64
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parents[2]

MODEL = "openai/gpt-image-2"
SIZE = "1536x1024"  # landscape 16:9-ish for X timeline

X_STYLE = (
    "X Twitter infographic card, landscape 16:9, 1536x1024, "
    "dark charcoal background #0F0F0F, white bold sans-serif Chinese text, "
    "accent cyan #1D9BF0 and warm orange #FF6B35, "
    "high contrast readable at mobile timeline, minimal flat design, "
    "clean grid lines, tech thread preview aesthetic, information dense, "
    "no watermark, no avatar, no IP, no 3D, no neon overload."
)

X_NEGATIVE = (
    "低质量，模糊，乱码，竖版，小红书风格，白底数据风，"
    "人物照片，复杂背景，过度装饰。"
)


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


def generate(api_key: str, api_base: str, prompt: str, quality: str) -> bytes:
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
    return base64.b64decode(resp.json()["data"][0]["b64_json"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--quality", default="low", choices=("low", "medium", "high"))
    args = ap.parse_args()

    cfg_path = args.out / "x-images.json"
    if not cfg_path.exists():
        print(f"缺少 {cfg_path}", file=sys.stderr)
        return 1

    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    env = load_env()
    api_key = env.get("IMAGE_API_KEY", "")
    api_base = env.get("IMAGE_API_BASE", "https://api.ofox.ai/v1")
    if not api_key:
        print("缺少 IMAGE_API_KEY", file=sys.stderr)
        return 1

    args.out.mkdir(parents=True, exist_ok=True)
    manifest = []
    for item in cfg["images"]:
        prompt = X_STYLE + item["body"] + X_NEGATIVE
        print(f"[{item['file']}] quality={args.quality}")
        try:
            raw = generate(api_key, api_base, prompt, args.quality)
            out = args.out / item["file"]
            out.write_bytes(raw)
            print(f"  -> {out} ({len(raw)//1024} KB)")
            manifest.append({"file": item["file"], "status": "ok", "bytes": len(raw)})
        except Exception as e:
            print(f"  FAIL: {e}", file=sys.stderr)
            manifest.append({"file": item["file"], "status": "error", "error": str(e)})

    meta = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "platform": "X",
        "model": MODEL,
        "size": SIZE,
        "quality": args.quality,
        "images": manifest,
    }
    (args.out / "x-manifest.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
