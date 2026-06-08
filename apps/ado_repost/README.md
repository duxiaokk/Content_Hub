# Ado Content Agent

这个项目现在只保留两类能力：

1. 内容采集
2. 内容处理

也就是说，它现在是一个“先把内容抓回来，再把内容清洗好”的前置 agent，不再负责通知、审核或正式发布。

## 现在能做什么

### 1. 内容采集

采集模块在 `src/ado_repost/fetchers/`。

它现在负责：

- 从外部来源抓取内容
- 支持的来源包括：
  - X / Twitter
  - YouTube
  - Instagram
  - RSS
- 支持增量抓取
- 支持游标持久化

“增量抓取”可以理解成：只看上次之后的新内容，不重复从头抓。

“游标”可以理解成：程序记住自己已经处理到哪里了，下次继续接着来。

### 2. 内容处理

处理模块在 `src/ado_repost/processors/`。

它现在负责：

- 去重
- 翻译
- 格式化

更具体一点：

- 去重：避免同一条内容重复处理
- 翻译：目前会根据规则判断是否需要翻译
- 格式化：把原始内容整理成统一文本结构

## 项目结构

```text
src/ado_repost/
  fetchers/      # 抓取外部内容
  processors/    # 去重、翻译、格式化
  schema.py      # 数据结构
  config.py      # 配置加载
  main.py        # 主入口，只跑采集和处理
```

## 安装依赖

我们先安装依赖。这样做的原因是，项目运行需要 `yaml` 这个第三方库来读取配置文件。

```bash
py -m pip install -r requirements.txt
py -m pip install -e .
```

- `py -m pip install -r requirements.txt`
  - 按清单安装运行依赖
- `py -m pip install -e .`
  - 把当前项目注册为本地可编辑包

## 共享记忆池（游标持久化）

把增量抓取游标保存到共享记忆池（Redis 可选，SQLite 必选）：

```bash
$env:ADO_REPOST_CURSOR_STORE='mempool'
$env:SHARED_MEMORY_NAMESPACE='ado-repost'
$env:SHARED_MEMORY_SQLITE_PATH='./data/shared_mempool.db'
```

如果你有 Redis：

```bash
$env:SHARED_MEMORY_REDIS_URL='redis://localhost:6379/0'
$env:SHARED_MEMORY_REDIS_KEY_PREFIX='shared_memory:'
```

## 配置文件

配置文件路径是 [config.yaml](d:/Python/Ado_Repost/config.yaml)。

现在配置里只保留 `fetchers`：

- `lookback_hours`
  - 抓取时往前回看多少小时
- `persist_cursors`
  - 是否保存增量游标
- `max_retries`
  - 抓取失败时最多重试几次
- `timeout_seconds`
  - 请求超时时间
- `x_enabled`
  - 是否启用 X 抓取
- `youtube_enabled`
  - 是否启用 YouTube 抓取
- `instagram_enabled`
  - 是否启用 Instagram 抓取
- `youtube_api_key`
  - YouTube API 密钥
- `youtube_channel_id`
  - 要抓取的 YouTube 频道 ID

## 如何运行

我们现在运行主流程。这样做的原因是，主流程会依次执行：

1. 抓取内容
2. 保存 `latest.json`
3. 读取历史记录去重
4. 翻译和格式化
5. 输出处理结果

```bash
$env:PYTHONPATH='src'
py -m ado_repost.main --config config.yaml
```

- `$env:PYTHONPATH='src'`
  - 告诉 Python 去 `src/` 目录里找项目代码
- `py -m ado_repost.main`
  - 按模块方式运行主入口
- `--config config.yaml`
  - 指定配置文件

如果你只想看看处理结果，不想做任何额外副作用，可以用 dry-run：

```bash
$env:PYTHONPATH='src'
py -m ado_repost.main --dry-run --config config.yaml
```

这里的 dry-run 仍然会执行采集和处理，只是明确告诉你这是检查模式。

## 输出文件

程序会在 `data/` 目录写这些文件：

- `latest.json`
  - 本次抓取到的原始内容
- `history.json`
  - 已处理历史，用来去重
- `cursors.json`
  - 增量抓取游标
- `run_result.json`
  - 本次运行的处理结果摘要

## run_result.json 里有什么

现在结果里主要有这些字段：

- `status`
  - 本次运行状态，比如 `done`、`dry_run`、`skipped`
- `fetch_error`
  - 第一条抓取错误摘要
- `fetch_errors`
  - 全部抓取错误列表
- `new_items`
  - 新抓到并进入处理流程的条数
- `processed_items`
  - 实际处理完成的条数
- `messages`
  - 格式化后的文本列表
- `items`
  - 结构化处理结果列表

`items` 里每一项包含：

- `dedup_key`
- `title`
- `content`
- `source`
- `link`
- `formatted_message`

这意味着下游系统如果要接评论系统、审核系统或别的发布器，可以直接读取结构化结果，而不需要重新分析原始抓取内容。

## 已删除的能力

为了让项目职责更清楚，下面这些功能已经移除：

- Discord / ServerChan 通知推送
- 博客 API 发布
- 草稿生成
- 审核状态流转
- worker 发布队列
- 发布相关测试和 mock blog API

## 这个项目现在适合做什么

现在它更适合做这些事情：

- 作为评论系统的上游数据准备器
- 作为内容聚合器
- 作为清洗和标准化模块

如果你下一步要对接“评论发布系统”，最自然的方式是：

1. 先让这个项目输出稳定的结构化内容
2. 再由单独的评论模块读取 `run_result.json` 或 `latest.json`
3. 决定怎么生成和发布评论
