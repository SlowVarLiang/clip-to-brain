# Clip-to-Brain service launcher
# Usage:
#   .\start-clip.ps1
#   .\start-clip.ps1 -Telegram
#   .\start-clip.ps1 -Tunnel

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

Write-Host "Clip-to-Brain starting..." -ForegroundColor Cyan
Write-Host "  Dashboard : http://127.0.0.1:8765/clip/dashboard" -ForegroundColor Green
Write-Host "  CLI       : .\clip.ps1 <url>" -ForegroundColor Green
Write-Host "  Feishu    : POST http://127.0.0.1:8765/bot/feishu" -ForegroundColor Yellow
Write-Host ""

if ($Telegram) {
    if ($env:TELEGRAM_BOT_TOKEN) {
        $tgScript = Join-Path $Root "start-telegram.ps1"
        Start-Process powershell -ArgumentList "-NoExit", "-File", $tgScript | Out-Null
        Write-Host "  Telegram  : polling started in new window" -ForegroundColor Green
    } else {
        Write-Host "  Telegram  : skipped (TELEGRAM_BOT_TOKEN not set)" -ForegroundColor DarkYellow
    }
}

if ($Tunnel) {
    $tunnelScript = Join-Path $Root "tunnel.ps1"
    Start-Process powershell -ArgumentList "-NoExit", "-File", $tunnelScript | Out-Null
    Write-Host "  Tunnel    : started in new window" -ForegroundColor Green
}

Write-Host ""
Set-Location $Parser
& $Python -m parser.server
