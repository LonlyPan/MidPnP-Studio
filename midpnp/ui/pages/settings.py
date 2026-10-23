"""系统设置页。"""

from __future__ import annotations

import sys
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ... import APP_NAME, __version__
from ...config import AppSettings
from ..context import AppContext
from ..theme import COLORS
from ..widgets import Card, PageHeader, PageScroll, button, hline, make_chip


class SettingsPage(QWidget):
    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self._loading = False
        self._build()
        self._load()
        self._connect()

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.scroll = PageScroll(self)
        outer.addWidget(self.scroll)
        body = self.scroll.layout
        self.header = PageHeader("系统设置", "设备连接、机器行程与数据维护")
        self.saved_chip = make_chip("已加载")
        self.save_button = button("保存并应用", "save", "primary")
        self.reconnect_button = button("重新连接", "refresh", "subtle")
        self.header.add_action(self.saved_chip)
        self.header.add_action(self.reconnect_button)
        self.header.add_action(self.save_button)
        body.addWidget(self.header)

        columns = QHBoxLayout()
        columns.setSpacing(12)
        left = QVBoxLayout()
        left.setSpacing(12)
        right = QVBoxLayout()
        right.setSpacing(12)

        connection = Card()
        connection_title = QHBoxLayout()
        title = QLabel("设备与连接")
        title.setProperty("role", "section")
        connection_title.addWidget(title)
        connection_title.addStretch(1)
        self.connection_chip = make_chip("未连接")
        connection_title.addWidget(self.connection_chip)
        connection.body.addLayout(connection_title)
        form = QFormLayout()
        form.setSpacing(9)
        self.machine_name = QLineEdit()
        self.operator = QLineEdit()
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("内置模拟器（推荐演示）", "simulator")
        self.mode_combo.addItem("TCP / 以太网", "tcp")
        self.mode_combo.addItem("串口 Serial", "serial")
        form.addRow("设备名称", self.machine_name)
        form.addRow("操作员", self.operator)
        form.addRow("连接方式", self.mode_combo)
        connection.body.addLayout(form)

        self.mode_stack = QVBoxLayout()
        self.mode_stack.setSpacing(8)
        self.sim_panel = QWidget()
        sim_layout = QVBoxLayout(self.sim_panel)
        sim_layout.setContentsMargins(0, 0, 0, 0)
        sim_hint = QLabel("内置虚拟贴片机：包含 35 点演示板、供料器余料与完整生产动作，无需外部硬件。")
        sim_hint.setProperty("role", "hint")
        sim_hint.setWordWrap(True)
        sim_layout.addWidget(sim_hint)
        speed_form = QFormLayout()
        speed_form.setSpacing(9)
        self.sim_speed = QDoubleSpinBox()
        self.sim_speed.setRange(1, 30)
        self.sim_speed.setDecimals(1)
        self.sim_speed.setSuffix(" ×")
        self.sim_speed.setToolTip("模拟运行速度倍率；不影响真实设备")
        speed_form.addRow("仿真速度", self.sim_speed)
        sim_layout.addLayout(speed_form)
        self.mode_stack.addWidget(self.sim_panel)

        self.tcp_panel = QWidget()
        tcp_layout = QFormLayout(self.tcp_panel)
        tcp_layout.setContentsMargins(0, 0, 0, 0)
        tcp_layout.setSpacing(9)
        self.host = QLineEdit()
        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        tcp_layout.addRow("IP 地址", self.host)
        tcp_layout.addRow("端口", self.port)
        tcp_hint = QLabel("协议：UTF-8 JSON Lines，默认 10s 命令超时。详见 docs/MACHINE_PROTOCOL.md。")
        tcp_hint.setProperty("role", "faint")
        tcp_hint.setWordWrap(True)
        tcp_layout.addRow(tcp_hint)
        self.mode_stack.addWidget(self.tcp_panel)

        self.serial_panel = QWidget()
        serial_layout = QFormLayout(self.serial_panel)
        serial_layout.setContentsMargins(0, 0, 0, 0)
        serial_layout.setSpacing(9)
        self.serial_port = QLineEdit()
        self.serial_port.setPlaceholderText("COM3")
        self.baud = QComboBox()
        for baud in (9600, 19200, 38400, 57600, 115200, 230400, 460800, 921600):
            self.baud.addItem(str(baud), baud)
        serial_layout.addRow("串口", self.serial_port)
        serial_layout.addRow("波特率", self.baud)
        serial_layout.addRow(QLabel("串口模式需要 pyserial：pip install pyserial"))
        self.mode_stack.addWidget(self.serial_panel)
        connection.body.addLayout(self.mode_stack)
        connection.body.addWidget(hline())
        self.auto_connect = QCheckBox("启动时自动连接设备")
        connection.body.addWidget(self.auto_connect)
        self.test_button = button("测试并连接", "link", "subtle")
        connection.body.addWidget(self.test_button)
        self.mode_combo.currentIndexChanged.connect(self._update_mode_panel)
        left.addWidget(connection)

        production = Card()
        title = QLabel("生产选项")
        title.setProperty("role", "section")
        production.body.addWidget(title)
        self.optimize_route = QCheckBox("启用最近邻贴装路径优化")
        self.confirm_start = QCheckBox("开始生产前二次确认")
        self.stop_on_low = QCheckBox("供料器低料时停止生产")
        for control in (self.optimize_route, self.confirm_start, self.stop_on_low):
            production.body.addWidget(control)
        production.body.addWidget(hline())
        form = QFormLayout()
        form.setSpacing(9)
        self.camera_source = QComboBox()
        self.camera_source.addItem("离线仿真", "simulation")
        self.camera_source.addItem("未配置", "none")
        self.log_level = QComboBox()
        for level in ("DEBUG", "INFO", "WARN", "ERROR"):
            self.log_level.addItem(level)
        form.addRow("视觉来源", self.camera_source)
        form.addRow("日志级别", self.log_level)
        production.body.addLayout(form)
        left.addWidget(production)
        left.addStretch(1)

        machine = Card()
        title = QLabel("机器行程")
        title.setProperty("role", "section")
        machine.body.addWidget(title)
        hint = QLabel("修改行程后需重新连接设备；生产前检查会按新行程校验坐标。")
        hint.setProperty("role", "faint")
        hint.setWordWrap(True)
        machine.body.addWidget(hint)
        form = QFormLayout()
        form.setSpacing(9)
        self.travel_x = self._limit_spin(1000)
        self.travel_y = self._limit_spin(1000)
        self.travel_z = self._limit_spin(200)
        self.safe_z = self._limit_spin(200)
        self.max_speed = self._limit_spin(2000, " mm/s")
        self.nozzle_count = QSpinBox()
        self.nozzle_count.setRange(1, 12)
        form.addRow("X 行程", self.travel_x)
        form.addRow("Y 行程", self.travel_y)
        form.addRow("Z 行程", self.travel_z)
        form.addRow("安全高度", self.safe_z)
        form.addRow("最大速度", self.max_speed)
        form.addRow("吸嘴数量", self.nozzle_count)
        machine.body.addLayout(form)
        right.addWidget(machine)

        data = Card()
        title = QLabel("数据与维护")
        title.setProperty("role", "section")
        data.body.addWidget(title)
        path_label = QLabel("数据目录")
        path_label.setProperty("role", "muted")
        data.body.addWidget(path_label)
        self.path_value = QLineEdit(str(self.ctx.paths.root))
        self.path_value.setReadOnly(True)
        data.body.addWidget(self.path_value)
        row = QHBoxLayout()
        self.open_folder = button("打开目录", "folder", "subtle")
        self.backup_button = button("备份数据库", "database", "subtle")
        row.addWidget(self.open_folder)
        row.addWidget(self.backup_button)
        data.body.addLayout(row)
        data.body.addWidget(hline())
        reset_hint = QLabel("重置演示数据会删除全部产品、元件、供料器与生产记录，并重新写入 35 点演示产品。")
        reset_hint.setProperty("role", "hint")
        reset_hint.setWordWrap(True)
        data.body.addWidget(reset_hint)
        self.reset_button = button("重置演示数据", "trash", "danger")
        data.body.addWidget(self.reset_button)
        right.addWidget(data)

        about = Card()
        title = QLabel("关于")
        title.setProperty("role", "section")
        about.body.addWidget(title)
        self.about_label = QLabel(
            f"{APP_NAME}\n版本 {__version__} · 桌面贴片机上位机\n"
            "Python + PySide6 · SQLite · JSONL 机器协议"
        )
        self.about_label.setProperty("role", "muted")
        about.body.addWidget(self.about_label)
        about.body.addWidget(hline())
        self.runtime_label = QLabel("")
        self.runtime_label.setProperty("role", "faint")
        self.runtime_label.setWordWrap(True)
        about.body.addWidget(self.runtime_label)
        right.addWidget(about)
        right.addStretch(1)

        columns.addLayout(left, 1)
        columns.addLayout(right, 1)
        body.addLayout(columns)
        body.addStretch(1)

        self.save_button.clicked.connect(self._save)
        self.reconnect_button.clicked.connect(self._reconnect)
        self.test_button.clicked.connect(self._test_connect)
        self.open_folder.clicked.connect(lambda: self.ctx.open_path(self.ctx.paths.root))
        self.backup_button.clicked.connect(self._backup)
        self.reset_button.clicked.connect(self._reset_demo)
        self._update_mode_panel()

    def _limit_spin(self, maximum: int, suffix: str = " mm") -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(1, maximum)
        spin.setDecimals(1)
        spin.setSuffix(suffix)
        return spin

    def _connect(self) -> None:
        self.ctx.machine.connection_changed.connect(self._on_connection)

    def _on_connection(self, connected: bool, label: str) -> None:
        self.connection_chip.setText("已连接" if connected else "未连接")
        color = COLORS["accent"] if connected else COLORS["muted"]
        self.connection_chip.setStyleSheet(
            f"background: {color}16; border: 1px solid {color}55; color: {color};"
            "border-radius: 10px; padding: 3px 9px; font-size: 11px;"
        )
        self.connection_chip.setToolTip(label)

    def _update_mode_panel(self) -> None:
        mode = str(self.mode_combo.currentData())
        self.sim_panel.setVisible(mode == "simulator")
        self.tcp_panel.setVisible(mode == "tcp")
        self.serial_panel.setVisible(mode == "serial")

    def _load(self) -> None:
        settings = self.ctx.settings
        self._loading = True
        self.machine_name.setText(settings.machine_name)
        self.operator.setText(settings.operator)
        index = self.mode_combo.findData(settings.connection_mode)
        self.mode_combo.setCurrentIndex(max(0, index))
        self.host.setText(settings.host)
        self.port.setValue(settings.port)
        self.serial_port.setText(settings.serial_port)
        baud_index = self.baud.findData(settings.baud_rate)
        if baud_index < 0:
            self.baud.addItem(str(settings.baud_rate), settings.baud_rate)
            baud_index = self.baud.findData(settings.baud_rate)
        self.baud.setCurrentIndex(baud_index)
        self.sim_speed.setValue(settings.simulation_speed)
        self.auto_connect.setChecked(settings.auto_connect)
        self.optimize_route.setChecked(settings.optimize_route)
        self.confirm_start.setChecked(settings.confirm_before_start)
        self.stop_on_low.setChecked(settings.stop_on_low_feeder)
        camera_index = self.camera_source.findData(settings.camera_source)
        self.camera_source.setCurrentIndex(max(0, camera_index))
        log_index = self.log_level.findText(settings.log_level)
        self.log_level.setCurrentIndex(max(0, log_index))
        self.travel_x.setValue(settings.travel_x_mm)
        self.travel_y.setValue(settings.travel_y_mm)
        self.travel_z.setValue(settings.travel_z_mm)
        self.safe_z.setValue(settings.safe_z_mm)
        self.max_speed.setValue(settings.max_speed_mm_s)
        self.nozzle_count.setValue(settings.nozzle_count)
        self._update_mode_panel()
        self.runtime_label.setText(
            f"数据目录：{self.ctx.paths.root}\n"
            f"Python {sys.version.split()[0]} · Qt 运行环境\n"
            f"配置保存后立即生效，连接参数在下次重连时应用。"
        )
        self._loading = False

    def _collect(self) -> AppSettings:
        settings = self.ctx.settings
        settings.machine_name = self.machine_name.text().strip() or "MidPnP"
        settings.operator = self.operator.text().strip() or "操作员"
        settings.connection_mode = str(self.mode_combo.currentData())
        settings.host = self.host.text().strip()
        settings.port = self.port.value()
        settings.serial_port = self.serial_port.text().strip()
        settings.baud_rate = int(self.baud.currentData())
        settings.simulation_speed = self.sim_speed.value()
        settings.auto_connect = self.auto_connect.isChecked()
        settings.travel_x_mm = self.travel_x.value()
        settings.travel_y_mm = self.travel_y.value()
        settings.travel_z_mm = self.travel_z.value()
        settings.safe_z_mm = min(self.safe_z.value(), self.travel_z.value())
        settings.max_speed_mm_s = self.max_speed.value()
        settings.nozzle_count = self.nozzle_count.value()
        settings.optimize_route = self.optimize_route.isChecked()
        settings.confirm_before_start = self.confirm_start.isChecked()
        settings.stop_on_low_feeder = self.stop_on_low.isChecked()
        settings.camera_source = str(self.camera_source.currentData())
        settings.log_level = self.log_level.currentText()
        return settings

    def _save(self) -> None:
        if self._loading:
            return
        settings = self._collect()
        self.ctx.save_settings()
        self.saved_chip.setText("已保存")
        self.saved_chip.setStyleSheet(
            f"background: {COLORS['accent']}16; border: 1px solid {COLORS['accent']}55;"
            f" color: {COLORS['accent']}; border-radius: 10px; padding: 3px 9px; font-size: 11px;"
        )
        self.ctx.log(
            "INFO",
            "SETTINGS",
            f"设置已保存：{settings.machine_name} / {settings.connection_mode} / "
            f"{settings.travel_x_mm:.0f}×{settings.travel_y_mm:.0f}",
        )
        self.ctx.toast("设置已保存并应用", "success")

    def _test_connect(self) -> None:
        self._save()
        self.ctx.machine.connect_machine(self.ctx.settings, self.ctx.feeders())
        self.ctx.toast("正在按当前配置连接设备…", "info")

    def _reconnect(self) -> None:
        self._save()
        self.ctx.machine.disconnect_machine()
        QTimer.singleShot(350, lambda: self.ctx.machine.connect_machine(self.ctx.settings, self.ctx.feeders()))
        self.ctx.toast("正在重新连接设备…", "info")

    def _backup(self) -> None:
        default = self.ctx.paths.exports / "midpnp_backup.db"
        path, _ = QFileDialog.getSaveFileName(self, "备份数据库", str(default), "SQLite 数据库 (*.db)")
        if not path:
            return
        try:
            self.ctx.storage.backup_to(path)
        except Exception as exc:
            QMessageBox.critical(self, "备份失败", str(exc))
            return
        self.ctx.log("INFO", "DATA", f"数据库备份至 {path}")
        self.ctx.toast("数据库备份完成", "success")

    def _reset_demo(self) -> None:
        answer = QMessageBox.warning(
            self,
            "重置演示数据",
            "将删除全部产品、元件、供料器和生产记录，并恢复内置演示数据。\n\n确定继续？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        if self.ctx.machine.run_active:
            self.ctx.toast("生产运行中，无法重置数据", "warning")
            return
        self.ctx.storage.seed_demo(force=True)
        products = self.ctx.storage.list_products()
        self.ctx.current_product_id = products[0].id if products else ""
        self.ctx.signals.products_changed.emit()
        self.ctx.signals.components_changed.emit()
        self.ctx.signals.feeders_changed.emit()
        if self.ctx.connected:
            self.ctx.machine.sync_feeders(self.ctx.feeders())
        self.ctx.log("WARN", "DATA", "演示数据已重置")
        self.ctx.toast("演示数据已恢复", "success")
