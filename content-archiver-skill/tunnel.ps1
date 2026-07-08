# 内网穿透 — 暴露 Clip-to-Brain API 给飞书 Webhook
# 用法: .\tunnel.ps1
# 优先 cloudflared，其次 ngrok

param(
    [int]$Port = 8765
)

$ErrorActionPreference = "Stop"

Write-Host "暴露 http://127.0.0.1:$Port 到公网…" -ForegroundColor Cyan
Write-Host "飞书 Webhook 填: https://<隧道域名>/bot/feishu" -ForegroundColor Yellow
Write-Host ""

if (Get-Command cloudflared -ErrorAction SilentlyContinue) {
    cloudflared tunnel --url "http://127.0.0.1:$Port"
    exit $LASTEXITCODE
}

if (Get-Command ngrok -ErrorAction SilentlyContinue) {
    ngrok http $Port
    exit $LASTEXITCODE
}

Write-Host "未找到 cloudflared 或 ngrok。" -ForegroundColor Red
Write-Host ""
Write-Host "安装 cloudflared（推荐）:" -ForegroundColor Gray
Write-Host "  winget install Cloudflare.cloudflared" -ForegroundColor Gray
Write-Host "或 ngrok: https://ngrok.com/download" -ForegroundColor Gray
exit 1
