#!/bin/bash
# =============================================================================
# 平台主服务 & 调度中心 通用 entrypoint
# 功能：启动前自动执行数据库迁移
# =============================================================================
set -euo pipefail

echo "[entrypoint] Running database migrations..."
python -m alembic upgrade head || echo "[entrypoint] Alembic migration skipped (may be first run)"

echo "[entrypoint] Starting application..."
exec "$@"
