#!/usr/bin/env python3
"""
H5 长图页面流水线：提取图片 URL → 下载 → OCR → 合并 Markdown

用法:
  python h5_image_pipeline.py pipeline "<url>" --output result.json
  python h5_image_pipeline.py extract-urls "<url>" -o urls.json
  python h5_image_pipeline.py extract-urls --urls-json browser_urls.json -o urls.json
  python h5_image_pipeline.py download --urls urls.json --dir ./_ocr_temp
  python h5_image_pipeline.py ocr --dir ./_ocr_temp --output ocr_text.md
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

SKILL_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TEMP = SKILL_ROOT / "_ocr_temp"

IMG_PATTERNS = [
    re.compile(r"https?://growth-img\.xhscdn\.com/[^\s\"'<>]+", re.I),
    re.compile(r"https?://[^\"'<>]*xhscdn\.com/[^\s\"'<>]+", re.I),
    re.compile(r"//growth-img\.xhscdn\.com/[^\s\"'<>]+", re.I),
]

# 过滤头像、图标、二维码等（浏览器取图 / 通用网页 OCR）
IMG_SKIP = re.compile(
    r"avatar|icon|logo|emoji|qrcode|wx\.|weixin|data:image|1x1|spacer|favicon|badge",
    re.I,
)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _normalize_url(url: str) -> str:
    url = url.strip()
    if url.startswith("//"):
        return "https:" + url
    return url


def _dedupe_preserve_order(urls: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for u in urls:
        u = _normalize_url(u.split("?")[0] if "imageView2" not in u else u)
        # 保留带 imageView2 的完整 URL 用于下载高清图
        full = _normalize_url(u)
        key = full.split("?")[0]
        if key not in seen:
            seen.add(key)
            out.append(full if full.startswith("http") else u)
    return out


def filter_image_urls(urls: list[str]) -> list[str]:
    return [u for u in urls if u and not IMG_SKIP.search(u)]


def extract_urls_from_html(html: str, base_url: str = "") -> list[str]:
    found: list[str] = []
    for pat in IMG_PATTERNS:
        for m in pat.findall(html):
            u = _normalize_url(m)
            if base_url and u.startswith("/"):
                u = urljoin(base_url, u)
            found.append(u)
    for m in re.finditer(r'src=["\']([^"\']+)["\']', html):
        src = m.group(1)
        if src.startswith("data:"):
            continue
        full = _normalize_url(urljoin(base_url, src) if base_url else src)
        if full.startswith("http") and any(
            x in full.lower() for x in (".jpg", ".jpeg", ".png", ".webp", "image", "/img/")
        ):
            found.append(full)
    return filter_image_urls(_dedupe_preserve_order(found))


def fetch_page_urls(url: str) -> dict[str, Any]:
    try:
        import requests
    except ImportError:
        return {"success": False, "error": "缺少 requests，请 pip install requests", "urls": []}

    try:
        resp = requests.get(url, timeout=20, headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
        html = resp.text
    except Exception as exc:
        return {"success": False, "error": str(exc), "urls": [], "need_browser": True}

    urls = extract_urls_from_html(html, base_url=url)
    # 提升图片质量参数
    urls = [_enhance_image_url(u) for u in urls]

    result: dict[str, Any] = {
        "success": bool(urls),
        "source_url": url,
        "urls": urls,
        "count": len(urls),
        "need_browser": len(urls) == 0,
    }
    if not urls:
        result["hint"] = (
            "页面可能是 JS 渲染，请用 browser_navigate + CDP 获取 img.src，"
            "写入 JSON 数组后执行 extract-urls --urls-json"
        )
    return result


def _enhance_image_url(url: str) -> str:
    if "xhscdn.com" in url and "imageView2" not in url:
        sep = "&" if "?" in url else "?"
        return f"{url}{sep}nativeImg=true&imageView2/2/w/1125/q/90"
    return url


def load_urls_from_json(path: Path) -> list[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        urls = [_normalize_url(str(u)) for u in data]
    elif isinstance(data, dict):
        urls = [_normalize_url(str(u)) for u in data.get("urls", [])]
    else:
        urls = []
    return filter_image_urls([_enhance_image_url(u) for u in urls])


def download_images(urls: list[str], dest_dir: Path) -> dict[str, Any]:
    try:
        import requests
    except ImportError:
        return {"success": False, "error": "缺少 requests"}

    dest_dir.mkdir(parents=True, exist_ok=True)
    files: list[str] = []
    errors: list[str] = []

    for i, url in enumerate(urls, 1):
        ext = ".jpg"
        if ".png" in url.lower():
            ext = ".png"
        elif ".webp" in url.lower():
            ext = ".webp"
        out = dest_dir / f"page-{i:02d}{ext}"
        try:
            r = requests.get(url, timeout=30, headers={"User-Agent": USER_AGENT})
            r.raise_for_status()
            out.write_bytes(r.content)
            files.append(str(out))
        except Exception as exc:
            errors.append(f"{url}: {exc}")

    manifest = {
        "success": bool(files),
        "dir": str(dest_dir),
        "files": files,
        "count": len(files),
        "errors": errors,
    }
    manifest_path = dest_dir / "_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def ocr_images(image_dir: Path, output_md: Path | None = None) -> dict[str, Any]:
    try:
        from rapidocr_onnxruntime import RapidOCR
    except ImportError:
        return {
            "success": False,
            "error": "缺少 rapidocr-onnxruntime，请 pip install -r requirements-ocr.txt",
            "fallback": "Agent 请用 Read 工具逐张读取 image_dir 中的图片",
        }

    ocr = RapidOCR()
    images = sorted(
        [p for p in image_dir.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}]
    )
    if not images:
        return {"success": False, "error": f"目录中无图片: {image_dir}"}

    sections: list[str] = []
    all_text: list[str] = []

    for img in images:
        result, _ = ocr(str(img))
        lines: list[str] = []
        if result:
            for _box, text, score in result:
                if text and score and score > 0.5:
                    lines.append(text.strip())
        page_text = "\n".join(lines).strip()
        sections.append(f"## {img.name}\n\n{page_text or '_(未识别到文字)_'}\n")
        all_text.append(page_text)

    merged = "\n".join(sections)
    full = "\n\n---\n\n".join(t for t in all_text if t)

    if output_md:
        output_md.parent.mkdir(parents=True, exist_ok=True)
        output_md.write_text(f"# OCR 合并文本\n\n{merged}", encoding="utf-8")

    return {
        "success": bool(full.strip()),
        "output_md": str(output_md) if output_md else None,
        "pages": len(images),
        "char_count": len(full),
        "full_text": full,
        "sections": merged,
    }


def run_pipeline(url: str, temp_dir: Path, urls_json: Path | None = None) -> dict[str, Any]:
    if urls_json and urls_json.exists():
        urls = load_urls_from_json(urls_json)
        extract_result = {"success": True, "urls": urls, "source": "urls_json"}
    else:
        extract_result = fetch_page_urls(url)
        urls = extract_result.get("urls", [])

    if not urls:
        return {
            "success": False,
            "stage": "extract",
            "extract": extract_result,
        }

    if temp_dir.exists():
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)

    dl = download_images(urls, temp_dir)
    if not dl.get("success"):
        return {"success": False, "stage": "download", "extract": extract_result, "download": dl}

    ocr_out = temp_dir / "ocr_raw.md"
    ocr = ocr_images(temp_dir, ocr_out)

    return {
        "success": ocr.get("success", False),
        "source_url": url,
        "extract": extract_result,
        "download": dl,
        "ocr": {k: v for k, v in ocr.items() if k != "full_text"},
        "ocr_path": str(ocr_out),
        "full_text_preview": (ocr.get("full_text") or "")[:500],
        "full_text": ocr.get("full_text", ""),
    }


def cmd_extract(args: argparse.Namespace) -> int:
    if args.urls_json:
        urls = load_urls_from_json(Path(args.urls_json))
        result = {"success": bool(urls), "urls": urls, "count": len(urls), "source": "urls_json"}
    else:
        result = fetch_page_urls(args.url)
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(args.output)
    else:
        print(text)
    return 0 if result.get("success") or result.get("urls") else 1


def cmd_download(args: argparse.Namespace) -> int:
    urls = load_urls_from_json(Path(args.urls))
    result = download_images(urls, Path(args.dir))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("success") else 1


def cmd_ocr(args: argparse.Namespace) -> int:
    out = Path(args.output) if args.output else None
    result = ocr_images(Path(args.dir), out)
    payload = {k: v for k, v in result.items() if k != "full_text"}
    if args.print_text and result.get("full_text"):
        payload["full_text"] = result["full_text"]
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if result.get("success") else 1


def cmd_pipeline(args: argparse.Namespace) -> int:
    urls_json = Path(args.urls_json) if args.urls_json else None
    result = run_pipeline(args.url, Path(args.dir), urls_json)
    if args.output:
        save = dict(result)
        if len(save.get("full_text", "")) > 10000:
            save["full_text"] = save["full_text"][:10000] + "\n...(truncated)"
        Path(args.output).write_text(json.dumps(save, ensure_ascii=False, indent=2), encoding="utf-8")
        print(args.output)
    else:
        preview = dict(result)
        if "full_text" in preview and len(preview["full_text"]) > 2000:
            preview["full_text"] = preview["full_text"][:2000] + "..."
        print(json.dumps(preview, ensure_ascii=False, indent=2))
    return 0 if result.get("success") else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="H5 长图 OCR 流水线")
    sub = parser.add_subparsers(dest="command", required=True)

    p_extract = sub.add_parser("extract-urls", help="从 URL 或 JSON 提取图片地址")
    p_extract.add_argument("url", nargs="?", default="", help="页面 URL")
    p_extract.add_argument("--urls-json", help="浏览器 CDP 导出的 URL 数组 JSON")
    p_extract.add_argument("-o", "--output", help="输出 JSON")
    p_extract.set_defaults(func=cmd_extract)

    p_dl = sub.add_parser("download", help="下载图片")
    p_dl.add_argument("--urls", required=True, help="urls.json")
    p_dl.add_argument("--dir", default=str(DEFAULT_TEMP))
    p_dl.set_defaults(func=cmd_download)

    p_ocr = sub.add_parser("ocr", help="OCR 识别目录内图片")
    p_ocr.add_argument("--dir", default=str(DEFAULT_TEMP))
    p_ocr.add_argument("--output", help="输出 Markdown")
    p_ocr.add_argument("--print-text", action="store_true")
    p_ocr.set_defaults(func=cmd_ocr)

    p_pipe = sub.add_parser("pipeline", help="一键：提取→下载→OCR")
    p_pipe.add_argument("url", help="页面 URL")
    p_pipe.add_argument("--urls-json", help="可选：浏览器导出的 URL JSON（JS 页面时用）")
    p_pipe.add_argument("--dir", default=str(DEFAULT_TEMP))
    p_pipe.add_argument("-o", "--output", help="输出 pipeline JSON")
    p_pipe.set_defaults(func=cmd_pipeline)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
