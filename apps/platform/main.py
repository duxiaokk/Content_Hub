"""
功能摘要：本文件是多 Agent 任务编排平台的入口，负责组装所有组件并启动网络服务。

初学者指南：
这是整个平台系统的"启动开关"。当你运行项目时，首先执行的就是这个文件。
它会把页面路由、用户登录、文章管理等功能模块全部注册到一起，
并配置静态文件目录和全局异常处理。如果你要修改网站整体行为（比如添加新模块），
重点关注下方的 app.include_router() 部分。

主要成员：
- app: 基于 FastAPI（网络框架）构建的应用程序实例，承载整个网络服务
- auth_exception_handler(): 处理未登录异常，决定跳转登录页还是返回错误信息
- csrf_cookie_middleware(): 为每个请求设置跨站请求伪造防护令牌
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import FileResponse
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from core.observability import init_observability
from routers import ai, agent, comments, demo, digests, internal_tasks, pages, posts, reviews, sources
from routers.api_v1 import api_v1
from database import Base, check_db_health, engine
from web_deps import get_or_set_csrf_cookie
from middleware.rate_limit import RateLimitMiddleware
from middleware.timeout import TimeoutMiddleware

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
IMAGE_DIR = os.path.join(BASE_DIR, "image")
FRONTEND_DIST_DIR = os.path.join(BASE_DIR, "frontend", "dist")
FRONTEND_ASSETS_DIR = os.path.join(FRONTEND_DIST_DIR, "assets")

os.makedirs(STATIC_DIR, exist_ok=True)
os.makedirs(IMAGE_DIR, exist_ok=True)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="Ado_Jk Multi-Agent Orchestration Platform",
    version="1.0.0",
    docs_url=None,
    redoc_url=None,
    openapi_url="/openapi.json",
    lifespan=lifespan,
    description="""
## Ado_Jk 多 Agent 内容编排平台

### API 版本

| 前缀 | 说明 |
|------|------|
| `/api/v1/` | **标准 API**（推荐使用）|
| `/api/internal/` | 内部 Agent 通信 |
| `/` | 页面路由（HTML）|

### 认证方式

- **Bearer Token**: `Authorization: Bearer <access_token>`
- **Cookie**: 浏览器自动携带 `access_token` Cookie
- **内部调用**: `x-internal-token: <token>`

### 统一响应格式

```json
{"code": 0, "data": {...}, "message": "ok"}
```

错误码: `0`成功, `4xxxx`客户端错误, `5xxx`服务端错误, `6xxxx`业务状态
""",
)
app.mount("/static/images", StaticFiles(directory=IMAGE_DIR), name="static_images")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
if os.path.isdir(FRONTEND_ASSETS_DIR):
    app.mount("/console-assets", StaticFiles(directory=FRONTEND_ASSETS_DIR), name="console_assets")

app.include_router(comments.router)
app.include_router(posts.router)
app.include_router(pages.router)
app.include_router(ai.router)
app.include_router(agent.router)
app.include_router(internal_tasks.router)
app.include_router(demo.router)
app.include_router(sources.router)
app.include_router(reviews.router)
app.include_router(digests.router)

# API v1 标准化路由
app.include_router(api_v1)

# 可观测性初始化
init_observability("platform", app)

# 中间件: 限流 + 超时（仅对 /api/ 路径生效）
app.add_middleware(RateLimitMiddleware)
app.add_middleware(TimeoutMiddleware)

@app.exception_handler(HTTPException)
async def auth_exception_handler(request: Request, exc: HTTPException):
    if exc.status_code == status.HTTP_401_UNAUTHORIZED:
        accept = (request.headers.get("accept") or "").lower()
        wants_html = "text/html" in accept or "*/*" in accept
        if request.method.upper() == "GET" and wants_html:
            return RedirectResponse(url="/console", status_code=status.HTTP_302_FOUND)

        detail = (
            exc.detail
            if isinstance(exc.detail, str) and exc.detail.strip()
            else "\u672a\u767b\u5f55"
        )
        return JSONResponse(status_code=status.HTTP_401_UNAUTHORIZED, content={"detail": detail})
    return await http_exception_handler(request, exc)


@app.get("/docs", include_in_schema=False)
def swagger_docs():
    openapi_url = app.openapi_url or "/openapi.json"
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css">
        <title>{app.title} - Swagger UI</title>
    </head>
    <body>
        <div id="swagger-ui"></div>
        <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
        <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-standalone-preset.js"></script>
        <script>
        window.onload = function() {{
            window.ui = SwaggerUIBundle({{
                url: "{openapi_url}",
                dom_id: "#swagger-ui",
                deepLinking: true,
                persistAuthorization: true,
                presets: [SwaggerUIBundle.presets.apis, SwaggerUIStandalonePreset],
                layout: "BaseLayout",
                requestInterceptor: function(request) {{
                    var match = document.cookie.match(/(?:^|; )csrf_token=([^;]+)/);
                    if (match && match[1]) {{
                        request.headers["X-CSRF-Token"] = decodeURIComponent(match[1]);
                    }}
                    request.credentials = "same-origin";
                    return request;
                }}
            }});
        }};
        </script>
    </body>
    </html>
    """
    return HTMLResponse(html)


@app.get("/health")
def platform_health():
    """平台主服务健康检查。"""
    from core.error_codes import ErrorCode
    db_status = check_db_health()
    return {
        "code": ErrorCode.SUCCESS.value,
        "data": {
            "status": "ok",
            "service": "platform",
            "db": db_status["status"],
        },
        "message": "ok",
    }


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Pydantic 校验异常 → 统一错误格式。"""
    from core.error_codes import ErrorCode
    msg = "请求参数校验失败"
    errors = exc.errors()
    if errors:
        first = errors[0]
        loc = ".".join(str(l) for l in first.get("loc", [])) if first.get("loc") else ""
        msg = f"{first.get('msg', '参数校验失败')}" + (f" ({loc})" if loc else "")
    return JSONResponse(
        status_code=422,
        content={"code": ErrorCode.VALIDATION_ERROR, "data": None, "message": msg},
    )


@app.middleware("http")
async def csrf_cookie_middleware(request: Request, call_next):
    response = await call_next(request)
    try:
        get_or_set_csrf_cookie(request, response)
    except Exception:
        logger.exception("failed to set csrf cookie")
    return response


def _console_index_html() -> str:
    index_path = os.path.join(FRONTEND_DIST_DIR, "index.html")
    if not os.path.isfile(index_path):
        raise HTTPException(status_code=404, detail="console frontend not built")
    with open(index_path, "r", encoding="utf-8") as file_handle:
        html = file_handle.read()
    html = html.replace('src="/console/assets/', 'src="/console-assets/')
    html = html.replace('href="/console/assets/', 'href="/console-assets/')
    html = html.replace('href="/vite.svg"', 'href="/static/images/favicon.ico"')
    return html


@app.get("/console", include_in_schema=False)
@app.get("/console/{full_path:path}", include_in_schema=False)
def console_spa_entry(full_path: str = ""):
    return HTMLResponse(_console_index_html())
