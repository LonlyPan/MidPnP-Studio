"""手动控制页：轴点动、真空、吸嘴、传送带与供料器。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ...core.models import MachineState
from ..context import AppContext
from ..status import state_color, state_label
from ..theme import COLORS
from ..widgets import (
    Card,
    PageHeader,
    StatusDot,
    button,
    hline,
    make_chip,
    set_css,
)


class ManualPage(QWidget):
    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self._step = 1.0
        self._speed_pct = 40
        self._vacuum_on = False
        self._build()
        self._connect()
        self._on_state(self.ctx.machine.state.value)

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(14)
        self.header = PageHeader("手动控制", "维护、对针与换料时的手动点动面板")
        self.state_chip = make_chip("离线")
        self.home_button = button("回原点", "home", "primary")
        self.header.add_action(self.state_chip)
        self.header.add_action(self.home_button)
        outer.addWidget(self.header)

        content = QHBoxLayout()
        content.setSpacing(12)

        axis_card = Card(padding=18)
        axis_top = QHBoxLayout()
        axis_title = QLabel("轴控制")
        axis_title.setProperty("role", "section")
        axis_top.addWidget(axis_title)
        axis_top.addStretch(1)
        self.soft_limit = make_chip(
            f"软限位 {self.ctx.settings.travel_x_mm:.0f} × {self.ctx.settings.travel_y_mm:.0f} mm"
        )
        axis_top.addWidget(self.soft_limit)
        axis_card.body.addLayout(axis_top)

        coords = QHBoxLayout()
        coords.setSpacing(10)
        self.coord_labels = {}
        for axis, unit in (("X", "mm"), ("Y", "mm"), ("Z", "mm")):
            box = QWidget()
            set_css(box, "inset")
            box_layout = QVBoxLayout(box)
            box_layout.setContentsMargins(14, 10, 14, 10)
            box_layout.setSpacing(0)
            name = QLabel(f"{axis} AXIS")
            name.setProperty("role", "eyebrow")
            value = QLabel("0.00")
            value.setStyleSheet(
                "font-family: 'Cascadia Mono'; font-size: 30px; font-weight: 700; color: #e8f2f5;"
            )
            unit_label = QLabel(unit)
            unit_label.setProperty("role", "faint")
            box_layout.addWidget(name)
            box_layout.addWidget(value)
            box_layout.addWidget(unit_label)
            self.coord_labels[axis] = value
            coords.addWidget(box, 1)
        axis_card.body.addLayout(coords)
        axis_card.body.addWidget(hline())

        settings_row = QHBoxLayout()
        step_label = QLabel("点动步长")
        step_label.setProperty("role", "muted")
        settings_row.addWidget(step_label)
        self.step_group = QButtonGroup(self)
        self.step_group.setExclusive(True)
        for step in (0.1, 1.0, 10.0):
            control = button(f"{step:g} mm", variant="subtle")
            control.setProperty("segment", "true")
            control.setCheckable(True)
            control.setFixedWidth(66)
            if step == 1.0:
                control.setChecked(True)
            control.clicked.connect(lambda checked=False, value=step: self._set_step(value))
            self.step_group.addButton(control)
            settings_row.addWidget(control)
        settings_row.addSpacing(20)
        speed_label = QLabel("速度")
        speed_label.setProperty("role", "muted")
        settings_row.addWidget(speed_label)
        self.speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.speed_slider.setRange(5, 100)
        self.speed_slider.setValue(self._speed_pct)
        self.speed_slider.setFixedWidth(160)
        self.speed_slider.valueChanged.connect(self._set_speed)
        settings_row.addWidget(self.speed_slider)
        self.speed_value = QLabel(f"{self._speed_pct}%")
        self.speed_value.setStyleSheet("font-family: 'Cascadia Mono';")
        self.speed_value.setFixedWidth(38)
        settings_row.addWidget(self.speed_value)
        settings_row.addStretch(1)
        axis_card.body.addLayout(settings_row)

        jog_area = QHBoxLayout()
        jog_area.addStretch(1)
        jog_grid = QGridLayout()
        jog_grid.setSpacing(8)
        self.jog_buttons: dict[str, Any] = {}
        specs = [
            ("Y+", 0, 1, "arrow-up", COLORS["accent"]),
            ("X-", 1, 0, "arrow-left", COLORS["accent"]),
            ("HOME", 1, 1, "home", COLORS["text"]),
            ("X+", 1, 2, "arrow-right", COLORS["accent"]),
            ("Y-", 2, 1, "arrow-down", COLORS["accent"]),
        ]
        for name, row, col, icon_name, color in specs:
            control = button("", icon_name, "subtle")
            control.setProperty("jog", "true")
            control.setMinimumSize(68, 58)
            control.setIconSize(QSize(22, 22))
            control.setToolTip(f"{name} 点动")
            if name == "HOME":
                control.setToolTip("移动到原点")
                control.clicked.connect(self._home)
            else:
                control.clicked.connect(lambda checked=False, axis=name: self._jog(axis))
            jog_grid.addWidget(control, row, col)
            self.jog_buttons[name] = control
        jog_area.addLayout(jog_grid)
        jog_area.addSpacing(24)
        z_column = QVBoxLayout()
        z_column.setSpacing(8)
        z_up = button("Z+  上", "arrow-up", "subtle")
        z_down = button("Z−  下", "arrow-down", "subtle")
        z_up.setMinimumHeight(58)
        z_down.setMinimumHeight(58)
        z_up.clicked.connect(lambda: self._jog("Z+"))
        z_down.clicked.connect(lambda: self._jog("Z-"))
        z_column.addWidget(z_up)
        z_column.addSpacing(6)
        z_column.addWidget(z_down)
        z_column.addStretch(1)
        self.jog_buttons["Z+"] = z_up
        self.jog_buttons["Z-"] = z_down
        jog_area.addLayout(z_column)
        jog_area.addStretch(1)
        axis_card.body.addLayout(jog_area)

        io_label = QLabel("轴状态 · 仿真 IO")
        io_label.setProperty("role", "eyebrow")
        axis_card.body.addSpacing(6)
        axis_card.body.addWidget(io_label)
        io_row = QHBoxLayout()
        io_row.setSpacing(8)
        self.io_tiles: dict[str, QLabel] = {}
        for key, title in (
            ("x", "X 行程"),
            ("y", "Y 行程"),
            ("z", "Z 行程"),
            ("servo", "伺服"),
            ("vacuum", "真空"),
        ):
            tile, value = self._status_tile(title, "正常" if key != "vacuum" else "关闭")
            self.io_tiles[key] = value
            io_row.addWidget(tile, 1)
        axis_card.body.addLayout(io_row)

        quick_label = QLabel("快捷定位")
        quick_label.setProperty("role", "eyebrow")
        axis_card.body.addSpacing(10)
        axis_card.body.addWidget(quick_label)
        quick_row = QHBoxLayout()
        quick_row.setSpacing(8)
        self.quick_buttons: list[QPushButton] = []
        for label_text, key in (
            ("安全高度", "safe"),
            ("板卡中心", "board"),
            ("机械原点", "origin"),
            ("料站 01", "feeder"),
        ):
            control = button(label_text, "target" if key != "origin" else "home", "subtle")
            control.setMinimumHeight(42)
            control.clicked.connect(lambda checked=False, target=key: self._quick_move(target))
            quick_row.addWidget(control, 1)
            self.quick_buttons.append(control)
        axis_card.body.addLayout(quick_row)

        axis_card.body.addSpacing(10)
        self.action_header = QHBoxLayout()
        action_title = QLabel("最近操作")
        action_title.setProperty("role", "eyebrow")
        self.action_header.addWidget(action_title)
        self.action_header.addStretch(1)
        self.action_chip = make_chip("LOCAL")
        self.action_header.addWidget(self.action_chip)
        axis_card.body.addLayout(self.action_header)
        self.action_container = QVBoxLayout()
        self.action_container.setSpacing(2)
        axis_card.body.addLayout(self.action_container)
        self._action_rows: list[QWidget] = []
        self._action_placeholder = True
        self._add_action_row("等待手动操作")
        axis_card.body.addStretch(1)

        axis_footer = QHBoxLayout()
        self.position_hint = QLabel("提示：点动命令受软限位保护；生产运行时手动轴控被锁定。")
        self.position_hint.setProperty("role", "faint")
        axis_footer.addWidget(self.position_hint)
        axis_footer.addStretch(1)
        self.nozzle_state = QLabel("NOZZLE N1")
        self.nozzle_state.setProperty("role", "mono")
        axis_footer.addWidget(self.nozzle_state)
        axis_card.body.addLayout(axis_footer)
        content.addWidget(axis_card, 1)

        side = QVBoxLayout()
        side.setSpacing(12)

        vacuum = Card()
        vacuum_title = QLabel("吸嘴与真空")
        vacuum_title.setProperty("role", "section")
        vacuum.body.addWidget(vacuum_title)
        vacuum_row = QHBoxLayout()
        self.vacuum_dot = StatusDot(COLORS["faint"], 9)
        self.vacuum_label = QLabel("真空关闭")
        self.vacuum_label.setStyleSheet("font-size: 15px; font-weight: 600;")
        vacuum_row.addWidget(self.vacuum_dot)
        vacuum_row.addWidget(self.vacuum_label)
        vacuum_row.addStretch(1)
        vacuum.body.addLayout(vacuum_row)
        self.vacuum_button = button("打开真空", "zap", "primary", 38)
        self.vacuum_button.setCheckable(True)
        self.vacuum_button.clicked.connect(self._toggle_vacuum)
        vacuum.body.addWidget(self.vacuum_button)
        nozzle_row = QHBoxLayout()
        nozzle_label = QLabel("吸嘴")
        nozzle_label.setProperty("role", "muted")
        self.nozzle_combo = QComboBox()
        for i in range(1, 5):
            self.nozzle_combo.addItem(f"N{i}", f"N{i}")
        nozzle_row.addWidget(nozzle_label)
        nozzle_row.addStretch(1)
        nozzle_row.addWidget(self.nozzle_combo)
        vacuum.body.addLayout(nozzle_row)
        change_nozzle = button("切换吸嘴", "refresh", "subtle")
        change_nozzle.clicked.connect(self._change_nozzle)
        vacuum.body.addWidget(change_nozzle)
        side.addWidget(vacuum)

        conveyor = Card()
        conveyor_title = QLabel("传送与照明")
        conveyor_title.setProperty("role", "section")
        conveyor.body.addWidget(conveyor_title)
        status_row = QHBoxLayout()
        self.conveyor_label = QLabel("传送带停止")
        self.conveyor_label.setProperty("role", "muted")
        status_row.addWidget(self.conveyor_label)
        status_row.addStretch(1)
        conveyor.body.addLayout(status_row)
        conveyor_row = QHBoxLayout()
        self.feed_button = button("进板", "arrow-right", "subtle")
        self.stop_button = button("停止", "stop", "subtle")
        self.reverse_button = button("退板", "arrow-left", "subtle")
        self.feed_button.clicked.connect(lambda: self._conveyor("feed"))
        self.stop_button.clicked.connect(lambda: self._conveyor("stop"))
        self.reverse_button.clicked.connect(lambda: self._conveyor("reverse"))
        for control in (self.feed_button, self.stop_button, self.reverse_button):
            conveyor_row.addWidget(control, 1)
        conveyor.body.addLayout(conveyor_row)
        self.lights_button = button("打开照明", "zap", "subtle")
        self.lights_button.setCheckable(True)
        self.lights_button.clicked.connect(self._toggle_lights)
        conveyor.body.addWidget(self.lights_button)
        side.addWidget(conveyor)

        feeder = Card()
        feeder_title = QLabel("供料器点动")
        feeder_title.setProperty("role", "section")
        feeder.body.addWidget(feeder_title)
        slot_row = QHBoxLayout()
        slot_label = QLabel("槽位")
        slot_label.setProperty("role", "muted")
        self.slot_spin = QSpinBox()
        self.slot_spin.setRange(1, 40)
        self.slot_spin.setValue(1)
        self.slot_spin.setPrefix("SLOT ")
        slot_row.addWidget(slot_label)
        slot_row.addStretch(1)
        slot_row.addWidget(self.slot_spin)
        feeder.body.addLayout(slot_row)
        advance = button("前进一个料位", "feeder", "subtle")
        advance.clicked.connect(self._feed_advance)
        feeder.body.addWidget(advance)
        self.feeder_hint = QLabel("补料/调试时使用，动作会同步扣减余料。")
        self.feeder_hint.setProperty("role", "hint")
        self.feeder_hint.setWordWrap(True)
        feeder.body.addWidget(self.feeder_hint)
        feeder.body.addStretch(1)
        side.addWidget(feeder)
        side.addStretch(1)
        content.addLayout(side, 0)
        outer.addLayout(content, 1)

        self.home_button.clicked.connect(self._home)

    def _add_action_row(self, text: str) -> None:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(8)
        dot = StatusDot(COLORS["faint"], 5)
        label = QLabel(text)
        label.setStyleSheet("font-size: 11px; color: #9cb0bc;")
        stamp = QLabel(datetime.now().strftime("%H:%M:%S"))
        stamp.setStyleSheet(f"font-family: 'Cascadia Mono'; font-size: 10px; color: {COLORS['faint']};")
        layout.addWidget(dot)
        layout.addWidget(label, 1)
        layout.addWidget(stamp)
        self.action_container.insertWidget(0, row)
        self._action_rows.insert(0, row)
        while len(self._action_rows) > 4:
            old = self._action_rows.pop()
            old.setParent(None)
            old.deleteLater()

    def _record_action(self, text: str) -> None:
        if self._action_placeholder and self._action_rows:
            first = self._action_rows[0]
            first.setParent(None)
            first.deleteLater()
            self._action_rows.clear()
            self._action_placeholder = False
        self._add_action_row(text)
        self.ctx.log("INFO", "MANUAL", text)

    def _status_tile(self, title: str, value: str) -> tuple[QWidget, QLabel]:
        tile = QWidget()
        set_css(tile, "inset")
        layout = QVBoxLayout(tile)
        layout.setContentsMargins(10, 7, 10, 7)
        layout.setSpacing(2)
        name = QLabel(title)
        name.setProperty("role", "faint")
        value_label = QLabel(value)
        value_label.setStyleSheet(f"color: {COLORS['accent']}; font-size: 11px; font-weight: 600;")
        layout.addWidget(name)
        layout.addWidget(value_label)
        return tile, value_label

    def _connect(self) -> None:
        self.ctx.machine.state_changed.connect(self._on_state)
        self.ctx.machine.connection_changed.connect(lambda *_: self._on_state(self.ctx.machine.state.value))
        self.ctx.machine.position_changed.connect(self._on_position)
        self.ctx.machine.vacuum_changed.connect(self._on_vacuum)
        self.ctx.machine.telemetry.connect(self._on_telemetry)
        self.ctx.signals.settings_changed.connect(self._refresh_limits)

    def _refresh_limits(self) -> None:
        self.soft_limit.setText(
            f"软限位 {self.ctx.settings.travel_x_mm:.0f} × {self.ctx.settings.travel_y_mm:.0f} mm"
        )

    def _set_step(self, step: float) -> None:
        self._step = step

    def _set_speed(self, value: int) -> None:
        self._speed_pct = value
        self.speed_value.setText(f"{value}%")

    def _speed(self) -> float:
        return self.ctx.settings.limits.max_speed_mm_s * self._speed_pct / 100.0

    def _jog(self, axis: str) -> None:
        dx = self._step if axis == "X+" else (-self._step if axis == "X-" else 0.0)
        dy = self._step if axis == "Y+" else (-self._step if axis == "Y-" else 0.0)
        dz = self._step if axis == "Z+" else (-self._step if axis == "Z-" else 0.0)
        self.ctx.machine.jog(dx, dy, dz, self._speed())
        self._record_action(f"点动 {axis}  {self._step:g} mm  @ {self._speed_pct}%")

    def _home(self) -> None:
        if self.ctx.machine.run_active:
            self.ctx.toast("生产进行中，无法回原点", "warning")
            return
        self.ctx.machine.home()
        self._record_action("执行回原点")

    def _conveyor(self, action: str) -> None:
        self.ctx.machine.conveyor(action)
        self._record_action({"feed": "传送带进板", "reverse": "传送带退板", "stop": "传送带停止"}.get(action, action))

    def _feed_advance(self) -> None:
        slot = self.slot_spin.value()
        self.ctx.machine.feed(slot, 1)
        self._record_action(f"槽位 {slot:02d} 前进一个料位")

    def _quick_move(self, target: str) -> None:
        if self.ctx.machine.run_active:
            self.ctx.toast("生产进行中，手动轴控已锁定", "warning")
            return
        product = self.ctx.current_product
        safe_z = self.ctx.settings.limits.safe_z_mm
        if target == "safe":
            self.ctx.machine.move_to(self.coord_value("X"), self.coord_value("Y"), safe_z, self._speed())
            self._record_action("快捷定位：安全高度")
        elif target == "board" and product:
            center = product.board_center
            self.ctx.machine.move_to(center.x, center.y, safe_z, self._speed())
            self._record_action("快捷定位：板卡中心")
        elif target == "origin":
            self.ctx.machine.move_to(0.0, 0.0, safe_z, self._speed())
            self._record_action("快捷定位：机械原点")
        elif target == "feeder":
            feeders = [f for f in self.ctx.feeders() if f.enabled]
            if feeders:
                feeder = feeders[0]
                self.ctx.machine.move_to(feeder.pick_x_mm, feeder.pick_y_mm, feeder.pick_z_mm, self._speed())
                self._record_action(f"快捷定位：槽位 {feeder.slot:02d}")
            else:
                self.ctx.toast("没有可用供料器", "warning")

    def coord_value(self, axis: str) -> float:
        try:
            return float(self.coord_labels[axis].text().strip())
        except ValueError:
            return 0.0

    def _toggle_vacuum(self, checked: bool) -> None:
        self.ctx.machine.vacuum(checked)
        self._record_action(f"真空{'开启' if checked else '关闭'}")

    def _change_nozzle(self) -> None:
        nozzle = str(self.nozzle_combo.currentData())
        self.ctx.machine.nozzle(nozzle)
        self._record_action(f"切换吸嘴 {nozzle}")

    def _toggle_lights(self, checked: bool) -> None:
        self.ctx.machine.lights(checked)
        self.lights_button.setText("关闭照明" if checked else "打开照明")
        self._record_action(f"照明{'开启' if checked else '关闭'}")

    def _on_position(self, x: float, y: float, z: float) -> None:
        self.coord_labels["X"].setText(f"{x:8.2f}")
        self.coord_labels["Y"].setText(f"{y:8.2f}")
        self.coord_labels["Z"].setText(f"{z:8.2f}")
        limits = self.ctx.settings.limits
        for key, value, maximum in (("x", x, limits.travel_x_mm), ("y", y, limits.travel_y_mm), ("z", z, limits.travel_z_mm)):
            if value < 0.05:
                text, color = "原点", COLORS["warn"]
            elif value >= maximum - 0.05:
                text, color = "上限", COLORS["warn"]
            else:
                text, color = "行程内", COLORS["accent"]
            self.io_tiles[key].setText(text)
            self.io_tiles[key].setStyleSheet(f"color: {color}; font-size: 11px; font-weight: 600;")

    def _on_vacuum(self, on: bool) -> None:
        self._vacuum_on = on
        self.vacuum_button.setChecked(on)
        self.vacuum_button.setText("关闭真空" if on else "打开真空")
        self.vacuum_dot.set_color(COLORS["accent"] if on else COLORS["faint"])
        self.vacuum_label.setText("真空开启" if on else "真空关闭")
        self.vacuum_label.setStyleSheet(
            f"font-size: 15px; font-weight: 600; color: {COLORS['accent'] if on else COLORS['text']};"
        )
        self.io_tiles["vacuum"].setText("开启" if on else "关闭")
        self.io_tiles["vacuum"].setStyleSheet(
            f"color: {COLORS['accent'] if on else COLORS['faint']}; font-size: 11px; font-weight: 600;"
        )

    def _on_telemetry(self, data: dict[str, Any]) -> None:
        if data.get("type") == "conveyor":
            state = str(data.get("state", "stopped"))
            self.conveyor_label.setText({"feeding": "传送带进板中", "reversing": "传送带退板中", "stopped": "传送带停止"}.get(state, state))
        elif data.get("type") == "lights":
            on = bool(data.get("on", False))
            self.lights_button.setChecked(on)
            self.lights_button.setText("关闭照明" if on else "打开照明")
        elif "nozzle" in data:
            index = self.nozzle_combo.findData(str(data["nozzle"]))
            if index >= 0:
                self.nozzle_combo.setCurrentIndex(index)
            self.nozzle_state.setText(f"NOZZLE {data['nozzle']}")

    def _on_state(self, state_value: str) -> None:
        try:
            state = MachineState(state_value)
        except ValueError:
            state = MachineState.OFFLINE
        color = state_color(state)
        label = state_label(state)
        self.state_chip.setText(label)
        self.state_chip.setStyleSheet(
            f"background: {color}16; border: 1px solid {color}55; color: {color};"
            "border-radius: 10px; padding: 3px 9px; font-size: 11px; font-weight: 700;"
        )
        enabled = self.ctx.connected and state not in {
            MachineState.OFFLINE,
            MachineState.CONNECTING,
            MachineState.ERROR,
            MachineState.ESTOP,
            MachineState.RUNNING,
            MachineState.PAUSED,
        }
        self.home_button.setEnabled(self.ctx.connected and not self.ctx.machine.run_active)
        for control in self.jog_buttons.values():
            control.setEnabled(enabled)
        for control in self.quick_buttons:
            control.setEnabled(enabled)
        self.speed_slider.setEnabled(enabled)
        self.vacuum_button.setEnabled(enabled)
        self.nozzle_combo.setEnabled(enabled)
        self.feed_button.setEnabled(enabled)
        self.stop_button.setEnabled(enabled)
        self.reverse_button.setEnabled(enabled)
        self.lights_button.setEnabled(self.ctx.connected)
        self.slot_spin.setEnabled(enabled)
        if state is MachineState.RUNNING:
            self.position_hint.setText("生产运行中，手动轴控已锁定。")
        elif state in {MachineState.ERROR, MachineState.ESTOP}:
            self.position_hint.setText("设备报警，请先排除故障并复位。")
        else:
            self.position_hint.setText("提示：点动命令受软限位保护；生产运行时手动轴控被锁定。")
        if state in {MachineState.ERROR, MachineState.ESTOP, MachineState.OFFLINE}:
            self.io_tiles["servo"].setText("未使能")
            self.io_tiles["servo"].setStyleSheet(f"color: {COLORS['danger']}; font-size: 11px; font-weight: 600;")
        elif state is MachineState.HOMING:
            self.io_tiles["servo"].setText("回零中")
            self.io_tiles["servo"].setStyleSheet(f"color: {COLORS['warn']}; font-size: 11px; font-weight: 600;")
        else:
            self.io_tiles["servo"].setText("使能")
            self.io_tiles["servo"].setStyleSheet(f"color: {COLORS['accent']}; font-size: 11px; font-weight: 600;")
