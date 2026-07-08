# Telegram 长轮询 Bot（无需 webhook / 内网穿透）
# 用法:
#   1. 在 .env.local 设置 TELEGRAM_BOT_TOKEN=...
#   2. .\start-telegram.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$AutoMedia = Split-Path -Parent $Root
$Python = Join-Path $AutoMedia "video-parser\.venv\Scripts\python.exe"
$Bot = Join-Path $Root "scripts\clip_bot.py"
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

if (-not $env:TELEGRAM_BOT_TOKEN) {
    throw "请在 $EnvFile 设置 TELEGRAM_BOT_TOKEN"
}

$env:PYTHONIOENCODING = "utf-8"
$prof = if ($env:CLIP_PROFILE) { $env:CLIP_PROFILE } else { "default-creator" }
Write-Host "Telegram Bot 长轮询启动… profile=$prof" -ForegroundColor Green
& $Python $Bot poll --profile $prof
