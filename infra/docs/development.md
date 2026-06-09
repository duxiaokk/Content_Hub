# Content Hub 本地开发指南

## 1. 适用范围

本文档说明 Content Hub 工作区的本地开发方式，重点回答以下问题：

- 本地需要准备什么环境
- 第一次进入仓库后先做什么
- 三个服务分别怎么启动
- 启动失败时先检查什么

当前内容基于仓库中的现有脚本和目录结构整理，适用于当前迁移阶段。

## 2. 环境要求

本地开发目前默认基于以下环境：

- Windows
- PowerShell
- Python 3.11

如果环境与上述条件不一致，现有脚本可能无法直接复用。

## 3. 工作区结构理解

本地开发时，主要会接触以下目录：

```text
apps/
  platform/
  comment_agent/
  ado_repost/        # 当前承载 content_bridge 代码与兼容入口
libs/
  shared_memory/
infra/
  scripts/
  docs/
```

开发时可以先这样理解：

- `apps/` 放具体服务
- `libs/` 放共享代码
- `infra/scripts/` 放工作区级启动脚本
- `infra/docs/` 放工作区级说明文档

## 4. 第一次进入仓库要做什么

第一次在本地使用这个工作区时，先初始化虚拟环境。

执行：

```powershell
.\infra\scripts\bootstrap_workspace.ps1
```

如果还需要同时初始化 `platform` 的虚拟环境，执行：

```powershell
.\infra\scripts\bootstrap_workspace.ps1 -IncludeContentHub
```

### 4.1 这条脚本实际做了什么

根据当前脚本实现，这个初始化脚本会：

1. 为 `apps/comment_agent` 创建 `.venv`
2. 为 `apps/ado_repost` 创建 `.venv`
3. 按 `requirements.txt` 安装依赖
4. 为需要共享库的服务执行 `pip install -e libs/shared_memory`
5. 在传入 `-IncludeContentHub` 时，为 `apps/platform` 也执行同样流程，并安装共享库

这意味着：

- `comment_agent` 和 `content_bridge`（当前目录 `apps/ado_repost`）是默认初始化对象
- `platform` 当前需要显式带参数才会一起初始化
- 共享库安装责任已经收敛到工作区初始化脚本，而不是继续写死在某个服务的依赖文件里

### 4.2 当前推荐初始化规则

当前建议统一按下面的方式初始化：

1. 先运行 `.\infra\scripts\bootstrap_workspace.ps1`
2. 如果需要本地启动 `platform`，使用 `-IncludeContentHub`
3. 不要再手工把 `shared-memory @ file:///...` 这类绝对路径写回服务依赖文件

如果需要单独重建某个服务的虚拟环境，也应优先复用这条工作区脚本，而不是在子目录里自行发明新的安装步骤。

## 5. 本地启动方式

### 5.1 分别启动

当前推荐的分别启动方式如下：

```powershell
.\infra\scripts\start_content_hub.ps1
.\infra\scripts\start_comment_agent.ps1
.\infra\scripts\start_content_bridge.ps1
```

当前脚本默认端口为：

- `platform`: `8000`
- `comment_agent`: `8001`
- `content_bridge`: `8002`

### 5.2 一键启动

如果需要同时打开三个服务，可执行：

```powershell
.\infra\scripts\start_all.ps1
```

这个脚本当前的行为是：

- 分别打开 3 个新的 PowerShell 窗口
- 每个窗口运行一个服务启动脚本

它适合本地联调，不适合作为正式部署方式。

## 6. 各服务当前启动规则

### 6.1 platform

启动脚本：

```powershell
.\infra\scripts\start_content_hub.ps1
```

当前行为：

- 工作目录切换到 `apps/platform`
- 优先使用 `apps/platform/.venv/Scripts/python.exe`
- 如果本地虚拟环境不存在，则退回到 `py -3.11`
- 使用 `uvicorn main:app --reload`

### 6.2 comment_agent

启动脚本：

```powershell
.\infra\scripts\start_comment_agent.ps1
```

当前行为：

- 工作目录切换到 `apps/comment_agent`
- 启动前把 `libs/shared_memory/src` 加入 `PYTHONPATH`
- 优先使用 `apps/comment_agent/.venv/Scripts/python.exe`
- 使用 `uvicorn app.main:app --reload`

这里说明一个关键点：

`PYTHONPATH` 可以理解成“Python 运行时去哪里找额外源码目录”。  
因为 `comment_agent` 当前依赖工作区内的共享库源码，所以脚本里先把共享库路径加进去了。

### 6.3 content_bridge

启动脚本：

```powershell
.\infra\scripts\start_content_bridge.ps1
```

当前行为：

- 工作目录切换到 `apps/ado_repost`
- 启动前把 `apps/ado_repost/src` 加入 `PYTHONPATH`
- 启动前把 `libs/shared_memory/src` 加入 `PYTHONPATH`
- 优先使用 `apps/ado_repost/.venv/Scripts/python.exe`
- 使用 `uvicorn content_bridge.server:app --reload`

这说明 `content_bridge` 当前不仅依赖自己的 `src` 目录结构，也依赖共享库源码目录。

## 7. 当前建议启动顺序

当前阶段建议按以下顺序启动：

1. `platform`
2. `comment_agent`
3. `content_bridge`

这不是严格架构保证，而是当前仓库文档和脚本层面的推荐顺序。  
后续如果服务边界和依赖关系进一步收敛，这个顺序可以再重新评估。

## 8. 依赖管理现状

当前仓库中，三个服务都已经有依赖文件，但管理方式还没有完全统一：

- `apps/platform/requirements.txt`
- `apps/platform/pyproject.toml`
- `apps/comment_agent/requirements.txt`
- `apps/ado_repost/requirements.txt`（当前承载 `content_bridge`）
- `apps/ado_repost/pyproject.toml`

### 8.1 当前主依赖入口

在当前阶段，推荐把以下文件视为“实际安装入口”：

- `platform`: `requirements.txt`
- `comment_agent`: `requirements.txt`
- `content_bridge`: `requirements.txt`

把以下文件视为“辅助配置文件”：

- `apps/platform/pyproject.toml`
  - 当前主要承载 `ruff`、`pytest` 等工具配置
- `apps/ado_repost/pyproject.toml`
  - 当前承载 `content_bridge` 的包元数据和工具配置，但不是工作区脚本的默认安装入口

这意味着：

- 现阶段不要假设 `pyproject.toml` 已经完全替代 `requirements.txt`
- 如果是按工作区脚本初始化，真正生效的依赖入口仍然是 `requirements.txt`

当前可确认的问题：

1. 依赖声明方式未完全统一
2. `platform`、`comment_agent`、`content_bridge` 仍混用 `requirements.txt` 与 `pyproject.toml`
3. 工作区级依赖规范刚开始形成，但还没有完全收敛

因此，目前本地开发应优先依赖现有脚本，不建议自行发明新的安装方式。

## 9. 常见排查顺序

如果本地启动失败，建议先按这个顺序排查：

1. 确认 PowerShell 中使用的是 Python 3.11
2. 确认对应服务的 `.venv` 是否已创建
3. 确认是否先执行过 `bootstrap_workspace.ps1`
4. 确认依赖是否安装完成
5. 确认服务端口 `8000`、`8001`、`8002` 未被占用
6. 确认共享库路径是否已通过脚本注入 `PYTHONPATH`

如果是 `comment_agent` 或 `content_bridge` 启动失败，应优先怀疑共享库依赖和源码路径问题。

## 10. 当前开发约束

在工作区彻底收敛前，建议遵循以下约束：

1. 新开发优先依赖 `libs/shared_memory`
2. 不要继续新增对 `shared_mempool` 的正式依赖
3. 启动服务时优先使用工作区已有脚本
4. 不要把本机绝对路径继续写入新文档和新依赖声明
5. 新增和修改 Markdown 文档时统一使用 UTF-8 编码
6. 共享库安装优先通过 `bootstrap_workspace.ps1` 处理，不要在服务依赖文件中重复写本地路径包引用

## 11. 后续待补内容

当前本地开发流程文档已经覆盖初始化和启动入口，但后续还需要继续补齐：

- 测试运行方式
- 数据库初始化方式
- 各服务健康检查地址
- 调试日志查看方式
- 文档编码统一规范
- 依赖入口最终是否统一到 `pyproject.toml`

这些内容将在后续阶段继续补充。
