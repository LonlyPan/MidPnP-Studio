"""机器适配器抽象。"""

from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from typing import Any, Callable

from ..protocol import MachineError


EventCallback = Callable[[str, dict[str, Any]], None]


class MachineBackend(ABC):
    """同步命令式机器适配器。

    实例由机器工作线程独占；UI 线程只能通过 MachineService 访问。
    """

    name = "Machine"

    def __init__(self, on_event: EventCallback | None = None) -> None:
        self._on_event = on_event
        self._abort = threading.Event()

    def _emit(self, event: str, data: dict[str, Any] | None = None) -> None:
        if self._on_event:
            self._on_event(event, data or {})

    def request_stop(self) -> None:
        """从其他线程请求中止当前阻塞动作（由适配器在安全点检查）。"""
        self._abort.set()

    def clear_stop(self) -> None:
        self._abort.clear()

    @abstractmethod
    def connect(self) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def disconnect(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def command(self, command: str, **args: Any) -> dict[str, Any]:
        raise NotImplementedError

    @property
    @abstractmethod
    def connected(self) -> bool:
        raise NotImplementedError

    def _require_connected(self) -> None:
        if not self.connected:
            raise MachineError("机器未连接")
