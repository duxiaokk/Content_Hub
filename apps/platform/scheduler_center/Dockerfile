# =============================================================================
# 调度中心 Dockerfile (Scheduler Center)
# =============================================================================
# 可作为 API 服务器、Dispatcher、Ingest Worker 三种角色运行：
#   API Server:      CMD ["python", "-m", "uvicorn", "scheduler_center.main:app", ...]
#   Dispatcher:      CMD ["python", "-m", "scheduler_center.worker"]
#   Ingest Worker:   CMD ["python", "-m", "scheduler_center.ingest_worker"]
# =============================================================================

FROM python:3.13-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update -qq \
    && apt-get install -y -qq --no-install-recommends \
        curl ca-certificates \
        gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 从项目根目录复制 requirements.txt（调度中心使用同一份依赖）
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# ---------------------------------------------------------------------------
# 运行阶段
# ---------------------------------------------------------------------------
FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update -qq \
    && apt-get install -y -qq --no-install-recommends \
        curl ca-certificates libpq5 \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd -r appuser && useradd -r -g appuser -s /bin/false appuser

WORKDIR /app

COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# 复制项目代码（调度中心需要 core/ scheduler_center/ 和根目录工具模块）
COPY --chown=appuser:appuser core/ ./core/
COPY --chown=appuser:appuser scheduler_center/ ./scheduler_center/
COPY --chown=appuser:appuser services/ ./services/
COPY --chown=appuser:appuser models.py ./models.py
COPY --chown=appuser:appuser database.py ./database.py
COPY --chown=appuser:appuser scheduler_client.py ./scheduler_client.py
COPY --chown=appuser:appuser requirements.txt ./requirements.txt

RUN mkdir -p /app/data /app/logs \
    && chown -R appuser:appuser /app

USER appuser

# 默认作为 API 服务器运行，docker-compose 中可通过 command 覆盖
EXPOSE 8010

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f -s http://localhost:8010/health || exit 1

CMD ["python", "-m", "uvicorn", "scheduler_center.main:app", "--host", "0.0.0.0", "--port", "8010"]
