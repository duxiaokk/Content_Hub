param(
  [string]$HostAddress = "127.0.0.1",
  [int]$Port = 8002
)

& (Join-Path $PSScriptRoot "start_content_bridge.ps1") -HostAddress $HostAddress -Port $Port
