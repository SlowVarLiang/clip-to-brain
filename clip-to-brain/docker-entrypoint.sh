#!/usr/bin/env bash
set -euo pipefail
VAULT=/app/vault
if [[ ! -d "$VAULT" ]] || [[ -z "$(ls -A "$VAULT" 2>/dev/null || true)" ]]; then
  echo "初始化 Obsidian vault…"
  python /app/content-archiver-skill/scripts/bootstrap_vault.py --dest "$VAULT"
fi
cd /app/video-parser
exec python -m parser.server
