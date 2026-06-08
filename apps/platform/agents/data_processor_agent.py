"""Data Processor Agent — 独立 FastAPI 服务

数据处理 Agent：提取、清洗、转换、校验结构化数据。

任务类型: data.process, data.extract, data.transform, data.clean, data.convert

输入:  source data + operation + rules
输出:  transformed result

启动:     python -m agents.data_processor_agent --port 8110
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
from typing import Any

import httpx

from agents.base_agent import AgentConfig, BaseAgent

# --- 可选依赖 ---
try:
    import yaml as yaml_lib
    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False

try:
    import jsonschema
    _HAS_JSONSCHEMA = True
except ImportError:
    _HAS_JSONSCHEMA = False


class DataProcessorAgent(BaseAgent):
    """Data Processor Agent — 数据处理。"""

    def supported_task_types(self) -> list[str]:
        return ["data.process", "data.extract", "data.transform", "data.clean", "data.enrich", "data.validate", "data.convert"]

    async def execute(self, task_type: str, payload: dict[str, Any], trace_id: str | None) -> dict[str, Any]:
        operation = str(payload.get("operation", task_type.split(".")[-1] if "." in task_type else "transform"))
        data = payload.get("data", {}) if isinstance(payload.get("data"), dict) else {}
        rules = payload.get("rules", []) if isinstance(payload.get("rules"), list) else []
        schema_hint = payload.get("schema_hint")
        json_schema = payload.get("json_schema")
        chunk_size = payload.get("chunk_size")
        stream_mode = bool(payload.get("stream", False))

        # --- 格式转换 ---
        if task_type == "data.convert" or operation == "convert":
            return self._do_convert(payload)

        # --- JSON Schema 校验 ---
        if json_schema and _HAS_JSONSCHEMA:
            validation_result = self._validate_json_schema(data, json_schema)
            if not validation_result.get("valid", True):
                return {"operation": "validate_schema", "result": validation_result, "error": "Schema validation failed"}

        # --- 分块处理 + 流模式 ---
        if chunk_size and isinstance(chunk_size, int) and chunk_size > 0:
            raw_data = payload.get("data")
            chunks = self._split_into_chunks(raw_data, chunk_size)
            all_results = []
            for i, chunk in enumerate(chunks):
                chunk_payload = {**payload, "data": chunk}
                chunk_result = await self._execute_single(operation, chunk_payload, schema_hint, trace_id)
                chunk_result["_chunk_index"] = i
                all_results.append(chunk_result)
            if stream_mode:
                return {
                    "operation": f"{operation}_stream",
                    "chunk_count": len(all_results),
                    "total_processed": sum(r.get("processed_count", 0) for r in all_results),
                    "result": {"chunks": all_results},
                }
            # 合并结果
            merged = self._merge_chunk_results(all_results)
            return {"operation": operation, "result": merged, "processed_count": len(all_results), "chunked": True}

        return await self._execute_single(operation, payload, schema_hint, trace_id)

    async def _execute_single(self, operation: str, payload: dict[str, Any], schema_hint: dict | None, trace_id: str | None) -> dict[str, Any]:
        data = payload.get("data", {}) if isinstance(payload.get("data"), dict) else {}
        rules = payload.get("rules", []) if isinstance(payload.get("rules"), list) else []

        handlers = {
            "extract": self._do_extract,
            "transform": self._do_transform,
            "clean": self._do_clean,
            "enrich": self._do_enrich,
            "validate": self._do_validate,
            "process": self._do_transform,
        }
        handler = handlers.get(operation, self._do_transform)
        result = handler(data, rules, schema_hint, payload)
        return {"operation": operation, "result": result, "processed_count": 1}

    # ------------------------------------------------------------------
    # 操作实现
    # ------------------------------------------------------------------

    def _do_extract(self, data: dict, rules: list, schema: dict | None, payload: dict) -> dict:
        fields = [r.get("field", r.get("key", "")) for r in rules]
        if not fields:
            return data
        extracted = {}
        for field in fields:
            if field in data:
                extracted[field] = data[field]
        return extracted if extracted else data

    def _do_transform(self, data: dict, rules: list, schema: dict | None, payload: dict) -> dict:
        result: dict[str, Any] = dict(data)
        for rule in rules:
            field = rule.get("field", "")
            action = rule.get("action", "")
            value = rule.get("value")
            if not field:
                continue
            if action == "rename":
                new_name = str(value)
                if field in result:
                    result[new_name] = result.pop(field)
            elif action == "set":
                result[field] = value
            elif action == "delete":
                result.pop(field, None)
            elif action == "cast":
                cast_type = str(value)
                if field in result:
                    try:
                        if cast_type == "int":
                            result[field] = int(result[field])
                        elif cast_type == "float":
                            result[field] = float(result[field])
                        elif cast_type == "str":
                            result[field] = str(result[field])
                        elif cast_type == "bool":
                            result[field] = bool(result[field])
                        elif cast_type == "json":
                            result[field] = json.loads(result[field]) if isinstance(result[field], str) else result[field]
                    except (ValueError, TypeError, json.JSONDecodeError):
                        pass
        return result

    def _do_clean(self, data: dict, rules: list, schema: dict | None, payload: dict) -> dict:
        result: dict[str, Any] = {}
        for key, value in data.items():
            if value is None or value == "":
                continue
            if isinstance(value, str):
                cleaned = value.strip()
                cleaned = re.sub(r"\s+", " ", cleaned)  # 合并多余空格
                if cleaned:
                    result[key] = cleaned
            else:
                result[key] = value
        return result

    def _do_enrich(self, data: dict, rules: list, schema: dict | None, payload: dict) -> dict:
        result: dict[str, Any] = dict(data)
        context = payload.get("context", {})
        for rule in rules:
            field = rule.get("field", "")
            source = rule.get("source", "")
            if field and source and source in context:
                result[field] = context[source]
        return result

    def _do_validate(self, data: dict, rules: list, schema: dict | None, payload: dict) -> dict:
        errors: list[str] = []
        if schema:
            for field, expected_type in schema.items():
                if field in data:
                    val = data[field]
                    if expected_type == "string" and not isinstance(val, str):
                        errors.append(f"Field '{field}' expected string, got {type(val).__name__}")
                    elif expected_type == "number" and not isinstance(val, (int, float)):
                        errors.append(f"Field '{field}' expected number, got {type(val).__name__}")
                    elif expected_type == "list" and not isinstance(val, list):
                        errors.append(f"Field '{field}' expected list, got {type(val).__name__}")
        for rule in rules:
            field = rule.get("field", "")
            required = rule.get("required", False)
            if required and field not in data:
                errors.append(f"Required field '{field}' missing")
        return {"valid": len(errors) == 0, "errors": errors, "data": data}

    # ------------------------------------------------------------------
    # 分块处理
    # ------------------------------------------------------------------

    def _split_into_chunks(self, data: Any, chunk_size: int) -> list[Any]:
        """将大数据集按 chunk_size 拆分。支持 list 和 dict 类型。"""
        if isinstance(data, list):
            return [data[i:i + chunk_size] for i in range(0, len(data), chunk_size)]
        if isinstance(data, dict):
            items = list(data.items())
            chunks: list[dict] = []
            for i in range(0, len(items), chunk_size):
                chunks.append(dict(items[i:i + chunk_size]))
            return chunks
        # 单条数据，不拆分
        return [data]

    def _merge_chunk_results(self, results: list[dict]) -> dict | list | Any:
        """合并分块处理结果。"""
        merged_data: dict[str, Any] = {}
        merged_list: list[Any] = []
        is_list = False
        for r in results:
            inner = r.get("result", r)
            if isinstance(inner, dict):
                merged_data.update(inner)
            elif isinstance(inner, list):
                merged_list.extend(inner)
                is_list = True
            else:
                return inner  # 单一类型，返回最后一条（覆盖模式）
        if is_list and not merged_data:
            return merged_list
        if merged_list and merged_data:
            return merged_list
        return merged_data if merged_data else merged_list

    # ------------------------------------------------------------------
    # JSON Schema 校验
    # ------------------------------------------------------------------

    def _validate_json_schema(self, data: Any, schema: dict) -> dict:
        """使用 jsonschema 库校验数据。"""
        if not _HAS_JSONSCHEMA:
            return {"valid": True, "warning": "jsonschema not installed, skipping validation"}
        try:
            jsonschema.validate(instance=data, schema=schema)
            return {"valid": True, "errors": []}
        except jsonschema.ValidationError as e:
            return {"valid": False, "errors": [{"path": list(e.absolute_path), "message": e.message}]}
        except jsonschema.SchemaError as e:
            return {"valid": False, "errors": [{"path": [], "message": f"Schema error: {e.message}"}]}

    # ------------------------------------------------------------------
    # 格式转换: CSV ↔ JSON ↔ YAML
    # ------------------------------------------------------------------

    def _do_convert(self, payload: dict) -> dict[str, Any]:
        """执行 data.convert 任务，支持 CSV↔JSON↔YAML 转换。"""
        data = payload.get("data")
        source_format = str(payload.get("source_format", "")).lower()
        target_format = str(payload.get("target_format", "")).lower()

        # 自动检测源格式
        if not source_format and isinstance(data, str):
            data_stripped = data.strip()
            if data_stripped.startswith("{") or data_stripped.startswith("["):
                source_format = "json"
            elif ":" in data_stripped and ("\n" in data_stripped or data_stripped.count("\n") >= 1):
                source_format = "yaml"
            else:
                source_format = "csv"
        elif not source_format:
            if isinstance(data, (dict, list)):
                source_format = "json"
            else:
                source_format = "csv"

        # 统一转换路径
        intermediate: dict | list | None = None

        if source_format == "csv":
            intermediate = self._csv_to_dicts(data)
        elif source_format == "json":
            intermediate = json.loads(data) if isinstance(data, str) else data
        elif source_format == "yaml":
            if _HAS_YAML:
                intermediate = yaml_lib.safe_load(data) if isinstance(data, str) else data
            else:
                return {"operation": "convert", "error": "yaml library not installed", "result": None}

        if target_format == "json":
            result = json.dumps(intermediate, ensure_ascii=False, indent=2) if intermediate is not None else ""
        elif target_format == "csv":
            result = self._dicts_to_csv(intermediate) if isinstance(intermediate, list) else ""
        elif target_format == "yaml":
            if _HAS_YAML:
                result = yaml_lib.dump(intermediate, allow_unicode=True, default_flow_style=False) if intermediate is not None else ""
            else:
                return {"operation": "convert", "error": "yaml library not installed", "result": None}
        else:
            # 默认按目标格式返回
            result = intermediate

        return {
            "operation": "convert",
            "source_format": source_format,
            "target_format": target_format,
            "result": result,
        }

    def _csv_to_dicts(self, data: str | list) -> list[dict]:
        """将 CSV 字符串转为 dict 列表。"""
        if isinstance(data, list):
            return data
        reader = csv.DictReader(io.StringIO(str(data)))
        return [dict(row) for row in reader]

    def _dicts_to_csv(self, data: list[dict]) -> str:
        """将 dict 列表转为 CSV 字符串。"""
        if not data:
            return ""
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=list(data[0].keys()))
        writer.writeheader()
        for row in data:
            writer.writerow(row)
        return output.getvalue()


# =========================================================================
# 入口
# =========================================================================


def create_app():
    config = AgentConfig(
        agent_key=os.getenv("AGENT_KEY", "data-processor-agent"),
        agent_name=os.getenv("AGENT_NAME", "Data Processor Agent"),
        base_url=os.getenv("AGENT_BASE_URL", "http://127.0.0.1:8110"),
        task_types=["data.process", "data.extract", "data.transform", "data.clean", "data.enrich", "data.validate", "data.convert"],
        capabilities={"kind": "data_processor", "operations": ["extract", "transform", "clean", "enrich", "validate", "convert"]},
    )
    return DataProcessorAgent(config).create_app()


app = create_app()


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("AGENT_PORT", "8110"))
    uvicorn.run("agents.data_processor_agent:app", host="0.0.0.0", port=port, reload=True)
