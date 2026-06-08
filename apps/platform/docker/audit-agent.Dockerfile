# =============================================================================
# Audit Agent Dockerfile
# =============================================================================
# 自包含构建，不依赖预构建基础镜像。
# docker-compose 中自动构建。

FROM python:3.13-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update -qq \
    && apt-get install -y -qq --no-install-recommends \
        curl ca-certificates gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

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
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -r appuser && useradd -r -g appuser -s /bin/false appuser

WORKDIR /app

COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# 复制 Agent 所需代码
COPY --chown=appuser:appuser core/ ./core/
COPY --chown=appuser:appuser services/ ./services/
COPY --chown=appuser:appuser audit_agent.py ./audit_agent.py
COPY --chown=appuser:appuser docker/agent_entrypoint.sh /agent_entrypoint.sh
RUN chmod +x /agent_entrypoint.sh

USER appuser

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f -s http://localhost:8000/health || exit 1

ENTRYPOINT ["/agent_entrypoint.sh"]
CMD ["python", "-m", "uvicorn", "audit_agent:app", "--host", "0.0.0.0", "--port", "8000"]
