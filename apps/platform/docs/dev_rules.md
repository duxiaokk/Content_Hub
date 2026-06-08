# Development Rules

1. 项目根目录是 `D:\Python\Personal Blog`。
2. 不再使用 `my_blog/` 作为项目根目录。
3. 后端入口是 `main.py`。
4. 启动命令是 `python tasks.py run --host 127.0.0.1 --port 8000`。
5. 提交前必须执行 `python tasks.py check`。
6. `.env`、`blog.db`、`*.log`、`.venv/`、`my_blog/` 不提交。
7. 不要把临时脚本、调试图片、缓存目录提交到仓库。
8. 修改业务逻辑前先跑测试。
9. 修改数据库模型后必须考虑 `migrations`。
10. `router`、`service`、`model` 的职责不要混在一起。
