# shared-memory

一个最小可复用的“共享记忆池”SDK：Redis（可选）作为临时层，SQLite 作为持久层。

## 安装（本机三项目共享）

在需要使用的项目里加入本地依赖：

- `shared-memory @ file:///D:/Python/content_hub/libs/shared_memory`
- 需要 Redis 时：`shared-memory[redis] @ file:///D:/Python/content_hub/libs/shared_memory`

## 快速使用

```python
from shared_memory import SharedMemory, SharedMemoryConfig

mem = SharedMemory(
    SharedMemoryConfig(
        namespace="demo",
        sqlite_path="./shared_memory.db",
        redis_url="redis://localhost:6379/0",
        redis_key_prefix="shared_memory:",
        default_ttl_seconds=3600,
    )
)

mem.set("k1", {"a": 1}, ttl_seconds=60)
value = mem.get("k1")
mem.delete("k1")

with mem.lock("task:123", ttl_seconds=30, timeout_seconds=5):
    mem.set("task:123:state", {"status": "running"})

mem.close()
```

## 环境变量（CLI 与示例代码可用）

- `SHARED_MEMORY_NAMESPACE`
- `SHARED_MEMORY_DEFAULT_TTL_SECONDS`（`none/null/0` 表示永久）
- `SHARED_MEMORY_REDIS_URL`
- `SHARED_MEMORY_REDIS_KEY_PREFIX`
- `SHARED_MEMORY_REDIS_TIMEOUT_SECONDS`
- `SHARED_MEMORY_REDIS_CONNECT_TIMEOUT_SECONDS`
- `SHARED_MEMORY_SQLITE_PATH`
- `SHARED_MEMORY_SQLITE_TIMEOUT_SECONDS`

兼容旧变量名（如果你之前用过 `shared_mempool`）：

- `SHARED_MEMPOOL_*`

## 备份与恢复

```bash
shared-memory backup --out backup.jsonl
shared-memory restore --in backup.jsonl
```

也可以指定 namespace：

```bash
shared-memory backup --namespace ado-repost --out ado-repost.jsonl
shared-memory restore --namespace ado-repost --in ado-repost.jsonl
```
