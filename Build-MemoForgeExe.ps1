$ErrorActionPreference = "Stop"

function Write-Info([string]$Message) {
    Write-Host "[MemoForge Build] $Message"
}

function Test-CommandAvailable([string]$Name) {
    return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

$venvPython = Join-Path $projectRoot "venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Info "Creating virtual environment..."
    if (Test-CommandAvailable "py") {
        & py -3 -m venv (Join-Path $projectRoot "venv")
    } elseif (Test-CommandAvailable "python") {
        & python -m venv (Join-Path $projectRoot "venv")
    } else {
        throw "Python 3 is required to build the EXE."
    }
}

if (-not (Test-Path $venvPython)) {
    throw "Could not find venv python at '$venvPython'."
}

Write-Info "Installing build/runtime dependencies..."
& $venvPython -m pip install --upgrade pip
if (Test-Path (Join-Path $projectRoot "requirements.txt")) {
    & $venvPython -m pip install -r (Join-Path $projectRoot "requirements.txt")
}
& $venvPython -m pip install pyinstaller

Write-Info "Building MemoForge.exe ..."
& $venvPython -m PyInstaller `
    --noconfirm `
    --clean `
    --windowed `
    --name MemoForge `
    main.py

Write-Info "Build complete. Output: dist\\MemoForge.exe"
