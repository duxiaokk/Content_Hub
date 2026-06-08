# Personal Blog 项目结构文档

本文档描述了重构后（扁平化结构）的项目组织方式、各模块职责以及核心开发规范。

## 1. 项目概览
本项目是一个基于 FastAPI 的个人博客系统，采用扁平化根目录结构，去除了冗余的嵌套层级。

## 2. 目录结构树
```text
.
├── agents/             # AI 智能体逻辑（Prompt 工程、文章生成）
├── clients/            # 外部 API 客户端（LLM 调用等）
├── core/               # 核心配置（环境变量、全局设置）
├── crud/               # 数据库 CRUD 操作封装
├── docs/               # 项目文档与历史归档
│   └── archive/        # 废弃资产归档（如前端原型）
├── image/              # 用户上传的文章图片存储
├── migrations/         # Alembic 数据库迁移脚本
├── models/             # SQLAlchemy 数据库模型
├── routers/            # FastAPI 路由层（处理请求与响应）
├── schemas/            # Pydantic 模型（数据验证与序列化）
├── services/           # 业务逻辑层（解耦路由与数据库操作）
├── static/             # 静态资源（CSS, JS, Images）
├── templates/          # Jinja2 HTML 模板
├── tests/              # 自动化测试用例（单元测试、集成测试）
├── main.py             # 应用入口程序
├── database.py         # 数据库连接与 Session 配置
├── security.py         # 认证、加密与权限校验
├── alembic.ini         # 数据库迁移配置
├── pytest.ini          # 测试运行配置
└── pyproject.toml      # 项目工具配置（Ruff, Lint 等）
```

## 3. 模块职责说明

### 核心层 (Core)
- **main.py**: 负责初始化 FastAPI 实例，挂载路由，配置中间件及静态文件路径。
- **database.py**: 负责 SQLAlchemy 引擎初始化，定义 `Base` 类，管理 `get_db` 依赖项。
- **security.py**: 负责 JWT 逻辑（Cookie 存储）、密码哈希（PBKDF2）及 `get_current_user` 依赖。

### 数据层 (Data)
- **models.py / models/**: 核心 ORM 模型。目前核心模型位于根目录 `models.py`，待后续任务重构。
- **crud/**: 保持原子化的数据库操作，不包含复杂的业务逻辑。
- **migrations/**: 记录数据库演进历史，由 Alembic 管理。

### 业务逻辑层 (Business)
- **services/**: 协调 CRUD 操作，处理复杂业务逻辑（如点赞防抖、AI 内容生成流程）。
- **agents/**: 封装 AI 相关的特定逻辑，如提示词拼接和 LLM 响应处理。

### 接口与展现层 (API & Web)
- **routers/**: 按照功能拆分的路由模块（Auth, Posts, Comments, AI, Pages）。
- **schemas/**: 定义 API 输入输出的契约，保证数据验证。
- **templates/**: 存放 HTML，使用 Jinja2 语法进行服务端渲染。

## 4. 关键规范
- **导入规范**: 使用绝对导入（例如 `from database import Base`），禁止使用相对导入。
- **测试规范**: 所有测试文件必须以 `test_` 开头，并存放在 `tests/` 目录下。运行 `python tasks.py test` 触发。
- **数据库迁移**: 所有的数据库变更必须通过 `alembic revision --autogenerate` 生成并在 `migrations/` 中记录。
- **静态资源**: 用户上传内容存放在 `image/`，UI 资源存放在 `static/`。

## 5. 最近重构记录 (2026-05-18)
- **扁平化**: 移除了 `my_blog/` 嵌套层级，将所有核心代码提升至根目录。
- **低风险清理**: 删除了 `tmp3.jpg`、`static/js/main.jsx`、`alembic/` (冗余目录) 及 `add_created_at_column.py`。
- **测试重组**: 将所有 `test_*.py` 移动到 `tests/` 目录，并配置 `pytest.ini`。
- **资产归档**: 将非运行时的前端原型移动至 `docs/archive/frontend_assets/`。
