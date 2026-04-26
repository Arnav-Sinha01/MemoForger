$ErrorActionPreference = "Stop"

function Write-Info([string]$Message) {
    Write-Host "[MemoForge] $Message"
}

function Test-CommandAvailable([string]$Name) {
    return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

function Ensure-PythonVenv([string]$ProjectRoot) {
    $venvPython = Join-Path $ProjectRoot "venv\Scripts\python.exe"
    if (Test-Path $venvPython) {
        return $venvPython
    }

    Write-Info "Python virtual environment not found. Creating one..."
    if (Test-CommandAvailable "py") {
        & py -3 -m venv (Join-Path $ProjectRoot "venv")
    } elseif (Test-CommandAvailable "python") {
        & python -m venv (Join-Path $ProjectRoot "venv")
    } else {
        throw "Python 3 was not found. Install Python 3.x and retry."
    }

    if (-not (Test-Path $venvPython)) {
        throw "Failed to create virtual environment at '$venvPython'."
    }
    return $venvPython
}

function Ensure-PythonDeps([string]$ProjectRoot, [string]$VenvPython) {
    $requirementsPath = Join-Path $ProjectRoot "requirements.txt"
    $depsMarker = Join-Path $ProjectRoot ".deps_installed.ok"

    if (-not (Test-Path $requirementsPath)) {
        Write-Info "requirements.txt not found, skipping dependency bootstrap."
        return
    }

    $needsInstall = $true
    if (Test-Path $depsMarker) {
        $markerTime = (Get-Item $depsMarker).LastWriteTimeUtc
        $requirementsTime = (Get-Item $requirementsPath).LastWriteTimeUtc
        $needsInstall = $markerTime -lt $requirementsTime
    }

    if ($needsInstall) {
        Write-Info "Installing/updating Python dependencies..."
        & $VenvPython -m pip install --upgrade pip
        & $VenvPython -m pip install -r $requirementsPath
        New-Item -ItemType File -Path $depsMarker -Force | Out-Null
    }
}

function Ensure-OllamaInstalled {
    if (Test-CommandAvailable "ollama") {
        return
    }

    Write-Info "Ollama was not found. Installing automatically..."
    if (Test-CommandAvailable "winget") {
        & winget install --id Ollama.Ollama -e --accept-package-agreements --accept-source-agreements
    } else {
        throw "Ollama is missing and winget is unavailable. Install Ollama from https://ollama.com/download/windows"
    }

    if (-not (Test-CommandAvailable "ollama")) {
        $fallbackPath = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"
        if (Test-Path $fallbackPath) {
            $env:Path = "$($env:Path);$(Split-Path $fallbackPath -Parent)"
        }
    }

    if (-not (Test-CommandAvailable "ollama")) {
        throw "Ollama installation could not be verified. Open a new terminal and run 'ollama --version'."
    }
}

function Test-OllamaApi([int]$TimeoutSec = 3) {
    try {
        Invoke-RestMethod -Uri "http://localhost:11434/api/tags" -Method Get -TimeoutSec $TimeoutSec | Out-Null
        return $true
    } catch {
        return $false
    }
}

function Ensure-OllamaRunning {
    if (Test-OllamaApi -TimeoutSec 2) {
        return
    }

    Write-Info "Starting Ollama service..."
    $ollamaCmd = Get-Command ollama -ErrorAction Stop
    Start-Process -FilePath $ollamaCmd.Source -ArgumentList "serve" -WindowStyle Hidden

    $deadline = (Get-Date).AddSeconds(45)
    while ((Get-Date) -lt $deadline) {
        if (Test-OllamaApi -TimeoutSec 2) {
            Write-Info "Ollama is running."
            return
        }
        Start-Sleep -Milliseconds 800
    }

    throw "Ollama did not become ready in time."
}

try {
    $projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
    Set-Location $projectRoot

    Write-Info "Bootstrapping MemoForge..."
    $venvPython = Ensure-PythonVenv -ProjectRoot $projectRoot
    Ensure-PythonDeps -ProjectRoot $projectRoot -VenvPython $venvPython
    Ensure-OllamaInstalled
    Ensure-OllamaRunning

    Write-Info "Launching application..."
    & $venvPython (Join-Path $projectRoot "main.py")
    exit $LASTEXITCODE
}
catch {
    Write-Host ""
    Write-Host "[MemoForge] Startup failed: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
