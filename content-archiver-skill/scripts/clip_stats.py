"""Clip-to-Brain 归档统计 — CLI / Dashboard / API 共用。"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


def _read_frontmatter_field(text: str, key: str) -> str:
    if not text.startswith("---"):
        return ""
    parts = text.split("---", 2)
    if len(parts) < 3:
        return ""
    for line in parts[1].splitlines():
        if line.strip().startswith(f"{key}:"):
            return line.split(":", 1)[1].strip().strip('"').strip("'")
    return ""


def collect_stats(yuye_root: Path, *, days: int = 1) -> dict[str, Any]:
    skip_dirs = {"_transcripts", "_originals", "_ocr_temp", "output", ".obsidian", "copilot"}
    cutoff = (datetime.now() - timedelta(days=max(days - 1, 0))).strftime("%Y-%m-%d")
    today = datetime.now().strftime("%Y-%m-%d")

    total = remixable = long_ref = archived = 0
    items: list[dict[str, str]] = []

    for md in sorted(yuye_root.rglob("*.md"), reverse=True):
        if any(part in skip_dirs for part in md.parts):
            continue
        if md.name.startswith("_") and md.parent.name != "04-viral-topics":
            continue
        name = md.name
        if len(name) < 11 or name[10] != "-":
            continue
        date_part = name[:10]
        if date_part < cutoff:
            continue

        text = md.read_text(encoding="utf-8")
        rel = md.relative_to(yuye_root).as_posix()
        rating = _read_frontmatter_field(text, "value_rating")
        title = _read_frontmatter_field(text, "title") or md.stem[11:]
        platform = _read_frontmatter_field(text, "platform")
        author = _read_frontmatter_field(text, "author")

        if date_part == today:
            total += 1
            if "可二创" in rating:
                remixable += 1
            if "长期参考" in rating:
                long_ref += 1
        archived += 1

        items.append(
            {
                "date": date_part,
                "title": title,
                "relative_path": rel,
                "value_rating": rating or "—",
                "platform": platform,
                "author": author,
                "status": _read_frontmatter_field(text, "status") if "_inbox" in rel else "",
            }
        )

    items.sort(key=lambda x: (x["date"], x["relative_path"]), reverse=True)

    return {
        "today": today,
        "days": days,
        "summary": {
            "today_total": total,
            "today_remixable": remixable,
            "today_long_ref": long_ref,
            "period_total": archived,
        },
        "items": items[:50],
    }
