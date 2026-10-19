<#
.SYNOPSIS
    Stop a server started with .\start.ps1 -Background.
#>
$Backend = Join-Path $PSScriptRoot "backend"
$pidFile = Join-Path $Backend "server.pid"

if (-not (Test-Path $pidFile)) {
    Write-Host "No server.pid found; nothing to stop."
    exit 0
}

$serverPid = [int](Get-Content $pidFile)
if (Get-Process -Id $serverPid -ErrorAction SilentlyContinue) {
    if ($env:OS -eq "Windows_NT") {
        # The venv python.exe is a launcher with a child interpreter; kill the whole tree.
        taskkill /PID $serverPid /T /F | Out-Null
    } else {
        Stop-Process -Id $serverPid -Force
    }
    Write-Host "Stopped server (PID $serverPid)."
} else {
    Write-Host "Server (PID $serverPid) was not running."
}
Remove-Item $pidFile
