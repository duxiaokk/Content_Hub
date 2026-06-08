# 数据库迁移回滚与恢复文档

> P2 数据库迁移升级 — 失败回滚方案与应急恢复步骤。

---

## 1. 回滚策略

### 1.1 迁移前检查清单

在开始迁移前必须确认：

- [ ] 已执行全量备份 `python scripts/db_backup_sqlite.py --compress`
- [ ] 备份文件已校验（文件大小 > 0，manifest.json 完整）
- [ ] PostgreSQL 目标库已创建且可连接
- [ ] 目标 PostgreSQL 库为空（或确认表不冲突）
- [ ] 通知团队停止写入操作（进入只读维护模式）

### 1.2 回滚层级

| 阶段 | 回滚方式 | 数据损失 |
|------|----------|----------|
| Alembic 迁移失败 | `alembic downgrade -1` | 无（表结构回滚） |
| 数据迁移失败 | 从备份恢复 SQLite + 清理 PG | 无（源数据完整） |
| 迁移后数据校验失败 | `psql DROP SCHEMA public CASCADE` + 重新迁移 | 无 |
| 迁移后运行中发现异常 | 切回 SQLite 数据源 | 迁移后的新增数据丢失 |

---

## 2. 回滚操作步骤

### 2.1 Alembic 迁移回滚

```bash
# 回滚最后一个迁移
alembic downgrade -1

# 回滚到指定版本
alembic downgrade 7b6d2d1f4f10

# 查看当前版本
alembic current
```

### 2.2 数据迁移后回滚

如果数据已经复制到 PostgreSQL 但需要退回 SQLite：

```bash
# 1. 停止应用
docker compose stop platform scheduler-api scheduler-dispatcher

# 2. 修改 .env 切回 SQLite
DATABASE_URL=sqlite:///./blog.db
SCHEDULER_DATABASE_URL=sqlite:///./scheduler.db

# 3. 重启应用
docker compose start platform scheduler-api scheduler-dispatcher

# 4. 清理 PostgreSQL（可选）
psql -h localhost -U blog_user -d blog_db -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
```

### 2.3 从备份完全恢复

```bash
# 1. 停止所有服务
docker compose down

# 2. 清理损坏的数据库文件
rm blog.db scheduler.db
rm scheduler_center/scheduler.db

# 3. 从备份恢复
# 压缩备份:
gunzip -c backups/blog_20260606_120000.db.gz > blog.db
gunzip -c backups/scheduler_20260606_120000.db.gz > scheduler.db
# 未压缩:
cp backups/blog_20260606_120000.db ./blog.db
cp backups/scheduler_20260606_120000.db ./scheduler.db

# 4. 恢复文件目录
tar -xzf backups/agent_drafts_20260606_120000.tar.gz
tar -xzf backups/image_20260606_120000.tar.gz

# 5. 重启服务
docker compose up -d
```

---

## 3. 应急恢复

### 3.1 PostgreSQL 连接池耗尽

```sql
-- 查看活跃连接
SELECT pid, state, query FROM pg_stat_activity WHERE datname = 'blog_db';

-- 终止空闲连接
SELECT pg_terminate_backend(pid) FROM pg_stat_activity
WHERE datname = 'blog_db' AND state = 'idle' AND pid <> pg_backend_pid();
```

### 3.2 迁移中断恢复

如果 `db_migrate_sqlite_to_pg.py` 中断：

```bash
# 1. 检查已迁移的表
psql -h localhost -U blog_user -d blog_db -c "\dt"

# 2. 清理已迁移数据，从头开始
psql -h localhost -U blog_user -d blog_db -c "
  TRUNCATE event_logs, agent_drafts, comment_likes, comments,
           post_likes, posts, users CASCADE;
  TRUNCATE scheduler_task_logs, scheduler_task_events,
           scheduler_task_attempts, scheduler_tasks, scheduler_agents CASCADE;
"

# 3. 重新执行迁移
python scripts/db_migrate_sqlite_to_pg.py
```

### 3.3 迁移后数据不一致

| 症状 | 排查 | 修复 |
|------|------|------|
| 行数不一致 | `SELECT COUNT(*) FROM ...` 对比 | 重新执行迁移脚本 |
| Boolean 列显示 0/1 | `published` 列类型未转换 | 执行 `0002_pg_compat` upgrade |
| 时区错误 | `created_at` 偏移 8 小时 | 执行 `0002_pg_compat` upgrade |
| 外键约束失败 | 依赖表未迁移 | 按正确顺序（users→posts→comments）重迁 |

---

## 4. 迁移后验证 SQL

```sql
-- 1. 行数校验
SELECT 'users' AS tbl, COUNT(*) FROM users
UNION ALL SELECT 'posts', COUNT(*) FROM posts
UNION ALL SELECT 'comments', COUNT(*) FROM comments
UNION ALL SELECT 'agent_drafts', COUNT(*) FROM agent_drafts
UNION ALL SELECT 'event_logs', COUNT(*) FROM event_logs;

-- 2. Boolean 列校验
SELECT published, COUNT(*) FROM posts GROUP BY published;

-- 3. 时区校验
SELECT created_at, pg_typeof(created_at) FROM posts LIMIT 1;
-- 期望: pg_typeof = timestamp with time zone

-- 4. 索引校验
SELECT tablename, indexname FROM pg_indexes
WHERE schemaname = 'public' ORDER BY tablename, indexname;

-- 5. 约束校验
SELECT conname, contype FROM pg_constraint
WHERE conrelid = 'posts'::regclass;
```

---

## 5. 维护窗口建议

| 数据量 | 预计迁移时间 | 建议窗口 |
|--------|-------------|----------|
| < 1 万行 | < 30 秒 | 5 分钟 |
| 1-10 万行 | 1-5 分钟 | 15 分钟 |
| 10-100 万行 | 5-30 分钟 | 1 小时 |
| > 100 万行 | 考虑分批迁移 | 2 小时+ |
