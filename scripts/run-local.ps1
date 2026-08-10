# Local run without Docker (Windows / PowerShell)
# Usage from repo root:
#   .\scripts\run-local.ps1
#   .\scripts\run-local.ps1 -WorkerOnly
#   .\scripts\run-local.ps1 -ApiOnly

param(
    [switch]$ApiOnly,
    [switch]$WorkerOnly
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path "$PSScriptRoot\.."
$Svc = Join-Path $Root "services\integration"
$VenvPython = Join-Path $Svc ".venv\Scripts\python.exe"
$EnvFile = Join-Path $Root ".env"

if (-not (Test-Path $VenvPython)) {
    throw "venv not found. Run: python -m venv services\integration\.venv && pip install -r services\integration\requirements.txt"
}
if (-not (Test-Path $EnvFile)) {
    throw ".env missing. Copy .env.example to .env and fill secrets."
}

# Load .env into process env for child processes
Get-Content $EnvFile | ForEach-Object {
    if ($_ -match '^\s*#' -or $_ -notmatch '=') { return }
    $k, $v = $_ -split '=', 2
    Set-Item -Path "Env:$($k.Trim())" -Value $v.Trim().Trim('"').Trim("'")
}

Set-Location $Svc

if (-not $WorkerOnly) {
    Write-Host "Starting API on http://localhost:$($env:APP_PORT) ..."
    Start-Process -FilePath $VenvPython -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", ($env:APP_PORT -as [string]), "--reload" -WorkingDirectory $Svc -NoNewWindow
}

if (-not $ApiOnly) {
    Write-Host "Starting worker ..."
    Start-Process -FilePath $VenvPython -ArgumentList "-m", "app.worker.runner" -WorkingDirectory $Svc -NoNewWindow
}

Write-Host "Done. Health: curl http://localhost:$($env:APP_PORT)/health"
