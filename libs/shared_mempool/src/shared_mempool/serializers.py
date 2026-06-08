from __future__ import annotations

import base64
import json
import pickle
from dataclasses import dataclass
from typing import Any, Protocol

from .errors import SerializationError


class Serializer(Protocol):
    name: str

    def dumps(self, value: Any) -> bytes:
        ...

    def loads(self, payload: bytes) -> Any:
        ...


@dataclass(frozen=True, slots=True)
class JsonSerializer:
    name: str = "json"

    def dumps(self, value: Any) -> bytes:
        try:
            wrapper = self._wrap(value)
            return json.dumps(wrapper, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise SerializationError(str(exc)) from exc

    def loads(self, payload: bytes) -> Any:
        try:
            raw = json.loads(payload.decode("utf-8"))
            return self._unwrap(raw)
        except (TypeError, ValueError, UnicodeDecodeError) as exc:
            raise SerializationError(str(exc)) from exc

    def _wrap(self, value: Any) -> dict[str, Any]:
        if isinstance(value, bytes):
            return {"t": "bytes", "v": base64.b64encode(value).decode("ascii")}
        if isinstance(value, (str, int, float, bool)) or value is None:
            return {"t": "json", "v": value}
        if isinstance(value, list):
            return {"t": "json", "v": [self._to_jsonable(item) for item in value]}
        if isinstance(value, dict):
            return {"t": "json", "v": self._to_jsonable(value)}
        raise SerializationError(f"json serializer does not support type: {type(value)!r}")

    def _to_jsonable(self, value: Any) -> Any:
        if isinstance(value, bytes):
            return {"__type__": "bytes", "value": base64.b64encode(value).decode("ascii")}
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        if isinstance(value, list):
            return [self._to_jsonable(item) for item in value]
        if isinstance(value, dict):
            return {str(k): self._to_jsonable(v) for k, v in value.items()}
        raise SerializationError(f"json serializer does not support nested type: {type(value)!r}")

    def _unwrap(self, raw: Any) -> Any:
        if not isinstance(raw, dict):
            raise SerializationError("invalid json payload")
        if raw.get("t") == "bytes":
            return base64.b64decode(str(raw.get("v") or "").encode("ascii"))
        if raw.get("t") == "json":
            return self._from_jsonable(raw.get("v"))
        raise SerializationError("invalid json payload")

    def _from_jsonable(self, value: Any) -> Any:
        if isinstance(value, list):
            return [self._from_jsonable(item) for item in value]
        if isinstance(value, dict):
            if value.get("__type__") == "bytes":
                return base64.b64decode(str(value.get("value") or "").encode("ascii"))
            return {k: self._from_jsonable(v) for k, v in value.items()}
        return value


@dataclass(frozen=True, slots=True)
class PickleSerializer:
    name: str = "pickle"
    protocol: int = pickle.HIGHEST_PROTOCOL

    def dumps(self, value: Any) -> bytes:
        try:
            return pickle.dumps(value, protocol=self.protocol)
        except pickle.PickleError as exc:
            raise SerializationError(str(exc)) from exc

    def loads(self, payload: bytes) -> Any:
        try:
            return pickle.loads(payload)
        except pickle.PickleError as exc:
            raise SerializationError(str(exc)) from exc


def get_serializer(name: str | None) -> Serializer:
    actual = (name or "json").strip().lower()
    if actual == "json":
        return JsonSerializer()
    if actual == "pickle":
        return PickleSerializer()
    raise SerializationError(f"unknown serializer: {name}")
