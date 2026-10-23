"""TCP JSONL 机器适配器。"""

from __future__ import annotations

import socket
import time
from typing import Any

from ..protocol import LineFramer, MachineError, ProtocolError, RequestTracker, encode_message
from .base import EventCallback, MachineBackend


class TcpBackend(MachineBackend):
    name = "TCP Machine"

    def __init__(self, host: str, port: int, timeout: float = 10.0, on_event: EventCallback | None = None) -> None:
        super().__init__(on_event)
        self.host = host
        self.port = port
        self.timeout = timeout
        self._socket: socket.socket | None = None
        self._framer = LineFramer()
        self._tracker = RequestTracker(self._emit)
        self._messages: list[dict[str, Any]] = []

    @property
    def connected(self) -> bool:
        return self._socket is not None

    def connect(self) -> dict[str, Any]:
        if self._socket is not None:
            return self.command("status")
        try:
            self._socket = socket.create_connection((self.host, self.port), timeout=3.0)
            self._socket.settimeout(0.2)
        except OSError as exc:
            self._socket = None
            raise MachineError(f"无法连接 {self.host}:{self.port} — {exc}") from exc
        self._framer.reset()
        self._messages.clear()
        try:
            result = self.command("status", timeout=3.0)
        except Exception:
            self.disconnect()
            raise
        self._emit("state", {"state": str(result.get("state", "ready"))})
        self._emit("log", {"level": "INFO", "message": f"TCP 已连接 {self.host}:{self.port}"})
        return result

    def disconnect(self) -> None:
        if self._socket is not None:
            try:
                self._socket.close()
            except OSError:
                pass
            self._socket = None
        self._emit("state", {"state": "offline"})

    def command(self, command: str, timeout: float | None = None, **args: Any) -> dict[str, Any]:
        self._require_connected()
        request = self._tracker.make_request(command, args)
        assert self._socket is not None
        try:
            self._socket.sendall(encode_message(request))
        except OSError as exc:
            self.disconnect()
            raise MachineError(f"发送失败，连接已断开: {exc}") from exc
        return self._wait_response(int(request["id"]), timeout or self.timeout)

    def _wait_response(self, request_id: int, timeout: float) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            while self._messages:
                message = self._messages.pop(0)
                if self._tracker.consume(message):
                    continue
                if message.get("id") == request_id:
                    return RequestTracker.validate_response(message, request_id)
            self._receive()
        raise MachineError(f"等待机器响应超时（{timeout:.1f}s）")

    def _receive(self) -> None:
        assert self._socket is not None
        try:
            data = self._socket.recv(65536)
        except socket.timeout:
            return
        except OSError as exc:
            self.disconnect()
            raise MachineError(f"接收失败，连接已断开: {exc}") from exc
        if not data:
            self.disconnect()
            raise MachineError("机器主动关闭了连接")
        try:
            self._messages.extend(self._framer.feed(data))
        except ProtocolError:
            self._framer.reset()
            raise
