"""机器服务：串行化命令执行、生产任务编排与 Qt 信号桥接。"""

from __future__ import annotations

import queue
import threading
import time
from datetime import datetime
from typing import Any

from PySide6.QtCore import QObject, Signal

from ...config import AppSettings
from ..models import Feeder, JobPlan, MachineState, new_id, now_iso
from ..protocol import MachineError
from .serial_link import SerialBackend
from .simulator import SimulatorBackend
from .tcp import TcpBackend


_PHASE_LABELS = {
    "preparing": "准备生产",
    "moving_to_feeder": "前往供料器",
    "picking": "取料",
    "moving_to_board": "搬运至板面",
    "placing": "贴装",
    "placed": "贴装完成",
}


class MachineService(QObject):
    connection_changed = Signal(bool, str)
    state_changed = Signal(str)
    position_changed = Signal(float, float, float)
    vacuum_changed = Signal(bool)
    telemetry = Signal(dict)
    log = Signal(str, str, str)
    run_started = Signal(dict)
    run_progress = Signal(dict)
    run_finished = Signal(dict)
    notification = Signal(str, str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._commands: queue.Queue[tuple[str, dict[str, Any]] | None] = queue.Queue()
        self._thread = threading.Thread(target=self._worker_loop, name="machine-io", daemon=True)
        self._backend: Any = None
        self._connected = False
        self._state = MachineState.OFFLINE
        self._state_lock = threading.RLock()
        self._run_active = False
        self._pause_event = threading.Event()
        self._stop_event = threading.Event()
        self._estop_event = threading.Event()
        self._shutdown = threading.Event()
        self._thread.start()

    # ---------------- public properties ----------------

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def state(self) -> MachineState:
        with self._state_lock:
            return self._state

    @property
    def run_active(self) -> bool:
        return self._run_active

    # ---------------- lifecycle ----------------

    def connect_machine(self, settings: AppSettings, feeders: list[Feeder]) -> None:
        if self._run_active:
            self.notification.emit("生产进行中，无法重新连接", "warning")
            return
        self._set_state(MachineState.CONNECTING)
        self.connection_changed.emit(False, "正在连接…")
        self.log.emit("INFO", "LINK", f"正在连接：{settings.connection_mode}")
        self._commands.put(("connect", {"settings": settings.to_dict(), "feeders": [f.to_dict() for f in feeders]}))

    def disconnect_machine(self) -> None:
        if self._run_active:
            self.stop()
        self._commands.put(("disconnect", {}))

    def shutdown(self) -> None:
        self._shutdown.set()
        self._stop_event.set()
        self._pause_event.clear()
        backend = self._backend
        if backend is not None:
            try:
                backend.request_stop()
            except Exception:
                pass
        self._commands.put(None)
        self._thread.join(timeout=1.5)

    def _worker_loop(self) -> None:
        while not self._shutdown.is_set():
            try:
                item = self._commands.get(timeout=0.2)
            except queue.Empty:
                continue
            if item is None:
                break
            name, payload = item
            try:
                if name == "connect":
                    self._do_connect(payload["settings"], payload["feeders"])
                elif name == "disconnect":
                    self._do_disconnect()
                elif name == "job":
                    self._do_job(payload["plan"])
                elif name == "command":
                    self._do_command(payload["command"], payload["args"])
                elif name == "estop":
                    self._do_estop()
                elif name == "sync_feeders":
                    self._do_sync_feeders(payload["feeders"])
            except Exception as exc:  # 工作线程兜底，避免静默退出
                self.log.emit("ERROR", "SYSTEM", f"机器线程异常：{exc}")
                self.notification.emit(f"机器异常：{exc}", "error")
                self._set_state(MachineState.ERROR)
                self.connection_changed.emit(False, f"异常：{exc}")

    def _do_connect(self, settings_data: dict[str, Any], feeders_data: list[dict[str, Any]]) -> None:
        self._do_disconnect()
        settings = AppSettings.from_dict(settings_data)
        feeders = [Feeder.from_dict(item) for item in feeders_data]
        backend: Any
        mode = settings.connection_mode
        try:
            if mode == "simulator":
                backend = SimulatorBackend(
                    feeders=feeders,
                    limits=settings.limits,
                    speed_factor=settings.simulation_speed,
                    on_event=self._on_backend_event,
                )
            elif mode == "tcp":
                backend = TcpBackend(settings.host, settings.port, on_event=self._on_backend_event)
            elif mode == "serial":
                backend = SerialBackend(settings.serial_port, settings.baud_rate, on_event=self._on_backend_event)
            else:
                raise MachineError(f"未知连接模式：{mode}")
            self._backend = backend
            status = backend.connect()
            self._connected = True
            label = {
                "simulator": f"模拟器 · {settings.machine_name}",
                "tcp": f"TCP · {settings.host}:{settings.port}",
                "serial": f"串口 · {settings.serial_port}",
            }[mode]
            self.connection_changed.emit(True, label)
            self.log.emit("INFO", "LINK", f"设备已连接（{label}）")
            self._apply_status(status)
        except Exception as exc:
            self._connected = False
            self._backend = None
            self.connection_changed.emit(False, f"连接失败：{exc}")
            self.log.emit("ERROR", "LINK", f"连接失败：{exc}")
            self.notification.emit(f"连接失败：{exc}", "error")
            self._set_state(MachineState.ERROR)

    def _do_disconnect(self) -> None:
        if self._backend is not None:
            try:
                self._backend.disconnect()
            except Exception:
                pass
        self._backend = None
        self._connected = False
        self.connection_changed.emit(False, "未连接")
        self._set_state(MachineState.OFFLINE)

    def _do_sync_feeders(self, feeders_data: list[dict[str, Any]]) -> None:
        if self._backend is None:
            return
        feeders = [Feeder.from_dict(item) for item in feeders_data]
        setter = getattr(self._backend, "set_feeders", None)
        if callable(setter):
            setter(feeders)

    # ---------------- manual commands ----------------

    def command(self, command: str, **args: Any) -> None:
        if not self._connected:
            self.notification.emit("设备未连接", "warning")
            return
        if self._run_active and command not in {"status"}:
            self.notification.emit("生产进行中，手动命令已锁定", "warning")
            return
        self._commands.put(("command", {"command": command, "args": args}))

    def home(self) -> None:
        if self._run_active:
            self.notification.emit("生产进行中，无法回原点", "warning")
            return
        self._set_state(MachineState.HOMING)
        self.command("home")

    def jog(self, dx: float = 0.0, dy: float = 0.0, dz: float = 0.0, speed: float | None = None) -> None:
        self.command("jog", dx=dx, dy=dy, dz=dz, speed=speed)

    def move_to(self, x: float, y: float, z: float | None = None, speed: float | None = None) -> None:
        self.command("move", x=x, y=y, z=z, speed=speed)

    def vacuum(self, on: bool) -> None:
        self.command("vacuum", on=on)

    def feed(self, slot: int, count: int = 1) -> None:
        self.command("feed", slot=slot, count=count)

    def conveyor(self, action: str) -> None:
        self.command("conveyor", action=action)

    def nozzle(self, nozzle: str) -> None:
        self.command("nozzle", nozzle=nozzle)

    def sync_feeders(self, feeders: list[Feeder]) -> None:
        """在连接状态下同步料站余料/坐标，无需重连。"""
        if self._connected:
            self._commands.put(("sync_feeders", {"feeders": [f.to_dict() for f in feeders]}))

    def lights(self, on: bool) -> None:
        self.command("lights", on=on)

    def clear_fault(self) -> None:
        if self._run_active:
            self.notification.emit("请先停止当前任务", "warning")
            return
        self._estop_event.clear()
        self._stop_event.clear()
        self._pause_event.clear()
        if self._connected:
            self.command("clear_fault")
            self._set_state(MachineState.IDLE)
        else:
            self._set_state(MachineState.OFFLINE)
        self.notification.emit("报警已复位", "info")

    def _do_command(self, command: str, args: dict[str, Any]) -> None:
        if self._backend is None:
            raise MachineError("机器未连接")
        try:
            result = self._backend.command(command, **args)
            if command == "status":
                self._apply_status(result)
        except MachineError as exc:
            self.log.emit("ERROR", "MACHINE", str(exc))
            self.notification.emit(str(exc), "error")

    # ---------------- production ----------------

    def start_job(self, plan: JobPlan) -> bool:
        if not self._connected:
            self.notification.emit("设备未连接，无法开始生产", "warning")
            return False
        if self._run_active:
            self.notification.emit("已有生产任务在运行", "warning")
            return False
        if self._estop_event.is_set() or self.state is MachineState.ESTOP:
            self.notification.emit("急停未复位，无法开始生产", "error")
            return False
        if self.state not in {MachineState.READY, MachineState.IDLE}:
            self.notification.emit(f"设备当前状态（{self.state.value}）不允许开始生产", "warning")
            return False
        if not plan.steps:
            self.notification.emit("没有可执行的贴装点", "warning")
            return False
        self._run_active = True
        self._pause_event.clear()
        self._stop_event.clear()
        self._commands.put(("job", {"plan": plan.to_dict()}))
        self.run_started.emit(
            {
                "run_id": new_id("RUN-"),
                "product_id": plan.product_id,
                "product_name": plan.product_name,
                "total": plan.total,
                "estimated_cycle_s": plan.estimated_cycle_s,
                "started_at": now_iso(),
            }
        )
        return True

    def pause(self) -> None:
        if not self._run_active or self.state is not MachineState.RUNNING:
            return
        self._pause_event.set()
        self._set_state(MachineState.PAUSED)
        self.log.emit("INFO", "JOB", "生产已暂停")
        self.notification.emit("生产已暂停", "info")

    def resume(self) -> None:
        if not self._run_active or self.state is not MachineState.PAUSED:
            return
        self._pause_event.clear()
        self._set_state(MachineState.RUNNING)
        self.log.emit("INFO", "JOB", "生产继续")
        self.notification.emit("生产继续", "info")

    def stop(self) -> None:
        if not self._run_active:
            return
        self._stop_event.set()
        self._pause_event.clear()
        backend = self._backend
        if backend is not None:
            backend.request_stop()
        self.log.emit("WARN", "JOB", "操作员请求停止生产")

    def emergency_stop(self) -> None:
        self._estop_event.set()
        self._stop_event.set()
        self._pause_event.clear()
        backend = self._backend
        if backend is not None:
            backend.request_stop()
        self._set_state(MachineState.ESTOP)
        self.connection_changed.emit(self._connected, "急停已触发" if self._connected else "未连接")
        self.log.emit("ERROR", "SAFETY", "急停按钮被按下")
        self.notification.emit("急停已触发 — 请排除风险后复位", "error")
        self._commands.put(("estop", {}))

    def _do_estop(self) -> None:
        if self._backend is None:
            return
        try:
            self._backend.command("estop")
        except Exception:
            pass

    def _wait_if_paused(self) -> None:
        while self._pause_event.is_set() and not self._stop_event.is_set() and not self._estop_event.is_set():
            time.sleep(0.05)

    def _should_abort(self) -> bool:
        return self._stop_event.is_set() or self._estop_event.is_set() or self._shutdown.is_set()

    def _do_job(self, plan_data: dict[str, Any]) -> None:
        if self._backend is None:
            self._run_active = False
            self._set_state(MachineState.ERROR)
            return
        self._backend.clear_stop()
        steps: list[dict[str, Any]] = list(plan_data.get("steps", []))
        total = len(steps)
        placed = 0
        failed = 0
        feeder_usage: dict[str, int] = {}
        started = datetime.now()
        started_iso = started.isoformat(timespec="seconds")
        status = "Completed"
        self._set_state(MachineState.RUNNING)
        self.log.emit("INFO", "JOB", f"开始生产 {plan_data.get('product_name', '')}，共 {total} 点")
        self.run_progress.emit(
            {
                "phase": "preparing",
                "phase_label": _PHASE_LABELS["preparing"],
                "index": 0,
                "total": total,
                "placed": 0,
                "failed": 0,
            }
        )
        try:
            for step in steps:
                if self._should_abort():
                    status = "E-Stopped" if self._estop_event.is_set() else "Cancelled"
                    break
                self._wait_if_paused()
                if self._should_abort():
                    status = "E-Stopped" if self._estop_event.is_set() else "Cancelled"
                    break
                index = int(step.get("index", 0))
                refdes = str(step.get("refdes", ""))
                pick = step.get("pick", {})
                place = step.get("place", {})
                slot = int(step.get("feeder_slot", 0))
                nozzle = str(step.get("nozzle", "N1"))
                feeder_id = str(step.get("feeder_id", ""))
                self.run_progress.emit(
                    {
                        "phase": "moving_to_feeder",
                        "phase_label": f"{_PHASE_LABELS['moving_to_feeder']} · {refdes}",
                        "index": index,
                        "total": total,
                        "refdes": refdes,
                        "placed": placed,
                        "failed": failed,
                    }
                )
                self._backend.command(
                    "move",
                    x=float(pick.get("x", 0)),
                    y=float(pick.get("y", 0)),
                    z=float(pick.get("z", 0)),
                )
                self._backend.command("pick", slot=slot, nozzle=nozzle)
                self._backend.command("feed", slot=slot, count=1)
                feeder_usage[feeder_id] = feeder_usage.get(feeder_id, 0) + 1
                if self._should_abort():
                    status = "E-Stopped" if self._estop_event.is_set() else "Cancelled"
                    break
                self._wait_if_paused()
                self.run_progress.emit(
                    {
                        "phase": "moving_to_board",
                        "phase_label": f"{_PHASE_LABELS['moving_to_board']} · {refdes}",
                        "index": index,
                        "total": total,
                        "refdes": refdes,
                        "placed": placed,
                        "failed": failed,
                    }
                )
                self._backend.command(
                    "move",
                    x=float(place.get("x", 0)),
                    y=float(place.get("y", 0)),
                    z=10.0,
                )
                self.run_progress.emit(
                    {
                        "phase": "placing",
                        "phase_label": f"{_PHASE_LABELS['placing']} · {refdes}",
                        "index": index,
                        "total": total,
                        "refdes": refdes,
                        "placed": placed,
                        "failed": failed,
                    }
                )
                self._backend.command(
                    "place",
                    x=float(place.get("x", 0)),
                    y=float(place.get("y", 0)),
                    rotation=float(step.get("rotation_deg", 0)),
                )
                placed += 1
                self.run_progress.emit(
                    {
                        "phase": "placed",
                        "phase_label": f"已贴装 {refdes}",
                        "index": index,
                        "total": total,
                        "refdes": refdes,
                        "placed": placed,
                        "failed": failed,
                        "feeder_id": feeder_id,
                        "slot": slot,
                    }
                )
        except MachineError as exc:
            if self._should_abort():
                status = "E-Stopped" if self._estop_event.is_set() else "Cancelled"
            else:
                failed += 1
                status = "Faulted"
                self.log.emit("ERROR", "JOB", f"贴装异常：{exc}")
                self.notification.emit(f"生产异常：{exc}", "error")
        except Exception as exc:
            failed += 1
            status = "Faulted"
            self.log.emit("ERROR", "JOB", f"生产线程异常：{exc}")
        finally:
            finished = datetime.now()
            duration = max(0.0, (finished - started).total_seconds())
            if status != "Completed" and self._backend is not None:
                try:
                    self._backend.command("vacuum", on=False)
                except Exception:
                    pass
            if status == "E-Stopped":
                self._set_state(MachineState.ESTOP)
            elif status == "Faulted":
                self._set_state(MachineState.ERROR)
            else:
                self._set_state(MachineState.READY)
            self._pause_event.clear()
            self._stop_event.clear()
            self._run_active = False
            if self._backend is not None and not self._estop_event.is_set():
                try:
                    self._backend.clear_stop()
                except Exception:
                    pass
            self.run_finished.emit(
                {
                    "run_id": new_id("RUN-"),
                    "product_id": str(plan_data.get("product_id", "")),
                    "product_name": str(plan_data.get("product_name", "")),
                    "started_at": started_iso,
                    "finished_at": finished.isoformat(timespec="seconds"),
                    "duration_s": duration,
                    "total": total,
                    "placed": placed,
                    "failed": failed,
                    "skipped": max(0, total - placed - failed),
                    "status": status,
                    "feeder_usage": feeder_usage,
                }
            )
            self.log.emit(
                "INFO" if status == "Completed" else "WARN",
                "JOB",
                f"生产结束：{status} · {placed}/{total} 点 · {duration:.1f}s",
            )

    # ---------------- backend events ----------------

    def _on_backend_event(self, event: str, data: dict[str, Any]) -> None:
        if event == "position":
            self.position_changed.emit(float(data.get("x", 0)), float(data.get("y", 0)), float(data.get("z", 0)))
        elif event == "state":
            state = str(data.get("state", "ready")).lower()
            mapping = {
                "offline": MachineState.OFFLINE,
                "connecting": MachineState.CONNECTING,
                "idle": MachineState.IDLE,
                "homing": MachineState.HOMING,
                "ready": MachineState.READY,
                "running": MachineState.RUNNING,
                "paused": MachineState.PAUSED,
                "error": MachineState.ERROR,
                "estop": MachineState.ESTOP,
            }
            self._set_state(mapping.get(state, MachineState.READY))
        elif event == "vacuum":
            self.vacuum_changed.emit(bool(data.get("on", False)))
        elif event == "log":
            self.log.emit(str(data.get("level", "INFO")), "MACHINE", str(data.get("message", "")))
        else:
            payload = {"type": event}
            payload.update(data)
            self.telemetry.emit(payload)

    def _apply_status(self, status: dict[str, Any]) -> None:
        state = str(status.get("state", "ready")).lower()
        mapping = {
            "offline": MachineState.OFFLINE,
            "idle": MachineState.IDLE,
            "ready": MachineState.READY,
            "error": MachineState.ERROR,
            "estop": MachineState.ESTOP,
        }
        self._set_state(mapping.get(state, MachineState.READY))
        self.position_changed.emit(
            float(status.get("x", 0)), float(status.get("y", 0)), float(status.get("z", 0))
        )
        self.vacuum_changed.emit(bool(status.get("vacuum", False)))

    def _set_state(self, state: MachineState) -> None:
        with self._state_lock:
            changed = self._state != state
            self._state = state
        if changed:
            self.state_changed.emit(state.value)
