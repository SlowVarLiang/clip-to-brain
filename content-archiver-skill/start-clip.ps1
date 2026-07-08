# 启动 Clip-to-Brain 全套服务
# 用法:
#   .\start-clip.ps1                    # 仅 API + Dashboard
#   .\start-clip.ps1 -Telegram          # 后台启动 Telegram 长轮询
#   .\start-clip.ps1 -Tunnel            # 另开窗口跑内网穿透

param(
    [switch]$Telegram,
    [switch]$Tunnel
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$AutoMedia = Split-Path -Parent $Root
$Parser = Join-Path $AutoMedia "video-parser"
$Python = Join-Path $Parser ".venv\Scripts\python.exe"
$EnvFile = Join-Path $AutoMedia ".env.local"

if (-not (Test-Path $Python)) { $Python = "python" }

function Import-DotEnv([string]$Path) {
    if (-not (Test-Path $Path)) { return }
    Get-Content $Path -Encoding UTF8 | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#")) { return }
        $idx = $line.IndexOf("=")
        if ($idx -lt 1) { return }
        $key = $line.Substring(0, $idx).Trim()
        $val = $line.Substring($idx + 1).Trim().Trim('"').Trim("'")
        [Environment]::SetEnvironmentVariable($key, $val, "Process")
    }
}

Import-DotEnv $EnvFile
Import-DotEnv (Join-Path $Root ".env.local")

Write-Host "Clip-to-Brain 服务启动中…" -ForegroundColor Cyan
Write-Host "  Dashboard : http://127.0.0.1:8765/clip/dashboard" -ForegroundColor Green
Write-Host "  CLI       : .\clip.ps1 `"<链接>`"" -ForegroundColor Green
Write-Host "  飞书 Hook : POST http://127.0.0.1:8765/bot/feishu (+ tunnel.ps1 暴露公网)" -ForegroundColor Yellow
Write-Host ""

if ($Telegram) {
    if ($env:TELEGRAM_BOT_TOKEN) {
        Start-Process powershell -ArgumentList @(
            "-NoExit", "-File", (Join-Path $Root "start-telegram.ps1")
        ) | Out-Null
        Write-Host "  Telegram  : 长轮询已在另一窗口启动" -ForegroundColor Green
    } else {
        Write-Host "  Telegram  : 跳过（未设置 TELEGRAM_BOT_TOKEN）" -ForegroundColor DarkYellow
    }
}

if ($Tunnel) {
    Start-Process powershell -ArgumentList @(
        "-NoExit", "-File", (Join-Path $Root "tunnel.ps1")
    ) | Out-Null
    Write-Host "  Tunnel    : 内网穿透已在另一窗口启动" -ForegroundColor Green
}

Write-Host ""
Set-Location $Parser
& $Python -m parser.server
