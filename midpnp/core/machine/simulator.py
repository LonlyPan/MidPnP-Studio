"""高保真贴片机模拟器：无硬件也能完整演示取料、贴装与生产流程。"""

from __future__ import annotations

import math
import threading
import time
from typing import Any

from ..models import Feeder, MachineLimits
from ..protocol import MachineError
from .base import EventCallback, MachineBackend


class SimulatorBackend(MachineBackend):
    name = "MidPnP Simulator"

    def __init__(
        self,
        feeders: list[Feeder] | None = None,
        limits: MachineLimits | None = None,
        speed_factor: float = 8.0,
        on_event: EventCallback | None = None,
    ) -> None:
        super().__init__(on_event)
        self.limits = limits or MachineLimits()
        self.speed_factor = max(1.0, float(speed_factor))
        self._feeders: dict[str, Feeder] = {f.id: f for f in (feeders or [])}
        self._closed = True
        self._estopped = False
        self._state = "offline"
        self._homed = True
        self._x = 0.0
        self._y = 0.0
        self._z = self.limits.safe_z_mm
        self._vacuum = False
        self._nozzle = "N1"
        self._conveyor = "stopped"
        self._lights = False
        self._placed = 0
        self._lock = threading.Lock()

    @property
    def connected(self) -> bool:
        return not self._closed

    def set_feeders(self, feeders: list[Feeder]) -> None:
        for feeder in feeders:
            existing = self._feeders.get(feeder.id)
            if existing is not None:
                existing.remaining = feeder.remaining
                existing.component_id = feeder.component_id
                existing.pick_x_mm = feeder.pick_x_mm
                existing.pick_y_mm = feeder.pick_y_mm
                existing.pick_z_mm = feeder.pick_z_mm
                existing.slot = feeder.slot
            else:
                self._feeders[feeder.id] = feeder


    def connect(self) -> dict[str, Any]:
        if not self._closed:
            return self._status()
        self._closed = False
        self._estopped = False
        self._state = "ready" if self._homed else "idle"
        self._sleep(0.35)
        self._emit("state", {"state": self._state})
        self._emit("position", {"x": self._x, "y": self._y, "z": self._z})
        self._emit("log", {"level": "INFO", "message": "模拟器已连接，轴伺服使能"})
        return self._status()

    def disconnect(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._state = "offline"
        self._vacuum = False
        self._emit("state", {"state": "offline"})
        self._emit("log", {"level": "INFO", "message": "模拟器已断开"})

    def command(self, command: str, **args: Any) -> dict[str, Any]:
        self._require_connected()
        if self._estopped and command not in {"status", "clear_fault", "ping"}:
            raise MachineError("急停已触发，请先复位")
        handlers = {
            "ping": self._ping,
            "status": lambda **_: self._status(),
            "home": self._home,
            "move": self._move,
            "jog": self._jog,
            "pick": self._pick,
            "place": self._place,
            "feed": self._feed,
            "vacuum": self._set_vacuum,
            "nozzle": self._set_nozzle,
            "conveyor": self._set_conveyor,
            "lights": self._set_lights,
            "clear_fault": self._clear_fault,
            "estop": self._estop,
            "get_feeders": lambda **_: {"feeders": [f.to_dict() for f in self._feeders.values()]},
        }
        handler = handlers.get(command)
        if handler is None:
            raise MachineError(f"模拟器不支持命令: {command}")
        with self._lock:
            return handler(**args)

    # ---------------- commands ----------------

    def _ping(self, **_: Any) -> dict[str, Any]:
        return {"ok": True, "name": self.name, "version": "1.0"}

    def _status(self) -> dict[str, Any]:
        return {
            "state": self._state,
            "x": round(self._x, 3),
            "y": round(self._y, 3),
            "z": round(self._z, 3),
            "vacuum": self._vacuum,
            "nozzle": self._nozzle,
            "homed": self._homed,
            "conveyor": self._conveyor,
            "lights": self._lights,
            "placed": self._placed,
        }

    def _home(self, **_: Any) -> dict[str, Any]:
        self._transition("homing")
        self._vacuum = False
        self._emit("vacuum", {"on": False})
        self._z = self.limits.safe_z_mm
        self._move_abs(0.0, 0.0, self.limits.safe_z_mm, self.limits.max_speed_mm_s)
        self._homed = True
        self._transition("ready")
        self._emit("log", {"level": "INFO", "message": "回原点完成"})
        return self._status()

    def _move(self, x: float | None = None, y: float | None = None, z: float | None = None, speed: float | None = None, **_: Any) -> dict[str, Any]:
        if self._state not in {"ready", "running", "paused", "idle"}:
            raise MachineError(f"当前状态 {self._state} 不允许移动")
        target_x = self._x if x is None else float(x)
        target_y = self._y if y is None else float(y)
        target_z = self._z if z is None else float(z)
        self._move_abs(target_x, target_y, target_z, float(speed or self.limits.max_speed_mm_s))
        return self._status()

    def _jog(self, dx: float = 0.0, dy: float = 0.0, dz: float = 0.0, speed: float | None = None, **_: Any) -> dict[str, Any]:
        return self._move(
            x=self._x + float(dx),
            y=self._y + float(dy),
            z=self._z + float(dz),
            speed=speed,
        )

    def _move_abs(self, x: float, y: float, z: float, speed: float) -> None:
        if not (0 <= x <= self.limits.travel_x_mm and 0 <= y <= self.limits.travel_y_mm and 0 <= z <= self.limits.travel_z_mm):
            raise MachineError(
                f"目标点超出行程: ({x:.1f}, {y:.1f}, {z:.1f}) / "
                f"({self.limits.travel_x_mm:g}, {self.limits.travel_y_mm:g}, {self.limits.travel_z_mm:g})"
            )
        distance = math.sqrt((x - self._x) ** 2 + (y - self._y) ** 2 + (z - self._z) ** 2)
        if distance < 0.001:
            return
        speed = max(1.0, min(float(speed), self.limits.max_speed_mm_s))
        duration = max(0.04, distance / speed / self.speed_factor)
        steps = max(1, min(16, int(duration / 0.03)))
        start_x, start_y, start_z = self._x, self._y, self._z
        for step in range(1, steps + 1):
            if self._abort.is_set():
                raise MachineError("动作已中止")
            ratio = step / steps
            self._x = start_x + (x - start_x) * ratio
            self._y = start_y + (y - start_y) * ratio
            self._z = start_z + (z - start_z) * ratio
            self._emit("position", {"x": self._x, "y": self._y, "z": self._z})
            time.sleep(duration / steps)
        self._x, self._y, self._z = x, y, z
        self._emit("position", {"x": x, "y": y, "z": z})

    def _pick(self, slot: int | None = None, feeder_id: str = "", nozzle: str | None = None, **_: Any) -> dict[str, Any]:
        feeder = self._find_feeder(slot=slot, feeder_id=feeder_id)
        if feeder is None:
            raise MachineError("未找到供料器")
        if feeder.remaining <= 0:
            raise MachineError(f"供料器 {feeder.slot:02d} 已无余料")
        if nozzle:
            self._nozzle = str(nozzle)
        self._sleep(0.06)
        self._vacuum = True
        self._emit("vacuum", {"on": True})
        self._emit("log", {"level": "DEBUG", "message": f"吸嘴 {self._nozzle} 从槽位 {feeder.slot:02d} 取料"})
        return {"picked": True, "component_id": feeder.component_id, "slot": feeder.slot, "nozzle": self._nozzle}

    def _place(self, x: float | None = None, y: float | None = None, rotation: float = 0.0, **_: Any) -> dict[str, Any]:
        if not self._vacuum:
            raise MachineError("吸嘴无真空，无法贴装")
        if x is not None and y is not None:
            self._move_abs(float(x), float(y), 1.0, self.limits.max_speed_mm_s)
        self._sleep(0.05)
        self._vacuum = False
        self._placed += 1
        self._emit("vacuum", {"on": False})
        self._emit("log", {"level": "DEBUG", "message": f"贴装完成，角度 {rotation:.1f}°"})
        return {"placed": True, "count": self._placed}

    def _feed(self, slot: int | None = None, feeder_id: str = "", count: int = 1, **_: Any) -> dict[str, Any]:
        feeder = self._find_feeder(slot=slot, feeder_id=feeder_id)
        if feeder is None:
            raise MachineError("未找到供料器")
        amount = max(1, int(count))
        if feeder.remaining < amount:
            raise MachineError(f"供料器 {feeder.slot:02d} 余料不足")
        feeder.remaining -= amount
        self._sleep(0.025)
        self._emit("feeder", {"id": feeder.id, "slot": feeder.slot, "remaining": feeder.remaining})
        return {"remaining": feeder.remaining, "slot": feeder.slot}

    def _set_vacuum(self, on: bool = True, **_: Any) -> dict[str, Any]:
        self._vacuum = bool(on)
        self._sleep(0.03)
        self._emit("vacuum", {"on": self._vacuum})
        return {"vacuum": self._vacuum}

    def _set_nozzle(self, nozzle: str = "N1", **_: Any) -> dict[str, Any]:
        index = int(str(nozzle).lstrip("Nn") or "1")
        if not 1 <= index <= self.limits.nozzle_count:
            raise MachineError(f"吸嘴 {nozzle} 不存在")
        self._nozzle = f"N{index}"
        self._sleep(0.04)
        return {"nozzle": self._nozzle}

    def _set_conveyor(self, action: str = "stop", **_: Any) -> dict[str, Any]:
        mapping = {"feed": "feeding", "reverse": "reversing", "stop": "stopped"}
        if action not in mapping:
            raise MachineError(f"传送带动作无效: {action}")
        self._conveyor = mapping[action]
        self._emit("conveyor", {"state": self._conveyor})
        self._sleep(0.1)
        if action != "stop":
            self._conveyor = "stopped"
            self._emit("conveyor", {"state": "stopped"})
        return {"conveyor": self._conveyor}

    def _set_lights(self, on: bool = True, **_: Any) -> dict[str, Any]:
        self._lights = bool(on)
        self._emit("lights", {"on": self._lights})
        return {"lights": self._lights}

    def _clear_fault(self, **_: Any) -> dict[str, Any]:
        self._estopped = False
        self._state = "ready" if self._homed else "idle"
        self._emit("state", {"state": self._state})
        self._emit("log", {"level": "INFO", "message": "报警已复位"})
        return self._status()

    def _estop(self, **_: Any) -> dict[str, Any]:
        self._estopped = True
        self._vacuum = False
        self._conveyor = "stopped"
        self._state = "estop"
        self._emit("vacuum", {"on": False})
        self._emit("state", {"state": "estop"})
        self._emit("log", {"level": "ERROR", "message": "急停触发，伺服已断开"})
        return self._status()

    # ---------------- helpers ----------------

    def _find_feeder(self, slot: int | None, feeder_id: str) -> Feeder | None:
        if feeder_id:
            return self._feeders.get(str(feeder_id))
        if slot is not None:
            for feeder in self._feeders.values():
                if feeder.slot == int(slot):
                    return feeder
        return None

    def _transition(self, state: str) -> None:
        self._state = state
        self._emit("state", {"state": state})

    def _sleep(self, duration: float) -> None:
        remaining = duration / self.speed_factor
        while remaining > 0:
            if self._abort.is_set():
                raise MachineError("动作已中止")
            chunk = min(0.02, remaining)
            time.sleep(chunk)
            remaining -= chunk

    def _err(self, message: str) -> None:
        self._emit("log", {"level": "ERROR", "message": message})
        raise MachineError(message)
