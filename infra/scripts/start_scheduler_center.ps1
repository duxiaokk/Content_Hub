param(
  [string]$HostAddress = "127.0.0.1",
  [int]$Port = 9001
)

$projectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$appDir = Join-Path $projectRoot "apps\platform"
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
  $venvPython = Join-Path $appDir ".venv\Scripts\python.exe"
}

$env:PYTHONPATH = $projectRoot
if (-not $env:SECRET_KEY) {
  $env:SECRET_KEY = "local-dev-secret-key"
}
if (-not $env:SCHEDULER_INTERNAL_TOKEN) {
  $env:SCHEDULER_INTERNAL_TOKEN = "local-dev-scheduler-token"
}

Push-Location $appDir
try {
  if (Test-Path $venvPython) {
    & $venvPython -m uvicorn scheduler_center.main:app --reload --host $HostAddress --port $Port
  } else {
    py -3.11 -m uvicorn scheduler_center.main:app --reload --host $HostAddress --port $Port
  }
} finally {
  Pop-Location
}
