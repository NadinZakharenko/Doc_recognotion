# Start Cloudflare quick tunnel → local API (replaces ngrok for pilot).
# Usage from repo root:
#   .\scripts\start-cloudflare-tunnel.ps1
#   .\scripts\start-cloudflare-tunnel.ps1 -Port 8080 -UpdateEnv -SetWebhook
#
# Uses HTTP/2 (--protocol http2): more reliable behind VPN/fake-ip (e.g. Browsec).

param(
    [int]$Port = 8080,
    [switch]$UpdateEnv,
    [switch]$SetWebhook
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path "$PSScriptRoot\.."
$Data = Join-Path $Root "data"
New-Item -ItemType Directory -Force -Path $Data | Out-Null

$cfCandidates = @(
    "$env:ProgramFiles\cloudflared\cloudflared.exe",
    "${env:ProgramFiles(x86)}\cloudflared\cloudflared.exe",
    "$env:LOCALAPPDATA\cloudflared\cloudflared.exe"
)
$cf = $cfCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $cf) {
    $cmd = Get-Command cloudflared -ErrorAction SilentlyContinue
    if ($cmd) { $cf = $cmd.Source }
}
if (-not $cf) {
    throw "cloudflared not found. Install: winget install --id Cloudflare.cloudflared -e"
}

Get-Process cloudflared -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1

$log = Join-Path $Data "cloudflared.out.log"
$err = Join-Path $Data "cloudflared.err.log"
Remove-Item $log, $err -ErrorAction SilentlyContinue

$origin = "http://127.0.0.1:$Port"
Write-Host "Starting cloudflared → $origin (protocol=http2)"
Start-Process -FilePath $cf `
    -ArgumentList @("tunnel", "--url", $origin, "--protocol", "http2", "--no-autoupdate") `
    -WorkingDirectory $Root `
    -WindowStyle Hidden `
    -RedirectStandardOutput $log `
    -RedirectStandardError $err

$url = $null
for ($i = 0; $i -lt 60; $i++) {
    Start-Sleep -Seconds 1
    $txt = ""
    if (Test-Path $err) { $txt += (Get-Content $err -Raw -ErrorAction SilentlyContinue) }
    if (Test-Path $log) { $txt += (Get-Content $log -Raw -ErrorAction SilentlyContinue) }
    # Success banner line only — avoid matching https://api.trycloudflare.com from errors.
    if ($txt -match 'https://[a-z0-9]+(?:-[a-z0-9]+)+\.trycloudflare\.com') {
        $url = $Matches[0]
        break
    }
    if ($txt -match 'failed to request quick Tunnel') {
        throw "cloudflared failed to create quick tunnel (DNS/VPN?). See $err"
    }
}

if (-not $url) {
    Write-Host "--- cloudflared.err.log ---"
    if (Test-Path $err) { Get-Content $err -Tail 40 }
    throw "Failed to obtain trycloudflare.com URL"
}

Write-Host "Tunnel URL: $url"

if ($UpdateEnv) {
    foreach ($envPath in @((Join-Path $Root ".env"), (Join-Path $Root "services\integration\.env"))) {
        if (-not (Test-Path $envPath)) { continue }
        $raw = Get-Content $envPath -Raw
        if ($raw -match "(?m)^TELEGRAM_WEBHOOK_BASE_URL=") {
            $raw = $raw -replace "(?m)^TELEGRAM_WEBHOOK_BASE_URL=.*$", "TELEGRAM_WEBHOOK_BASE_URL=$url"
        } else {
            $raw = $raw.TrimEnd() + "`nTELEGRAM_WEBHOOK_BASE_URL=$url`n"
        }
        Set-Content $envPath $raw -NoNewline
    }
    Write-Host "Updated TELEGRAM_WEBHOOK_BASE_URL in .env"
}

if ($SetWebhook) {
    & (Join-Path $PSScriptRoot "set_telegram_webhook.ps1")
}

Write-Host "Done. Health: $url/health"
Write-Host "Logs: $err"
