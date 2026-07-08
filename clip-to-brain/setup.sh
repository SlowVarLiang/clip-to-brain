#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
REPO="$(dirname "$ROOT")"
ARCHIVER="$REPO/content-archiver-skill"
PARSER="$REPO/video-parser"
VENV="$PARSER/.venv"

echo "Clip-to-Brain Setup"

if [[ ! -d "$VENV" ]]; then
  python3 -m venv "$VENV"
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"
pip install -q -U pip
pip install -q -r "$PARSER/requirements.txt"
pip install -q -r "$ARCHIVER/requirements.txt"

if [[ ! -f "$REPO/.env.local" ]]; then
  cp "$ROOT/.env.example" "$REPO/.env.local"
  echo "已创建 .env.local — 请填写 LLM_API_KEY"
fi

python "$ARCHIVER/scripts/bootstrap_vault.py" --dest "$REPO/vault"

echo ""
echo "安装完成。"
echo "  1. 编辑 $REPO/.env.local"
echo "  2. cd content-archiver-skill && python scripts/clip.py \"<链接>\""
