"""主窗口：侧边导航、顶栏、状态栏与页面容器。"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .. import APP_NAME, APP_NAME_ZH, __version__
from ..core.models import MachineState, RunRecord
from .context import AppContext
from .icons import app_icon, icon, nav_icon
from .machine_gallery import DeviceCard, MachineGalleryDialog
from .pages.components import ComponentsPage
from .pages.feeders import FeedersPage
from .pages.home import HomePage
from .pages.logs import LogsPage
from .pages.manual import ManualPage
from .pages.packages import PackagesPage
from .pages.production import ProductionPage
from .pages.programming import ProgrammingPage
from .pages.settings import SettingsPage
from .pages.vision import VisionPage
from .status import state_color, state_label
from .theme import COLORS
from .widgets import StatusDot, Toast, set_css, vline


NAV_ITEMS = [
    ("home", "首页", "home", "运行"),
    ("production", "生产执行", "production", "运行"),
    ("programming", "产品编程", "programming", "运行"),
    ("feeders", "供料器", "feeder", "运行"),
    ("components", "元件库", "component", "运行"),
    ("packages", "封装库", "layers", "运行"),
    ("manual", "手动控制", "manual", "运行"),
    ("vision", "视觉对位", "vision", "运行"),
    ("logs", "系统日志", "logs", "系统"),
    ("settings", "系统设置", "settings", "系统"),
]


class MainWindow(QMainWindow):
    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.machine = ctx.machine
        self._nav_buttons: dict[str, QPushButton] = {}
        self._pages: dict[str, QWidget] = {}
        self._head = (0.0, 0.0, 0.0)
        self._connected = False
        self.setWindowTitle(f"{APP_NAME} · {APP_NAME_ZH}")
        self.setWindowIcon(app_icon())
        self.setMinimumSize(1280, 820)
        self.resize(1600, 980)
        self._build()
        self._wire()
        self._clock_timer = QTimer(self)
        self._clock_timer.timeout.connect(self._tick_clock)
        self._clock_timer.start(1000)
        self._tick_clock()
        QTimer.singleShot(700, self._auto_connect)
        self.navigate("home")

    # ---------------- build ----------------

    def _build(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._build_sidebar())

        main = QWidget()
        main_layout = QVBoxLayout(main)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        main_layout.addWidget(self._build_topbar())
        main_layout.addWidget(self._build_alarm_banner())

        self.stack = QStackedWidget()
        self._create_pages()
        main_layout.addWidget(self.stack, 1)
        main_layout.addWidget(self._build_statusbar())
        layout.addWidget(main, 1)

        self.toast = Toast(self)

    def _build_sidebar(self) -> QFrame:
        sidebar = QFrame()
        set_css(sidebar, "sidebar")
        sidebar.setFixedWidth(226)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 0, 0, 12)
        layout.setSpacing(0)

        logo_row = QHBoxLayout()
        logo_row.setContentsMargins(18, 18, 16, 14)
        logo_row.setSpacing(10)
        mark = QLabel()
        mark.setPixmap(app_icon(96).pixmap(38, 38))
        mark.setFixedSize(40, 40)
        text_col = QVBoxLayout()
        text_col.setSpacing(0)
        brand = QLabel("MidPnP")
        brand.setStyleSheet("font-size: 18px; font-weight: 800; letter-spacing: 0.5px;")
        studio = QLabel("S T U D I O")
        studio.setStyleSheet(
            f"font-size: 9px; font-weight: 700; color: {COLORS['accent']}; letter-spacing: 3px;"
        )
        text_col.addWidget(brand)
        text_col.addWidget(studio)
        logo_row.addWidget(mark)
        logo_row.addLayout(text_col)
        logo_row.addStretch(1)
        layout.addLayout(logo_row)

        machine_wrap = QHBoxLayout()
        machine_wrap.setContentsMargins(14, 0, 14, 12)
        self.device_card = DeviceCard(self.ctx.profile)
        self.device_card.clicked.connect(self._switch_device)
        self.sidebar_dot = self.device_card.dot
        self.sidebar_state = self.device_card.state
        self.sidebar_machine = self.device_card.name
        self.sidebar_conn = self.device_card.conn
        machine_wrap.addWidget(self.device_card)
        layout.addLayout(machine_wrap)

        group = ""
        self._nav_group = QButtonGroup(self)
        self._nav_group.setExclusive(True)
        for key, label, icon_name, item_group in NAV_ITEMS:
            if item_group != group:
                group = item_group
                layout.addSpacing(8)
                section = QLabel("系统" if group == "系统" else "运行")
                section.setStyleSheet(
                    f"color: {COLORS['faint']}; font-size: 9px; font-weight: 700;"
                    " letter-spacing: 2px; padding-left: 20px;"
                )
                layout.addWidget(section)
                layout.addSpacing(4)
            control = QPushButton(f"  {label}")
            control.setProperty("nav", "true")
            control.setCheckable(True)
            control.setIcon(nav_icon(icon_name, 19))
            control.setIconSize(QSize(19, 19))
            control.setCursor(Qt.CursorShape.PointingHandCursor)
            control.clicked.connect(lambda checked=False, page=key: self.navigate(page))
            self._nav_group.addButton(control)
            self._nav_buttons[key] = control
            layout.addWidget(control)

        layout.addStretch(1)
        footer = QVBoxLayout()
        footer.setContentsMargins(18, 8, 18, 0)
        footer.setSpacing(6)
        line = QFrame()
        set_css(line, "divider")
        footer.addWidget(line)
        mode = {
            "simulator": "SIMULATION MODE",
            "tcp": "TCP CONNECTED MODE",
            "serial": "SERIAL MODE",
        }.get(self.ctx.settings.connection_mode, "OFFLINE MODE")
        self.mode_label = QLabel(mode)
        self.mode_label.setStyleSheet(
            f"color: {COLORS['accent']}; font-family: 'Cascadia Mono'; font-size: 9px; letter-spacing: 1px;"
        )
        footer.addWidget(self.mode_label)
        version = QLabel(f"v{__version__}  ·  本地数据")
        version.setStyleSheet(f"color: {COLORS['faint']}; font-size: 9px;")
        footer.addWidget(version)
        layout.addLayout(footer)
        return sidebar

    def _build_topbar(self) -> QFrame:
        bar = QFrame()
        set_css(bar, "topbar")
        bar.setFixedHeight(62)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(24, 0, 18, 0)
        layout.setSpacing(12)

        crumb_col = QVBoxLayout()
        crumb_col.setSpacing(1)
        self.crumb = QLabel("生产总览")
        self.crumb.setStyleSheet("font-size: 13px; font-weight: 600;")
        self.crumb_sub = QLabel("工作区 / MIDPNP M1")
        self.crumb_sub.setProperty("role", "faint")
        crumb_col.addWidget(self.crumb)
        crumb_col.addWidget(self.crumb_sub)
        layout.addLayout(crumb_col)
        layout.addStretch(1)

        self.conn_button = QPushButton("  未连接")
        self.conn_button.setIcon(icon("link", COLORS["muted"], 15))
        self.conn_button.setProperty("variant", "subtle")
        self.conn_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.conn_button.setFixedHeight(30)
        self.conn_button.setToolTip("打开连接设置")
        layout.addWidget(self.conn_button)

        time_col = QVBoxLayout()
        time_col.setSpacing(0)
        self.clock = QLabel("--:--:--")
        self.clock.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.clock.setStyleSheet("font-family: 'Cascadia Mono'; font-size: 14px; font-weight: 600;")
        self.date_label = QLabel("")
        self.date_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.date_label.setProperty("role", "faint")
        time_col.addWidget(self.clock)
        time_col.addWidget(self.date_label)
        layout.addLayout(time_col)
        layout.addWidget(vline())

        user = QHBoxLayout()
        user.setSpacing(7)
        avatar = QLabel(self.ctx.settings.operator[:1] or "O")
        avatar.setFixedSize(26, 26)
        avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        avatar.setStyleSheet(
            f"background: {COLORS['accent_soft']}; color: {COLORS['accent']};"
            f" border: 1px solid {COLORS['accent_dim']}; border-radius: 13px; font-weight: 700;"
        )
        user_name = QLabel(self.ctx.settings.operator)
        user_name.setStyleSheet("font-size: 12px;")
        user.addWidget(avatar)
        user.addWidget(user_name)
        layout.addLayout(user)

        self.estop_button = QPushButton("■  急停")
        self.estop_button.setProperty("variant", "estop")
        self.estop_button.setFixedSize(94, 36)
        self.estop_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.estop_button.setToolTip("立即停止所有运动（急停按钮）")
        layout.addWidget(self.estop_button)
        return bar

    def _build_alarm_banner(self) -> QFrame:
        self.alarm_banner = QFrame()
        self.alarm_banner.setFixedHeight(38)
        self.alarm_banner.setStyleSheet(
            f"background: #2a1015; border-bottom: 1px solid {COLORS['danger']}55;"
        )
        layout = QHBoxLayout(self.alarm_banner)
        layout.setContentsMargins(24, 0, 20, 0)
        layout.setSpacing(10)
        glyph = QLabel()
        glyph.setPixmap(icon("warning", COLORS["danger"], 16).pixmap(16, 16))
        layout.addWidget(glyph)
        self.alarm_label = QLabel("设备报警，请排除故障后复位")
        self.alarm_label.setStyleSheet("color: #ff9aa4; font-size: 12px; font-weight: 600;")
        layout.addWidget(self.alarm_label)
        layout.addStretch(1)
        self.alarm_reset = QPushButton("复位报警")
        self.alarm_reset.setProperty("variant", "danger")
        self.alarm_reset.setFixedHeight(26)
        self.alarm_reset.clicked.connect(self.ctx.machine.clear_fault)
        layout.addWidget(self.alarm_reset)
        self.alarm_banner.hide()
        return self.alarm_banner

    def _build_statusbar(self) -> QFrame:
        bar = QFrame()
        set_css(bar, "statusbar")
        bar.setFixedHeight(28)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(20, 0, 20, 0)
        layout.setSpacing(14)
        self.footer_dot = StatusDot(COLORS["muted"], 6)
        layout.addWidget(self.footer_dot)
        self.footer_state = QLabel("离线")
        self.footer_state.setStyleSheet("font-size: 10px; font-weight: 600;")
        layout.addWidget(self.footer_state)
        self.footer_conn = QLabel("未连接")
        self.footer_conn.setStyleSheet(f"color: {COLORS['faint']}; font-size: 10px;")
        layout.addWidget(self.footer_conn)
        layout.addWidget(self._separator_label())
        self.footer_position = QLabel("X 0.0   Y 0.0   Z 0.0")
        self.footer_position.setStyleSheet(
            f"font-family: 'Cascadia Mono'; font-size: 10px; color: {COLORS['muted']};"
        )
        layout.addWidget(self.footer_position)
        layout.addWidget(self._separator_label())
        self.footer_vacuum = QLabel("VACUUM OFF")
        self.footer_vacuum.setStyleSheet(
            f"font-family: 'Cascadia Mono'; font-size: 10px; color: {COLORS['faint']};"
        )
        layout.addWidget(self.footer_vacuum)
        layout.addStretch(1)
        self.footer_product = QLabel("")
        self.footer_product.setStyleSheet(f"color: {COLORS['faint']}; font-size: 10px;")
        layout.addWidget(self.footer_product)
        layout.addWidget(self._separator_label())
        footer_version = QLabel(f"MidPnP Studio v{__version__}")
        footer_version.setStyleSheet(f"color: {COLORS['faint']}; font-size: 10px;")
        layout.addWidget(footer_version)
        return bar

    def _separator_label(self) -> QLabel:
        label = QLabel("·")
        label.setStyleSheet(f"color: {COLORS['border']};")
        return label

    def _create_pages(self) -> None:
        self.home = HomePage(self.ctx)
        self.production = ProductionPage(self.ctx)
        self.programming = ProgrammingPage(self.ctx)
        self.feeders = FeedersPage(self.ctx)
        self.components = ComponentsPage(self.ctx)
        self.packages = PackagesPage(self.ctx)
        self.manual = ManualPage(self.ctx)
        self.vision = VisionPage(self.ctx)
        self.logs = LogsPage(self.ctx)
        self.settings = SettingsPage(self.ctx)
        for key, page in (
            ("home", self.home),
            ("production", self.production),
            ("programming", self.programming),
            ("feeders", self.feeders),
            ("components", self.components),
            ("packages", self.packages),
            ("manual", self.manual),
            ("vision", self.vision),
            ("logs", self.logs),
            ("settings", self.settings),
        ):
            self._pages[key] = page
            self.stack.addWidget(page)

    # ---------------- signals ----------------

    def _wire(self) -> None:
        self.conn_button.clicked.connect(self._on_conn_clicked)
        self.estop_button.clicked.connect(self._emergency_stop)
        self.ctx.signals.navigate.connect(self.navigate)
        self.ctx.signals.start_production.connect(self._start_production)
        self.ctx.signals.toast.connect(self.show_toast)
        self.ctx.signals.product_changed.connect(self._on_product_changed)
        self.ctx.signals.settings_changed.connect(self._on_settings_changed)
        self.ctx.signals.profile_changed.connect(self._on_profile_changed)

        self.machine.connection_changed.connect(self._on_connection)
        self.machine.state_changed.connect(self._on_state)
        self.machine.position_changed.connect(self._on_position)
        self.machine.vacuum_changed.connect(self._on_vacuum)
        self.machine.log.connect(self._on_machine_log)
        self.machine.notification.connect(self.show_toast)
        self.machine.run_finished.connect(self._on_run_finished)

    # ---------------- navigation ----------------

    def navigate(self, key: str) -> None:
        page = self._pages.get(key)
        if page is None:
            return
        self.stack.setCurrentWidget(page)
        for button_key, control in self._nav_buttons.items():
            control.setChecked(button_key == key)
        item = next((item for item in NAV_ITEMS if item[0] == key), None)
        if item:
            self.crumb.setText(item[1])
            self.crumb_sub.setText(f"工作区 / {self.ctx.profile.name} / {item[1]}")
        if key == "logs":
            self.logs.refresh()
        elif key == "home":
            self.home.refresh()

    def _start_production(self) -> None:
        self.navigate("production")
        QTimer.singleShot(80, self.production._start)

    # ---------------- startup ----------------

    def _auto_connect(self) -> None:
        self.ctx.log("INFO", "APP", f"{APP_NAME} v{__version__} 已启动")
        self._on_settings_changed()
        if self.ctx.settings.auto_connect and not self._connected:
            self.ctx.machine.connect_machine(self.ctx.settings, self.ctx.feeders(), self.ctx.profile)

    def showEvent(self, event: Any) -> None:  # noqa: N802
        super().showEvent(event)
        self.toast.reposition()

    def resizeEvent(self, event: Any) -> None:  # noqa: N802
        super().resizeEvent(event)
        if hasattr(self, "toast"):
            self.toast.reposition()

    # ---------------- clock ----------------

    def _tick_clock(self) -> None:
        now = datetime.now()
        weekdays = "一二三四五六日"
        self.clock.setText(now.strftime("%H:%M:%S"))
        self.date_label.setText(f"{now.month}月{now.day}日 周{weekdays[now.weekday()]}")

    # ---------------- machine events ----------------

    def _on_connection(self, connected: bool, label: str) -> None:
        self._connected = connected
        self.ctx.connected = connected
        self.footer_conn.setText(label)
        self.sidebar_conn.setText(label)
        color = COLORS["accent"] if connected else COLORS["muted"]
        self.conn_button.setText("  已连接" if connected else "  未连接")
        self.conn_button.setToolTip(label)
        self.conn_button.setIcon(icon("wifi" if connected else "link", color, 15))
        self.conn_button.setStyleSheet(
            f"QPushButton {{ background: {color}0e; border: 1px solid {color}33;"
            f" color: {color if connected else COLORS['muted']}; border-radius: 5px; padding: 5px 9px; font-size: 11px; }}"
            "QPushButton:hover { background: #152530; }"
        )
        if not connected:
            self.footer_dot.set_color(COLORS["muted"])
            self.footer_state.setText("离线")
            self.alarm_banner.hide()
        else:
            self._on_state(self.machine.state.value)

    def _on_state(self, state_value: str) -> None:
        try:
            state = MachineState(state_value)
        except ValueError:
            state = MachineState.OFFLINE
        color = state_color(state)
        label = state_label(state)
        self.sidebar_dot.set_color(color)
        self.sidebar_state.setText(f"设备{label}" if state not in {MachineState.RUNNING, MachineState.PAUSED} else label)
        self.sidebar_state.setStyleSheet(f"font-size: 11px; font-weight: 600; color: {color};")
        self.footer_dot.set_color(color)
        self.footer_state.setText(label)
        self.footer_state.setStyleSheet(f"font-size: 10px; font-weight: 600; color: {color};")
        if state in {MachineState.ERROR, MachineState.ESTOP}:
            self.alarm_label.setText(
                "急停已触发，请排除风险后复位" if state is MachineState.ESTOP else "设备报警，请检查日志并复位"
            )
            self.alarm_banner.show()
        else:
            self.alarm_banner.hide()

    def _on_position(self, x: float, y: float, z: float) -> None:
        self._head = (x, y, z)
        self.ctx.head = (x, y, z)
        self.footer_position.setText(f"X {x:6.1f}   Y {y:6.1f}   Z {z:5.1f}")

    def _on_vacuum(self, on: bool) -> None:
        self.ctx.vacuum = on
        self.footer_vacuum.setText("VACUUM ON" if on else "VACUUM OFF")
        self.footer_vacuum.setStyleSheet(
            f"font-family: 'Cascadia Mono'; font-size: 10px;"
            f" color: {COLORS['accent'] if on else COLORS['faint']};"
        )

    def _on_machine_log(self, level: str, source: str, message: str) -> None:
        self.ctx.log(level, source, message)

    def _on_product_changed(self, product: Any) -> None:
        if product:
            self.footer_product.setText(f"{product.name} · REV {product.revision}")
            self.crumb_sub.setText(f"工作区 / {self.ctx.profile.name} / {self.crumb.text()}")

    def _on_settings_changed(self) -> None:
        self.device_card.set_profile(self.ctx.profile)
        mode = {
            "simulator": "SIMULATION MODE",
            "tcp": "TCP MODE",
            "serial": "SERIAL MODE",
        }.get(self.ctx.settings.connection_mode, "OFFLINE MODE")
        self.mode_label.setText(mode)
        self.crumb_sub.setText(f"工作区 / {self.ctx.profile.name} / {self.crumb.text()}")
        self.footer_product.setText(
            f"{self.ctx.current_product.name} · REV {self.ctx.current_product.revision}"
            if self.ctx.current_product
            else ""
        )

    def _on_profile_changed(self, profile: Any) -> None:
        self.device_card.set_profile(self.ctx.profile)
        self.crumb_sub.setText(f"工作区 / {self.ctx.profile.name} / {self.crumb.text()}")
        self.ctx.toast(f"设备已切换：{self.ctx.profile.name}", "info")

    def _on_conn_clicked(self) -> None:
        if not self._connected:
            self._open_connect_dialog()
        else:
            self.navigate("settings")

    def _open_connect_dialog(self) -> None:
        from .connect_dialog import ConnectDialog

        dialog = ConnectDialog(self.ctx, parent=self)
        dialog.exec()

    def _switch_device(self) -> None:
        if self.machine.run_active:
            self.show_toast("生产运行中，无法切换设备", "warning")
            return
        dialog = MachineGalleryDialog(self.ctx, first_run=False, parent=self)
        if not dialog.exec() or dialog.selected_profile is None:
            return
        profile = dialog.selected_profile
        if profile.id == self.ctx.profile.id:
            return
        was_connected = self._connected
        try:
            self.ctx.apply_profile(profile)
        except Exception as exc:
            QMessageBox.critical(self, "切换失败", str(exc))
            return
        self.device_card.set_profile(self.ctx.profile)
        self.home.refresh(profile_changed=True)
        if was_connected:
            self.machine.disconnect_machine()
            QTimer.singleShot(300, self._open_connect_dialog)

    # ---------------- actions ----------------

    def _emergency_stop(self) -> None:
        self.machine.emergency_stop()

    def _on_run_finished(self, payload: dict[str, Any]) -> None:
        try:
            record: RunRecord = self.ctx.record_run(payload)
        except Exception as exc:
            self.ctx.log("ERROR", "RUN", f"生产记录保存失败：{exc}")
            self.show_toast(f"生产记录保存失败：{exc}", "error")
            return
        self.home.refresh()
        self.production.refresh()
        self.feeders.refresh()
        if record.status == "Completed":
            self.show_toast(
                f"生产完成：{record.placed}/{record.total} 点，用时 {record.duration_s:.0f}s",
                "success",
            )
        elif record.status == "Cancelled":
            self.show_toast(f"生产已停止：完成 {record.placed}/{record.total} 点", "warning")
        elif record.status == "Faulted":
            self.show_toast(f"生产异常中止：完成 {record.placed}/{record.total} 点", "error")

    def show_toast(self, message: str, level: str = "info") -> None:
        self.toast.show_message(message, level)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        if self.machine.run_active:
            answer = QMessageBox.question(
                self,
                "退出 MidPnP Studio",
                "生产任务仍在运行，退出将停止任务。确定退出？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self.machine.stop()
            deadline = time.monotonic() + 2.5
            while self.machine.run_active and time.monotonic() < deadline:
                QApplication.processEvents()
                time.sleep(0.04)
        try:
            self.ctx.save_settings()
        except Exception:
            pass
        self.machine.shutdown()
        try:
            self.ctx.storage.close()
        except Exception:
            pass
        event.accept()
