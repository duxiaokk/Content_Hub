# T009: ai_rewrite_config — AI Processor：改写处理器 + 统一配置

## 目标（一句话）
增强现有改写处理器，支持从 `rewrite_profiles` 表读取配置，并实现统一 LLM 处理配置（provider/model/timeout/fallback/token_limit）。

## 依赖
- 前置任务：T008（摘要/分类/标签处理器已完成）、T001（`rewrite_profiles` 表已建）
- 阻塞项：依赖 LLM 配置

## 输入文件（请先阅读）
- 现有 rewrite processor：[apps/ai_processor/processors/rewrite/processor.py](file:///D:/Python/content_hub/apps/ai_processor/processors/rewrite/processor.py)
- LLM client：[apps/ai_processor/runtime/llm_client.py](file:///D:/Python/content_hub/apps/ai_processor/runtime/llm_client.py)
- 配置模型：[apps/ai_processor/runtime/settings.py](file:///D:/Python/content_hub/apps/ai_processor/runtime/settings.py)
- rewrite_profiles 表结构（T001 产出）
- 架构文档：`content_hub_product_architecture.md` 第 10 节（AI 处理策略）
- 任务清单：`content_hub_mvp_task_breakdown.md` 第 4.3 节第 1、6、7 项

## 输出要求（具体、可检查）

### 1. 增强 `RewriteProcessor`
在 [apps/ai_processor/processors/rewrite/processor.py](file:///D:/Python/content_hub/apps/ai_processor/processors/rewrite/processor.py) 中修改/增强（保留现有逻辑）：

```python
class RewriteProcessor:
    name = "rewrite"

    def __init__(self, profile: dict):
        """从 rewrite_profiles 表传入配置"""
        self.profile = profile

    async def process(self, content: ContentAsset, context: ProcessContext) -> ProcessResult:
        """将原文改写为中文化技术博客风格"""
        ...
```

要求：
- 从 `rewrite_profiles` 表加载配置（provider / model / system_prompt / max_tokens / timeout）。
- 默认 profile 为 `zh_tech_blog`（对应 `CONTENT_HUB_DEFAULT_REWRITE_PROFILE`）。
- System prompt：将技术内容改写为中文技术博客风格，保留代码块和关键术语。
- 输出改写结果到 `ProcessResult.content`：
  - `rewritten_title`：改写后的中文标题
  - `rewritten_content`：改写后的中文正文

### 2. 降级策略
实现 `fallback_strategy` 三种模式：
- `"skip"`（默认）：LLM 失败时跳过撤回改写结果，保留原内容 -> 审核队列仍需人工编辑。
- `"raw"`：LLM 失败时用 raw_content + 原文标题直接进入审核。
- `"retry"`：失败时重试一次（最多 1 次重试）。

### 3. 统一处理配置层
新建 `apps/ai_processor/runtime/config.py`（或修改现有 settings.py）：

```python
@dataclass
class AIProcessorConfig:
    provider: str = "deepseek"          # 从 .env 读取
    model: str = "deepseek-v4-flash"
    timeout_seconds: int = 60
    fallback_strategy: str = "skip"     # skip / raw / retry
    max_tokens_per_call: int = 2048
    enable_cost_tracking: bool = True
```

要求：
- 配置优先从 `rewrite_profiles` 表读取（按 profile name），未命中则从环境变量 fallback。
- 每次 LLM 调用后累计 token 消耗。

### 4. 回写 content_items
改完成后回写：
- `content_items.rewritten_title`
- `content_items.rewritten_content`
- `content_items.pipeline_status` = `"processed"`

### 5. 分层策略汇总
最终处理链：
```text
规则过滤（上游） → summarize → classify → tag → score 评估
  → score ≥ 阈值的进入 rewrite
  → score < 阈值的跳过改写，直接入审核队列
```
阈值建议默认为 0.5（可配）。

## 验收标准（必须全部勾选才算完成）
- [ ] `RewriteProcessor` 从 `rewrite_profiles` 表正确加载配置
- [ ] 默认 profile `zh_tech_blog` 可用
- [ ] LLM 失败时按 fallback_strategy 执行降级（skip/raw/retry）
- [ ] `rewritten_title` 和 `rewritten_content` 正确回写到 `content_items`
- [ ] token 消耗累计记录正确
- [ ] score 阈值过滤生效（低分内容不进 rewrite）
- [ ] `AIProcessorConfig` 可从 .env 和 rewrite_profiles 表两种来源加载
- [ ] 更新 [codex_board.md](file:///D:/Python/content_hub/codex_board.md) 标记 T009 为完成
