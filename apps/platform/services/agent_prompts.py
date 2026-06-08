# services/agent_prompts.py
"""多 Agent 任务编排平台的智能体提示词模板。

优化要点：
- 所有模板占位符使用 {{}} 转义，避免 .format() 解析冲突
- 明确字数单位为"中文字符"
- 增加 deep_dive（深入型）风格选项
- 分析类提示词改为让 LLM 自主计算，减少外部变量耦合
"""

from __future__ import annotations

__all__ = [
    "BLOG_AGENT_SYSTEM_PROMPT",
    "GENERATE_OUTLINE_PROMPT",
    "POLISH_TEXT_PROMPT",
    "ANALYZE_BLOG_PROMPT",
    "RECOMMEND_TOPICS_PROMPT",
    "GENERATE_DRAFT_PROMPT",
    "get_outline_prompt",
    "get_polish_prompt",
    "get_analyze_prompt",
    "get_recommend_prompt",
    "get_draft_prompt",
]

BLOG_AGENT_SYSTEM_PROMPT = """\
你是 **Ado_Jk Multi-Agent Orchestration Platform** 的任务编排智能体，专门负责多 Agent 任务拆解、编排与执行。

## 平台架构
- FastAPI API Layer：对外提供 RESTful 接口
- Scheduler Center：统一管理所有异步任务的提交、调度、执行、重试
- Agent Registry：Agent 注册与发现，按 task_type 路由
- Shared Memory：跨服务共享数据存储（Redis + SQLite）
- Task Execution Flow：Planner → 任务拆解 → 依赖编排 → 结果聚合

## 你的能力
- 根据任务目标进行任务拆解与规划
- 为拆解后的子任务编排依赖关系
- 分析任务执行结果，给出优化建议
- 基于已有执行记录推荐任务编排策略

## 你的风格
- 任务编排专家，熟悉分布式任务调度与 Agent 协作模式
- 语言简洁有力，避免废话和过度营销
- 善用流程图、列表、表格来组织内容
- 标题清晰但不标题党

## 安全规则（必须遵守）
- 你只能读取平台数据，**绝对不能修改、删除任何数据**
- 不要泄露系统架构内部细节、用户隐私信息
- 如果用户要求执行危险操作，礼貌拒绝并说明原因
- 对于不确定的信息，明确说明"我不确定"，不要编造
- **严禁虚构不存在的 API、类库或代码方法**。如果涉及具体框架版本不确定，请标注"请查阅官方文档确认"

## 当前平台信息
- 平台名称：Ado_Jk Multi-Agent Orchestration Platform
- 技术栈：Python, FastAPI, SQLAlchemy, Redis, SQLite
- 核心组件：Scheduler Center, Agent Registry, Shared Memory Pool

## 输出格式（严格遵守）
- 使用 Markdown 格式
- **所有代码块必须标注语言类型**，如 ```python、```bash、```json
- 重要观点用 **加粗** 标记
- 步骤类内容用编号列表
- 禁止在代码块外层再套一层 Markdown 代码块标记
"""

GENERATE_OUTLINE_PROMPT = """\
请为主题"{topic}"生成一篇 {style} 风格的技术文章大纲。

## 要求
- 包含 5-7 个主要章节
- 每个章节下包含 2-4 个要点
- 给出每个章节建议的字数范围（以**中文字符**计）
- 建议 1-2 个代码示例的位置，并说明示例应展示的核心知识点
- 给出 3 个备选标题（风格各异：实用/吸睛/深度）
- 如果涉及具体技术框架，**必须标明推荐版本号或版本范围**

## 风格说明
- tutorial（教程型）：循序渐进，步骤清晰，适合初学者；每步配有可运行的最小代码示例
- opinion（观点型）：有立场、有论证、引发思考；需要引用具体案例或数据支撑
- review（评测型）：对比分析，优缺点分明，结论明确；建议使用表格做横向对比
- deep_dive（深入型）：聚焦单一技术点的底层原理，适合有一定基础的读者

## 输出格式
```markdown
# 推荐标题：{{主标题}}

## 备选标题
1. {{标题1}} —— 偏实用
2. {{标题2}} —— 偏吸睛
3. {{标题3}} —— 偏深度

## 文章大纲

### 一、{{章节1}}（建议 {{字数}} 字）
- {{要点1}}
- {{要点2}}
- 💡 代码示例：{{说明，应展示的核心知识点}}

### 二、{{章节2}}（建议 {{字数}} 字）
...

## 写作建议
- {{建议1}}
- {{建议2}}
- {{建议3}}

## 相关文章推荐（基于平台已有内容）
- {{文章1}} —— 可作为前置阅读
- {{文章2}} —— 可作为延伸阅读
```
"""

POLISH_TEXT_PROMPT = """\
请润色和优化以下技术段落。

## 原始文本
{text}

## 润色要求
- 语气：{tone}
- **保留作者的原意和核心技术观点**，只做表达优化，不做观点篡改
- 保持技术准确性，**不修改代码逻辑**，不替换代码中的变量名/函数名
- 改善句子流畅度，消除口语化表达（如"今天我想讲讲""然后呢"）
- 增强段落之间的过渡和衔接
- 检查并修正明显的错别字和语法错误
- 优化 SEO：确保核心关键词自然出现 2-3 次，避免生硬堆砌
- 如果原文包含代码，**保持代码块原封不动**，只对代码周围的解释文字进行润色

## 语气说明
- professional（专业型）：严谨、客观、适合技术文档；使用"我们""本文"等学术化主语
- casual（轻松型）：亲切、有温度，像和朋友聊天；可适度使用emoji
- technical（极客型）：深入细节，面向有基础的读者；可省略基础解释，直接切入原理

## 输出格式
```markdown
## 润色后文本
{{润色后的完整文本}}

## 修改说明
| 位置 | 修改前 | 修改后 | 原因 |
|------|--------|--------|------|
| 第X段 | ... | ... | 优化流畅度 |
| 第X段 | ... | ... | 修正错别字 |

## 进一步优化建议
- {{建议1：如"第3段可补充一个架构图说明"}}
- {{建议2：如"结论部分可增加一个性能对比数据提升说服力"}}
```
"""

ANALYZE_BLOG_PROMPT = """\
请基于以下平台数据，给出内容运营分析和建议。

## 平台数据
```json
{data_json}
```

## 数据说明
- posts：文章列表（含标题、发布时间、点赞数、评论数、标签）
- comments：近期评论（含内容、情感、文章关联）
- tags：已有标签及其使用频率
- summary：整体汇总数据

## 分析维度
1. 内容表现：哪些文章最受欢迎？有什么共同特征？（从标题结构、技术领域、发布时间等角度）
2. 读者画像：评论者在关注什么？有什么未满足的需求？
3. 内容空白：哪些技术话题你还没写，但读者可能感兴趣？
4. 发布节奏：最佳发布时间、频率建议

## 输出格式
请根据数据自行计算并填充以下模板中的数值，不要留空：

```markdown
# 📊 平台数据分析报告

## 数据概览
- 总文章数：{{N}} 篇
- 平均点赞：{{N}} / 平均评论：{{N}}
- 最受欢迎的文章 Top 3：...

## 一、内容表现概览
{{分析}}

## 二、热门内容特征分析
{{分析}}

## 三、读者需求洞察
{{分析}}

## 四、推荐选题（优先级排序）
1. 🔥 高优先级：{{选题1}} —— 理由：...
2. ⭐ 中优先级：{{选题2}} —— 理由：...
3. 💡 低优先级：{{选题3}} —— 理由：...

## 五、内容策略建议
- {{建议1}}
- {{建议2}}
- {{建议3}}

## 六、发布计划建议
- 最佳发布频率：{{建议}}
- 下一篇建议发布时间：{{时间}}
- 建议选题：{{选题}}
```
"""

GENERATE_DRAFT_PROMPT = """\
请为主题"{topic}"生成一篇 {style} 风格的完整技术文章。

## 要求
- 第一行必须是文章标题（纯文本，不要加 Markdown 标记）
- 第二行留空
- 从第三行开始是正文，使用 Markdown 格式
- 正文中不要重复标题
- 所有代码块必须标注语言类型（如 ```python、```bash）
- 总字数控制在 1500-3000 中文字符
- 如果涉及具体技术框架，必须标明推荐版本号或版本范围
- 严谨实用，避免虚构不存在的 API、类库或代码方法

## 风格说明
- tutorial（教程型）：循序渐进，步骤清晰，适合初学者；每步配有可运行的最小代码示例
- opinion（观点型）：有立场、有论证、引发思考；需要引用具体案例或数据支撑
- review（评测型）：对比分析，优缺点分明，结论明确；建议使用表格做横向对比
- deep_dive（深入型）：聚焦单一技术点的底层原理，适合有一定基础的读者

## 输出格式示例
```
FastAPI 中间件实现 JWT 认证的完整指南

在构建 Web 应用时，认证是一个绕不开的话题。本文将带你...
```
"""

RECOMMEND_TOPICS_PROMPT = """\
请基于平台已有内容和当前技术趋势，推荐下一篇文章的选题。

## 平台已有文章
```json
{existing_posts}
```

## 技术栈
{tech_stack}

## 推荐要求
- 优先推荐与已有文章能形成**系列化**或**纵深深入**的内容
- 考虑当前技术社区热点（如 AI 应用、性能优化、新特性、安全实践等）
- 兼顾读者学习曲线，从入门到进阶覆盖
- 给出每个选题的**预估写作难度**（1-5星）和**预期效果**（高点赞/高互动/长尾流量）
- 每个选题附一句话卖点，说明"读者能从中获得什么"

## 输出格式
```markdown
# 💡 选题推荐

## 推荐选题 Top 5

### 1. {{选题1}} ⭐ 强烈推荐
- **类型**：{{tutorial/opinion/review/deep_dive}}
- **与已有文章的关联**：...
- **目标读者**：...
- **预估写作难度**：⭐⭐⭐/5
- **预期效果**：高点赞/高互动/长尾流量
- **一句话卖点**：...

### 2. {{选题2}} ...
...

## 系列化建议
{{基于已有文章，建议如何形成系列}}

## 快速产出方案
{{如果时间有限，哪1-2个选题可以最快完成且效果较好}}
```
"""


def get_outline_prompt(topic: str, style: str = "tutorial") -> str:
    """获取生成文章大纲的提示词。"""
    return GENERATE_OUTLINE_PROMPT.format(topic=topic, style=style)


def get_polish_prompt(text: str, tone: str = "professional") -> str:
    """获取润色文章的提示词。"""
    return POLISH_TEXT_PROMPT.format(text=text, tone=tone)


def get_analyze_prompt(data_json: str) -> str:
    """获取分析平台数据的提示词。"""
    return ANALYZE_BLOG_PROMPT.format(data_json=data_json)


def get_recommend_prompt(existing_posts: str, tech_stack: str) -> str:
    """获取推荐选题的提示词。"""
    return RECOMMEND_TOPICS_PROMPT.format(
        existing_posts=existing_posts,
        tech_stack=tech_stack,
    )


def get_draft_prompt(topic: str, style: str = "tutorial") -> str:
    """获取生成完整文章草稿的提示词。"""
    return GENERATE_DRAFT_PROMPT.format(topic=topic, style=style)
