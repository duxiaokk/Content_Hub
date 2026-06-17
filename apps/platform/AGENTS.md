# Content Hub Platform - 子模块补充规则

## 1. 继承关系
- 本目录及其子目录首先继承仓库根目录 `D:\Python\content_hub\AGENTS.md`
- 本文件只补充 `apps/platform` 的特定约束
- 若与根规则冲突，以根规则为准

## 2. 模块定位
- `apps/platform` 是平台层与控制台相关模块
- 典型范围包括：
  - API
  - 数据模型
  - Alembic 迁移
  - 前端模板
  - 调度中心接入

## 3. 平台层实现约束

### 数据库
- 默认数据库可能是 SQLite，本地环境已知会出现 `disk I/O error`
- 涉及迁移或数据库验收时，优先说明备份要求
- 若默认库不可用，可使用干净临时 SQLite 库完成 Alembic 验证
- 迁移链必须保持单 head

### API
- 使用 FastAPI 风格
- 优先复用现有依赖注入、schema、响应结构
- 鉴权、会话、cookie 相关逻辑保持与现有实现一致

### 模板与前端
- 保持当前页面结构和命名风格
- 中文界面文案保持一致
- 不因为单个任务重写整页模板或样式体系

## 4. 验证重点
- 若任务涉及迁移，至少验证：
  - `alembic upgrade head`
  - `alembic current`
  - 必要时 `alembic downgrade -1`
- 若任务涉及 API 或页面，优先补最小必要测试或验收步骤

## 5. Git 提交
- 平台目录下任务完成后，仍遵循根目录 `AGENTS.md` 的自动提交规则
- 只提交当前平台任务相关文件

