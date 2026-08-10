# Start ngrok tunnel → local API and register Telegram webhook.
# Usage from repo root:
#   .\scripts\start-ngrok.ps1
#   .\scripts\start-ngrok.ps1 -Port 8080 -NoWebhook

param(
    [int]$Port = 8080,
    [switch]$NoWebhook
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path "$PSScriptRoot\.."
$Data = Join-Path $Root "data"
New-Item -ItemType Directory -Force -Path $Data | Out-Null

$candidates = @(
    (Join-Path $Root "tools\ngrok\ngrok.exe"),
    "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\Ngrok.Ngrok_Microsoft.Winget.Source_8wekyb3d8bbwe\ngrok.exe",
    "$env:LOCALAPPDATA\ngrok\ngrok.exe"
)
$ngrok = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $ngrok) {
    $cmd = Get-Command ngrok -ErrorAction SilentlyContinue
    if ($cmd) { $ngrok = $cmd.Source }
}
if (-not $ngrok) { throw "ngrok.exe not found. Place at tools\ngrok\ngrok.exe (v3.20+)" }

Get-Process cloudflared -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Get-Process ngrok -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1

$log = Join-Path $Data "ngrok.out.log"
$err = Join-Path $Data "ngrok.err.log"
Remove-Item $log, $err -ErrorAction SilentlyContinue

Write-Host "Starting ngrok http 127.0.0.1:$Port ..."
Start-Process -FilePath $ngrok `
    -ArgumentList @("http", "127.0.0.1:$Port", "--log=stdout", "--log-format=logfmt") `
    -WorkingDirectory $Root `
    -WindowStyle Hidden `
    -RedirectStandardOutput $log `
    -RedirectStandardError $err

$url = $null
for ($i = 0; $i -lt 45; $i++) {
    Start-Sleep -Seconds 1
    try {
        $t = Invoke-RestMethod "http://127.0.0.1:4040/api/tunnels" -TimeoutSec 2
        $url = ($t.tunnels | Where-Object { $_.public_url -like "https://*" } | Select-Object -First 1).public_url
        if ($url) { break }
    } catch {}
}
if (-not $url) {
    if (Test-Path $log) { Get-Content $log -Tail 30 }
    throw "Failed to get ngrok public URL (need authtoken + ngrok v3.20+)"
}

Write-Host "Tunnel URL: $url"
foreach ($envPath in @((Join-Path $Root ".env"), (Join-Path $Root "services\integration\.env"))) {
    if (-not (Test-Path $envPath)) { continue }
    $raw = Get-Content $envPath -Raw
    $raw = $raw -replace "(?m)^TELEGRAM_WEBHOOK_BASE_URL=.*$", "TELEGRAM_WEBHOOK_BASE_URL=$url"
    Set-Content $envPath $raw -NoNewline
}
Write-Host "Updated TELEGRAM_WEBHOOK_BASE_URL"

if (-not $NoWebhook) {
    & (Join-Path $PSScriptRoot "set_telegram_webhook.ps1")
}

Write-Host "Done. Health: $url/health  (ngrok inspect: http://127.0.0.1:4040)"
