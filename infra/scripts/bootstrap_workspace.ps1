param(
  [string]$PythonVersion = "3.11",
  [switch]$IncludeContentHub
)

$projectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)

function Initialize-AppVenv {
  param(
    [string]$AppDir,
    [string]$RequirementsPath
  )

  $venvDir = Join-Path $AppDir ".venv"
  $venvPython = Join-Path $venvDir "Scripts\python.exe"

  if (-not (Test-Path $venvPython)) {
    py -$PythonVersion -m venv $venvDir
  }

  & $venvPython -m ensurepip --upgrade

  if (Test-Path $RequirementsPath) {
    & $venvPython -m pip install -r $RequirementsPath
  }
}

Initialize-AppVenv `
  -AppDir (Join-Path $projectRoot "apps\comment_agent") `
  -RequirementsPath (Join-Path $projectRoot "apps\comment_agent\requirements.txt")

Initialize-AppVenv `
  -AppDir (Join-Path $projectRoot "apps\ado_repost") `
  -RequirementsPath (Join-Path $projectRoot "apps\ado_repost\requirements.txt")

if ($IncludeContentHub) {
  Initialize-AppVenv `
    -AppDir (Join-Path $projectRoot "apps\platform") `
    -RequirementsPath (Join-Path $projectRoot "apps\platform\requirements.txt")
}
