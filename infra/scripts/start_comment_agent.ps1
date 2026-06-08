param(
  [string]$HostAddress = "127.0.0.1",
  [int]$Port = 8001
)

$projectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$appDir = Join-Path $projectRoot "apps\comment_agent"
$sharedMemorySrc = Join-Path $projectRoot "libs\shared_memory\src"
$venvPython = Join-Path $appDir ".venv\Scripts\python.exe"

$env:PYTHONPATH = "$sharedMemorySrc;$env:PYTHONPATH"

Push-Location $appDir
try {
  if (Test-Path $venvPython) {
    & $venvPython -m uvicorn app.main:app --reload --host $HostAddress --port $Port
  } else {
    py -3.11 -m uvicorn app.main:app --reload --host $HostAddress --port $Port
  }
} finally {
  Pop-Location
}
