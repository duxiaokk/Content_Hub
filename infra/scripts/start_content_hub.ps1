param(
  [string]$HostAddress = "127.0.0.1",
  [int]$Port = 8000
)

$projectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$appDir = Join-Path $projectRoot "apps\platform"
# 优先使用项目根目录的 .venv（已安装所有依赖）
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
  $venvPython = Join-Path $appDir ".venv\Scripts\python.exe"
}

$env:PYTHONPATH = $projectRoot
if (-not $env:SECRET_KEY) {
  $env:SECRET_KEY = "local-dev-secret-key"
}

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
