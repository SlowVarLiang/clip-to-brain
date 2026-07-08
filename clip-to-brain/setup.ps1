# Clip-to-Brain 安装脚本 (Windows)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Repo = Split-Path -Parent $Root
$Archiver = Join-Path $Repo "content-archiver-skill"
$Parser = Join-Path $Repo "video-parser"
$Venv = Join-Path $Parser ".venv"
$Python = Join-Path $Venv "Scripts\python.exe"

Write-Host "Clip-to-Brain Setup" -ForegroundColor Cyan

# venv
if (-not (Test-Path $Python)) {
    Write-Host "创建 Python 虚拟环境…"
    python -m venv $Venv
}
Write-Host "安装 video-parser 依赖…"
& $Python -m pip install -q -U pip
& $Python -m pip install -q -r (Join-Path $Parser "requirements.txt")
& $Python -m pip install -q -r (Join-Path $Archiver "requirements.txt")

# .env.local
$EnvExample = Join-Path $Root ".env.example"
$EnvLocal = Join-Path $Repo ".env.local"
if (-not (Test-Path $EnvLocal)) {
    Copy-Item $EnvExample $EnvLocal
    Write-Host "已创建 .env.local — 请填写 LLM_API_KEY" -ForegroundColor Yellow
}

# vault + config
& $Python (Join-Path $Archiver "scripts\bootstrap_vault.py") --dest (Join-Path $Repo "vault")

Write-Host ""
Write-Host "安装完成。" -ForegroundColor Green
Write-Host "  1. 编辑 $EnvLocal"
Write-Host "  2. cd content-archiver-skill"
Write-Host "  3. .\clip.ps1 `"<链接>`""
