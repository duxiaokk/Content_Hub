# =============================================================================
# 平台主服务 Dockerfile (Platform Main Service)
# =============================================================================
# 构建:  docker build -t personal-blog:latest .
# 运行:  docker run -p 8000:8000 --env-file .env personal-blog:latest
# =============================================================================

FROM python:3.13-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# 安装系统依赖（psycopg2 编译需要 gcc + libpq-dev）
RUN apt-get update -qq \
    && apt-get install -y -qq --no-install-recommends \
        curl ca-certificates \
        gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 分层安装 Python 依赖
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

# 创建非 root 用户
RUN groupadd -r appuser && useradd -r -g appuser -s /bin/false appuser

WORKDIR /app

# 从 builder 复制已安装的 Python 包
COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# 复制应用代码
COPY --chown=appuser:appuser . .

# 创建运行时目录
RUN mkdir -p /app/data /app/logs /app/content/agent_drafts /app/image \
    && chown -R appuser:appuser /app

USER appuser

# 数据库迁移
COPY --chown=appuser:appuser docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f -s http://localhost:8000/ || exit 1

ENTRYPOINT ["/entrypoint.sh"]
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
