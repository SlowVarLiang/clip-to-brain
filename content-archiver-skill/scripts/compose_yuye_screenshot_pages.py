#!/usr/bin/env python3
"""予野六页 · P3/P4 实拍拼图（1080×1440 白底数据风边框）。"""
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1440
BG = (250, 250, 248)
NAVY = (26, 51, 82)
ORANGE = (239, 72, 34)
GRAY = (120, 120, 120)
BORDER = 3


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        r"C:\Windows\Fonts\msyhbd.ttc" if bold else r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\simhei.ttf",
        r"C:\Windows\Fonts\arial.ttf",
    ]
    for p in candidates:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size=size)
            except OSError:
                continue
    return ImageFont.load_default()


def _canvas() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle(
        (BORDER, BORDER, W - BORDER, H - BORDER),
        radius=16,
        outline=(0, 0, 0),
        width=BORDER,
    )
    # dot matrix top-left
    for r in range(4):
        for c in range(4):
            draw.ellipse((28 + c * 10, 28 + r * 10, 34 + c * 10, 34 + r * 10), fill=ORANGE)
    return img, draw


def _tag(draw: ImageDraw.ImageDraw, text: str) -> None:
    f = _font(28, bold=True)
    bbox = draw.textbbox((0, 0), text, font=f)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    pad_x, pad_y = 20, 12
    x, y = 56, 72
    draw.rounded_rectangle(
        (x, y, x + tw + pad_x * 2, y + th + pad_y * 2),
        radius=8,
        fill=ORANGE,
    )
    draw.text((x + pad_x, y + pad_y - 2), text, fill=(255, 255, 255), font=f)


def _fit(img: Image.Image, box_w: int, box_h: int) -> Image.Image:
    img = img.convert("RGB")
    ratio = min(box_w / img.width, box_h / img.height)
    nw, nh = max(1, int(img.width * ratio)), max(1, int(img.height * ratio))
    return img.resize((nw, nh), Image.Resampling.LANCZOS)


def _paste_centered(base: Image.Image, img: Image.Image, x: int, y: int, box_w: int, box_h: int) -> None:
    fitted = _fit(img, box_w, box_h)
    px = x + (box_w - fitted.width) // 2
    py = y + (box_h - fitted.height) // 2
    base.paste(fitted, (px, py))


def _label(draw: ImageDraw.ImageDraw, text: str, x: int, y: int) -> None:
    draw.text((x, y), text, fill=NAVY, font=_font(22, bold=True))


def compose_p3(raw: Path, out: Path) -> None:
    s01 = Image.open(raw / "S01-主界面.png")
    s04 = Image.open(raw / "S04-发指令.png")
    s05 = Image.open(raw / "S05-执行计划与授权.png")

    base, draw = _canvas()
    _tag(draw, "第 1 天就能照做 · 实拍 3 步")

    margin_x, top = 56, 160
    inner_w = W - margin_x * 2
    panel_h = 380
    gap = 24
    labels = [
        "① 打开 Codex，绑定项目文件夹",
        "② 粘贴中文指令（含完成标准）",
        "③ 确认计划 → 批准权限 → 执行",
    ]
    shots = [s01, s04, s05]

    for i, (shot, label) in enumerate(zip(shots, labels)):
        y = top + i * (panel_h + gap + 36)
        _label(draw, label, margin_x, y)
        y2 = y + 34
        draw.rounded_rectangle(
            (margin_x, y2, margin_x + inner_w, y2 + panel_h),
            radius=12,
            outline=(200, 200, 200),
            width=2,
        )
        _paste_centered(base, shot, margin_x + 8, y2 + 8, inner_w - 16, panel_h - 16)

    out.parent.mkdir(parents=True, exist_ok=True)
    base.save(out, quality=92)
    print(f"  -> {out}")


def compose_p4(raw: Path, out: Path) -> None:
    s03 = Image.open(raw / "S03-整理前.png")
    s06a = Image.open(raw / "S06-整理后-文件夹.png")
    s06b = Image.open(raw / "S06-整理后-变更清单.png")

    base, draw = _canvas()
    _tag(draw, "予野亲测 · 2026-07-07")

    margin_x, top = 56, 160
    half_w = (W - margin_x * 2 - 16) // 2
    compare_h = 340

    _label(draw, "整理前", margin_x, top)
    _label(draw, "整理后", margin_x + half_w + 16, top)
    y0 = top + 34

    for x_off, shot in [(margin_x, s03), (margin_x + half_w + 16, s06a)]:
        draw.rounded_rectangle(
            (x_off, y0, x_off + half_w, y0 + compare_h),
            radius=12,
            outline=(200, 200, 200),
            width=2,
        )
        _paste_centered(base, shot, x_off + 6, y0 + 6, half_w - 12, compare_h - 12)

    # arrow
    ax = W // 2
    draw.text((ax - 8, y0 + compare_h // 2 - 16), "→", fill=ORANGE, font=_font(36, bold=True))

    y1 = y0 + compare_h + 40
    _label(draw, "变更清单（Codex 输出）", margin_x, y1)
    y2 = y1 + 34
    list_h = H - y2 - 56
    draw.rounded_rectangle(
        (margin_x, y2, W - margin_x, y2 + list_h),
        radius=12,
        outline=(200, 200, 200),
        width=2,
    )
    _paste_centered(base, s06b, margin_x + 6, y2 + 6, W - margin_x * 2 - 12, list_h - 12)

    # stats bar
    stats = "10 个文件 · documents/ 3 · images/ 2 · 前缀 2026-07-07"
    draw.text((margin_x, H - 48), stats, fill=GRAY, font=_font(20))

    base.save(out, quality=92)
    print(f"  -> {out}")


def compose_p5_kb(raw: Path, out: Path) -> None:
    kb = Image.open(raw / "S09-知识库框架.png")

    base, draw = _canvas()
    _tag(draw, "附 · 我写内容用的知识库")

    margin_x, top = 56, 160
    inner_w = W - margin_x * 2
    intro = "AI 写稿前先过七库：经验、对标、选题、平台规则… 这篇 Codex 亲测也来自 03+04+07"
    draw.text((margin_x, top), intro, fill=NAVY, font=_font(20))

    y0 = top + 44
    box_h = H - y0 - 72
    draw.rounded_rectangle(
        (margin_x, y0, margin_x + inner_w, y0 + box_h),
        radius=12,
        outline=(200, 200, 200),
        width=2,
    )
    _paste_centered(base, kb, margin_x + 8, y0 + 8, inner_w - 16, box_h - 16)

    draw.text((margin_x, H - 48), "YuYe内容知识库 · lumis 七库框架", fill=GRAY, font=_font(20))

    out.parent.mkdir(parents=True, exist_ok=True)
    base.save(out, quality=92)
    print(f"  -> {out}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True, help="topic 输出目录")
    ap.add_argument("--raw", type=Path, help="raw 截图目录，默认 out/assets/raw")
    args = ap.parse_args()

    raw = args.raw or (args.out / "assets" / "raw")
    for name in (
        "S01-主界面.png",
        "S03-整理前.png",
        "S04-发指令.png",
        "S05-执行计划与授权.png",
        "S06-整理后-文件夹.png",
        "S06-整理后-变更清单.png",
    ):
        if not (raw / name).exists():
            raise SystemExit(f"缺少截图: {raw / name}")

    print("[P3] 实拍拼图")
    compose_p3(raw, args.out / "page-03-怎么开始.jpg")
    print("[P4] 实拍拼图")
    compose_p4(raw, args.out / "page-04-亲测成果.jpg")
    kb = raw / "S09-知识库框架.png"
    if kb.exists():
        print("[P5] 知识库框架")
        compose_p5_kb(raw, args.out / "page-05-知识库框架.jpg")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
