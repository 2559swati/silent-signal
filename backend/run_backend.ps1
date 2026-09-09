# PowerShell script to start the SilentSignal backend with Python 3.12
# Save this as run_backend.ps1 in the backend folder

$venvPath = "$PSScriptRoot\.venv12"
$pythonExe = "python"

# Locate a Python 3.12 interpreter
$py = Get-Command python -ErrorAction SilentlyContinue
if ($py) {
    $ver = & $py.Path -c "import sys; print('.'.join(map(str, sys.version_info[:2])))"
    if ($ver -ne "3.12") { $pythonExe = "python3.12" }
} else { $pythonExe = "python3.12" }

# Create venv if it does not exist
if (-not (Test-Path $venvPath)) {
    Write-Host "Creating Python 3.12 virtual environment..."
    & $pythonExe -m venv $venvPath
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Failed to create venv. Ensure Python 3.12 is installed and in PATH."
        exit 1
    }
}

# Activate venv
$activate = Join-Path $venvPath "Scripts\Activate.ps1"
if (-not (Test-Path $activate)) {
    Write-Error "Activation script not found: $activate"
    exit 1
}
. $activate

# Upgrade pip and install requirements
python -m pip install --upgrade pip
python -m pip install -r "$PSScriptRoot\requirements.txt"

# Run FastAPI with uvicorn
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
