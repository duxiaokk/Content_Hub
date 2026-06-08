# Content Hub Workspace

这是新的总项目根目录，统一承载主平台、评论服务、Ado 内容采集服务以及共享库。

## 目录结构

```text
content_hub/
  apps/
    platform/         # 主平台
    comment_agent/    # 评论服务
    ado_repost/       # 内容采集与处理服务
  libs/
    shared_memory/    # 统一共享记忆库
    shared_mempool/   # 历史副本，暂时保留
  infra/
    docs/
    docker/
    scripts/
```

## 当前约定

- 新的总项目根目录：`D:\Python\content_hub`
- 主平台目录：`D:\Python\content_hub\apps\platform`
- 评论服务目录：`D:\Python\content_hub\apps\comment_agent`
- Ado 服务目录：`D:\Python\content_hub\apps\ado_repost`
- 统一共享库目录：`D:\Python\content_hub\libs\shared_memory`

## 推荐启动顺序

1. 启动 `platform`
2. 启动 `comment_agent`
3. 启动 `ado_repost`

## 快速启动

在 PowerShell 中执行：

```powershell
.\infra\scripts\start_content_hub.ps1
.\infra\scripts\start_comment_agent.ps1
.\infra\scripts\start_ado_repost.ps1
```

或者直接一键启动：

```powershell
.\infra\scripts\start_all.ps1
```

## 初始化环境

首次在新工作区开发时，先初始化虚拟环境：

```powershell
.\infra\scripts\bootstrap_workspace.ps1
```

如果你也想重建主平台的虚拟环境：

```powershell
.\infra\scripts\bootstrap_workspace.ps1 -IncludeContentHub
```

默认使用本机 `Python 3.11` 创建新环境。

## 共享库说明

- 所有新开发优先使用 `libs/shared_memory`
- `libs/shared_mempool` 目前仅作为历史参考副本保留
- 后续可以再做一次收敛，把 `shared_mempool` 内容合并或移除

## 当前状态

- 已基于旧目录完成副本迁移
- `ado_repost` 和 `comment_agent` 的共享库依赖已改到新根目录
- 主平台 `content_hub` 已优先从工作区级共享库加载 `shared_memory`
- 旧目录暂未删除，便于对照和回滚
