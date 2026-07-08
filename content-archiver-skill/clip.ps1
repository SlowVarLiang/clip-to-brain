# Clip-to-Brain 统一入口（Windows）
# 用法:
#   .\clip.ps1 "https://weixin.qq.com/sph/..."
#   .\clip.ps1 "https://mp.weixin.qq.com/s/..." -Open
#   .\clip.ps1 -InputFile .\draft.txt -Category 04 -Subfolder methodology
#   .\clip.ps1 -Stats
#   .\clip.ps1 -Reextract "D:\...\note.md"

param(
    [Parameter(Position = 0, ValueFromRemainingArguments = $true)]
    [string[]]$ClipArg,
    [string]$InputFile = "",
    [string]$Account = "",
    [string]$Profile = "",
    [string]$Category = "",
    [string]$Subfolder = "",
    [string]$Title = "",
    [switch]$Json,
    [switch]$Stats,
    [switch]$ListProfiles,
    [switch]$Open,
    [switch]$NoTopic,
    [int]$Days = 1,
    [string[]]$Reextract = @()
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path (Split-Path -Parent $Root) "video-parser\.venv\Scripts\python.exe"
$Script = Join-Path $Root "scripts\clip.py"
$Config = Join-Path $Root "config.json"

if (-not (Test-Path $Python)) { $Python = "python" }

$env:PYTHONIOENCODING = "utf-8"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$pyArgs = @($Script, "--config", $Config)

if ($ListProfiles) {
    $pyArgs += "--list-profiles"
} elseif ($Stats) {
    $pyArgs += "--stats"
    if ($Days -gt 1) { $pyArgs += @("--days", $Days) }
} elseif ($Reextract.Count -gt 0) {
    $pyArgs += "--reextract"
    foreach ($n in $Reextract) { if ($n) { $pyArgs += $n } }
} elseif ($InputFile) {
    $pyArgs += @("--file", $InputFile)
} elseif ($ClipArg) {
    foreach ($i in $ClipArg) { if ($i) { $pyArgs += $i } }
} else {
    throw "需要链接、-InputFile、-Stats 或 -Reextract"
}

if ($Profile) { $pyArgs += @("--profile", $Profile) }
elseif ($Account) { $pyArgs += @("--account", $Account) }
if ($Category) { $pyArgs += @("--category", $Category) }
if ($Subfolder) { $pyArgs += @("--subfolder", $Subfolder) }
if ($Title) { $pyArgs += @("--title", $Title) }
if ($Json) { $pyArgs += "--json" }
if ($Open) { $pyArgs += "--open" }
if ($NoTopic) { $pyArgs += "--no-topic" }

& $Python @pyArgs
