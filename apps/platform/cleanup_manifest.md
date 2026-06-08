# 项目文件清理清单
# 项目路径: D:\Python\Personal Blog
# 生成时间: 2026-05-24

## 一、Python 字节码缓存（运行时自动生成，可安全清理）
- __pycache__/
- core/__pycache__/
- crud/__pycache__/
- migrations/__pycache__/
- migrations/versions/__pycache__/
- routers/__pycache__/
- schemas/__pycache__/
- services/__pycache__/
- tests/__pycache__/

## 二、工具/构建缓存（可安全清理）
- .ruff_cache/
- .cursor/
- .vercel/

## 三、IDE 配置目录（不影响项目构建运行）
- .idea/
- .vscode/

## 四、备份/旧项目目录（项目重构前备份，可安全清理）
- _backup_my_blog_before_flatten_20260507_212540/
- _outer_old_before_flatten_20260507_212540/
- my_blog_backup/

## 五、临时/冗余虚拟环境（保留 .venv 主环境）
- .venv_flat/
- .venv_flat_test/

## 六、废弃前端存档（项目已改用 Jinja2 模板，未使用 React/Vue）
- docs/archive/

## 七、视觉测试临时文件
- visual_artifacts/
- visual_baseline/

## 八、孤立/废弃文件（无业务引用或内容为空）
- models/article_draft.py（仅有一行注释，无实际代码，未被 models.py 引用）
- clients/llm_client.py（仅有一行注释，无实际代码）
- static/js/main.css（实际内容为 React JS 代码，文件扩展名错误且未被任何模板引用）
- tmp.jpg（临时图片文件）

## 九、重复资源文件
- static/images/fe97ccd141eca9ac.jpg（与 image/3c71dc33c58f4effa223b39a4afd54ea.jpg MD5 值完全相同）

## 十、空文件（无内容且未被引用）
- templates/button_variants.html（0 字节，未被任何代码引用）

## 十一、测试文件（非生产必需，清理后不影响核心业务流程）
- conftest.py
- pytest.ini
- tests/test_ai_removal.py
- tests/test_auth.py
- tests/test_crud.py
- tests/test_posts_api.py
- tests/tests_visual_glass_button_playwright.py
