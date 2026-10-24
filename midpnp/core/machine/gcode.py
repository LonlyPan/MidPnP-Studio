"""G-code 驱动后端。

对应 OpenPnP 的 `GcodeDriver`：把抽象动作（home / move / pick / place / …）
映射为配置文件里的命令模板，模板用 `{变量}` 占位，例如：

    "move": "G1 X{x} Y{y} Z{z} F{speed}"

这样换一台控制器只改 JSON 里的 `driver.commands`，不用改 Python 代码。
支持 TCP 与串口两种链路，应答默认以 `ok` 结束，可在 `ok_responses` 里配置。
"""

from __future__ import annotations

import re
import socket
import threading
import time
from typing import Any

from ..models import Feeder
from ..profiles.schema import MachineProfile, NozzleConfig
from ..protocol import MachineError

_DEFAULT_COMMANDS = {
    "connect": "",
    "home": "G28",
    "move": "G1 X{x} Y{y} Z{z} F{speed}",
    "jog": "G91\nG1 X{dx} Y{dy} Z{dz} F{speed}\nG90",
    "pick": "M42 P{slot} S1\nG4 P{delay}",
    "place": "G4 P{delay}\nM42 P{slot} S0",
    "vacuum": "M42 P{vacuum_pin} S{state}",
    "feed": "G4 P{delay}",
    "nozzle": "T{nozzle_index}",
    "conveyor": "M600 P{action}",
    "lights": "M355 S{state}",
    "estop": "M112",
    "clear_fault": "M999",
    "status": "M114",
}


class _LineTransport:
    """按行收发的链路（TCP / 串口）。"""

    def __init__(self, timeout: float = 10.0) -> None:
        self.timeout = timeout
        self._controller: Any = None
        self._reader: Any = None
        self._lock = threading.RLock()
        self._buffer = b""

    def open(self) -> None:  # pragma: no cover - 由子类实现
        raise NotImplementedError

    def close(self) -> None:
        try:
            if self._reader is not None:
                self._reader.close()
        except Exception:
            pass
        try:
            if self._controller is not None:
                self._controller.close()
        except Exception:
            pass
        self._reader = None
        self._controller = None
        self._buffer = b""

    def write_line(self, line: str) -> None:
        if self._controller is None:
            raise MachineError("G-code 链路未连接")
        self._controller.write((line.rstrip("\r\n") + "\n").encode("utf-8"))
        try:
            self._controller.flush()
        except Exception:
            pass

    def read_line(self, deadline: float) -> str:
        if self._reader is None:
            raise MachineError("G-code 链路未连接")
        while time.time() < deadline:
            if b"\n" in self._buffer:
                raw, self._buffer = self._buffer.split(b"\n", 1)
                return raw.decode("utf-8", errors="replace").strip()
            try:
                chunk = self._reader.readline()
            except (socket.timeout, TimeoutError):
                continue
            except OSError as exc:
                raise MachineError(f"读取失败：{exc}") from exc
            if not chunk:
                raise MachineError("控制器关闭了连接")
            self._buffer += chunk
        raise MachineError("等待控制器应答超时")


class _TcpTransport(_LineTransport):
    def __init__(self, host: str, port: int, timeout: float = 10.0) -> None:
        super().__init__(timeout)
        self.host = host
        self.port = port

    def open(self) -> None:
        try:
            self._controller = socket.create_connection((self.host, self.port), timeout=self.timeout)
            self._controller.settimeout(self.timeout)
            self._reader = self._controller.makefile("rb")
        except OSError as exc:
            raise MachineError(f"无法连接 {self.host}:{self.port}：{exc}") from exc


class _SerialTransport(_LineTransport):
    def __init__(self, port: str, baud_rate: int, timeout: float = 10.0) -> None:
        super().__init__(timeout)
        self.port = port
        self.baud_rate = baud_rate

    def open(self) -> None:
        try:
            import serial  # pyserial
        except ImportError as exc:  # pragma: no cover
            raise MachineError("串口模式需要 pyserial：pip install pyserial") from exc
        try:
            self._controller = serial.Serial(self.port, self.baud_rate, timeout=0.05)
            self._reader = self._controller
        except Exception as exc:
            raise MachineError(f"无法打开串口 {self.port}：{exc}") from exc


class _Vars(dict):
    def __missing__(self, key: str) -> str:  # 未提供的变量按 OpenPnP 语义删除整段
        return ""


class GcodeBackend:
    """把 profile.driver.commands 渲染成实际 G-code 并收发。"""

    def __init__(self, profile: MachineProfile, on_event: Any = None) -> None:
        self.profile = profile
        self.on_event = on_event
        self.driver = profile.driver
        self.commands = dict(_DEFAULT_COMMANDS)
        self.commands.update({key: value for key, value in self.driver.commands.items() if value})
        self._transport: _LineTransport | None = None
        self._stopped = False
        self._state = "offline"
        self._position = (0.0, 0.0, 0.0)
        self._vacuum = False
        self._nozzles = profile.nozzle_ids()

    # ---------------- 生命周期 ----------------

    def connect(self) -> dict[str, Any]:
        transport_type = "tcp" if self.driver.type.endswith("tcp") else "serial"
        if transport_type == "tcp":
            transport: _LineTransport = _TcpTransport(self.driver.host, self.driver.port, self.driver.timeout_s)
        else:
            transport = _SerialTransport(self.driver.serial_port, self.driver.baud_rate, self.driver.timeout_s)
        transport.open()
        self._transport = transport
        if self.driver.connect_delay_ms:
            time.sleep(self.driver.connect_delay_ms / 1000.0)
        self._state = "ready"
        self._emit("state", state="ready")
        status = self.command("status")
        return status

    def disconnect(self) -> None:
        if self._transport is not None:
            self._transport.close()
        self._transport = None
        self._state = "offline"
        self._emit("state", state="offline")

    def request_stop(self) -> None:
        self._stopped = True

    def clear_stop(self) -> None:
        self._stopped = False

    def set_feeders(self, feeders: list[Feeder]) -> None:
        self._feeders = {feeder.slot: feeder for feeder in feeders}

    # ---------------- 命令 ----------------

    def command(self, name: str, **args: Any) -> dict[str, Any]:
        if name == "status":
            return self._status()
        template = self.commands.get(name)
        if not template:
            return {"ok": True, "skipped": name}
        variables = self._variables(name, **args)
        for line in str(template).split("\n"):
            rendered = line.format_map(variables).strip()
            if not rendered:
                continue
            response = self._send(rendered)
            self._handle_response(name, response)
        if name == "move":
            self._position = (
                float(args.get("x", self._position[0])),
                float(args.get("y", self._position[1])),
                float(args.get("z", self._position[2])),
            )
            self._emit("position", x=self._position[0], y=self._position[1], z=self._position[2])
        elif name == "home":
            self._position = (0.0, 0.0, 0.0)
            self._emit("position", x=0.0, y=0.0, z=0.0)
        elif name == "vacuum":
            self._vacuum = bool(args.get("on"))
            self._emit("vacuum", on=self._vacuum)
        return {"ok": True, "command": name}

    def _variables(self, name: str, **args: Any) -> _Vars:
        axes = {axis_id: axis for axis_id, axis in self.profile.axes.items()}
        default_speed = float(self.profile.safety.max_speed_mm_s or 300.0)
        speed = float(args.get("speed") or default_speed)
        nozzle_id = str(args.get("nozzle", ""))
        nozzle: NozzleConfig | None = self.profile.nozzle(nozzle_id) if nozzle_id else None
        delay_ms = 0
        if nozzle is not None:
            delay_ms = int(nozzle.pick_dwell_ms if name == "pick" else nozzle.place_dwell_ms)
        variables = _Vars(
            x=f"{float(args.get('x', 0.0)):.3f}",
            y=f"{float(args.get('y', 0.0)):.3f}",
            z=f"{float(args.get('z', 0.0)):.3f}",
            dx=f"{float(args.get('dx', 0.0)):.3f}",
            dy=f"{float(args.get('dy', 0.0)):.3f}",
            dz=f"{float(args.get('dz', 0.0)):.3f}",
            rotation=f"{float(args.get('rotation', 0.0)):.3f}",
            speed=f"{speed * 60.0:.0f}",
            slot=str(int(args.get("slot", 1))),
            nozzle=nozzle_id,
            nozzle_index=str(self._nozzles.index(nozzle_id) if nozzle_id in self._nozzles else 0),
            delay=f"{delay_ms / 1000.0:.3f}",
            vacuum_pin=str(args.get("pin", 0)),
            state="1" if args.get("on") else "0",
            action=str(args.get("action", "")),
            count=str(int(args.get("count", 1))),
            timeout=f"{self.driver.timeout_s:.1f}",
        )
        if "x" in axes:
            variables.setdefault("x_min", f"{axes['x'].min:.3f}")
            variables.setdefault("x_max", f"{axes['x'].max:.3f}")
        return variables

    def _send(self, line: str) -> str:
        transport = self._transport
        if transport is None:
            raise MachineError("G-code 链路未连接")
        if self._stopped:
            raise MachineError("操作已取消")
        transport.write_line(line)
        deadline = time.time() + self.driver.timeout_s
        while True:
            response = transport.read_line(deadline)
            if not response:
                continue
            lowered = response.lower()
            if "error" in lowered or "!!" in response:
                raise MachineError(f"控制器报错：{response}")
            for token in self.driver.ok_responses or ["ok"]:
                if token.lower() in lowered:
                    return response
            if re.search(r"x:\s*-?\d", lowered):
                return response

    def _handle_response(self, name: str, response: str) -> None:
        lowered = response.lower()
        position = _parse_position(response)
        if position is not None and name != "move":
            self._position = position
            self._emit("position", x=position[0], y=position[1], z=position[2])
        if "error" in lowered:
            self._emit("log", level="ERROR", message=response)

    def _status(self) -> dict[str, Any]:
        template = self.commands.get("status", "")
        position = self._position
        vacuum = self._vacuum
        if template:
            try:
                response = ""
                for line in str(template).split("\n"):
                    if line.strip():
                        response = self._send(line.format_map(_Vars()))
                parsed = _parse_position(response)
                if parsed is not None:
                    position = parsed
                self._position = position
            except MachineError:
                pass
        return {
            "state": self._state,
            "x": position[0],
            "y": position[1],
            "z": position[2],
            "vacuum": vacuum,
        }

    def _emit(self, event: str, **data: Any) -> None:
        if callable(self.on_event):
            try:
                self.on_event(event, data)
            except Exception:
                pass


def _parse_position(text: str) -> tuple[float, float, float] | None:
    match = re.search(
        r"X:\s*(-?\d+(?:\.\d+)?).*?Y:\s*(-?\d+(?:\.\d+)?).*?Z:\s*(-?\d+(?:\.\d+)?)",
        text,
        re.IGNORECASE,
    )
    if not match:
        return None
    return (float(match.group(1)), float(match.group(2)), float(match.group(3)))
