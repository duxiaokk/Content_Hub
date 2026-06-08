param(
    [string]$TaskName = "PersonalBlogWeeklyCleanup",
    [ValidateSet("Scan", "Clean")]
    [string]$Mode = "Scan",
    [string]$PythonExe = "python",
    [string]$DayOfWeek = "Sunday",
    [string]$StartTime = "03:30"
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$ScriptPath = Join-Path $PSScriptRoot "cleanup_workspace.py"
$WhitelistPath = Join-Path $ProjectRoot "configs\cleanup_whitelist.json"
$BackupDir = ".tmp/cleanup_backups"
$ReportDir = ".tmp/cleanup_reports"

if (-not (Test-Path $ScriptPath)) {
    throw "Cleanup script not found: $ScriptPath"
}

$commandMode = $Mode.ToLower()
$arguments = @(
    $ScriptPath,
    "--root", $ProjectRoot,
    "--whitelist", $WhitelistPath,
    "--backup-dir", $BackupDir,
    "--report-dir", $ReportDir,
    $commandMode
)

if ($commandMode -eq "clean") {
    $arguments += "--yes"
}

$action = New-ScheduledTaskAction -Execute $PythonExe -Argument ($arguments -join " ")
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $DayOfWeek -At $StartTime
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Weekly scan or cleanup for Personal Blog temporary files" `
    -Force | Out-Null

Write-Host "Scheduled task registered: $TaskName"
Write-Host "Mode: $Mode"
Write-Host "Schedule: every $DayOfWeek at $StartTime"
