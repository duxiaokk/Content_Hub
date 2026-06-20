# shared_mempool 引用审计

## 1. 审计目的

本文档用于回答一个非常具体的问题：

`libs/shared_mempool` 现在到底还有没有运行时价值，还是已经只剩历史残留？

第三阶段后续是否可以清理、归档或删除这个目录，必须先基于这个审计结果判断，而不是靠感觉操作。

## 2. 审计结论

当前结论如下：

1. 运行时代码已经主要切换到 `libs/shared_memory`
2. `libs/shared_mempool` 目前更像历史包目录，而不是正式运行依赖
3. 当前残留主要集中在：
   - 历史包目录本身
   - 旧环境变量兼容
   - 默认 SQLite 文件名仍使用 `shared_mempool.db`
   - 历史 README 和配置说明

换句话说：

`shared_mempool` 现在不是“核心运行依赖”，而是“尚未清理干净的历史命名和兼容层”。

## 3. 已确认的运行时现状

### 3.1 comment_agent

在 [mempool.py](D:/Python/content_hub/apps/comment_agent/app/core/mempool.py) 中，当前实际导入的是：

- `from shared_memory import MemoryPool, MemoryPoolConfig`

这说明 `comment_agent` 的运行时共享库已经切到 `shared_memory`。

但在 [config.py](D:/Python/content_hub/apps/comment_agent/app/core/config.py) 中，仍然保留了：

- 默认 SQLite 文件名：`./shared_mempool.db`
- `MEMPOOL_*` 命名体系

这属于“命名残留”，不是“包依赖残留”。

### 3.2 content_bridge（当前代码目录 `apps/ado_repost`）

在 [mempool.py](D:/Python/content_hub/apps/ado_repost/src/ado_repost/mempool.py) 中，当前实际导入的是：

- `from shared_memory import MemoryPool, MemoryPoolConfig`

同时它还兼容读取两套环境变量：

- `SHARED_MEMORY_*`
- `SHARED_MEMPOOL_*`

并且默认 SQLite 文件名仍然是：

- `shared_mempool.db`

这说明：

1. 正式共享库入口已经是 `shared_memory`
2. `shared_mempool` 目前只剩兼容变量和文件命名痕迹

## 4. 历史目录现状

`libs/shared_mempool` 当前仍是一个完整旧包，包含：

- `src/shared_mempool/`
- `tests/`
- `pyproject.toml`
- `README.md`

并且它自己的文档仍在引导使用者：

- 单独安装 `shared_mempool`
- 通过路径或 `PYTHONPATH` 方式引入

这会继续误导新开发者，以为它仍然是正式入口。

## 5. 当前残留分类

### 5.1 可直接认定为历史残留

- `libs/shared_mempool/` 包目录
- 旧 README 中关于 `shared_mempool` 的安装说明
- 历史环境变量前缀 `SHARED_MEMPOOL_*`

### 5.2 需要单独迁移或重命名

- `shared_mempool.db` 这类默认 SQLite 文件名
- `MEMPOOL_*` / `SHARED_MEMPOOL_*` 命名兼容逻辑
- `apps/ado_repost/README.md` 中的历史共享存储说明

### 5.3 当前不建议直接删除的部分

在完全确认没有运行时依赖之前，不建议立刻删除：

- `libs/shared_mempool/tests`
- `libs/shared_mempool/src/shared_mempool`

原因不是它们还在正式使用，而是删除前最好先完成：

1. 兼容变量清单确认
2. 文件命名清理
3. 文档入口替换

## 6. 建议的清理顺序

建议后续按这个顺序推进：

1. 先统一文档入口
   - 所有工作区文档只承认 `shared_memory` 是正式共享库

2. 再统一配置命名
   - 逐步减少 `SHARED_MEMPOOL_*` 兼容读取
   - 收敛到 `SHARED_MEMORY_*` 或确定的统一前缀

3. 再统一默认文件命名
   - 把 `shared_mempool.db` 改成更贴近正式命名的文件名

4. 最后处理 `libs/shared_mempool`
   - 归档
   - 标记废弃
   - 或删除

## 7. 当前建议

基于当前审计结果，建议立即执行的不是“直接删除 `libs/shared_mempool`”，而是：

1. 继续把正式入口收敛到 `shared_memory`
2. 开始清理命名和兼容层
3. 在完成兼容层清理后，再决定是否删除旧包目录

这会比直接删目录更稳，也更符合当前仓库的真实状态。

## 8. 当前已完成的第一步收敛

当前工作区已经开始执行第一步命名收敛：

1. 默认 SQLite 文件名开始从 `shared_mempool.db` 迁移到 `shared_memory.db`
2. 新示例配置优先使用 `SHARED_MEMORY_*`
3. `content_bridge` 的示例注册名已开始替换旧的 `ado-repost`

这说明共享库治理已经从“只做说明”进入“开始改默认值”的阶段，但兼容读取暂时仍会保留。

---

## 9. 清理完成（2026-06-19）

- `libs/shared_mempool` 目录已完全删除
- `libs/shared_memory` 作为唯一共享库持续维护
- `content_bridge.mempool` 的 `sys.path.insert` 和 `try/except ModuleNotFoundError` 已移除
- 所有模块均直接使用 `from shared_memory import ...` 导入

`shared_mempool` 治理已结束。
