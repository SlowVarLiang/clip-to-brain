# Clip-to-Brain publish script
# Usage: .\publish.ps1 [-RepoName clip-to-brain] [-Public]

param(
    [string]$RepoName = "clip-to-brain",
    [switch]$Public,
    [string]$Description = "Clip-to-Brain: paste links to local Obsidian notes"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Repo = Split-Path -Parent $Root

Set-Location $Repo

# Git identity
$prevEap = $ErrorActionPreference
$ErrorActionPreference = "SilentlyContinue"
$name = git config user.name 2>$null
$email = git config user.email 2>$null
$ErrorActionPreference = $prevEap
if (-not $name -or -not $email) {
    Write-Host "Configure Git identity first:" -ForegroundColor Yellow
    Write-Host '  git config --global user.name "SlowVarLiang"' -ForegroundColor Cyan
    Write-Host '  git config --global user.email "you@example.com"' -ForegroundColor Cyan
    exit 1
}

# gh login
$ghOk = $false
try {
    gh auth status 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) { $ghOk = $true }
} catch {}

if (-not $ghOk) {
    Write-Host "Login to GitHub CLI first:" -ForegroundColor Yellow
    Write-Host "  gh auth login" -ForegroundColor Cyan
    exit 1
}

$visibility = if ($Public) { "--public" } else { "--private" }

# Initial commit
$hasCommit = $false
$prevEap = $ErrorActionPreference
$ErrorActionPreference = "SilentlyContinue"
git rev-parse HEAD 2>$null | Out-Null
if ($LASTEXITCODE -eq 0) { $hasCommit = $true }
$ErrorActionPreference = $prevEap

if (-not $hasCommit) {
    Write-Host "Creating initial commit..." -ForegroundColor Cyan
    git add .
    git commit -m "Clip-to-Brain v0.1.0: open-source self-hosted release" -m "Paste links to generate local Obsidian notes with Profile, Dashboard, Telegram Bot, and Docker support."
}

# Remote + push
$remoteUrl = $null
$prevEap = $ErrorActionPreference
$ErrorActionPreference = "SilentlyContinue"
$remoteUrl = git remote get-url origin 2>$null
$ErrorActionPreference = $prevEap
if (-not $remoteUrl) {
    Write-Host "Creating GitHub repo: $RepoName ..." -ForegroundColor Cyan
    gh repo create $RepoName $visibility --description $Description --source=. --remote=origin --push
} else {
    Write-Host "Pushing to $remoteUrl ..." -ForegroundColor Cyan
    git push -u origin HEAD
}

# Release
$tag = "v0.1.0"
$notesFile = Join-Path $Root "RELEASE_v0.1.0.md"
if (Test-Path $notesFile) {
    Write-Host "Creating GitHub Release $tag ..." -ForegroundColor Cyan
    gh release create $tag --title "Clip-to-Brain v0.1.0" --notes-file $notesFile 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Release may already exist. Manual: gh release create $tag --notes-file $notesFile" -ForegroundColor Yellow
    }
}

$url = gh repo view --json url -q .url 2>$null
Write-Host ""
Write-Host "Done!" -ForegroundColor Green
if ($url) {
    Write-Host "  $url" -ForegroundColor Cyan
    Write-Host "  Release: $url/releases/tag/v0.1.0"
}
