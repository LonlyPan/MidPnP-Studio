"""生产执行页：板卡视图、实时进度与贴装点状态。"""

from __future__ import annotations

import time
from typing import Any

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...core.models import JobPlan, MachineState
from ...core.planner import build_job
from ..context import AppContext
from ..dialogs import IssuesDialog
from ..icons import icon
from ..status import state_color, state_label
from ..theme import COLORS
from ..widgets import (
    BoardView,
    Card,
    PageHeader,
    RingProgress,
    StatusDot,
    button,
    format_duration,
    hline,
    make_chip,
)


class ProductionPage(QWidget):
    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self._plan: JobPlan | None = None
        self._statuses: dict[str, str] = {}
        self._started_monotonic: float | None = None
        self._placed = 0
        self._failed = 0
        self._total = 0
        self._current_ref = ""
        self._ended = False
        self._build()
        self._connect()
        self._clock = QTimer(self)
        self._clock.timeout.connect(self._update_elapsed)
        self._clock.start(1000)
        self.refresh()

    # ---------------- UI ----------------

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 16, 24, 16)
        outer.setSpacing(10)

        self.header = PageHeader("生产执行", "实时监控贴装路径、节拍与贴装点状态")
        product_label = QLabel("产品")
        product_label.setProperty("role", "muted")
        self.product_combo = QComboBox()
        self.product_combo.setMinimumWidth(220)
        self.product_combo.currentIndexChanged.connect(self._on_product_changed)
        self.header.add_action(product_label)
        self.header.add_action(self.product_combo)
        outer.addWidget(self.header)

        content = QHBoxLayout()
        content.setSpacing(12)

        board_card = Card(padding=12)
        board_card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        board_top = QHBoxLayout()
        title = QLabel("生产视图")
        title.setProperty("role", "section")
        board_top.addWidget(title)
        self.view_chip = make_chip("MACHINE VIEW")
        board_top.addWidget(self.view_chip)
        self.point_chip = make_chip("0 点", accent=True)
        board_top.addWidget(self.point_chip)
        board_top.addStretch(1)
        fit_button = button("适应窗口", "target", "ghost")
        fit_button.clicked.connect(self.board_view_reset)
        board_top.addWidget(fit_button)
        board_card.body.addLayout(board_top)
        self.board = BoardView(mode="machine")
        self.board.setMinimumHeight(260)
        self.board.placement_selected.connect(self._on_board_selected)
        board_card.body.addWidget(self.board, 1)
        legend = QHBoxLayout()
        legend.setSpacing(14)
        for label, color in (
            ("待贴装", COLORS["faint"]),
            ("贴装中", COLORS["warn"]),
            ("已完成", COLORS["success"]),
            ("异常", COLORS["danger"]),
        ):
            item = QHBoxLayout()
            item.setSpacing(5)
            item.addWidget(StatusDot(color, 6))
            text = QLabel(label)
            text.setProperty("role", "faint")
            item.addWidget(text)
            legend.addLayout(item)
        legend.addStretch(1)
        board_card.body.addLayout(legend)
        content.addWidget(board_card, 1)

        control = Card(padding=16)
        control.setFixedWidth(360)
        control.body.setSpacing(8)
        control_top = QHBoxLayout()
        control_title = QLabel("生产控制")
        control_title.setProperty("role", "section")
        self.state_chip = make_chip("离线")
        self.reset_button = QPushButton()
        self.reset_button.setIcon(icon("refresh", COLORS["muted"], 14))
        self.reset_button.setFixedSize(26, 26)
        self.reset_button.setProperty("variant", "ghost")
        self.reset_button.setToolTip("报警复位")
        self.reset_button.clicked.connect(self.ctx.machine.clear_fault)
        control_top.addWidget(control_title)
        control_top.addStretch(1)
        control_top.addWidget(self.reset_button)
        control_top.addWidget(self.state_chip)
        control.body.addLayout(control_top)

        self.ring = RingProgress(size=120)
        ring_wrap = QHBoxLayout()
        ring_wrap.addStretch(1)
        ring_wrap.addWidget(self.ring)
        ring_wrap.addStretch(1)
        control.body.addLayout(ring_wrap)

        self.phase_label = QLabel("等待开始生产")
        self.phase_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.phase_label.setStyleSheet("font-size: 14px; font-weight: 600;")
        control.body.addWidget(self.phase_label)

        counts = QHBoxLayout()
        counts.setSpacing(0)
        self.count_placed = self._count_block("已贴装", "0", COLORS["accent"])
        self.count_failed = self._count_block("失败", "0", COLORS["danger"])
        self.count_remain = self._count_block("剩余", "0", COLORS["muted"])
        counts.addWidget(self.count_placed[0], 1)
        line1 = QFrame()
        line1.setProperty("cssClass", "vdivider")
        line1.setFixedWidth(1)
        counts.addWidget(line1)
        counts.addWidget(self.count_failed[0], 1)
        line2 = QFrame()
        line2.setProperty("cssClass", "vdivider")
        line2.setFixedWidth(1)
        counts.addWidget(line2)
        counts.addWidget(self.count_remain[0], 1)
        control.body.addLayout(counts)
        control.body.addWidget(hline())

        self.meta_line = QLabel("供料器 —  ·  预计剩余 —  ·  已用时 —")
        self.meta_line.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.meta_line.setStyleSheet(f"color: {COLORS['muted']}; font-size: 11px;")
        control.body.addWidget(self.meta_line)
        self._meta_feeder = "—"
        self._meta_eta = "—"
        self._meta_elapsed = "—"
        control.body.addStretch(1)

        self.start_button = button("开始生产", "play", "primary", 38)
        self.pause_button = button("暂停", "pause", "", 34)
        self.stop_button = button("停止", "stop", "danger", 34)
        self.start_button.clicked.connect(self._start)
        self.pause_button.clicked.connect(self._pause_resume)
        self.stop_button.clicked.connect(self._stop)
        control.body.addWidget(self.start_button)
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(self.pause_button, 1)
        row.addWidget(self.stop_button, 1)
        control.body.addLayout(row)
        content.addWidget(control)
        outer.addLayout(content, 1)

        table_card = Card(padding=12)
        table_top = QHBoxLayout()
        table_title = QLabel("贴装点队列")
        table_title.setProperty("role", "section")
        table_top.addWidget(table_title)
        self.table_chip = make_chip("0 / 0")
        table_top.addWidget(self.table_chip)
        table_top.addStretch(1)
        self.queue_hint = QLabel("按最近邻路径优化")
        self.queue_hint.setProperty("role", "faint")
        table_top.addWidget(self.queue_hint)
        table_card.body.addLayout(table_top)
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["#", "位号", "元件", "供料器", "坐标 (mm)", "角度", "状态"])
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setDefaultSectionSize(28)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(0, 44)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(1, 90)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(3, 100)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(4, 160)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(5, 70)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(6, 90)
        self.table.setMinimumHeight(130)
        self.table.setMaximumHeight(238)
        table_card.body.addWidget(self.table)
        outer.addWidget(table_card)

    def resizeEvent(self, event: Any) -> None:  # noqa: N802
        super().resizeEvent(event)
        if hasattr(self, "table"):
            self.table.setMaximumHeight(max(130, min(238, self.height() - 680)))

    def _count_block(self, label: str, value: str, color: str) -> tuple[QWidget, QLabel]:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(0)
        value_label = QLabel(value)
        value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        value_label.setStyleSheet(f"font-family: 'Cascadia Mono'; font-size: 20px; font-weight: 700; color: {color};")
        name_label = QLabel(label)
        name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_label.setProperty("role", "faint")
        layout.addWidget(value_label)
        layout.addWidget(name_label)
        return widget, value_label

    def _connect(self) -> None:
        machine = self.ctx.machine
        machine.state_changed.connect(self._on_state)
        machine.connection_changed.connect(lambda *_: self._on_state(machine.state.value))
        machine.position_changed.connect(self._on_position)
        machine.run_started.connect(self._on_run_started)
        machine.run_progress.connect(self._on_run_progress)
        machine.run_finished.connect(self._on_run_finished)
        self.ctx.signals.product_changed.connect(self._on_product_event)
        self.ctx.signals.products_changed.connect(self.refresh)
        self.ctx.signals.feeders_changed.connect(self.refresh)
        self.board.placement_selected.connect(self._on_board_selected)

    def board_view_reset(self) -> None:
        self.board.reset_view()

    # ---------------- data ----------------

    def refresh(self) -> None:
        products = self.ctx.storage.list_products()
        current = self.ctx.current_product_id
        self.product_combo.blockSignals(True)
        self.product_combo.clear()
        for product in products:
            self.product_combo.addItem(f"{product.name}  ·  REV {product.revision}", product.id)
        index = self.product_combo.findData(current)
        if index >= 0:
            self.product_combo.setCurrentIndex(index)
        self.product_combo.blockSignals(False)

        product = self.ctx.current_product
        components = self.ctx.components()
        feeders = self.ctx.feeders()
        self.board.set_product(product, components)
        self.board.set_limits(self.ctx.settings.limits.travel_x_mm, self.ctx.settings.limits.travel_y_mm)
        self.board.set_components(components)
        if not product:
            self.table.setRowCount(0)
            self.point_chip.setText("0 点")
            return
        plan, issues = build_job(
            product,
            components,
            feeders,
            self.ctx.settings.limits,
            optimize=self.ctx.settings.optimize_route,
        )
        if self.ctx.machine.run_active and self._plan is not None:
            plan = self._plan
        else:
            self._plan = plan
        self._populate_table(plan)
        self.point_chip.setText(f"{plan.total} 点")
        self.queue_hint.setText("最近邻路径优化" if plan.optimized else "按原始顺序")
        self._on_state(self.ctx.machine.state.value)
        self._update_ring()

    def _populate_table(self, plan: JobPlan) -> None:
        self.table.setRowCount(len(plan.steps))
        self._row_by_ref: dict[str, int] = {}
        for row, step in enumerate(plan.steps):
            values = [
                f"{step.index:02d}",
                step.refdes,
                step.component_name,
                f"{step.feeder_slot:02d}",
                f"{step.place.x:.1f}, {step.place.y:.1f}",
                f"{step.rotation_deg:.1f}°",
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                if col in (0, 3, 4, 5):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(row, col, item)
            status = self._statuses.get(step.refdes, "pending")
            self._set_row_status(row, status)
            self._row_by_ref[step.refdes] = row
        done = self._placed + self._failed if (self._ended or self.ctx.machine.run_active) else 0
        self.table_chip.setText(f"{done} / {plan.total}")

    def _set_row_status(self, row: int, status: str) -> None:
        text, color = {
            "pending": ("待贴装", COLORS["muted"]),
            "placing": ("贴装中", COLORS["warn"]),
            "placed": ("完成", COLORS["success"]),
            "failed": ("失败", COLORS["danger"]),
            "skipped": ("跳过", COLORS["faint"]),
        }.get(status, ("待贴装", COLORS["muted"]))
        item = self.table.item(row, 6)
        if item is None:
            item = QTableWidgetItem()
            self.table.setItem(row, 6, item)
        item.setText(text)
        item.setForeground(QColor(color))
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        for col in range(6):
            cell = self.table.item(row, col)
            if cell:
                cell.setForeground(QColor(COLORS["text"] if status != "pending" else "#9aadb8"))

    def _on_product_changed(self, index: int) -> None:
        product_id = self.product_combo.itemData(index)
        if not product_id or product_id == self.ctx.current_product_id:
            return
        if self.ctx.machine.run_active:
            self.refresh()
            self.ctx.toast("生产进行中，不能切换产品", "warning")
            return
        self.ctx.select_product(str(product_id))
        self._statuses.clear()
        self.board.clear_statuses()
        self.refresh()

    def _on_product_event(self, product: Any) -> None:
        if product and product.id == self.ctx.current_product_id:
            self.refresh()

    def _on_board_selected(self, refdes: str) -> None:
        row = getattr(self, "_row_by_ref", {}).get(refdes)
        if row is not None:
            self.table.selectRow(row)
            self.table.scrollToItem(self.table.item(row, 0), QAbstractItemView.ScrollHint.PositionAtCenter)

    # ---------------- controls ----------------

    def _start(self) -> None:
        if not self.ctx.connected:
            self.ctx.machine.connect_machine(self.ctx.settings, self.ctx.feeders())
            self.ctx.toast("正在连接设备，连接后请再次点击开始", "info")
            return
        product = self.ctx.current_product
        if not product:
            self.ctx.toast("请先选择产品", "warning")
            return
        plan, issues = build_job(
            product,
            self.ctx.components(),
            self.ctx.feeders(),
            self.ctx.settings.limits,
            optimize=self.ctx.settings.optimize_route,
        )
        if any(issue.is_error for issue in issues):
            IssuesDialog(issues, self).exec()
            return
        if self.ctx.settings.stop_on_low_feeder:
            active_ids = {p.component_id for p in product.active_placements}
            low = [
                feeder
                for feeder in self.ctx.feeders()
                if feeder.component_id in active_ids and feeder.enabled and feeder.is_low
            ]
            if low:
                message = "、".join(f"槽位 {f.slot:02d}" for f in low)
                QMessageBox.warning(
                    self,
                    "低料阻止生产",
                    f"以下供料器低于低料阈值：{message}\n\n请补料或关闭“供料器低料时停止生产”设置。",
                )
                return
        if self.ctx.settings.confirm_before_start:
            answer = QMessageBox.question(
                self,
                "确认开始生产",
                f"产品：{product.name}\n贴装点：{plan.total}\n预计节拍：{format_duration(plan.estimated_cycle_s)}\n\n确认开始？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        if issues:
            self.ctx.toast(f"开始生产，存在 {len(issues)} 条提示", "warning")
        self._plan = plan
        self._statuses = {}
        self._placed = 0
        self._failed = 0
        self._total = plan.total
        self._current_ref = ""
        self._ended = False
        self._started_monotonic = time.monotonic()
        self._populate_table(plan)
        self.board.clear_statuses()
        if not self.ctx.machine.start_job(plan):
            self._started_monotonic = None
            return
        self.ctx.log("INFO", "UI", f"操作员启动生产：{product.name}")

    def _pause_resume(self) -> None:
        if self.ctx.machine.state is MachineState.PAUSED:
            self.ctx.machine.resume()
        else:
            self.ctx.machine.pause()

    def _stop(self) -> None:
        if not self.ctx.machine.run_active:
            return
        answer = QMessageBox.question(
            self,
            "停止生产",
            "停止当前生产任务？已完成的贴装点会记录在本次批次中。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.ctx.machine.stop()

    # ---------------- machine events ----------------

    def _on_position(self, x: float, y: float, z: float) -> None:
        self.board.set_head(x, y, z)

    def _on_state(self, state_value: str) -> None:
        try:
            state = MachineState(state_value)
        except ValueError:
            state = MachineState.OFFLINE
        label = state_label(state)
        color = state_color(state)
        self.state_chip.setText(label)
        self.state_chip.setStyleSheet(
            f"background: {color}16; border: 1px solid {color}55; color: {color};"
            "border-radius: 10px; padding: 3px 9px; font-size: 11px; font-weight: 700;"
        )
        run_active = self.ctx.machine.run_active
        self.start_button.setEnabled(
            self.ctx.connected and not run_active and state not in {MachineState.ESTOP, MachineState.HOMING}
        )
        self.pause_button.setEnabled(run_active and state in {MachineState.RUNNING, MachineState.PAUSED})
        self.stop_button.setEnabled(run_active)
        self.reset_button.setEnabled(state in {MachineState.ERROR, MachineState.ESTOP})
        self.pause_button.setText("继续" if state is MachineState.PAUSED else "暂停")
        if state is MachineState.RUNNING and run_active:
            self.phase_label.setText("生产运行中")
        elif state is MachineState.PAUSED:
            self.phase_label.setText("生产已暂停")
        elif state is MachineState.ESTOP:
            self.phase_label.setText("急停已触发")
        elif state is MachineState.ERROR:
            self.phase_label.setText("设备报警")
        elif not run_active and not self._ended:
            self.phase_label.setText("等待开始生产")

    def _refresh_meta(self) -> None:
        self.meta_line.setText(
            f"供料器 {self._meta_feeder}  ·  预计剩余 {self._meta_eta}  ·  已用时 {self._meta_elapsed}"
        )

    def _on_run_started(self, info: dict[str, Any]) -> None:
        self._placed = 0
        self._failed = 0
        self._total = int(info.get("total", 0))
        self._started_monotonic = time.monotonic()
        self._ended = False
        self._statuses.clear()
        self.board.clear_statuses()
        self._meta_feeder = "—"
        self._meta_eta = "—"
        self._meta_elapsed = "00:00"
        self._refresh_meta()
        self._update_ring()
        self._on_state(self.ctx.machine.state.value)

    def _on_run_progress(self, data: dict[str, Any]) -> None:
        self._placed = int(data.get("placed", self._placed))
        self._failed = int(data.get("failed", self._failed))
        self._total = int(data.get("total", self._total))
        self.phase_label.setText(str(data.get("phase_label", "")))
        self._current_ref = str(data.get("refdes", self._current_ref))
        if self._current_ref:
            step = next((s for s in self._plan.steps if s.refdes == self._current_ref), None) if self._plan else None
            if step is not None:
                self._meta_feeder = f"{step.feeder_slot:02d}"
                self._refresh_meta()
        phase = data.get("phase", "")
        if self._current_ref:
            row = getattr(self, "_row_by_ref", {}).get(self._current_ref)
            if row is not None:
                if phase in {"moving_to_feeder", "picking", "moving_to_board", "placing"}:
                    self._statuses[self._current_ref] = "placing"
                    self._set_row_status(row, "placing")
                    self.board.set_status(self._current_ref, "placing")
                    self.table.scrollToItem(self.table.item(row, 0), QAbstractItemView.ScrollHint.PositionAtCenter)
                elif phase == "placed":
                    self._statuses[self._current_ref] = "placed"
                    self._set_row_status(row, "placed")
                    self.board.set_status(self._current_ref, "placed")
        self._update_ring()
        self.table_chip.setText(f"{self._placed + self._failed} / {self._total}")

    def _on_run_finished(self, data: dict[str, Any]) -> None:
        self._ended = True
        self._placed = int(data.get("placed", self._placed))
        self._failed = int(data.get("failed", self._failed))
        status = str(data.get("status", "Completed"))
        if status == "Faulted" and self._current_ref:
            row = getattr(self, "_row_by_ref", {}).get(self._current_ref)
            if row is not None:
                self._statuses[self._current_ref] = "failed"
                self._set_row_status(row, "failed")
                self.board.set_status(self._current_ref, "failed")
        self.phase_label.setText(
            {
                "Completed": "生产完成",
                "Cancelled": "生产已停止",
                "Faulted": "生产异常中止",
                "E-Stopped": "急停中止",
            }.get(status, status)
        )
        self.table_chip.setText(f"{self._placed + self._failed} / {self._total}")
        self._started_monotonic = None
        self._meta_eta = "—"
        self._refresh_meta()
        self._update_ring(final=True)
        self._on_state(self.ctx.machine.state.value)

    def _update_ring(self, final: bool = False) -> None:
        total = max(self._total, self._plan.total if self._plan else 0)
        done = self._placed + self._failed
        pct = (done / total * 100) if total else (100 if final else 0)
        color = COLORS["accent"]
        if self._failed:
            color = COLORS["warn"]
        self.ring.set_progress(
            pct,
            f"{pct:.0f}%",
            f"{done} / {total} 点",
            color,
        )
        self.count_placed[1].setText(str(self._placed))
        self.count_failed[1].setText(str(self._failed))
        self.count_remain[1].setText(str(max(0, total - done)))

    def _update_elapsed(self) -> None:
        if self._started_monotonic is None:
            return
        elapsed = max(0.0, time.monotonic() - self._started_monotonic)
        self._meta_elapsed = format_duration(elapsed)
        done = self._placed + self._failed
        if done > 0 and self._total > done:
            remaining = elapsed / done * (self._total - done)
            self._meta_eta = format_duration(remaining)
        else:
            self._meta_eta = "—" if done == 0 else "00:00"
        self._refresh_meta()
