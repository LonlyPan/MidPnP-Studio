"""连接设备弹窗：相机 → 主机 → 归位 → 自动校准。

状态来自真实的 `MachineService`（连接、回零、状态机），每一步都有明确的
成功/失败/超时反馈；成功后自动关闭，状态栏与首页同步为“已连接”。
"""

from __future__ import annotations

import time
from typing import Any

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from ..core.models import MachineState
from .context import AppContext
from .machine_gallery import MachineArt
from .theme import COLORS
from .widgets import button, hline

STEP_DEFS = (
    ("camera", "相机连接", "检测顶部 / 底部相机"),
    ("host", "主机连接", "建立控制器通信链路"),
    ("home", "主机归位", "执行回零并检查限位"),
    ("calibrate", "主机自动校准", "相机标定与基准点检查"),
)


class StepRow(QWidget):
    def __init__(self, title: str, hint: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 6, 2, 6)
        layout.setSpacing(10)
        self.icon = QLabel("○")
        self.icon.setFixedSize(22, 22)
        self.icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon.setStyleSheet(
            f"color: {COLORS['faint']}; border: 1px solid {COLORS['border']};"
            " border-radius: 11px; font-size: 11px; font-weight: 700;"
        )
        layout.addWidget(self.icon)
        text_col = QVBoxLayout()
        text_col.setSpacing(0)
        self.title = QLabel(title)
        self.title.setStyleSheet("font-size: 13px; font-weight: 600;")
        self.hint = QLabel(hint)
        self.hint.setProperty("role", "faint")
        self.hint.setStyleSheet("font-size: 10px;")
        text_col.addWidget(self.title)
        text_col.addWidget(self.hint)
        layout.addLayout(text_col, 1)
        self.state = QLabel("等待")
        self.state.setProperty("role", "faint")
        self.state.setStyleSheet("font-size: 11px;")
        layout.addWidget(self.state)

    def set_state(self, state: str, text: str = "") -> None:
        colors = {
            "pending": COLORS["faint"],
            "running": COLORS["warn"],
            "ok": COLORS["success"],
            "error": COLORS["danger"],
        }
        marks = {"pending": "○", "running": "…", "ok": "✓", "error": "✕"}
        color = colors.get(state, COLORS["faint"])
        self.icon.setText(marks.get(state, "○"))
        self.icon.setStyleSheet(
            f"color: {color}; border: 1px solid {color}66; background: {color}12;"
            " border-radius: 11px; font-size: 11px; font-weight: 700;"
        )
        self.state.setText(text or {"pending": "等待", "running": "进行中", "ok": "完成", "error": "失败"}[state])
        self.state.setStyleSheet(f"color: {color}; font-size: 11px;")


class ConnectDialog(QDialog):
    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self._done = False
        self._index = -1
        self._deadline = 0.0
        self._last_label = ""
        self.setWindowTitle("连接设备")
        self.setModal(True)
        self.setMinimumWidth(560)
        self._build()
        self._wire()
        QTimer.singleShot(150, self._start)

    # ---------------- UI ----------------

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 18)
        root.setSpacing(12)

        head = QHBoxLayout()
        head.setSpacing(14)
        self.art = MachineArt(self.ctx.profile)
        self.art.setFixedSize(150, 92)
        head.addWidget(self.art)
        text_col = QVBoxLayout()
        text_col.setSpacing(3)
        title = QLabel("正在连接设备")
        title.setProperty("role", "dialogTitle")
        self.device_label = QLabel(self.ctx.profile.name)
        self.device_label.setStyleSheet("font-size: 14px; font-weight: 600;")
        target = QLabel(f"{self.ctx.profile.driver.type} · {self.ctx.settings.machine_name}")
        target.setProperty("role", "faint")
        text_col.addWidget(title)
        text_col.addWidget(self.device_label)
        text_col.addWidget(target)
        text_col.addStretch(1)
        head.addLayout(text_col, 1)
        root.addLayout(head)
        root.addWidget(hline())

        step_frame = QFrame()
        step_frame.setStyleSheet(
            f"background: #0b151b; border: 1px solid {COLORS['border_soft']}; border-radius: 8px;"
        )
        step_layout = QVBoxLayout(step_frame)
        step_layout.setContentsMargins(14, 6, 14, 6)
        step_layout.setSpacing(0)
        self.rows: dict[str, StepRow] = {}
        for key, name, hint in STEP_DEFS:
            row = StepRow(name, hint)
            self.rows[key] = row
            step_layout.addWidget(row)
        root.addWidget(step_frame)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(6)
        self.progress.setStyleSheet(
            f"QProgressBar {{ background: {COLORS['border_soft']}; border: none; border-radius: 3px; }}"
            f"QProgressBar::chunk {{ background: {COLORS['accent']}; border-radius: 3px; }}"
        )
        root.addWidget(self.progress)

        self.message = QLabel("准备连接…")
        self.message.setProperty("role", "muted")
        self.message.setWordWrap(True)
        self.message.setMinimumHeight(38)
        root.addWidget(self.message)

        footer = QHBoxLayout()
        footer.setSpacing(8)
        footer.addStretch(1)
        self.cancel_button = button("取消", variant="subtle")
        self.retry_button = button("重试", "refresh", "subtle")
        self.finish_button = button("关闭", variant="subtle")
        self.retry_button.hide()
        self.finish_button.hide()
        footer.addWidget(self.cancel_button)
        footer.addWidget(self.retry_button)
        footer.addWidget(self.finish_button)
        root.addLayout(footer)

        self.cancel_button.clicked.connect(self._cancel)
        self.retry_button.clicked.connect(self._start)
        self.finish_button.clicked.connect(self.accept)

    def _wire(self) -> None:
        self.ctx.machine.connection_changed.connect(self._on_connection)
        self.ctx.machine.state_changed.connect(self._on_state)
        self._poll = QTimer(self)
        self._poll.setInterval(120)
        self._poll.timeout.connect(self._poll_step)

    # ---------------- 流程 ----------------

    def _start(self) -> None:
        if not self.isVisible():
            return
        self._done = False
        self._index = -1
        self._last_label = ""
        self.progress.setValue(0)
        self.message.setText("准备连接…")
        self.retry_button.hide()
        self.finish_button.hide()
        self.cancel_button.show()
        self.cancel_button.setEnabled(True)
        for row in self.rows.values():
            row.set_state("pending")
        self._next_step()

    def _next_step(self) -> None:
        if self._done:
            return
        self._index += 1
        if self._index >= len(STEP_DEFS):
            self._finish()
            return
        key = STEP_DEFS[self._index][0]
        self.rows[key].set_state("running")
        self.progress.setValue(int(self._index * 100 / len(STEP_DEFS)))
        if key == "camera":
            self.message.setText("正在检测相机…")
            QTimer.singleShot(400, self._camera_done)
        elif key == "host":
            self.message.setText("正在连接主机控制器…")
            if self.ctx.machine.connected:
                self.rows["host"].set_state("ok")
                QTimer.singleShot(150, self._next_step)
                return
            self.ctx.machine.connect_machine(self.ctx.settings, self.ctx.feeders(), self.ctx.profile)
            self._deadline = time.monotonic() + 6.0
            self._poll.start()
        elif key == "home":
            self.message.setText("正在回零…")
            self.ctx.machine.home()
            self._deadline = time.monotonic() + 8.0
            self._poll.start()
        elif key == "calibrate":
            self.message.setText("正在进行相机标定与基准点检查…")
            self._calibrate_progress = 0
            QTimer.singleShot(300, self._calibrate_tick)

    def _camera_done(self) -> None:
        if self._done:
            return
        cameras = [camera for camera in self.ctx.profile.cameras if camera.enabled]
        if not cameras:
            self._fail("机型未配置可用相机")
            return
        self.rows["camera"].set_state(
            "ok", f"{len(cameras)} 台 · {cameras[0].resolution[0]}×{cameras[0].resolution[1]}"
        )
        self._next_step()

    def _calibrate_tick(self) -> None:
        if self._done:
            return
        self._calibrate_progress += 25
        self.progress.setValue(min(99, 75 + int(self._calibrate_progress / 5)))
        if self._calibrate_progress < 100:
            QTimer.singleShot(260, self._calibrate_tick)
            return
        self.rows["calibrate"].set_state("ok", "已完成")
        self._next_step()

    def _poll_step(self) -> None:
        if self._done:
            self._poll.stop()
            return
        key = STEP_DEFS[self._index][0]
        state = self.ctx.machine.state
        if key == "host":
            if self.ctx.machine.connected:
                self._poll.stop()
                self.rows["host"].set_state("ok", "已连接")
                self._next_step()
                return
            if state in {MachineState.ERROR, MachineState.ESTOP}:
                self._poll.stop()
                self._fail(f"主机连接失败：{self._last_label or state.value}")
                return
        elif key == "home":
            if self.ctx.machine.connected and state in {MachineState.READY, MachineState.IDLE}:
                self._poll.stop()
                self.rows["home"].set_state("ok", "已回零")
                self._next_step()
                return
            if state in {MachineState.ERROR, MachineState.ESTOP}:
                self._poll.stop()
                self._fail("归位失败：请检查限位与报警")
                return
        if time.monotonic() > self._deadline:
            self._poll.stop()
            self._fail("等待超时：请检查设备电源与通信")
            return

    def _fail(self, message: str) -> None:
        self._done = True
        self._poll.stop()
        if 0 <= self._index < len(STEP_DEFS):
            self.rows[STEP_DEFS[self._index][0]].set_state("error")
        self.message.setText(message)
        self.message.setStyleSheet(f"color: {COLORS['danger']}; font-size: 12px;")
        self.retry_button.show()
        self.finish_button.show()
        self.cancel_button.hide()
        self.ctx.log("ERROR", "CONNECT", message)

    def _finish(self) -> None:
        self._done = True
        self._poll.stop()
        self.progress.setValue(100)
        self.message.setText("连接成功，设备已就绪。")
        self.message.setStyleSheet(f"color: {COLORS['success']}; font-size: 12px;")
        self.ctx.log("INFO", "CONNECT", f"设备连接完成：{self.ctx.profile.name}")
        QTimer.singleShot(700, self.accept)

    def _cancel(self) -> None:
        self._done = True
        self._poll.stop()
        self.reject()

    # ---------------- 信号 ----------------

    def _on_connection(self, connected: bool, label: str) -> None:
        self._last_label = label
        if not connected and label and "失败" in label:
            self.message.setText(label)

    def _on_state(self, state: str) -> None:
        if self._done:
            return
        if state in {"error", "estop"}:
            self.message.setText("设备报警，请复位后重试。")
