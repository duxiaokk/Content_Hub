# PostgreSQL 参数调优与迁移压测

> P2 数据库迁移升级 — 生产环境 PostgreSQL 配置建议与迁移压测方案。

---

## 1. PostgreSQL 参数调优

### 1.1 连接参数 (docker-compose.yml 环境变量)

```yaml
postgres:
  environment:
    # 最大连接数
    POSTGRES_MAX_CONNECTIONS: "100"
    # 共享缓冲区 (默认 128MB → 建议 25% 系统内存)
    POSTGRES_SHARED_BUFFERS: "256MB"
    # 有效缓存大小 (建议 50-75% 系统内存)
    POSTGRES_EFFECTIVE_CACHE_SIZE: "768MB"
    # 维护工作内存 (VACUUM/REINDEX 等)
    POSTGRES_MAINTENANCE_WORK_MEM: "64MB"
    # WAL 缓冲区
    POSTGRES_WAL_BUFFERS: "16MB"
    # 每个操作的工作内存
    POSTGRES_WORK_MEM: "4MB"
    # 随机页成本 (SSD: 1.0-1.1, HDD: 4.0)
    POSTGRES_RANDOM_PAGE_COST: "1.1"
    # 检查点间隔
    POSTGRES_CHECKPOINT_TIMEOUT: "15min"
    POSTGRES_MAX_WAL_SIZE: "2GB"
    POSTGRES_MIN_WAL_SIZE: "80MB"
```

### 1.2 SQLAlchemy 连接池调优

```python
# database.py — 生产环境推荐值
engine = create_engine(
    settings.resolved_database_url,
    pool_size=20,           # 核心连接数 (2 * CPU + 1)
    max_overflow=40,        # 峰值溢出连接数
    pool_timeout=30,        # 等待连接超时 (秒)
    pool_recycle=1800,      # 连接回收时间 (秒，小于 PG idle timeout)
    pool_pre_ping=True,     # 使用前检查连接有效性
    echo_pool=False,        # 生产环境关闭连接池日志
)
```

### 1.3 索引策略建议

| 表 | 当前索引 | 建议增加 | 原因 |
|----|---------|----------|------|
| `posts` | tech_tag, deleted_at, deleted_by, module_id | `(published, created_at)` | 首页列表查询 |
| `posts` | — | `(created_at DESC)` | 按时间排序 |
| `comments` | (article_id, created_at) 等 | — | 已有复合索引，足够 |
| `agent_drafts` | status, created_at 等 | `(status, created_at)` 复合 | 审核列表查询 |
| `scheduler_tasks` | status, next_run_at 等 | `(status, next_run_at)` 复合 | Dispatcher 轮询 |

```sql
-- 创建推荐索引
CREATE INDEX CONCURRENTLY idx_posts_published_created ON posts(published, created_at DESC);
CREATE INDEX CONCURRENTLY idx_tasks_status_next_run ON scheduler_tasks(status, next_run_at)
    WHERE status = 'PENDING';
```

### 1.4 VACUUM 策略

```sql
-- 启用 autovacuum 调优 (postgresql.conf)
ALTER SYSTEM SET autovacuum_vacuum_scale_factor = 0.05;   -- 默认 0.2 → 5%
ALTER SYSTEM SET autovacuum_analyze_scale_factor = 0.02;  -- 默认 0.1 → 2%
ALTER SYSTEM SET autovacuum_vacuum_cost_limit = 2000;     -- 默认 200

-- 对大表单独配置
ALTER TABLE event_logs SET (autovacuum_vacuum_scale_factor = 0.02);
ALTER TABLE scheduler_task_events SET (autovacuum_vacuum_scale_factor = 0.02);
```

---

## 2. 迁移压测方案

### 2.1 压测目标

| 指标 | 目标值 | 说明 |
|------|--------|------|
| 迁移吞吐量 | > 1000 行/秒 | SQLite → PG 数据复制速度 |
| API 延迟 (P50) | < 50ms | 迁移后正常负载下的响应时间 |
| API 延迟 (P99) | < 200ms | 迁移后正常负载下的响应时间 |
| 错误率 | < 0.1% | 迁移过程中/后的请求错误率 |
| 连接池等待 | < 1s | pool_timeout 内获取连接 |

### 2.2 压测场景

#### 场景 A: 数据迁移吞吐量

```bash
# 生成测试数据 (SQLite)
python -c "
import sqlite3, random, datetime, string
conn = sqlite3.connect('blog.db')
conn.execute('''CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT, title VARCHAR(255),
    content TEXT, published BOOLEAN DEFAULT 1, created_at DATETIME)''')
for i in range(100000):
    title = ''.join(random.choices(string.ascii_letters, k=20))
    content = ''.join(random.choices(string.ascii_letters, k=500))
    conn.execute('INSERT INTO posts(title, content) VALUES(?,?)', (title, content))
conn.commit()
conn.close()
print('Inserted 100,000 test rows')
"

# 执行迁移并计时
time python scripts/db_migrate_sqlite_to_pg.py
```

#### 场景 B: API 并发压测（迁移后）

```bash
# 使用 wrk / hey 压测平台 API
# 首页列表
wrk -t4 -c50 -d30s http://localhost:8000/
# 文章详情
wrk -t4 -c50 -d30s http://localhost:8000/api/v1/posts/1
# AI 接口 (Mock LLM)
wrk -t4 -c10 -d30s -s post.lua http://localhost:8000/ai/outline

# 或使用 Python 压测
python scheduler_center/scripts/load_test.py
```

#### 场景 C: 数据库连接池压力

```bash
# 模拟高并发连接
python -c "
import concurrent.futures, time
from database import SessionLocal
from models import Post

def query():
    db = SessionLocal()
    try:
        db.query(Post).limit(10).all()
    finally:
        db.close()

start = time.time()
with concurrent.futures.ThreadPoolExecutor(max_workers=50) as pool:
    list(pool.map(lambda _: query(), range(1000)))
print(f'1000 queries in {time.time()-start:.2f}s')
"
```

### 2.3 压测结果记录模板

```csv
场景, 并发数, 请求数, P50(ms), P99(ms), 错误数, 错误率, 备注
A-migrate, 1, 100000行, -, -, 0, 0%, 吞吐 1200行/s
B-list, 50, 10000, 35, 120, 0, 0%, -
B-detail, 50, 10000, 28, 95, 0, 0%, -
B-ai, 10, 500, 150, 400, 2, 0.4%, LLM timeout
C-pool, 50, 1000, 12, 45, 0, 0%, -
```

---

## 3. 监控指标

### 3.1 PostgreSQL 关键监控

```sql
-- 活跃连接数
SELECT count(*) FROM pg_stat_activity WHERE datname = 'blog_db';

-- 等待中的查询
SELECT pid, wait_event_type, wait_event, query
FROM pg_stat_activity WHERE wait_event IS NOT NULL AND datname = 'blog_db';

-- 表大小
SELECT relname, pg_size_pretty(pg_total_relation_size(relid)) AS total_size
FROM pg_stat_user_tables ORDER BY pg_total_relation_size(relid) DESC;

-- 缓存命中率 (应 > 99%)
SELECT sum(heap_blks_hit) / nullif(sum(heap_blks_hit + heap_blks_read), 0) * 100 AS cache_hit_ratio
FROM pg_statio_user_tables;

-- 慢查询 (需要先启用 pg_stat_statements)
SELECT query, mean_exec_time, calls
FROM pg_stat_statements ORDER BY mean_exec_time DESC LIMIT 10;
```

### 3.2 应用层监控

- 在 `check_db_health()` 中加入连接池状态检查
- 在 `/health` 端点返回数据库状态
- 在 `scheduler_client.py` 中加入调用耗时 histogram

---

## 4. 事务策略建议

| 场景 | 隔离级别 | 原因 |
|------|----------|------|
| 文章列表查询 | READ COMMITTED (默认) | 无需事务一致性 |
| 点赞操作 | READ COMMITTED + 重试 | 乐观并发，冲突时重试 |
| 评论创建 | READ COMMITTED | 无跨表一致性要求 |
| Agent 草稿审核 | READ COMMITTED | 调度中心保证幂等 |
| 数据迁移 | READ COMMITTED + 批量提交 | 每 1000 行提交一次 |
