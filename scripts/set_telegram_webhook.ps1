# Register Telegram webhook for pilot tunnel (Cloudflare / ngrok).
# Usage (from repo root):
#   .\scripts\set_telegram_webhook.ps1

$ErrorActionPreference = "Stop"

function Get-DotEnvValue([string]$Key) {
    $path = Join-Path (Resolve-Path "$PSScriptRoot\..") ".env"
    if (-not (Test-Path $path)) { return $null }
    $line = Get-Content $path | Where-Object { $_ -match "^\s*$Key\s*=" } | Select-Object -First 1
    if (-not $line) { return $null }
    return ($line -split "=", 2)[1].Trim().Trim('"').Trim("'")
}

$token = $env:TELEGRAM_BOT_TOKEN
if (-not $token) { $token = Get-DotEnvValue "TELEGRAM_BOT_TOKEN" }

$base = $env:TELEGRAM_WEBHOOK_BASE_URL
if (-not $base) { $base = Get-DotEnvValue "TELEGRAM_WEBHOOK_BASE_URL" }

$secret = $env:TELEGRAM_WEBHOOK_SECRET
if (-not $secret) { $secret = Get-DotEnvValue "TELEGRAM_WEBHOOK_SECRET" }

if (-not $token) { throw "TELEGRAM_BOT_TOKEN is empty" }
if (-not $base) { throw "TELEGRAM_WEBHOOK_BASE_URL is empty (tunnel HTTPS URL)" }
if (-not $secret) { throw "TELEGRAM_WEBHOOK_SECRET is empty" }

$url = "$($base.TrimEnd('/'))/telegram/webhook"
Write-Host "Setting webhook to $url"

$root = Resolve-Path "$PSScriptRoot\.."
$py = Join-Path $root "services\integration\.venv\Scripts\python.exe"
$helper = Join-Path $PSScriptRoot "_set_telegram_webhook.py"

if ((Test-Path $py) -and (Test-Path $helper)) {
    & $py $helper $token $url $secret
    exit $LASTEXITCODE
}

$resp = Invoke-RestMethod -Method Post -Uri "https://api.telegram.org/bot$token/setWebhook" -ContentType "application/json" -Body (@{
    url                  = $url
    secret_token         = $secret
    drop_pending_updates = $true
    allowed_updates      = @("message", "callback_query")
} | ConvertTo-Json)

$resp | ConvertTo-Json -Depth 5
Invoke-RestMethod "https://api.telegram.org/bot$token/getWebhookInfo" | ConvertTo-Json -Depth 5
