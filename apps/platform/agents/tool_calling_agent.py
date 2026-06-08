"""Tool Calling Agent — 独立 FastAPI 服务

工具调用 Agent：执行外部工具（搜索、翻译、HTTP调用、文件IO、API调用、数据库查询等）。

任务类型: tool.call, tool.search, tool.http

内置工具:
  - web_search: 模拟网页搜索
  - translate: 文本翻译（LLM驱动）
  - http_get: HTTP GET 请求
  - text_stats: 文本统计
  - file_io: 文件读写/目录列表（带路径消毒）
  - api_call: 通用REST API调用（带指数退避重试）
  - database_query: 只读SQL查询（SQLAlchemy）
  - 全局速率限制（按工具类型/每分钟/每小时）

输入:  intent + tool_calls 或 auto-select by LLM
输出:  call results + summary

启动:     python -m agents.tool_calling_agent --port 8120
"""
from __future__ import annotations

import asyncio
import datetime
import json
import os
import pathlib
import re
import time
from collections import defaultdict
from typing import Any

import httpx

from agents.base_agent import AgentConfig, BaseAgent

# ------------------------------------------------------------------
# Rate Limiting
# ------------------------------------------------------------------

_RATE_LIMITS: dict[str, dict[str, float]] = {
    "file_io":        {"max_per_minute": 30,  "max_per_hour": 500},
    "api_call":       {"max_per_minute": 20,  "max_per_hour": 200},
    "database_query": {"max_per_minute": 10,  "max_per_hour": 100},
    "web_search":     {"max_per_minute": 15,  "max_per_hour": 300},
    "translate":      {"max_per_minute": 10,  "max_per_hour": 100},
    "http_get":       {"max_per_minute": 20,  "max_per_hour": 300},
    "text_stats":     {"max_per_minute": 60,  "max_per_hour": 2000},
}

RATE_LIMIT_ENABLED = str(os.getenv("RATE_LIMIT_ENABLED", "true")).lower() == "true"

_tool_call_logs: dict[str, list[float]] = defaultdict(list)


def _cleanup_old_logs(now: float | None = None) -> None:
    now = now or time.time()
    cutoff = now - 3600  # 1 hour
    for name in list(_tool_call_logs):
        _tool_call_logs[name] = [t for t in _tool_call_logs[name] if t > cutoff]
        if not _tool_call_logs[name]:
            del _tool_call_logs[name]


def _check_rate_limit(tool_name: str) -> None:
    if not RATE_LIMIT_ENABLED:
        return
    limits = _RATE_LIMITS.get(tool_name)
    if not limits:
        return
    now = time.time()
    _cleanup_old_logs(now)
    logs = _tool_call_logs[tool_name]

    # per-minute check
    max_per_min = limits.get("max_per_minute")
    if max_per_min:
        minute_ago = now - 60
        recent = [t for t in logs if t > minute_ago]
        if len(recent) >= max_per_min:
            raise RuntimeError(
                f"Rate limit exceeded for '{tool_name}': {max_per_min} calls/min."
            )

    # per-hour check
    max_per_hour = limits.get("max_per_hour")
    if max_per_hour:
        if len(logs) >= max_per_hour:
            raise RuntimeError(
                f"Rate limit exceeded for '{tool_name}': {max_per_hour} calls/hour."
            )


def _record_tool_call(tool_name: str) -> None:
    if not RATE_LIMIT_ENABLED:
        return
    _tool_call_logs[tool_name].append(time.time())


class ToolCallingAgent(BaseAgent):
    """Tool Calling Agent — 工具调用。"""

    _AVAILABLE_TOOLS: dict[str, dict] = {
        "web_search":     {"name": "web_search",     "description": "执行网页搜索"},
        "translate":      {"name": "translate",      "description": "文本翻译"},
        "http_get":       {"name": "http_get",       "description": "HTTP GET请求"},
        "text_stats":     {"name": "text_stats",     "description": "文本统计（字数/词频等）"},
        "file_io":        {"name": "file_io",        "description": "文件读写与目录列表"},
        "api_call":       {"name": "api_call",       "description": "通用REST API调用"},
        "database_query": {"name": "database_query", "description": "只读SQL查询"},
    }

    def supported_task_types(self) -> list[str]:
        return ["tool.call", "tool.execute", "tool.search", "tool.http", "tool.translate"]

    async def execute(self, task_type: str, payload: dict[str, Any], trace_id: str | None) -> dict[str, Any]:
        tool_calls = payload.get("tool_calls") if isinstance(payload.get("tool_calls"), list) else None

        # 如果未指定 tool_calls，用 LLM 自动选择
        if not tool_calls:
            intent = str(payload.get("intent", ""))
            tool_calls = await self._auto_select_tools(intent, payload.get("context", {}))

        results = []
        for tc in tool_calls:
            tool_name = tc.get("tool_name", tc.get("name", ""))
            params = tc.get("parameters", tc.get("params", {}))
            if not isinstance(params, dict):
                params = {}
            result = await self._execute_tool(tool_name, params)
            results.append(result)

        summary = self._build_summary(results)
        return {"results": results, "summary": summary}

    # ------------------------------------------------------------------
    # 工具执行
    # ------------------------------------------------------------------

    async def _execute_tool(self, tool_name: str, params: dict) -> dict:
        # Rate limit check
        try:
            _check_rate_limit(tool_name)
        except RuntimeError as exc:
            return {"tool_name": tool_name, "success": False, "error": str(exc)}
        try:
            if tool_name == "web_search":
                result = self._tool_web_search(params)
            elif tool_name == "translate":
                result = await self._tool_translate(params)
            elif tool_name == "http_get":
                result = await self._tool_http_get(params)
            elif tool_name == "text_stats":
                result = self._tool_text_stats(params)
            elif tool_name == "file_io":
                result = await self._tool_file_io(params)
            elif tool_name == "api_call":
                result = await self._tool_api_call(params)
            elif tool_name == "database_query":
                result = await self._tool_database_query(params)
            else:
                return {"tool_name": tool_name, "success": False, "error": f"Unknown tool: {tool_name}"}
            _record_tool_call(tool_name)
            return result
        except Exception as exc:
            return {"tool_name": tool_name, "success": False, "error": str(exc)}

    def _tool_web_search(self, params: dict) -> dict:
        query = str(params.get("query", ""))
        return {
            "tool_name": "web_search",
            "success": True,
            "result": {"query": query, "results": [{"title": f"Result for: {query}", "snippet": f"Mock results for '{query}'"}]},
            "duration_ms": 0,
        }

    async def _tool_translate(self, params: dict) -> dict:
        text = str(params.get("text", ""))
        source_lang = str(params.get("source_lang", "auto"))
        target_lang = str(params.get("target_lang", "en"))

        if self.config.mock_llm or not self.config.llm_api_key:
            return {
                "tool_name": "translate", "success": True,
                "result": {"text": f"[Translation: {target_lang}]\n{text}", "source_lang": source_lang, "target_lang": target_lang},
                "duration_ms": 0,
            }

        body = {
            "model": self.config.llm_model,
            "messages": [
                {"role": "system", "content": f"Translate the following text to {target_lang}. Output only the translation."},
                {"role": "user", "content": text},
            ],
            "temperature": 0.1,
            "max_tokens": min(len(text) * 2 + 500, 4000),
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{self.config.llm_base_url}/chat/completions",
                json=body,
                headers={"Authorization": f"Bearer {self.config.llm_api_key}"},
            )
        resp.raise_for_status()
        translated = resp.json()["choices"][0]["message"]["content"]
        return {
            "tool_name": "translate", "success": True,
            "result": {"text": translated, "source_lang": source_lang, "target_lang": target_lang},
            "duration_ms": 0,
        }

    async def _tool_http_get(self, params: dict) -> dict:
        url = str(params.get("url", ""))
        if not url:
            return {"tool_name": "http_get", "success": False, "error": "URL required"}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url)
            return {
                "tool_name": "http_get", "success": True,
                "result": {"status_code": resp.status_code, "body": resp.text[:5000]},
            }
        except Exception as e:
            return {"tool_name": "http_get", "success": False, "error": str(e)}

    def _tool_text_stats(self, params: dict) -> dict:
        text = str(params.get("text", ""))
        words = len(re.findall(r"\b\w+\b", text))
        chars = len(text)
        lines = text.count("\n") + 1 if text else 0
        return {
            "tool_name": "text_stats", "success": True,
            "result": {"word_count": words, "char_count": chars, "line_count": lines},
        }

    # ------------------------------------------------------------------
    # file_io — 文件读写 & 目录列表（带路径消毒）
    # ------------------------------------------------------------------

    @staticmethod
    def _sanitize_path(base_dir: str, user_path: str) -> pathlib.Path:
        """消毒路径，防止目录穿越攻击。"""
        base = pathlib.Path(base_dir).expanduser().resolve()
        if not base.is_dir():
            raise ValueError(f"Base directory does not exist: {base_dir}")

        # Normalize and resolve the full path
        candidate = (base / user_path).expanduser().resolve()
        # 确保 candidate 在 base 之下
        try:
            candidate.relative_to(base)
        except ValueError:
            raise ValueError(f"Path traversal detected: {user_path}")
        return candidate

    async def _tool_file_io(self, params: dict) -> dict:
        action = str(params.get("action", "read")).lower()
        base_dir = str(params.get("base_dir", os.getcwd()))
        file_path = str(params.get("path", ""))
        content = params.get("content")

        try:
            target = self._sanitize_path(base_dir, file_path)

            if action == "read":
                if not target.is_file():
                    return {"tool_name": "file_io", "success": False, "error": f"File not found: {file_path}"}
                text = target.read_text(encoding="utf-8")
                return {
                    "tool_name": "file_io", "success": True,
                    "result": {"action": "read", "path": str(target), "content": text[:10000]},
                }

            elif action == "write":
                if content is None:
                    return {"tool_name": "file_io", "success": False, "error": "Content required for write action"}
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(str(content), encoding="utf-8")
                return {
                    "tool_name": "file_io", "success": True,
                    "result": {"action": "write", "path": str(target), "size_bytes": len(str(content))},
                }

            elif action == "list":
                if not target.is_dir():
                    return {"tool_name": "file_io", "success": False, "error": f"Not a directory: {file_path}"}
                entries = []
                for p in sorted(target.iterdir()):
                    try:
                        entries.append({
                            "name": p.name,
                            "type": "dir" if p.is_dir() else "file",
                            "size_bytes": p.stat().st_size if p.is_file() else 0,
                        })
                    except OSError:
                        entries.append({"name": p.name, "type": "unknown", "size_bytes": 0})
                return {
                    "tool_name": "file_io", "success": True,
                    "result": {"action": "list", "path": str(target), "entries": entries[:500]},
                }

            else:
                return {"tool_name": "file_io", "success": False, "error": f"Unknown action: {action}"}

        except ValueError as exc:
            return {"tool_name": "file_io", "success": False, "error": f"Path error: {exc}"}
        except OSError as exc:
            return {"tool_name": "file_io", "success": False, "error": f"IO error: {exc}"}

    # ------------------------------------------------------------------
    # api_call — 通用 REST API 调用（带指数退避重试）
    # ------------------------------------------------------------------

    async def _tool_api_call(self, params: dict) -> dict:
        url = str(params.get("url", ""))
        if not url:
            return {"tool_name": "api_call", "success": False, "error": "URL required"}

        method = str(params.get("method", "GET")).upper()
        headers = params.get("headers") if isinstance(params.get("headers"), dict) else {}
        body = params.get("body")
        timeout = float(params.get("timeout", 30.0))
        max_retries = min(int(params.get("max_retries", 3)), 5)  # cap at 5

        last_error = None
        for attempt in range(max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    req_kwargs: dict[str, Any] = {"headers": headers}
                    if body is not None:
                        if isinstance(body, dict):
                            req_kwargs["json"] = body
                        else:
                            req_kwargs["content"] = str(body)
                    resp = await client.request(method, url, **req_kwargs)
                    return {
                        "tool_name": "api_call", "success": True,
                        "result": {
                            "status_code": resp.status_code,
                            "headers": dict(resp.headers),
                            "body": resp.text[:10000],
                        },
                        "retries": attempt,
                    }
            except (httpx.TimeoutException, httpx.ConnectError, httpx.RemoteProtocolError) as exc:
                last_error = str(exc)
                if attempt < max_retries:
                    backoff = 2 ** attempt  # 1s, 2s, 4s
                    await asyncio.sleep(backoff)
            except Exception as exc:
                return {"tool_name": "api_call", "success": False, "error": str(exc), "retries": attempt}

        return {"tool_name": "api_call", "success": False, "error": f"Max retries ({max_retries}) exceeded: {last_error}"}

    # ------------------------------------------------------------------
    # database_query — 只读 SQL 查询
    # ------------------------------------------------------------------

    async def _tool_database_query(self, params: dict) -> dict:
        sql = str(params.get("sql", "")).strip()
        if not sql:
            return {"tool_name": "database_query", "success": False, "error": "SQL required"}

        # 只允许 SELECT / SHOW / DESCRIBE / EXPLAIN（只读操作）
        sql_upper = sql.upper().lstrip()
        allowed_prefixes = ("SELECT", "SHOW", "DESCRIBE", "EXPLAIN", "WITH")
        if not any(sql_upper.startswith(prefix) for prefix in allowed_prefixes):
            return {
                "tool_name": "database_query", "success": False,
                "error": "Only read-only queries allowed (SELECT, SHOW, DESCRIBE, EXPLAIN, WITH)",
            }

        db_url = str(params.get("db_url", os.getenv("DATABASE_URL", "")))
        if not db_url:
            return {"tool_name": "database_query", "success": False, "error": "Database URL required"}

        try:
            from sqlalchemy import create_engine, text
            from sqlalchemy.exc import SQLAlchemyError
        except ImportError:
            return {"tool_name": "database_query", "success": False, "error": "SQLAlchemy not installed"}

        # 只读连接 — 每次查询都新建引擎/连接，保持隔离
        try:
            read_only_args = {
                "pool_pre_ping": True,
                "connect_args": {},
            }
            # 如果是 SQLite，添加只读模式
            if "sqlite" in db_url:
                read_only_args["connect_args"]["uri"] = True
            # 适用于 PostgreSQL/MySQL 的只读设置
            if "postgresql" in db_url or "mysql" in db_url:
                read_only_args["connect_args"]["options"] = "-c default_transaction_read_only=on"

            engine = create_engine(db_url, **read_only_args)
            with engine.connect() as conn:
                # 如支持则设置会话只读
                if "postgresql" in db_url:
                    conn.execute(text("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY"))
                result = conn.execute(text(sql))
                rows = [dict(row._mapping) for row in result.fetchall()]
                col_count = len(result.keys()) if rows else 0
            engine.dispose()
            return {
                "tool_name": "database_query", "success": True,
                "result": {"columns": list(rows[0].keys()) if rows else [], "rows": rows, "row_count": len(rows)},
            }
        except SQLAlchemyError as exc:
            return {"tool_name": "database_query", "success": False, "error": f"Database error: {exc}"}
        except Exception as exc:
            return {"tool_name": "database_query", "success": False, "error": str(exc)}

    # ------------------------------------------------------------------
    # LLM 自动选工具
    # ------------------------------------------------------------------

    async def _auto_select_tools(self, intent: str, context: dict) -> list[dict]:
        tool_descriptions = json.dumps(
            [{"name": n, "desc": d["description"]} for n, d in self._AVAILABLE_TOOLS.items()],
            ensure_ascii=False,
        )
        prompt = f"""根据用户意图选择工具。可用工具: {tool_descriptions}
用户意图: {intent}
输出 JSON 数组: [{{"tool_name":"...", "parameters":{{...}}}}]"""

        body = {
            "model": self.config.llm_model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1, "max_tokens": 500,
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{self.config.llm_base_url}/chat/completions",
                json=body,
                headers={"Authorization": f"Bearer {self.config.llm_api_key}"},
            )
        content = resp.json()["choices"][0]["message"]["content"]
        try:
            return json.loads(self._extract_json(content))
        except json.JSONDecodeError:
            return [{"tool_name": "web_search", "parameters": {"query": intent}}]

    # ------------------------------------------------------------------
    # 辅助
    # ------------------------------------------------------------------

    def _build_summary(self, results: list[dict]) -> str:
        successes = sum(1 for r in results if r.get("success"))
        return f"{successes}/{len(results)} tools succeeded"

    def _extract_json(self, content: str) -> str:
        content = content.strip()
        if "```json" in content:
            return content.split("```json")[1].split("```")[0]
        if "```" in content:
            return content.split("```")[1].split("```")[0]
        return content


# =========================================================================
# 入口
# =========================================================================


def create_app():
    config = AgentConfig(
        agent_key=os.getenv("AGENT_KEY", "tool-calling-agent"),
        agent_name=os.getenv("AGENT_NAME", "Tool Calling Agent"),
        base_url=os.getenv("AGENT_BASE_URL", "http://127.0.0.1:8120"),
        task_types=["tool.call", "tool.execute", "tool.search", "tool.http", "tool.translate"],
        capabilities={
            "kind": "tool_calling",
            "builtin_tools": list(ToolCallingAgent._AVAILABLE_TOOLS.keys()),
            "rate_limiting": {"enabled": RATE_LIMIT_ENABLED, "per_tool_limits": _RATE_LIMITS},
        },
    )
    return ToolCallingAgent(config).create_app()


app = create_app()


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("AGENT_PORT", "8120"))
    uvicorn.run("agents.tool_calling_agent:app", host="0.0.0.0", port=port, reload=True)
