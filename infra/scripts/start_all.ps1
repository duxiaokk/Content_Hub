$scriptDir = $PSScriptRoot

Start-Process powershell -ArgumentList "-NoExit", "-File", (Join-Path $scriptDir "start_content_hub.ps1")
Start-Process powershell -ArgumentList "-NoExit", "-File", (Join-Path $scriptDir "start_comment_agent.ps1")
Start-Process powershell -ArgumentList "-NoExit", "-File", (Join-Path $scriptDir "start_content_bridge.ps1")
