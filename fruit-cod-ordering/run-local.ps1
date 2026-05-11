$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

$env:STORAGE_MODE = "local"
$env:LOCAL_PREVIEW_FALLBACK = "true"
$env:FLASK_APP = "app.py"
$env:FLASK_ENV = "production"
$env:FLASK_DEBUG = "0"
$env:PORT = "5001"

$pythonCandidates = @(
  "$env:USERPROFILE\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe",
  "py",
  "python"
)

$python = $null
foreach ($candidate in $pythonCandidates) {
  try {
    if ($candidate -like "*\*" -and -not (Test-Path $candidate)) {
      continue
    }
    & $candidate --version *> $null
    $python = $candidate
    break
  } catch {
    continue
  }
}

if (-not $python) {
  throw "Python was not found. Install Python or update run-local.ps1 with your Python path."
}

& $python -m flask run --host 0.0.0.0 --port 5001 --no-reload
