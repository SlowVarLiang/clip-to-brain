#!/usr/bin/env bash
# =============================================================================
# video-parser Ubuntu 一键部署（GTX 1050 Ti 等 NVIDIA 显卡）
#
# 用法（复制整个 video-parser 文件夹到 Ubuntu 后，只需一条命令）：
#
#   cd ~/video-parser
#   sudo bash install-ubuntu.sh
#
# 可选：只允许局域网某网段访问（推荐）
#   sudo bash install-ubuntu.sh --lan-only
# =============================================================================

set -euo pipefail

LAN_ONLY=false
[[ "${1:-}" == "--lan-only" ]] && LAN_ONLY=true

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${PROJECT_ROOT}"

[[ -f main.py ]] || { echo "请在 video-parser 目录内运行此脚本"; exit 1; }

echo "==> [1/5] 安装系统依赖..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip ffmpeg curl

if command -v nvidia-smi &>/dev/null; then
  echo "    GPU: $(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)"
  WHISPER_DEVICE=cuda
  WHISPER_COMPUTE_TYPE=int8
else
  echo "    警告: 未检测到 nvidia-smi，转写将使用 CPU（很慢）"
  WHISPER_DEVICE=cpu
  WHISPER_COMPUTE_TYPE=int8
fi

echo "==> [2/5] 安装 Python 依赖..."
python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q --upgrade pip
pip install -q -r requirements.txt

echo "==> [3/5] 写入安全配置..."
API_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')"
cat > .env <<EOF
# install-ubuntu.sh 自动生成 — $(date -Iseconds)
TRANSCRIBE_BACKEND=local
WHISPER_MODEL=small
WHISPER_LANGUAGE=zh
WHISPER_DEVICE=${WHISPER_DEVICE}
WHISPER_COMPUTE_TYPE=${WHISPER_COMPUTE_TYPE}
WHISPER_BEAM_SIZE=5

API_HOST=0.0.0.0
API_PORT=8765
API_KEY=${API_KEY}
REQUIRE_API_KEY=true
DOCS_ENABLED=false
SERVE_WEB_UI=false
RATE_LIMIT_PER_MINUTE=20
TRANSCRIBE_URL_MODE=cdn

WX_SPH_API=https://sph.litao.workers.dev/api/fetch_video_profile
EOF
chmod 600 .env

echo "==> [4/5] 注册 systemd 服务..."
SERVICE_USER="${SUDO_USER:-$USER}"
cat > /etc/systemd/system/video-parser-api.service <<EOF
[Unit]
Description=Video Parser API
After=network.target

[Service]
Type=simple
User=${SERVICE_USER}
WorkingDirectory=${PROJECT_ROOT}
EnvironmentFile=${PROJECT_ROOT}/.env
ExecStart=${PROJECT_ROOT}/.venv/bin/python main.py --serve
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable video-parser-api
systemctl restart video-parser-api
sleep 2

echo "==> [5/5] 防火墙..."
if command -v ufw &>/dev/null; then
  ufw allow OpenSSH >/dev/null 2>&1 || true
  if ${LAN_ONLY}; then
    LAN_CIDR="$(ip -4 route show scope link 2>/dev/null | awk '/proto kernel/ {print $1; exit}')"
    LAN_CIDR="${LAN_CIDR:-192.168.0.0/16}"
    ufw allow from "${LAN_CIDR}" to any port 8765 proto tcp
    echo "    已允许 ${LAN_CIDR} → 8765"
  else
    ufw allow 8765/tcp
  fi
  ufw --force enable >/dev/null 2>&1 || true
fi

LAN_IP="$(hostname -I | awk '{print $1}')"
curl -sf http://127.0.0.1:8765/health >/dev/null && OK=✓ || OK=✗

cat <<EOF

================================================================================
  部署完成 ${OK}
================================================================================

  局域网调用地址:  http://${LAN_IP}:8765
  API Key（请妥善保存，只显示这一次）:

  ${API_KEY}

  测试:
  curl -s http://${LAN_IP}:8765/health
  curl -X POST http://${LAN_IP}:8765/pipeline \\
    -H "Content-Type: application/json" \\
    -H "X-API-Key: ${API_KEY}" \\
    -d '{"url":"小红书或抖音分享链接"}'

  安全说明:
  - 默认只监听 127.0.0.1；局域网通过 ufw 放行 8765
  - /docs 已关闭，/health 不泄露配置
  - 转写 URL 仅允许常见 CDN，拒绝内网地址
  - 每分钟限流 20 次（可在 .env 改 RATE_LIMIT_PER_MINUTE）

  运维:
  sudo systemctl status video-parser-api
  sudo systemctl restart video-parser-api
  sudo journalctl -u video-parser-api -f

  主电脑 Agent 环境变量:
  MEDIA_API_BASE=http://${LAN_IP}:8765
  MEDIA_API_KEY=${API_KEY}

  商业多客户（每客户独立 Key）:
  source .venv/bin/activate
  python scripts/manage_accounts.py add --name "客户名" --quota 1000 --rate 30

================================================================================
EOF
