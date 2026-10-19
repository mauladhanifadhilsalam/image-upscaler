<#
.SYNOPSIS
    Start the upscaler API + web UI on http://localhost:<Port>.

.PARAMETER Background
    Run hidden in the background, log to backend\server.log, and return once the
    server answers /api/health. Stop it with .\stop.ps1.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\start.ps1 -Background
#>
param(
    [int]$Port = 8000,
    [switch]$Background,
    [int]$TimeoutSeconds = 180
)

$ErrorActionPreference = "Stop"
$Backend = Join-Path $PSScriptRoot "backend"
$Venv = Join-Path $Backend ".venv"
$python = Join-Path $Venv "Scripts\python.exe"
if (-not (Test-Path $python)) { $python = Join-Path $Venv "bin/python" }
if (-not (Test-Path $python)) { throw "backend\.venv not found. Run .\setup.ps1 first." }

$healthUrl = "http://127.0.0.1:$Port/api/health"

function Get-Health {
    try { return Invoke-RestMethod -Uri $healthUrl -TimeoutSec 3 } catch { return $null }
}

$health = Get-Health
if ($health) {
    Write-Host "Already running on port $Port (upscaler: $($health.upscaler))."
    exit 0
}

$uvicornArgs = @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "$Port")

if (-not $Background) {
    Write-Host "Starting on http://localhost:$Port (Ctrl+C to stop)..."
    Push-Location $Backend
    try { & $python @uvicornArgs } finally { Pop-Location }
    exit $LASTEXITCODE
}

$log = Join-Path $Backend "server.log"
$options = @{
    FilePath               = $python
    ArgumentList           = $uvicornArgs
    WorkingDirectory       = $Backend
    RedirectStandardOutput = Join-Path $Backend "server.out.log"
    RedirectStandardError  = $log
    PassThru               = $true
}
if ($env:OS -eq "Windows_NT") { $options.WindowStyle = "Hidden" }
$process = Start-Process @options
Set-Content -Path (Join-Path $Backend "server.pid") -Value $process.Id

Write-Host "Starting in the background (PID $($process.Id)); loading the models can take a minute..."
$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
while ((Get-Date) -lt $deadline) {
    Start-Sleep -Seconds 2
    $health = Get-Health
    if ($health) {
        Write-Host "Ready: http://localhost:$Port  (upscaler: $($health.upscaler), scales: $($health.scales -join ', '))" -ForegroundColor Green
        exit 0
    }
    if ($process.HasExited) { break }
}
Write-Host "Server did not become ready. Last log lines from ${log}:" -ForegroundColor Red
if (Test-Path $log) { Get-Content $log -Tail 30 }
exit 1
