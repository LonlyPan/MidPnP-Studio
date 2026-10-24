"""生产总览页。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ...core.models import MachineState
from ...core.planner import build_job
from ..context import AppContext
from ..icons import icon
from ..status import state_color, state_label
from ..theme import COLORS
from ..widgets import (
    Card,
    EmptyState,
    InfoRow,
    MachineMiniature,
    MetricCard,
    PageHeader,
    PageScroll,
    StatusDot,
    button,
    format_duration,
    hline,
    make_chip,
)


def _fmt_int(value: float) -> str:
    return f"{int(value):,}"


class DashboardPage(QWidget):
    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self._build()
        self._connect()
        self.refresh()

    # ---------------- UI ----------------

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.scroll = PageScroll(self)
        layout.addWidget(self.scroll)
        body = self.scroll.layout

        self.header = PageHeader("生产总览", "实时掌握设备、产线与今日绩效")
        self.date_chip = make_chip("")
        self.refresh_button = button("刷新", "refresh", "subtle")
        self.header.add_action(self.date_chip)
        self.header.add_action(self.refresh_button)
        body.addWidget(self.header)

        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(12)
        self.kpi_placed = MetricCard("今日产出", "0", "点", "zap", COLORS["accent"])
        self.kpi_yield = MetricCard("直通率", "0.0", "%", "target", COLORS["success"])
        self.kpi_cycle = MetricCard("平均节拍", "0.0", "CPH", "clock", COLORS["blue"])
        self.kpi_run = MetricCard("今日批次", "0", "批", "layers", COLORS["purple"])
        for card in (self.kpi_placed, self.kpi_yield, self.kpi_cycle, self.kpi_run):
            kpi_row.addWidget(card, 1)
        body.addLayout(kpi_row)

        middle = QHBoxLayout()
        middle.setSpacing(12)

        hero = Card()
        hero.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        hero_top = QHBoxLayout()
        title = QLabel("设备状态")
        title.setProperty("role", "section")
        self.hero_state_chip = make_chip("离线", accent=False)
        hero_top.addWidget(title)
        hero_top.addStretch(1)
        hero_top.addWidget(self.hero_state_chip)
        hero.body.addLayout(hero_top)

        hero_content = QHBoxLayout()
        hero_content.setSpacing(18)
        status_col = QVBoxLayout()
        status_col.setSpacing(8)
        status_line = QHBoxLayout()
        status_line.setSpacing(8)
        self.hero_dot = StatusDot(COLORS["muted"], 10)
        self.hero_state = QLabel("设备离线")
        self.hero_state.setStyleSheet("font-size: 24px; font-weight: 700;")
        status_line.addWidget(self.hero_dot)
        status_line.addWidget(self.hero_state)
        status_line.addStretch(1)
        status_col.addLayout(status_line)
        self.hero_sub = QLabel("连接设备后即可开始生产")
        self.hero_sub.setProperty("role", "muted")
        self.hero_sub.setWordWrap(True)
        status_col.addWidget(self.hero_sub)

        status_col.addSpacing(6)
        self.hero_product_name = QLabel("未选择产品")
        self.hero_product_name.setStyleSheet("font-size: 15px; font-weight: 600;")
        status_col.addWidget(self.hero_product_name)
        self.hero_product_meta = QLabel("—")
        self.hero_product_meta.setProperty("role", "muted")
        status_col.addWidget(self.hero_product_meta)

        status_col.addStretch(1)
        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.hero_primary = button("开始生产", "play", "primary", 40)
        self.hero_primary.setMinimumWidth(120)
        self.hero_secondary = button("连接设备", "link", "subtle")
        actions.addWidget(self.hero_primary)
        actions.addWidget(self.hero_secondary)
        status_col.addLayout(actions)
        status_col.setContentsMargins(0, 0, 0, 0)
        hero_content.addLayout(status_col, 0)
        hero_content.setStretch(0, 0)

        self.miniature = MachineMiniature()
        self.miniature.setMinimumWidth(360)
        hero_content.addWidget(self.miniature, 1)
        hero.body.addLayout(hero_content, 1)

        hero.body.addWidget(hline())
        coords = QHBoxLayout()
        coords.setSpacing(18)
        self.coord_x = InfoRow("X 轴", "0.0 mm")
        self.coord_y = InfoRow("Y 轴", "0.0 mm")
        self.coord_z = InfoRow("Z 轴", "0.0 mm")
        self.coord_nozzle = InfoRow("吸嘴", "N1")
        for row in (self.coord_x, self.coord_y, self.coord_z, self.coord_nozzle):
            coords.addWidget(row, 1)
        hero.body.addLayout(coords)

        middle.addWidget(hero, 7)

        product = Card()
        product.body.setSpacing(10)
        product_top = QHBoxLayout()
        product_title = QLabel("当前产品")
        product_title.setProperty("role", "section")
        self.rev_chip = make_chip("REV A", accent=True)
        product_top.addWidget(product_title)
        product_top.addStretch(1)
        product_top.addWidget(self.rev_chip)
        product.body.addLayout(product_top)
        self.product_name = QLabel("—")
        self.product_name.setStyleSheet("font-size: 20px; font-weight: 700;")
        self.product_name.setWordWrap(True)
        product.body.addWidget(self.product_name)
        self.product_meta = QLabel("")
        self.product_meta.setProperty("role", "muted")
        self.product_meta.setWordWrap(True)
        product.body.addWidget(self.product_meta)
        product.body.addWidget(hline())

        self.info_placements = InfoRow("贴装点", "0")
        self.info_components = InfoRow("元件种类", "0")
        self.info_fiducials = InfoRow("基准点", "0")
        self.info_estimate = InfoRow("预计节拍", "—")
        for row in (self.info_placements, self.info_components, self.info_fiducials, self.info_estimate):
            product.body.addWidget(row)
        product.body.addStretch(1)

        feeder_title = QHBoxLayout()
        label = QLabel("供料器就绪")
        label.setProperty("role", "muted")
        self.feeder_pct = QLabel("0%")
        self.feeder_pct.setStyleSheet(f"color: {COLORS['accent']}; font-weight: 700;")
        feeder_title.addWidget(label)
        feeder_title.addStretch(1)
        feeder_title.addWidget(self.feeder_pct)
        product.body.addLayout(feeder_title)
        from PySide6.QtWidgets import QProgressBar

        self.feeder_bar = QProgressBar()
        self.feeder_bar.setRange(0, 100)
        self.feeder_bar.setTextVisible(False)
        product.body.addWidget(self.feeder_bar)
        self.open_programming = button("打开产品编程", "programming", "subtle")
        product.body.addWidget(self.open_programming)

        middle.addWidget(product, 4)
        body.addLayout(middle)

        bottom = QHBoxLayout()
        bottom.setSpacing(12)

        recent = Card()
        recent_top = QHBoxLayout()
        recent_title = QLabel("最近生产")
        recent_title.setProperty("role", "section")
        recent_top.addWidget(recent_title)
        recent_top.addStretch(1)
        view_all = QPushButton("查看日志")
        view_all.setProperty("variant", "ghost")
        view_all.setCursor(Qt.CursorShape.PointingHandCursor)
        view_all.clicked.connect(lambda: self.ctx.signals.navigate.emit("logs"))
        recent_top.addWidget(view_all)
        recent.body.addLayout(recent_top)
        self.recent_container = QVBoxLayout()
        self.recent_container.setSpacing(4)
        recent.body.addLayout(self.recent_container)
        recent.body.addStretch(1)
        bottom.addWidget(recent, 5)

        activity = Card()
        activity_top = QHBoxLayout()
        activity_title = QLabel("设备动态")
        activity_title.setProperty("role", "section")
        live_chip = make_chip("LIVE", accent=True)
        activity_top.addWidget(activity_title)
        activity_top.addStretch(1)
        activity_top.addWidget(live_chip)
        activity.body.addLayout(activity_top)
        self.activity_container = QVBoxLayout()
        self.activity_container.setSpacing(2)
        activity.body.addLayout(self.activity_container)
        activity.body.addStretch(1)
        bottom.addWidget(activity, 4)

        quick = Card()
        quick_title = QLabel("快捷操作")
        quick_title.setProperty("role", "section")
        quick.body.addWidget(quick_title)
        quick_grid = QGridLayout()
        quick_grid.setSpacing(8)
        actions_spec = [
            ("产品编程", "programming", "programming"),
            ("供料器", "feeder", "feeders"),
            ("手动控制", "manual", "manual"),
            ("视觉对位", "vision", "vision"),
        ]
        for i, (label_text, icon_name, page) in enumerate(actions_spec):
            control = QPushButton(f"  {label_text}")
            control.setIcon(icon(icon_name, COLORS["muted"], 18))
            control.setMinimumHeight(48)
            control.setStyleSheet("text-align: left; padding-left: 12px;")
            control.setCursor(Qt.CursorShape.PointingHandCursor)
            control.clicked.connect(lambda checked=False, key=page: self.ctx.signals.navigate.emit(key))
            quick_grid.addWidget(control, i // 2, i % 2)
        quick.body.addLayout(quick_grid)
        quick.body.addStretch(1)
        hint = QLabel("提示：模拟器已内置 35 点演示板，可直接运行完整生产流程。")
        hint.setProperty("role", "hint")
        hint.setWordWrap(True)
        quick.body.addWidget(hint)
        bottom.addWidget(quick, 3)

        body.addLayout(bottom, 1)
        body.addStretch(0)

    def _connect(self) -> None:
        self.refresh_button.clicked.connect(self.refresh)
        self.hero_secondary.clicked.connect(self._connect_or_settings)
        self.hero_primary.clicked.connect(self._start_or_connect)
        self.open_programming.clicked.connect(lambda: self.ctx.signals.navigate.emit("programming"))
        self.ctx.machine.state_changed.connect(self._on_state)
        self.ctx.machine.connection_changed.connect(self._on_connection)
        self.ctx.machine.position_changed.connect(self._on_position)
        self.ctx.machine.telemetry.connect(self._on_telemetry)
        self.ctx.signals.log_added.connect(self._on_log)
        self.ctx.signals.product_changed.connect(lambda *_: self.refresh())
        self.ctx.signals.products_changed.connect(self.refresh)
        self.ctx.signals.feeders_changed.connect(self.refresh)
        self.ctx.machine.run_finished.connect(lambda *_: self.refresh())

    # ---------------- actions ----------------

    def _connect_or_settings(self) -> None:
        if self.ctx.connected:
            self.ctx.signals.navigate.emit("settings")
            return
        self.ctx.machine.connect_machine(self.ctx.settings, self.ctx.feeders(), self.ctx.profile)

    def _start_or_connect(self) -> None:
        if not self.ctx.connected:
            self._connect_or_settings()
            return
        if self.ctx.machine.state is MachineState.PAUSED:
            self.ctx.machine.resume()
            self.ctx.signals.navigate.emit("production")
            return
        if self.ctx.machine.run_active:
            self.ctx.signals.navigate.emit("production")
            return
        if self.ctx.machine.state is MachineState.READY:
            self.ctx.signals.start_production.emit()
            return
        self.ctx.signals.navigate.emit("production")
        self.ctx.signals.toast.emit("已切换到生产页，确认参数后开始", "info")

    # ---------------- events ----------------

    def _on_connection(self, connected: bool, label: str) -> None:
        self.ctx.connected = connected
        self._on_state(self.ctx.machine.state.value)

    def _on_state(self, state_value: str) -> None:
        try:
            state = MachineState(state_value)
        except ValueError:
            state = MachineState.OFFLINE
        color = state_color(state)
        label = state_label(state)
        self.hero_dot.set_color(color)
        self.hero_state.setText(f"设备{label}" if state not in {MachineState.RUNNING, MachineState.PAUSED} else label)
        self.hero_state.setStyleSheet(f"font-size: 24px; font-weight: 700; color: {color};")
        self.hero_state_chip.setText(label.upper())
        self.hero_state_chip.setStyleSheet(
            f"background: {color}16; border: 1px solid {color}55; color: {color};"
            "border-radius: 10px; padding: 3px 9px; font-size: 11px; font-weight: 700;"
        )
        if state is MachineState.READY:
            self.hero_sub.setText("设备已就绪，等待开始生产")
            self.hero_primary.setText("开始生产")
            self.hero_secondary.setText("设备设置")
        elif state is MachineState.RUNNING:
            self.hero_sub.setText("生产任务执行中，请关注贴装进度")
            self.hero_primary.setText("查看生产")
            self.hero_secondary.setText("设备设置")
        elif state is MachineState.PAUSED:
            self.hero_sub.setText("任务已暂停，可继续或停止")
            self.hero_primary.setText("继续生产")
            self.hero_secondary.setText("设备设置")
        elif state in {MachineState.ERROR, MachineState.ESTOP}:
            self.hero_sub.setText("设备报警，请排除故障后复位")
            self.hero_primary.setText("查看报警")
            self.hero_secondary.setText("设备设置")
        elif state is MachineState.HOMING:
            self.hero_sub.setText("正在执行回原点动作…")
            self.hero_primary.setText("请稍候")
        elif self.ctx.connected:
            self.hero_sub.setText("设备在线，执行回原点后开始生产")
            self.hero_primary.setText("回原点")
            self.hero_secondary.setText("设备设置")
        else:
            self.hero_sub.setText("连接设备后即可开始生产")
            self.hero_primary.setText("开始生产")
            self.hero_secondary.setText("连接设备")
        self.miniature.set_state(state)
        self.hero_primary.setEnabled(state not in {MachineState.HOMING, MachineState.CONNECTING})

    def _on_position(self, x: float, y: float, z: float) -> None:
        self.ctx.head = (x, y, z)
        self.coord_x.set(f"{x:.1f} mm")
        self.coord_y.set(f"{y:.1f} mm")
        self.coord_z.set(f"{z:.1f} mm")
        limits = self.ctx.settings.limits
        self.miniature.set_machine((x, y), (limits.travel_x_mm, limits.travel_y_mm))

    def _on_telemetry(self, data: dict[str, Any]) -> None:
        if data.get("type") == "feeder":
            self.refresh()
        elif "nozzle" in data:
            self.coord_nozzle.set(str(data["nozzle"]))

    def _on_log(self, entry: Any) -> None:
        self._add_activity(entry.message, entry.timestamp, entry.level)

    # ---------------- refresh ----------------

    def refresh(self) -> None:
        now = datetime.now()
        weekdays = "一二三四五六日"
        self.date_chip.setText(f"{now.year}年{now.month}月{now.day}日 · 周{weekdays[now.weekday()]}")
        summary = self.ctx.storage.today_summary()
        self.kpi_placed.set(_fmt_int(summary["placed"]), f"失败 {int(summary['failed'])} 点")
        self.kpi_yield.set(f"{summary['yield']:.1f}", "良率 = 成功 / 总尝试", f"{summary['yield']:.1f}%")
        self.kpi_cycle.set(f"{summary['cph']:.0f}", "实际产出速度")
        self.kpi_run.set(_fmt_int(summary["runs"]), f"累计 {format_duration(summary['duration_s'])}")

        product = self.ctx.current_product
        if product:
            self.hero_product_name.setText(product.name)
            self.hero_product_meta.setText(
                f"REV {product.revision} · {product.board_width_mm:.0f} × {product.board_height_mm:.0f} mm · "
                f"{len(product.active_placements)} 个贴装点"
            )
            self.product_name.setText(product.name)
            self.rev_chip.setText(f"REV {product.revision}")
            self.product_meta.setText(
                f"{product.board_width_mm:.0f} × {product.board_height_mm:.0f} mm · "
                f"板厚 {product.board_thickness_mm:.1f} mm"
            )
            components = self.ctx.components()
            feeders = self.ctx.feeders()
            self.info_placements.set(f"{len(product.active_placements)} 点")
            self.info_components.set(f"{len({p.component_id for p in product.active_placements})} 种")
            self.info_fiducials.set(f"{len(product.fiducials)} 个")
            try:
                plan, issues = self.ctx.build_plan(product)
                self.info_estimate.set(
                    format_duration(plan.estimated_cycle_s) if not any(i.is_error for i in issues) else "待检查"
                )
            except Exception:
                self.info_estimate.set("—")

            active_component_ids = {p.component_id for p in product.active_placements}
            relevant = [f for f in feeders if f.component_id in active_component_ids and f.enabled]
            ready = len({f.component_id for f in relevant if not f.is_empty})
            total_comp = max(1, len(active_component_ids))
            pct = round(ready / total_comp * 100)
            self.feeder_bar.setValue(pct)
            self.feeder_pct.setText(f"{pct}%")
            self.feeder_pct.setStyleSheet(
                f"color: {COLORS['accent'] if pct >= 80 else COLORS['warn']}; font-weight: 700;"
            )
            self.miniature.set_product(product)
            self.miniature.set_machine(
                (self.ctx.head[0], self.ctx.head[1]),
                (self.ctx.settings.limits.travel_x_mm, self.ctx.settings.limits.travel_y_mm),
            )
        else:
            self.hero_product_name.setText("未选择产品")
            self.hero_product_meta.setText("请先在产品编程中创建产品")
            self.product_name.setText("—")
            self.info_placements.set("0")
            self.info_components.set("0")
            self.info_fiducials.set("0")
            self.info_estimate.set("—")
            self.feeder_bar.setValue(0)
            self.feeder_pct.setText("0%")

        self._refresh_recent()
        self._refresh_activity()
        self._on_state(self.ctx.machine.state.value)

    def _clear_layout(self, layout: QVBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _refresh_recent(self) -> None:
        self._clear_layout(self.recent_container)
        runs = self.ctx.storage.recent_runs(3)
        if not runs:
            self.recent_container.addWidget(EmptyState("暂无生产记录", "完成首批生产后将在这里显示", "production"))
            return
        for run in runs:
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(2, 7, 2, 7)
            row_layout.setSpacing(10)
            dot = StatusDot(COLORS["success"] if run.status == "Completed" else COLORS["warn"], 7)
            row_layout.addWidget(dot)
            text = QVBoxLayout()
            text.setSpacing(1)
            title = QLabel(run.product_name)
            title.setStyleSheet("font-weight: 600;")
            when = run.started_at.replace("T", " ")[5:16]
            sub = QLabel(f"{when} · {run.placed}/{run.total} 点 · {format_duration(run.duration_s)}")
            sub.setProperty("role", "faint")
            text.addWidget(title)
            text.addWidget(sub)
            row_layout.addLayout(text, 1)
            status = QLabel("完成" if run.status == "Completed" else run.status)
            status.setProperty("chip", "accent" if run.status == "Completed" else "true")
            row_layout.addWidget(status)
            self.recent_container.addWidget(row)
            self.recent_container.addWidget(hline())

    def _refresh_activity(self) -> None:
        while self.activity_container.count():
            item = self.activity_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        logs = self.ctx.storage.list_logs(limit=6)
        for entry in logs:
            self._add_activity(entry.message, entry.timestamp, entry.level, prepend=False)
        if not logs:
            self.activity_container.addWidget(EmptyState("暂无动态", "设备事件会显示在这里", "logs"))

    def _add_activity(self, message: str, timestamp: str, level: str, prepend: bool = True) -> None:
        row = QWidget()
        row.setToolTip(message)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(2, 5, 2, 5)
        row_layout.setSpacing(8)
        colors = {"INFO": COLORS["accent"], "WARN": COLORS["warn"], "ERROR": COLORS["danger"], "DEBUG": COLORS["faint"]}
        dot = StatusDot(colors.get(level.upper(), COLORS["muted"]), 6)
        row_layout.addWidget(dot, 0, Qt.AlignmentFlag.AlignTop)
        label = QLabel(message)
        label.setWordWrap(True)
        label.setStyleSheet("font-size: 12px; color: #b9c9d2;")
        row_layout.addWidget(label, 1)
        time_label = QLabel(timestamp[-8:] if "T" in timestamp else timestamp)
        time_label.setProperty("role", "faint")
        row_layout.addWidget(time_label, 0, Qt.AlignmentFlag.AlignTop)
        if prepend:
            self.activity_container.insertWidget(0, row)
            while self.activity_container.count() > 7:
                item = self.activity_container.takeAt(self.activity_container.count() - 1)
                if item.widget():
                    item.widget().deleteLater()
        else:
            self.activity_container.addWidget(row)
