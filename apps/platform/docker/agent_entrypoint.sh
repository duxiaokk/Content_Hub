#!/bin/bash
# =============================================================================
# Agent 通用 entrypoint
# 功能：等待调度中心就绪后自动注册，然后启动 Agent 服务
# =============================================================================
set -euo pipefail

SCHEDULER_URL="${SCHEDULER_CENTER_URL:-http://scheduler-api:8010}"
TOKEN="${SCHEDULER_INTERNAL_TOKEN:-local-dev-scheduler-token}"

echo "[agent-entrypoint] Waiting for Scheduler Center at ${SCHEDULER_URL}..."
for i in $(seq 1 30); do
    if curl -sf "${SCHEDULER_URL}/health" > /dev/null 2>&1; then
        echo "[agent-entrypoint] Scheduler Center is ready."
        break
    fi
    echo "[agent-entrypoint] Attempt ${i}/30 - scheduler not ready, retrying in 2s..."
    sleep 2
done

echo "[agent-entrypoint] Starting Agent..."
exec "$@"
