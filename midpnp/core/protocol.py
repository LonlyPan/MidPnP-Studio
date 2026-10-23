"""JSON Lines 机器协议。

帧格式：UTF-8 JSON + ``\\n``，请求/响应/事件共享同一通道。

请求: {"id": 12, "cmd": "move", "args": {"x": 120.5, "y": 88.0}}
响应: {"id": 12, "ok": true, "result": {...}} 或 {"id": 12, "ok": false, "error": "..."}
事件: {"event": "state", "data": {"state": "ready"}}
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable


class ProtocolError(RuntimeError):
    pass


class MachineError(RuntimeError):
    pass


def encode_message(message: dict[str, Any]) -> bytes:
    try:
        text = json.dumps(message, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ProtocolError(f"无法编码消息: {exc}") from exc
    return text.encode("utf-8") + b"\n"


class LineFramer:
    """增量解析 JSONL 数据，支持半包/粘包。"""

    def __init__(self, max_buffer: int = 2 * 1024 * 1024) -> None:
        self._buffer = bytearray()
        self._max_buffer = max_buffer

    def feed(self, data: bytes) -> list[dict[str, Any]]:
        if not data:
            return []
        self._buffer.extend(data)
        if len(self._buffer) > self._max_buffer:
            self._buffer.clear()
            raise ProtocolError("接收缓冲区溢出，已丢弃数据")
        messages: list[dict[str, Any]] = []
        while True:
            newline = self._buffer.find(b"\n")
            if newline < 0:
                break
            raw = bytes(self._buffer[:newline]).strip()
            del self._buffer[: newline + 1]
            if not raw:
                continue
            try:
                decoded = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ProtocolError(f"收到非法协议帧: {raw[:120]!r}") from exc
            if not isinstance(decoded, dict):
                raise ProtocolError("协议帧必须是 JSON 对象")
            messages.append(decoded)
        return messages

    def reset(self) -> None:
        self._buffer.clear()


@dataclass
class PendingRequest:
    request_id: int
    command: str
    created_at: float


class RequestTracker:
    """生成请求 ID 并分发事件回调。"""

    def __init__(self, event_callback: Callable[[str, dict[str, Any]], None] | None = None) -> None:
        self._next_id = 0
        self._events = event_callback

    @property
    def next_id(self) -> int:
        self._next_id += 1
        return self._next_id

    def make_request(self, command: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
        if not command or not isinstance(command, str):
            raise ProtocolError("命令名不能为空")
        return {"id": self.next_id, "cmd": command, "args": args or {}}

    def consume(self, message: dict[str, Any]) -> bool:
        """如果是事件帧则派发并返回 True；响应帧返回 False。"""
        if "event" in message:
            event = str(message.get("event", "unknown"))
            data = message.get("data") if isinstance(message.get("data"), dict) else {}
            if self._events:
                self._events(event, data)
            return True
        return False

    @staticmethod
    def validate_response(message: dict[str, Any], request_id: int) -> dict[str, Any]:
        if message.get("id") != request_id:
            raise ProtocolError(f"响应 ID {message.get('id')} 与请求 {request_id} 不匹配")
        if not message.get("ok", False):
            error = message.get("error") or "机器返回未知错误"
            raise MachineError(str(error))
        result = message.get("result", {})
        return result if isinstance(result, dict) else {"value": result}


def parse_status(result: dict[str, Any]) -> dict[str, Any]:
    """统一整理机器状态字段。"""
    return {
        "state": str(result.get("state", "ready")).lower(),
        "x": float(result.get("x", 0.0)),
        "y": float(result.get("y", 0.0)),
        "z": float(result.get("z", 0.0)),
        "vacuum": bool(result.get("vacuum", False)),
        "nozzle": str(result.get("nozzle", "N1")),
    }
