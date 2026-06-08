param(
  [string]$HostAddress = "127.0.0.1",
  [int]$Port = 8000
)

$projectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$appDir = Join-Path $projectRoot "apps\platform"
$venvPython = Join-Path $appDir ".venv\Scripts\python.exe"

Push-Location $appDir
try {
  if (Test-Path $venvPython) {
    & $venvPython -m uvicorn main:app --reload --host $HostAddress --port $Port
  } else {
    py -3.11 -m uvicorn main:app --reload --host $HostAddress --port $Port
  }
} finally {
  Pop-Location
}
