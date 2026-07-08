#!/usr/bin/env python3
"""初始化 Clip-to-Brain Obsidian 知识库目录。"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = SKILL_ROOT / "vault-template"
CONFIG_TEMPLATE = SKILL_ROOT / "config_template.json"


def bootstrap(dest: Path, *, vault_name: str = "ClipBrain") -> None:
    if not TEMPLATE.exists():
        print(f"错误: 模板不存在 {TEMPLATE}", file=sys.stderr)
        sys.exit(1)

    dest = dest.resolve()
    if dest.exists() and any(dest.iterdir()):
        print(f"目标目录非空，跳过复制: {dest}")
    else:
        dest.mkdir(parents=True, exist_ok=True)
        for item in TEMPLATE.iterdir():
            target = dest / item.name
            if item.is_dir():
                shutil.copytree(item, target, dirs_exist_ok=True)
            else:
                shutil.copy2(item, target)
        print(f"✅ 已创建知识库: {dest}")

    # 写入 config.json（若不存在）
    config_path = SKILL_ROOT / "config.json"
    if not config_path.exists() and CONFIG_TEMPLATE.exists():
        cfg = json.loads(CONFIG_TEMPLATE.read_text(encoding="utf-8"))
        cfg["lumis_root"] = str(dest).replace("\\", "/")
        obs = cfg.setdefault("obsidian", {})
        obs["vault_name"] = vault_name
        config_path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"✅ 已生成 config.json → lumis_root={dest}")
    else:
        print(f"config.json 已存在: {config_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="初始化 Clip-to-Brain 知识库")
    parser.add_argument(
        "--dest",
        default=str(SKILL_ROOT.parent / "vault"),
        help="Obsidian vault 路径（默认 ../vault）",
    )
    parser.add_argument("--vault-name", default="ClipBrain")
    args = parser.parse_args()
    bootstrap(Path(args.dest), vault_name=args.vault_name)
    print("\n下一步:")
    print("  1. Obsidian 打开该文件夹为 vault")
    print("  2. 配置 .env.local 中 LLM_API_KEY")
    print("  3. .\\clip.ps1 \"<链接>\"")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
