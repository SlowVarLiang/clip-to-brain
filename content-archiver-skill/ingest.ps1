# Lumis 链接一键入库（Windows）
# 用法:
#   .\ingest.ps1 "https://www.xiaohongshu.com/discovery/item/..."
#   .\ingest.ps1 -Url "链接1" "链接2"
#   .\ingest.ps1 -Url "链接" -Category 07 -Subfolder xiaohongshu

param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Url,
    [string]$Category = "",
    [string]$Subfolder = "",
    [switch]$SkipTranscribe
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path (Split-Path -Parent $Root) "video-parser\.venv\Scripts\python.exe"
$Script = Join-Path $Root "scripts\lumis_ingest.py"
$Config = Join-Path $Root "config.json"

if (-not (Test-Path $Python)) { $Python = "python" }

$pyArgs = @($Script, "--config", $Config, "ingest")
foreach ($u in $Url) { if ($u) { $pyArgs += $u } }
if ($Category) { $pyArgs += @("--category", $Category) }
if ($Subfolder) { $pyArgs += @("--subfolder", $Subfolder) }
if ($SkipTranscribe) { $pyArgs += "--skip-transcribe" }

& $Python @pyArgs
