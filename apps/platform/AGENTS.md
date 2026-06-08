# Ado_Jk Multi-Agent Orchestration Platform - AI Agent Guidelines

## Architecture Overview
Multi-Agent task orchestration platform built with FastAPI, SQLAlchemy ORM, Jinja2 templates, and custom authentication. SQLite default (blog.db), MySQL optional via env vars. No external auth deps - custom PBKDF2 password hashing and HMAC-signed tokens. Includes Scheduler Center for distributed task orchestration, Agent Registry for agent discovery, and Shared Memory Pool for cross-service data sharing.

## Key Components
- `main.py`: Core routes, post CRUD, like system (JSON file)
- `models.py`: Post/User SQLAlchemy models with UTC timestamps
- `database.py`: Engine setup with MySQL/SQLite fallback
- `security.py`: Custom JWT-like token auth (cookies), PBKDF2 hashing
- `routers/auth.py`: Login/register/logout with form+JSON support
- `templates/`: Jinja2 HTML with Chinese UI
- `static/`: CSS/JS/images, mounted at /static and /static/images

## Critical Workflows
- **Run app**: `uvicorn main:app --reload --host 127.0.0.1 --port 8010`
- **DB migrations**: Manual scripts like `add_created_at_column.py` (run with python path/to/script.py)
- **Test auth flow**: Use `tmp_verify.py` for end-to-end verification
- **Static files**: Place images in `image/` for /static/images/ access

## Project Conventions
- **Auth**: Cookie-based tokens, redirect to /login on 401
- **Content handling**: Support both JSON and form-encoded requests (parse_qs fallback)
- **Timestamps**: UTC datetime defaults, display as local time in templates
- **Ratings**: 1-5 star system, nullable integer
- **Search**: Title-only contains filter
- **Likes**: File-based counter in `like_count.json`, no DB persistence

## Integration Patterns
- **Database**: `get_db()` dependency for session management
- **User context**: `Depends(security.get_current_user_from_cookie)` for auth-required routes
- **Templates**: `templates.TemplateResponse(request, "template.html", context)`
- **Redirects**: `RedirectResponse(url, status_code=303)` for POST redirects
- **Error handling**: HTTPException with Chinese messages

## Development Notes
- No tests directory - manual verification via tmp_verify.py
- Dependencies minimal: fastapi, uvicorn, sqlalchemy, jinja2, pymysql
- Chinese comments/templates - maintain language consistency
- Environment config: SECRET_KEY, DB_*, ACCESS_TOKEN_EXPIRE_MINUTES
