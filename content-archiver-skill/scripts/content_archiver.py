#!/usr/bin/env python3
"""
YuYe 内容自动归档 — 将 Markdown 笔记写入对应分类目录并更新总索引。

用法:
  python content_archiver.py archive --note note.md --category 03 --subfolder _benchmark
  python content_archiver.py routes
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any

SKILL_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = SKILL_ROOT / "config.json"


def load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        print(f"错误: 配置文件不存在 {path}", file=sys.stderr)
        print("请复制 config_template.json 为 config.json", file=sys.stderr)
        sys.exit(1)
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def slugify(text: str, max_len: int = 60) -> str:
    text = unicodedata.normalize("NFKC", text or "untitled")
    text = re.sub(r'[\\/*?:"<>|]', "", text)
    text = re.sub(r"\s+", "-", text.strip())
    return text[:max_len] or "untitled"


def extract_frontmatter(content: str, key: str) -> str:
    if not content.startswith("---"):
        return ""
    parts = content.split("---", 2)
    if len(parts) < 3:
        return ""
    for line in parts[1].splitlines():
        if line.strip().startswith(f"{key}:"):
            return line.split(":", 1)[1].strip().strip('"').strip("'")
    return ""


def resolve_paths(
    config: dict[str, Any],
    category: str,
    subfolder: str | None,
) -> tuple[Path, dict[str, Any]]:
    categories = config.get("categories", {})
    if category not in categories:
        valid = ", ".join(sorted(categories))
        raise ValueError(f"无效 category: {category}，可选: {valid}")

    cat = categories[category]
    yuye_root = Path(config.get("YuYe_root") or config.get("lumis_root", "../vault"))
    if not yuye_root.is_absolute():
        yuye_root = (SKILL_ROOT / yuye_root).resolve()

    sub = subfolder or cat.get("default_subfolder", "")
    allowed = cat.get("subfolders", [])
    if allowed and sub not in allowed:
        raise ValueError(
            f"无效 subfolder: {sub}，{category} 可选: {', '.join(allowed)}"
        )

    dest_dir = yuye_root / cat["path"] / sub if sub else yuye_root / cat["path"]
    return dest_dir, cat


def ensure_index(path: Path) -> None:
    if path.exists():
        return
    header = (
        "# YuYe 内容索引总表\n\n"
        "| 日期 | 标题 | 类别 | 子目录 | 来源 | 标签 | 笔记 |\n"
        "|------|------|------|--------|------|------|------|\n"
    )
    path.write_text(header, encoding="utf-8")


def append_index_row(path: Path, row: str) -> None:
    content = path.read_text(encoding="utf-8")
    if row.strip() in content:
        return
    if not content.endswith("\n"):
        content += "\n"
    path.write_text(content + row + "\n", encoding="utf-8")


def archive_note(
    note_path: Path,
    category: str,
    subfolder: str | None,
    config: dict[str, Any],
    *,
    source: str = "",
) -> dict[str, Any]:
    dest_dir, cat = resolve_paths(config, category, subfolder)
    dest_dir.mkdir(parents=True, exist_ok=True)

    note_content = note_path.read_text(encoding="utf-8")
    title = extract_frontmatter(note_content, "title") or "未命名"
    tags = extract_frontmatter(note_content, "tags") or ""
    source_url = extract_frontmatter(note_content, "source_url") or source
    date = extract_frontmatter(note_content, "date") or datetime.now().strftime("%Y-%m-%d")

    dest_name = f"{date}-{slugify(title)}.md"
    dest = dest_dir / dest_name
    if dest.exists():
        stem = dest.stem
        suffix = dest.suffix
        n = 2
        while dest.exists():
            dest = dest_dir / f"{stem}-{n}{suffix}"
            n += 1

    dest.write_text(note_content, encoding="utf-8")

    yuye_root = Path(config.get("YuYe_root") or config.get("lumis_root", "../vault"))
    if not yuye_root.is_absolute():
        yuye_root = (SKILL_ROOT / yuye_root).resolve()
    index_path = yuye_root / config.get("index_file", "_content_index.md")
    ensure_index(index_path)

    sub = subfolder or cat.get("default_subfolder", "")
    rel_note = dest.relative_to(yuye_root).as_posix()
    row = (
        f"| {date} | {title} | {cat.get('label', category)} | {sub} "
        f"| {source_url or '—'} | {tags} | [[{rel_note}]] |"
    )
    append_index_row(index_path, row)

    result = {
        "success": True,
        "category": category,
        "subfolder": sub,
        "note_path": str(dest),
        "index_path": str(index_path),
        "relative_path": rel_note,
    }
    (SKILL_ROOT / "_last_archive.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return result


def cmd_routes(_args: argparse.Namespace, config: dict[str, Any]) -> int:
    print(json.dumps(config.get("categories", {}), ensure_ascii=False, indent=2))
    return 0


def cmd_archive(args: argparse.Namespace, config: dict[str, Any]) -> int:
    try:
        result = archive_note(
            Path(args.note),
            args.category,
            args.subfolder,
            config,
            source=args.source or "",
        )
    except ValueError as exc:
        print(json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False))
        return 1

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="YuYe 内容自动归档")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="config.json 路径")
    sub = parser.add_subparsers(dest="command", required=True)

    p_archive = sub.add_parser("archive", help="归档 Markdown 到指定分类目录")
    p_archive.add_argument("--note", required=True, help="Markdown 笔记路径")
    p_archive.add_argument("--category", required=True, help="类别编号 01-07")
    p_archive.add_argument("--subfolder", help="子目录名，省略则用 default_subfolder")
    p_archive.add_argument("--source", help="来源说明（可选，优先用 frontmatter）")
    p_archive.set_defaults(func=cmd_archive)

    p_routes = sub.add_parser("routes", help="输出分类目录映射 JSON")
    p_routes.set_defaults(func=cmd_routes)

    args = parser.parse_args()
    config = load_config(Path(args.config))
    return args.func(args, config)


if __name__ == "__main__":
    sys.exit(main())
