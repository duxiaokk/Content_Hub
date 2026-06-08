# SQLite → PostgreSQL 兼容性盘点

> P2 数据库迁移升级 — 逐表逐列分析差异，明确迁移改造点。

---

## 1. 结构概览

| 数据库 | 表数 | 索引数 | ORM 文件 | 迁移状态 |
|--------|------|--------|----------|----------|
| 平台主库 (blog.db) | 7 | 20+ | `models.py` | Alembic (混乱) |
| 调度中心 (scheduler.db) | 5 | 25+ | `scheduler_center/models.py` | SQLAlchemy create_all |

---

## 2. 平台主库逐表分析

### 2.1 `posts`

| 列 | SQLite 实际类型 | PG 目标类型 | 差异 |
|----|----------------|-------------|------|
| `id` | INTEGER PK | `SERIAL PK` | AUTOINCREMENT 语义 |
| `published` | INTEGER(0/1) | `BOOLEAN` | **需转换** |
| `created_at` | DATETIME (naive) | `TIMESTAMPTZ` | **需转换时区** |
| `deleted_at` | DATETIME (naive) | `TIMESTAMPTZ` | **需转换时区** |
| 其余列 | VARCHAR/TEXT/INTEGER | 同 | 兼容 |

### 2.2 `users`, `comments`, `post_likes`, `comment_likes`, `event_logs`

关键差异同上：`published`→BOOLEAN, `DateTime`→TIMESTAMPTZ。其余列兼容。

### 2.3 `agent_drafts`（当前版本）

| 列 | 差异 |
|----|------|
| `source_link` VARCHAR(1024) | PG 支持，兼容 |
| 所有 DateTime 列 | **需转换时区** |

---

## 3. 调度中心逐表分析

### 关键差异

| 项目 | SQLite | PostgreSQL | 改造 |
|------|--------|------------|------|
| `cancel_requested` 等 | INTEGER (0/1) | `BOOLEAN` | 建议改为 Boolean |
| `DateTime` `_utcnow()` | naive datetime | `TIMESTAMPTZ` | `_utcnow()` 返回 aware |
| `Float` | REAL | `DOUBLE PRECISION` | 兼容 |

---

## 4. 兼容性差异汇总

### 4.1 类型映射风险

| SQLite 行为 | PG 行为 | 迁移要点 |
|------------|---------|----------|
| INTEGER 存 Boolean | 原生 BOOLEAN | `published` 等列需 CAST |
| DATETIME 无时区 | TIMESTAMPTZ | 迁移时附加 `+00:00` |
| AUTOINCREMENT 隐式 | SERIAL / IDENTITY | SQLAlchemy 自动处理 |
| String 无长度限制 | String 需显式长度 | models.py 已声明长度 |
| UNIQUE nullable | NULL≠NULL（PG 多 NULL 允许） | 兼容 |

### 4.2 SQLite 专用代码（需移除/适配）

| 位置 | 代码 | 处理 |
|------|------|------|
| `add_platform_fields.py` | `PRAGMA table_info(posts)` | 废弃此脚本，合并到 Alembic |
| `scheduler_center/database.py` | `check_same_thread=False` | 仅 SQLite 分支生效，无需改动 |
| `scheduler_center/database.py` | `PRAGMA journal_mode=WAL` | 仅 SQLite 分支生效，无需改动 |
| `database.py` L24-25 | `check_same_thread=False` | 仅 SQLite 分支生效，无需改动 |

---

## 5. 迁移链现状与清理

### 当前迁移链

```
0001_initial        (基础表: posts, users, comments...)
  ↓
32c1f746183e        (创建旧版 agent_tasks + agent_drafts)
  ↓
09ae83bb82ab        (空操作 ← 无意义)
  ↓
e1f0d2a7c9b8        (删除 agent_tasks + agent_drafts)
  ↓
7b6d2d1f4f10        (重新创建新版 agent_drafts)
```

### 清理方案

1. `09ae83bb82ab` 是空操作，保留不影响
2. `e1f0d2a7c9b8` 删除了旧表，无数据损失
3. 手写脚本 `add_platform_fields.py` 需合并到 Alembic
4. 新建一个 PG 适配迁移 `0002_pg_compat`，调整 Boolean/DateTime 列

---

## 6. 迁移完整性 checklist

- [ ] posts.published: INTEGER → BOOLEAN
- [ ] 所有 DateTime 列: TIMESTAMP → TIMESTAMPTZ
- [ ] posts.rating: 加 CHECK (rating BETWEEN 1 AND 5)
- [ ] scheduler: cancel_requested / retryable / last_health_ok → BOOLEAN
- [ ] 移除 `add_platform_fields.py` 依赖
- [ ] 调度中心 models.py 的 `_utcnow()` 改为 aware datetime
