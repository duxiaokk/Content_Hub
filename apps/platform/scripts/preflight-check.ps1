<#
.SYNOPSIS
    Ado_Jk Platform 部署前验证脚本
.DESCRIPTION
    检查 Docker、端口、磁盘、配置等是否就绪
#>

$ErrorActionPreference = "Continue"
$ComposeDir = Split-Path -Parent $PSScriptRoot

# ANSI Colors
function Write-OK { Write-Host "[  OK  ] $args" -ForegroundColor Green }
function Write-FAIL { Write-Host "[ FAIL ] $args" -ForegroundColor Red }
function Write-WARN { Write-Host "[ WARN ] $args" -ForegroundColor Yellow }
function Write-INFO { Write-Host "[ INFO ] $args" -ForegroundColor Cyan }

Write-Host ""
Write-Host "=" * 60 -ForegroundColor Cyan
Write-Host "  Ado_Jk Platform - 部署前环境检查" -ForegroundColor Cyan
Write-Host "=" * 60 -ForegroundColor Cyan
Write-Host ""

$allOK = $true
$warnings = 0

# 1. Docker 检查
Write-INFO "检查 Docker 环境..."
try {
    $dockerVersion = docker --version 2>&1
    if ($LASTEXITCODE -eq 0) {
        $verMatch = [regex]::Match($dockerVersion, '(\d+\.\d+\.\d+)')
        $ver = if ($verMatch.Success) { $verMatch.Groups[1].Value } else { "unknown" }
        Write-OK "Docker 版本: $ver"
    }
} catch {
    Write-FAIL "Docker 未安装或不在 PATH 中"
    $allOK = $false
}

try {
    $composeVersion = docker compose version 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-OK "Docker Compose 可用"
    }
} catch {
    Write-FAIL "Docker Compose 不可用"
    $allOK = $false
}

try {
    $info = docker info 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-OK "Docker 守护进程运行中"
    } else {
        Write-FAIL "Docker 守护进程未运行"
        $allOK = $false
    }
} catch {
    Write-FAIL "无法连接 Docker 守护进程"
    $allOK = $false
}

# 2. 磁盘空间检查
Write-INFO "检查磁盘空间..."
try {
    $disk = Get-PSDrive -Name (Split-Path $ComposeDir -Qualifier).TrimEnd(':')
    $freeGB = [math]::Round($disk.Free / 1GB, 1)
    if ($freeGB -lt 2) {
        Write-FAIL "磁盘可用空间不足: ${freeGB}GB (建议 > 2GB)"
        $allOK = $false
    } else {
        Write-OK "磁盘可用空间: ${freeGB}GB"
    }
} catch {
    Write-WARN "无法检查磁盘空间"
    $warnings++
}

# 3. 端口占用检查
Write-INFO "检查端口占用..."
$requiredPorts = @(
    @{Port=8000; Service="Platform"},
    @{Port=8010; Service="Scheduler API"},
    @{Port=8100; Service="Planner Agent"},
    @{Port=8110; Service="Data Processor Agent"},
    @{Port=8120; Service="Tool Calling Agent"},
    @{Port=8130; Service="Content Generator Agent"},
    @{Port=8140; Service="Aggregator Agent"},
    @{Port=5432; Service="PostgreSQL"},
    @{Port=6379; Service="Redis"},
    @{Port=16686; Service="Jaeger UI"},
    @{Port=9090; Service="Prometheus"},
    @{Port=3100; Service="Loki"},
    @{Port=3000; Service="Grafana"}
)

foreach ($p in $requiredPorts) {
    $listening = Get-NetTCPConnection -LocalPort $p.Port -ErrorAction SilentlyContinue | Where-Object { $_.State -eq 'Listen' }
    if ($listening) {
        $procNames = @()
        foreach ($conn in $listening) {
            try {
                $proc = Get-Process -Id $conn.OwningProcess -ErrorAction SilentlyContinue
                if ($proc) { $procNames += $proc.ProcessName }
            } catch { }
        }
        $procStr = if ($procNames) { ($procNames | Select-Object -Unique) -join ', ' } else { "unknown" }
        Write-WARN "端口 $($p.Port) ($($p.Service)) 已被占用: $procStr"
        $warnings++
    } else {
        Write-OK "端口 $($p.Port) 可用 ($($p.Service))"
    }
}

# 4. 配置文件检查
Write-INFO "检查配置文件..."
$configFiles = @(
    @{Path="docker-compose.yml"; Required=$true},
    @{Path=".env.example"; Required=$true},
    @{Path=".env"; Required=$false},
    @{Path="configs/prometheus.yml"; Required=$true},
    @{Path="configs/loki-config.yml"; Required=$true},
    @{Path="configs/promtail-config.yml"; Required=$true},
    @{Path="configs/grafana-datasources.yml"; Required=$true},
    @{Path="configs/alerting_rules.yml"; Required=$true},
    @{Path="requirements.txt"; Required=$true},
    @{Path="alembic.ini"; Required=$true},
    @{Path="Dockerfile"; Required=$true},
    @{Path="scheduler_center/Dockerfile"; Required=$true},
    @{Path="docker/agent.Dockerfile"; Required=$true},
    @{Path="docker/audit-agent.Dockerfile"; Required=$true}
)

foreach ($cf in $configFiles) {
    $fullPath = Join-Path $ComposeDir $cf.Path
    if (Test-Path $fullPath) {
        # .env 检查内容
        if ($cf.Path -eq ".env") {
            $content = Get-Content $fullPath -Raw
            if ($content -match "change-me-in-production") {
                Write-WARN "$($cf.Path) 存在但包含默认占位值，请修改密钥"
                $warnings++
            } else {
                Write-OK "$($cf.Path) 存在"
            }
        } else {
            Write-OK "$($cf.Path) 存在"
        }
    } else {
        if ($cf.Required) {
            Write-FAIL "缺少必要文件: $($cf.Path)"
            $allOK = $false
        } else {
            Write-WARN "可选文件不存在: $($cf.Path)"
            $warnings++
        }
    }
}

# 5. Docker 资源检查
Write-INFO "检查 Docker 资源限制..."
try {
    $dockerInfo = docker info --format '{{json .}}' 2>&1 | ConvertFrom-Json
    $cpus = $dockerInfo.NCPU
    $memGB = [math]::Round([double]$dockerInfo.MemTotal / 1GB, 1)
    if ($cpus -lt 4) { Write-WARN "CPU 核心数较少: $cpus (建议 >= 4)"; $warnings++ }
    else { Write-OK "CPU 核心数: $cpus" }
    if ($memGB -lt 8) { Write-WARN "内存较少: ${memGB}GB (建议 >= 8GB)"; $warnings++ }
    else { Write-OK "内存: ${memGB}GB" }
} catch {
    Write-WARN "无法获取 Docker 资源信息"
    $warnings++
}

# 6. LLM 配置检查
Write-INFO "检查 LLM 配置..."
if (Test-Path (Join-Path $ComposeDir ".env")) {
    $envContent = Get-Content (Join-Path $ComposeDir ".env") -Raw
    if ($envContent -match 'LLM_API_KEY\s*=\s*(sk-placeholder|$)') {
        Write-WARN "LLM_API_KEY 未配置 (将使用 MOCK_LLM 模式)"
        $warnings++
    } else {
        Write-OK "LLM_API_KEY 已配置"
    }
} else {
    Write-WARN ".env 不存在，无法检查 LLM 配置"
    $warnings++
}

# 7. Python 版本检查（用于本地开发）
Write-INFO "检查 Python 环境..."
try {
    $pyVersion = python --version 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-OK "Python: $pyVersion"
    }
} catch {
    Write-INFO "Python 未安装 (Docker 部署不需要)"
}

# =========================================================================
# 结果
# =========================================================================
Write-Host ""
Write-Host "=" * 60 -ForegroundColor Cyan
if ($allOK -and $warnings -eq 0) {
    Write-Host "  结论: 全部检查通过，可以部署！" -ForegroundColor Green
} elseif ($allOK) {
    Write-Host "  结论: 检查通过 ($warnings 个警告)，建议处理后再部署" -ForegroundColor Yellow
} else {
    Write-Host "  结论: 存在失败项，请修复后再部署" -ForegroundColor Red
}
Write-Host "=" * 60 -ForegroundColor Cyan
Write-Host ""

if (-not $allOK) { exit 1 }
