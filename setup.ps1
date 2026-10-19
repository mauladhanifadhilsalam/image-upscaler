<#
.SYNOPSIS
    One-time setup for the image upscaler on Windows. Safe to re-run.

.DESCRIPTION
    Creates backend\.venv, installs PyTorch (CUDA build if an NVIDIA GPU is found,
    otherwise CPU), installs the backend requirements, makes sure the Real-ESRGAN
    weights are present, builds the web UI if it is missing and Node is available,
    and writes the MCP configs for Claude Code (.mcp.json) and Claude Desktop.

.PARAMETER Cpu
    Install the CPU-only PyTorch build even if an NVIDIA GPU is present.

.PARAMETER RegisterClaudeDesktop
    Also add the "image-upscaler" MCP server to Claude Desktop's config
    (%APPDATA%\Claude\claude_desktop_config.json; a .bak copy is kept).

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\setup.ps1
#>
param(
    [switch]$Cpu,
    [switch]$RegisterClaudeDesktop
)

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$Backend = Join-Path $Root "backend"
$Venv = Join-Path $Backend ".venv"

function Step($message) { Write-Host "==> $message" -ForegroundColor Cyan }

function Invoke-Checked {
    param([string]$Exe, [string[]]$Arguments)
    & $Exe @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Command failed ($LASTEXITCODE): $Exe $($Arguments -join ' ')" }
}

function Find-Python {
    # The Microsoft Store "python" stub prints nothing, so check the version explicitly.
    foreach ($candidate in @(@("py", "-3"), @("python"), @("python3"))) {
        if (-not (Get-Command $candidate[0] -ErrorAction SilentlyContinue)) { continue }
        $pyArgs = @($candidate | Select-Object -Skip 1) + @("-c", "import sys; print(sys.version_info >= (3, 10))")
        try { $ok = & $candidate[0] @pyArgs 2>$null } catch { continue }
        if ($ok -eq "True") { return , $candidate }
    }
    throw "Python 3.10 or newer was not found. Install it from https://www.python.org/downloads/ (tick 'Add python.exe to PATH'), open a new terminal and re-run this script."
}

function Write-Json($value, $path) {
    # Windows PowerShell's Set-Content -Encoding UTF8 adds a BOM, which breaks JSON parsers.
    [System.IO.File]::WriteAllText($path, ($value | ConvertTo-Json -Depth 10))
}

function Get-VenvPython {
    $windows = Join-Path $Venv "Scripts\python.exe"
    if (Test-Path $windows) { return $windows }
    return (Join-Path $Venv "bin/python")  # macOS / Linux
}

# 1. Virtual environment
$python = Get-VenvPython
if (Test-Path $python) {
    Step "Using existing virtual environment"
} else {
    $base = Find-Python
    Step "Creating virtual environment with $($base -join ' ')"
    $venvArgs = @($base | Select-Object -Skip 1) + @("-m", "venv", $Venv)
    Invoke-Checked $base[0] $venvArgs
    $python = Get-VenvPython
}
Invoke-Checked $python @("-m", "pip", "install", "--quiet", "--upgrade", "pip")

# 2. PyTorch (torch and torchvision must come from the same index)
$hasGpu = (-not $Cpu) -and [bool](Get-Command nvidia-smi -ErrorAction SilentlyContinue)
$index = if ($hasGpu) { "https://download.pytorch.org/whl/cu126" } else { "https://download.pytorch.org/whl/cpu" }
Step ("Installing PyTorch (" + $(if ($hasGpu) { "NVIDIA GPU / CUDA 12.6" } else { "CPU only" }) + "), this can take a few minutes")
Invoke-Checked $python @("-m", "pip", "install", "--quiet", "torch", "torchvision", "--index-url", $index)

# 3. Backend requirements
Step "Installing backend requirements"
Invoke-Checked $python @("-m", "pip", "install", "--quiet", "-r", (Join-Path $Backend "requirements.txt"))

# 4. Model weights (shipped in the zip; downloaded only if missing)
Step "Checking Real-ESRGAN model weights"
Invoke-Checked $python @((Join-Path $Backend "scripts\download_models.py"))

# 5. Web UI
$dist = Join-Path $Root "frontend\dist\index.html"
if (Test-Path $dist) {
    Step "Web UI already built"
} elseif (Get-Command npm -ErrorAction SilentlyContinue) {
    Step "Building web UI"
    Push-Location (Join-Path $Root "frontend")
    try {
        Invoke-Checked "npm" @("install", "--no-fund", "--no-audit")
        Invoke-Checked "npm" @("run", "build")
    } finally { Pop-Location }
} else {
    Write-Warning "frontend\dist is missing and Node.js is not installed; the API and MCP tools still work, only the web page is unavailable."
}

# 6. MCP configs with this machine's absolute paths
Step "Writing MCP configs"
$server = [ordered]@{
    command = (Resolve-Path $python).Path
    args    = @((Join-Path $Backend "scripts\mcp_server.py"))
    env     = [ordered]@{ UPSCALER_API_URL = "http://localhost:8000" }
}
$mcp = [ordered]@{ mcpServers = [ordered]@{ "image-upscaler" = $server } }
Write-Json $mcp (Join-Path $Root ".mcp.json")
Write-Json $mcp (Join-Path $Root "claude_desktop_config.snippet.json")

if ($RegisterClaudeDesktop) {
    $configDir = Join-Path $env:APPDATA "Claude"
    $configPath = Join-Path $configDir "claude_desktop_config.json"
    New-Item -ItemType Directory -Force $configDir | Out-Null
    if (Test-Path $configPath) {
        Copy-Item $configPath "$configPath.bak" -Force
        $config = Get-Content -Raw $configPath | ConvertFrom-Json
    } else {
        $config = [pscustomobject]@{}
    }
    if (-not $config.PSObject.Properties["mcpServers"]) {
        $config | Add-Member -NotePropertyName mcpServers -NotePropertyValue ([pscustomobject]@{})
    }
    $config.mcpServers | Add-Member -NotePropertyName "image-upscaler" -NotePropertyValue ([pscustomobject]$server) -Force
    Write-Json $config $configPath
    Step "Registered with Claude Desktop ($configPath). Restart Claude Desktop to load it."
}

# 7. Sanity check
Step "Verifying installation"
Invoke-Checked $python @("-c", "import torch, spandrel, fastapi, mcp; print('torch', torch.__version__, '| CUDA available:', torch.cuda.is_available())")

Write-Host ""
Write-Host "Setup complete." -ForegroundColor Green
Write-Host "  Start the server:  powershell -ExecutionPolicy Bypass -File .\start.ps1 -Background"
Write-Host "  Web UI:            http://localhost:8000"
Write-Host "  Claude Code:       run 'claude' in this folder (uses .mcp.json)"
Write-Host "  Claude Desktop:    re-run with -RegisterClaudeDesktop, or paste claude_desktop_config.snippet.json"
