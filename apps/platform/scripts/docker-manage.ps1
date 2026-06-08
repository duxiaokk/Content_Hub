<#
.SYNOPSIS
    Ado_Jk Platform Docker 一键管理脚本
.DESCRIPTION
    管理 docker-compose 服务的启动/停止/重启/状态/日志/清理
.PARAMETER Action
    操作: start, stop, restart, status, logs, clean, build, rebuild, health
.PARAMETER Service
    可选: 指定服务名 (e.g. platform, scheduler-api, planner-agent)
.PARAMETER Profile
    可选: Docker Compose profile (e.g. ingest)
.PARAMETER Follow
    是否跟踪日志输出 (仅 logs 操作)
.EXAMPLE
    .\docker-manage.ps1 start
    .\docker-manage.ps1 status
    .\docker-manage.ps1 logs -Service platform -Follow
    .\docker-manage.ps1 clean
#>
param(
    [Parameter(Position = 0)]
    [ValidateSet("start", "stop", "restart", "status", "logs", "clean", "build", "rebuild", "health")]
    [string]$Action = "start",

    [Parameter()]
    [string]$Service = "",

    [Parameter()]
    [string]$Profile = "",

    [Parameter()]
    [switch]$Follow
)

$ErrorActionPreference = "Stop"
$ComposeDir = Split-Path -Parent $PSScriptRoot
$ComposeFile = Join-Path $ComposeDir "docker-compose.yml"
$EnvFile = Join-Path $ComposeDir ".env"

# ANSI Colors
function Write-Color { param([string]$Color, [string]$Text) Write-Host $Text -ForegroundColor $Color }
function Write-Success { param([string]$Text) Write-Color Green "[OK] $Text" }
function Write-ErrorMsg { param([string]$Text) Write-Color Red "[FAIL] $Text" }
function Write-Warn { param([string]$Text) Write-Color Yellow "[WARN] $Text" }
function Write-Info { param([string]$Text) Write-Color Cyan "[INFO] $Text" }
function Write-Banner { param([string]$Text)
    Write-Host ""
    Write-Host "=" * 60 -ForegroundColor Cyan
    Write-Host "  $Text" -ForegroundColor Cyan
    Write-Host "=" * 60 -ForegroundColor Cyan
    Write-Host ""
}

# 构建 docker compose 命令参数
function Get-ComposeArgs {
    $args = @("compose")
    if ($ComposeFile) { $args += "-f"; $args += $ComposeFile }
    if ($EnvFile -and (Test-Path $EnvFile)) { $args += "--env-file"; $args += $EnvFile }
    if ($Profile) { $args += "--profile"; $args += $Profile }
    return $args
}

# 检查 Docker 是否可用
function Test-DockerAvailable {
    try {
        $null = docker --version 2>&1
        return $true
    } catch {
        return $false
    }
}

# 等待所有服务健康
function Wait-Healthy {
    param([int]$TimeoutSeconds = 120, [int]$IntervalSeconds = 5)
    
    Write-Info "等待所有服务健康检查通过 (最多 ${TimeoutSeconds}s)..."
    $elapsed = 0
    $allHealthy = $false
    
    while ($elapsed -lt $TimeoutSeconds) {
        $composeArgs = Get-ComposeArgs
        $ps_output = & docker $composeArgs ps --format json 2>&1
        
        if ($LASTEXITCODE -ne 0) {
            Write-Warn "docker compose ps 失败，继续等待..."
            Start-Sleep -Seconds $IntervalSeconds
            $elapsed += $IntervalSeconds
            continue
        }
        
        $unhealthy = @()
        $healthy = @()
        $allHealthy = $true
        
        foreach ($line in $ps_output) {
            try {
                $svc = $line | ConvertFrom-Json
                $svcName = $svc.Name
                $svcState = $svc.State
                $svcHealth = $svc.Health
                
                if ($svcHealth -and $svcHealth -ne "healthy" -and $svcState -eq "running") {
                    $allHealthy = $false
                    $unhealthy += "$svcName ($svcHealth)"
                }
                if ($svcHealth -eq "healthy") {
                    $healthy += $svcName
                }
            } catch { }
        }
        
        if ($allHealthy -and $healthy.Count -gt 0) {
            Write-Success "所有服务健康: $($healthy -join ', ')"
            return $true
        }
        
        if ($unhealthy.Count -gt 0) {
            Write-Info "等待中... 未就绪: $($unhealthy -join ', ') (${elapsed}s/${TimeoutSeconds}s)"
        }
        
        Start-Sleep -Seconds $IntervalSeconds
        $elapsed += $IntervalSeconds
    }
    
    Write-Warn "超时: 等待 ${TimeoutSeconds}s 后仍有服务未就绪"
    return $false
}

# 显示服务状态
function Show-Status {
    $composeArgs = Get-ComposeArgs
    Write-Banner "服务状态"
    
    & docker $composeArgs ps --format "table {{.Name}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}" 2>&1
    
    Write-Host ""
    Write-Info "健康检查摘要:"
    $ps_output = & docker $composeArgs ps --format json 2>&1
    foreach ($line in $ps_output) {
        try {
            $svc = $line | ConvertFrom-Json
            $healthIcon = switch ($svc.Health) {
                "healthy" { "[✓]" }
                "unhealthy" { "[✗]" }
                "starting" { "[~]" }
                default { "[?]" }
            }
            Write-Host "  $healthIcon $($svc.Name.PadRight(30)) $($svc.State.PadRight(12)) health=$($svc.Health)"
        } catch { }
    }
}

# 显示日志
function Show-Logs {
    $composeArgs = Get-ComposeArgs
    $logArgs = $composeArgs + @("logs")
    
    if ($Service) {
        $logArgs += $Service
    }
    if ($Follow) {
        $logArgs += "-f"
    }
    $logArgs += "--tail=50"
    
    & docker $logArgs 2>&1
}

# 构建镜像
function Build-Images {
    $action = if ($Action -eq "rebuild") { "重新构建" } else { "构建" }
    Write-Banner "$action Docker 镜像"
    
    $composeArgs = Get-ComposeArgs
    $buildArgs = $composeArgs + @("build", "--no-cache")
    
    if ($Service) {
        $buildArgs += $Service
    }
    
    & docker $buildArgs 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-ErrorMsg "镜像构建失败"
        exit 1
    }
    Write-Success "镜像构建完成"
}

# 启动服务
function Start-Services {
    Write-Banner "启动 Ado_Jk Platform 服务"
    
    $composeArgs = Get-ComposeArgs
    $upArgs = $composeArgs + @("up", "-d", "--remove-orphans")
    
    if ($Service) {
        $upArgs += $Service
    }
    
    # 确保 .env 存在
    if (-not (Test-Path $EnvFile)) {
        $envExample = Join-Path $ComposeDir ".env.example"
        if (Test-Path $envExample) {
            Copy-Item $envExample $EnvFile
            Write-Warn ".env 不存在，已从 .env.example 复制。请编辑 .env 设置密钥！"
        } else {
            Write-Warn ".env 和 .env.example 均不存在"
        }
    }
    
    Write-Info "执行: docker $($upArgs -join ' ')"
    & docker $upArgs 2>&1
    
    if ($LASTEXITCODE -ne 0) {
        Write-ErrorMsg "服务启动失败，请检查日志"
        exit 1
    }
    
    Write-Success "服务已启动"
    
    # 等待健康检查
    if (-not $Service) {
        Wait-Healthy
    }
}

# 停止服务
function Stop-Services {
    Write-Banner "停止 Ado_Jk Platform 服务"
    
    $composeArgs = Get-ComposeArgs
    $downArgs = $composeArgs + @("down")
    
    if ($Service) {
        $downArgs = $composeArgs + @("stop", $Service)
    }
    
    & docker $downArgs 2>&1
    Write-Success "服务已停止"
}

# 清理（含数据卷）
function Clean-All {
    Write-Banner "清理 Ado_Jk Platform (含数据卷)"
    Write-Warn "此操作将删除所有容器、网络和数据卷！数据将丢失！"
    
    $confirm = Read-Host "输入 'YES' 确认清理"
    if ($confirm -ne "YES") {
        Write-Info "已取消"
        return
    }
    
    $composeArgs = Get-ComposeArgs
    & docker $composeArgs down -v --remove-orphans 2>&1
    
    # 清理 dangling volumes
    & docker volume prune -f 2>&1
    
    Write-Success "清理完成"
}

# 健康检查详细报告
function Show-HealthReport {
    Write-Banner "服务健康检查详细报告"
    
    $composeArgs = Get-ComposeArgs
    $services = @(
        @{name="platform"; url="http://localhost:8000"; port=8000},
        @{name="scheduler-api"; url="http://localhost:8010/health"; port=8010},
        @{name="grafana"; url="http://localhost:3000/api/health"; port=3000},
        @{name="prometheus"; url="http://localhost:9090/-/healthy"; port=9090},
        @{name="jaeger"; url="http://localhost:16686/api/services"; port=16686},
        @{name="loki"; url="http://localhost:3100/ready"; port=3100}
    )
    
    foreach ($svc in $services) {
        try {
            $result = Invoke-WebRequest -Uri $svc.url -TimeoutSec 5 -UseBasicParsing
            if ($result.StatusCode -eq 200) {
                Write-Success "$($svc.name) ($($svc.port)): OK"
            } else {
                Write-Warn "$($svc.name) ($($svc.port)): HTTP $($result.StatusCode)"
            }
        } catch {
            Write-ErrorMsg "$($svc.name) ($($svc.port)): 不可达 - $_"
        }
    }
    
    # Agent 检查 (通过 scheduler API)
    try {
        $agents = Invoke-RestMethod -Uri "http://localhost:8010/api/v1/agents" -TimeoutSec 5
        $agentCount = $agents.Count
        Write-Success "已注册 Agent 数量: $agentCount"
    } catch {
        Write-Warn "无法获取 Agent 列表"
    }
}

# =========================================================================
# Main
# =========================================================================

if (-not (Test-DockerAvailable)) {
    Write-ErrorMsg "Docker 未安装或未运行。请先安装 Docker Desktop。"
    exit 1
}

Set-Location $ComposeDir

switch ($Action) {
    "start" {
        Start-Services
        Show-Status
    }
    "stop" {
        Stop-Services
    }
    "restart" {
        Stop-Services
        Start-Sleep -Seconds 3
        Start-Services
        Show-Status
    }
    "status" {
        Show-Status
        Show-HealthReport
    }
    "logs" {
        Show-Logs
    }
    "clean" {
        Clean-All
    }
    "build" {
        Build-Images
        Show-Status
    }
    "rebuild" {
        Stop-Services
        Build-Images
        Start-Services
        Show-Status
    }
    "health" {
        Show-HealthReport
    }
    default {
        Write-ErrorMsg "未知操作: $Action"
    }
}
