# shared-mempool

目标：在多个项目之间共享一套记忆池能力，使用 Redis 做临时层（低延迟/可设置 TTL），使用 SQLite 做持久层（断电可恢复）。

## 安装（本机工作区路径依赖）

在项目根目录：

```bash
pip install -e ..\shared_mempool
pip install -e ..\shared_mempool[redis]
```

如果当前环境无法联网安装构建依赖，也可以不安装，改为在运行前设置：

```powershell
$env:PYTHONPATH = "D:\Python\shared_mempool\src;" + $env:PYTHONPATH
```

## 环境变量

- `SHARED_MEMPOOL_NAMESPACE`：默认命名空间，默认 `default`
- `SHARED_MEMPOOL_DEFAULT_TTL_SECONDS`：默认 TTL，默认 `3600`；设为 `none` 表示不过期
- `SHARED_MEMPOOL_SERIALIZER`：`json` / `pickle`，默认 `json`
- `SHARED_MEMPOOL_REDIS_URL`：默认 `redis://localhost:6379/0`
- `SHARED_MEMPOOL_REDIS_KEY_PREFIX`：默认 `shared_mempool:`
- `SHARED_MEMPOOL_SQLITE_PATH`：SQLite 文件路径，默认 `./shared_mempool.db`

## Python API

```python
from shared_mempool import MemoryPool, MemoryPoolConfig

pool = MemoryPool(
    MemoryPoolConfig(
        namespace="comment-agent",
        redis_url="redis://localhost:6379/0",
        sqlite_path="./shared_mempool.db",
        serializer="json",
        default_ttl_seconds=3600,
    )
)

pool.set("k1", {"a": 1}, ttl_seconds=60)
value = pool.get("k1")
pool.close()
```

## CLI

```bash
shared-mempool health
shared-mempool set demo "{\"a\":1}" --ttl 60
shared-mempool get demo
shared-mempool backup --out backup.jsonl
shared-mempool restore --in backup.jsonl
```
