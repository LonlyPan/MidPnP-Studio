"""串口 JSONL 机器适配器（依赖 pyserial，按需安装）。"""

from __future__ import annotations

import time
from typing import Any

from ..protocol import LineFramer, MachineError, ProtocolError, RequestTracker, encode_message
from .base import EventCallback, MachineBackend


class SerialBackend(MachineBackend):
    name = "Serial Machine"

    def __init__(
        self,
        port: str,
        baud_rate: int = 115200,
        timeout: float = 10.0,
        on_event: EventCallback | None = None,
    ) -> None:
        super().__init__(on_event)
        self.port = port
        self.baud_rate = baud_rate
        self.timeout = timeout
        self._serial: Any = None
        self._framer = LineFramer()
        self._tracker = RequestTracker(self._emit)
        self._messages: list[dict[str, Any]] = []

    @property
    def connected(self) -> bool:
        return bool(self._serial is not None and getattr(self._serial, "is_open", False))

    def connect(self) -> dict[str, Any]:
        if self.connected:
            return self.command("status")
        try:
            import serial  # type: ignore
        except ImportError as exc:
            raise MachineError("串口模式需要安装 pyserial：pip install pyserial") from exc
        try:
            self._serial = serial.Serial(self.port, self.baud_rate, timeout=0.2, write_timeout=2.0)
        except Exception as exc:
            self._serial = None
            raise MachineError(f"无法打开串口 {self.port}: {exc}") from exc
        self._framer.reset()
        self._messages.clear()
        try:
            result = self.command("status", timeout=3.0)
        except Exception:
            self.disconnect()
            raise
        self._emit("state", {"state": str(result.get("state", "ready"))})
        self._emit("log", {"level": "INFO", "message": f"串口已连接 {self.port} @ {self.baud_rate}"})
        return result

    def disconnect(self) -> None:
        if self._serial is not None:
            try:
                self._serial.close()
            except Exception:
                pass
            self._serial = None
        self._emit("state", {"state": "offline"})

    def command(self, command: str, timeout: float | None = None, **args: Any) -> dict[str, Any]:
        self._require_connected()
        request = self._tracker.make_request(command, args)
        try:
            self._serial.write(encode_message(request))
            self._serial.flush()
        except Exception as exc:
            self.disconnect()
            raise MachineError(f"串口发送失败: {exc}") from exc
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
        raise MachineError(f"等待串口响应超时（{timeout:.1f}s）")

    def _receive(self) -> None:
        try:
            data = self._serial.readline()
        except Exception as exc:
            self.disconnect()
            raise MachineError(f"串口接收失败: {exc}") from exc
        if not data:
            return
        try:
            self._messages.extend(self._framer.feed(data))
        except ProtocolError:
            self._framer.reset()
            raise
