# Start MAX long-polling bot (pilot, no ngrok).
# Usage from repo root:
#   .\scripts\run-max-poller.ps1

$ErrorActionPreference = "Stop"
$Root = Resolve-Path "$PSScriptRoot\.."
$Svc = Join-Path $Root "services\integration"
$VenvPython = Join-Path $Svc ".venv\Scripts\python.exe"
$EnvFile = Join-Path $Root ".env"

if (-not (Test-Path $VenvPython)) {
    throw "venv not found at $VenvPython"
}
if (-not (Test-Path $EnvFile)) {
    throw ".env missing"
}

Get-Content $EnvFile | ForEach-Object {
    if ($_ -match '^\s*#' -or $_ -notmatch '=') { return }
    $k, $v = $_ -split '=', 2
    Set-Item -Path "Env:$($k.Trim())" -Value $v.Trim().Trim('"').Trim("'")
}

if (-not $env:MAX_BOT_TOKEN) { throw "MAX_BOT_TOKEN is empty in .env" }
$env:BOT_CHANNEL = if ($env:BOT_CHANNEL) { $env:BOT_CHANNEL } else { "max" }

Write-Host "Starting MAX poller (BOT_CHANNEL=$($env:BOT_CHANNEL)) ..."
Set-Location $Svc
& $VenvPython -m app.bot.max_poller
