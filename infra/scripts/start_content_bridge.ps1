param(
  [string]$HostAddress = "127.0.0.1",
  [int]$Port = 8002
)

$projectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$appDir = Join-Path $projectRoot "apps\ado_repost"
$srcDir = Join-Path $appDir "src"
$sharedMemorySrc = Join-Path $projectRoot "libs\shared_memory\src"
$venvPython = Join-Path $appDir ".venv\Scripts\python.exe"

$env:PYTHONPATH = "$srcDir;$sharedMemorySrc;$env:PYTHONPATH"

Push-Location $appDir
try {
  if (Test-Path $venvPython) {
    & $venvPython -m uvicorn content_bridge.server:app --reload --host $HostAddress --port $Port
  } else {
    py -3.11 -m uvicorn content_bridge.server:app --reload --host $HostAddress --port $Port
  }
} finally {
  Pop-Location
}
