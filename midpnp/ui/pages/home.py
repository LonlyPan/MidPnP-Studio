"""首页：相机画面 + 点动面板 + 机器线稿总览。

布局：
- 左侧上：单相机画面（顶部 / 底部切换）；
- 左侧下：Jog 点动；
- 右侧：整机线稿（中间底板、上下各 25 个电动飞达，按装料状态高亮）。
"""

from __future__ import annotations

import time
from typing import Any

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from ...core.models import MachineState
from ...core.vision import Point2, SimulatedCamera
from ..context import AppContext
from ..status import state_color, state_label
from ..theme import COLORS
from ..widgets import (
    Card,
    PageHeader,
    StatusDot,
    button,
    make_chip,
    set_css,
)
from .vision import CameraView


# ---------------------------------------------------------------- 线稿总览


class MachineScene(QWidget):
    """整机俯视线稿：上下两排电动飞达 + 中间底板 + 龙门/贴装头。"""

    GREEN = "#37d67a"
    AMBER = "#f0b429"
    DIM = "#24343d"

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.setMinimumSize(560, 500)
        self._profile = ctx.profile
        self._feeders: dict[int, Any] = {}
        self._components: dict[str, Any] = {}
        self._product: Any = None
        self._head = (0.0, 0.0, 0.0)
        self._state = MachineState.OFFLINE
        self._connected = False
        self._last_paint = 0.0
        self.refresh()

    # ---------------- 数据 ----------------

    def refresh(self) -> None:
        self._profile = self.ctx.profile
        self._feeders = {feeder.slot: feeder for feeder in self.ctx.feeders()}
        self._components = self.ctx.component_map()
        self._product = self.ctx.current_product
        self._state = self.ctx.machine.state
        self._connected = self.ctx.connected
        self.update()

    def set_head(self, x: float, y: float, z: float = 0.0) -> None:
        self._head = (x, y, z)
        now = time.monotonic()
        if now - self._last_paint > 0.07:
            self._last_paint = now
            self.update()

    def set_connection(self, connected: bool, state: str = "") -> None:
        self._connected = connected
        if state:
            try:
                self._state = MachineState(state)
            except ValueError:
                pass
        self.update()

    # ---------------- 绘制 ----------------

    def paintEvent(self, event: Any) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        width, height = self.width(), self.height()
        rect = QRectF(0.5, 0.5, width - 1, height - 1)
        painter.setPen(QPen(QColor(COLORS["border_soft"]), 1))
        painter.setBrush(QColor("#070d11"))
        painter.drawRoundedRect(rect, 10, 10)

        # 背景网格
        painter.setPen(QPen(QColor(255, 255, 255, 6), 1))
        for x in range(24, width, 28):
            painter.drawLine(QPointF(x, 6), QPointF(x, height - 6))
        for y in range(24, height, 28):
            painter.drawLine(QPointF(6, y), QPointF(width - 6, y))

        profile = self._profile
        if profile is None:
            painter.end()
            return
        bank = profile.feeders
        top_count = bank.top_count or max(1, bank.slot_count // 2)
        bottom_count = bank.bottom_count or max(0, bank.slot_count - top_count)
        first_slot = bank.first_slot

        margin_x = 30.0
        lane_h = min(104.0, height * 0.17)
        top_y = 46.0
        bottom_y = height - 30.0 - lane_h
        bed = QRectF(
            margin_x,
            top_y + lane_h + 20.0,
            width - margin_x * 2,
            max(80.0, bottom_y - (top_y + lane_h) - 40.0),
        )

        # 外框
        frame = QRectF(margin_x - 10, top_y - 16, width - margin_x * 2 + 20, bottom_y + lane_h + 20 - (top_y - 16))
        painter.setPen(QPen(QColor("#2b4652"), 1.4))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(frame, 8, 8)

        self._draw_bank(painter, QRectF(margin_x, top_y, width - margin_x * 2, lane_h), top_count, first_slot, "上排飞达")
        self._draw_bank(
            painter,
            QRectF(margin_x, bottom_y, width - margin_x * 2, lane_h),
            bottom_count,
            first_slot + top_count,
            "下排飞达",
        )
        self._draw_bed(painter, bed)

        if not self._connected:
            painter.setBrush(QColor(5, 10, 13, 80))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 10, 10)
            panel = QRectF(rect.center().x() - 150, rect.center().y() - 30, 300, 60)
            painter.setBrush(QColor(10, 18, 23, 235))
            painter.setPen(QPen(QColor(COLORS["warn"]), 1.2))
            painter.drawRoundedRect(panel, 8, 8)
            painter.setPen(QColor(COLORS["warn"]))
            painter.setFont(QFont("Microsoft YaHei UI", 11, QFont.Weight.DemiBold))
            painter.drawText(panel, Qt.AlignmentFlag.AlignCenter, "设备未连接\n点击「连接设备」开始")
        painter.end()

    # ---------------- 飞达区 ----------------

    def _draw_bank(
        self,
        painter: QPainter,
        area: QRectF,
        count: int,
        first_slot: int,
        title: str,
    ) -> None:
        if count <= 0:
            return
        # 料架底座
        painter.setPen(QPen(QColor(self.DIM), 1))
        painter.setBrush(QColor("#0b1419"))
        painter.drawRoundedRect(area, 5, 5)

        painter.setPen(QColor(COLORS["faint"]))
        painter.setFont(QFont("Microsoft YaHei UI", 8))
        painter.drawText(QPointF(area.left() + 4, area.top() - 7), title)

        inset = 6.0
        lane_w = (area.width() - inset * 2) / count
        for index in range(count):
            slot = first_slot + index
            lane = QRectF(area.left() + inset + index * lane_w, area.top() + 6, max(1.0, lane_w - 2), area.height() - 12)
            feeder = self._feeders.get(slot)
            component = self._components.get(feeder.component_id) if feeder else None
            self._draw_lane(painter, lane, slot, feeder, component)

    def _draw_lane(
        self,
        painter: QPainter,
        lane: QRectF,
        slot: int,
        feeder: Any,
        component: Any,
    ) -> None:
        installed = feeder is not None and feeder.enabled
        low = False
        if feeder is not None:
            low = feeder.is_empty or feeder.is_low
        if installed and not low:
            fill = QColor(self.GREEN)
            fill.setAlpha(34)
            border = QColor(self.GREEN)
            text_color = QColor("#d9f7e6")
            style = Qt.PenStyle.SolidLine
        elif feeder is not None:
            fill = QColor(self.AMBER)
            fill.setAlpha(28)
            border = QColor(self.AMBER)
            text_color = QColor("#ffe6b0")
            style = Qt.PenStyle.SolidLine
        else:
            fill = QColor(0, 0, 0, 0)
            border = QColor(self.DIM)
            text_color = QColor(COLORS["faint"])
            style = Qt.PenStyle.DashLine

        painter.setPen(QPen(border, 1.2, style))
        painter.setBrush(fill)
        painter.drawRoundedRect(lane, 2.5, 2.5)

        # 槽位号
        painter.setPen(QColor(COLORS["faint"]))
        painter.setFont(QFont("Cascadia Mono", 7))
        painter.drawText(
            QRectF(lane.left(), lane.top() + 3, lane.width(), 10),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
            f"{slot:02d}",
        )

        if feeder is None:
            return
        label = self._feeder_label(feeder, component)
        if not label:
            return
        painter.setPen(text_color)
        font = QFont("Cascadia Mono", 8)
        painter.setFont(font)
        metrics = QFontMetrics(font)
        text = metrics.elidedText(label, Qt.TextElideMode.ElideRight, int(lane.height() - 16))
        painter.save()
        painter.translate(lane.center().x() + 4, lane.bottom() - 7)
        painter.rotate(-90)
        painter.drawText(QPointF(0, 0), text)
        painter.restore()

    @staticmethod
    def _feeder_label(feeder: Any, component: Any) -> str:
        import re

        def compact(text: str) -> str:
            return re.sub(r"[^A-Za-z0-9]", "", text or "").upper()

        raw = (feeder.label or "").strip()
        if "·" in raw:
            raw = raw.split("·")[-1].strip()
        if not raw and component is not None:
            raw = str(component.name)
        package = str(getattr(component, "package", "") or "")
        compact_package = compact(package)
        compact_raw = compact(raw)
        if package and compact_package not in compact_raw:
            if not (len(raw) <= 5 and compact_package.startswith(compact_raw[:3])):
                raw = f"{raw}-{package}"
        return raw

    # ---------------- 底板 ----------------

    def _draw_bed(self, painter: QPainter, bed: QRectF) -> None:
        painter.setPen(QPen(QColor("#2b4652"), 1.2))
        painter.setBrush(QColor("#0a1216"))
        painter.drawRoundedRect(bed, 6, 6)

        # 吸附孔阵列
        painter.setPen(QPen(QColor(255, 255, 255, 22), 1))
        step = max(12, int(bed.width() / 46))
        y = bed.top() + 10
        while y < bed.bottom() - 6:
            x = bed.left() + 10
            while x < bed.right() - 6:
                painter.drawPoint(QPointF(x, y))
                x += step
            y += step

        profile = self._profile
        limits = profile.limits() if profile else None
        if limits is None:
            return
        travel_x = max(1.0, limits.travel_x_mm)
        travel_y = max(1.0, limits.travel_y_mm)

        def to_bed(mx: float, my: float) -> QPointF:
            return QPointF(
                bed.left() + max(0.0, min(1.0, mx / travel_x)) * bed.width(),
                bed.bottom() - max(0.0, min(1.0, my / travel_y)) * bed.height(),
            )

        # 产品板框
        product = self._product
        if product is not None:
            top_left = to_bed(product.board_origin_x_mm, product.board_origin_y_mm + product.board_height_mm)
            bottom_right = to_bed(
                product.board_origin_x_mm + product.board_width_mm,
                product.board_origin_y_mm,
            )
            board_rect = QRectF(top_left, bottom_right).normalized()
            painter.setPen(QPen(QColor(COLORS["accent"]), 1.0))
            fill = QColor(COLORS["accent"])
            fill.setAlpha(18)
            painter.setBrush(fill)
            painter.drawRect(board_rect)
            painter.setBrush(QColor(COLORS["accent"]))
            painter.setPen(Qt.PenStyle.NoPen)
            for placement in getattr(product, "placements", []):
                point = to_bed(
                    product.board_origin_x_mm + placement.x_mm,
                    product.board_origin_y_mm + placement.y_mm,
                )
                painter.drawEllipse(point, 1.4, 1.4)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(COLORS["warn"]), 1.2))
            for fiducial in getattr(product, "fiducials", []):
                point = to_bed(
                    product.board_origin_x_mm + fiducial.x_mm,
                    product.board_origin_y_mm + fiducial.y_mm,
                )
                painter.drawEllipse(point, 3.2, 3.2)

        # 底部相机孔（对应实物照片中的圆孔）
        hole = QPointF(bed.center().x(), bed.bottom() - bed.height() * 0.18)
        painter.setPen(QPen(QColor("#3a5663"), 1.2))
        painter.setBrush(QColor("#05090b"))
        painter.drawEllipse(hole, 18, 18)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(hole, 11, 11)
        painter.drawEllipse(hole, 4.5, 4.5)

        # 龙门与贴装头
        head_x, head_y, _ = self._head
        raw = to_bed(head_x, head_y)
        carriage = QPointF(
            max(bed.left() + 24.0, min(bed.right() - 24.0, raw.x())),
            max(bed.top() + 24.0, min(bed.bottom() - 24.0, raw.y())),
        )
        painter.setPen(QPen(QColor("#3f6270"), 3.0))
        painter.drawLine(QPointF(bed.left() + 4, carriage.y()), QPointF(bed.right() - 4, carriage.y()))
        painter.setPen(QPen(QColor("#243d49"), 1.0, Qt.PenStyle.DashLine))
        painter.drawLine(QPointF(carriage.x(), bed.top() + 4), QPointF(carriage.x(), bed.bottom() - 4))
        painter.setPen(QPen(QColor(COLORS["accent"]), 1.2, Qt.PenStyle.DashLine))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(carriage, 22, 22)
        painter.setPen(QPen(QColor(COLORS["accent"]), 1.4))
        painter.setBrush(QColor("#12232b"))
        painter.drawRoundedRect(QRectF(carriage.x() - 16, carriage.y() - 9, 32, 18), 3, 3)
        nozzle_count = max(1, len(self._profile.nozzle_ids())) if self._profile else 1
        for index in range(min(nozzle_count, 4)):
            offset = (index - (min(nozzle_count, 4) - 1) / 2) * 8
            painter.setBrush(QColor("#c9d6dc"))
            painter.drawEllipse(QPointF(carriage.x() + offset, carriage.y() + 13), 2.4, 2.4)
        painter.setPen(QColor(COLORS["accent"]))
        painter.setFont(QFont("Cascadia Mono", 7))
        painter.drawText(QPointF(carriage.x() + 26, carriage.y() - 16), "HEAD")

        # 坐标轴示意
        painter.setPen(QPen(QColor(COLORS["faint"]), 1))
        painter.setFont(QFont("Cascadia Mono", 7))
        painter.drawText(QPointF(bed.left() + 8, bed.top() + 14), f"X 0–{travel_x:.0f} mm")
        painter.save()
        painter.translate(bed.right() - 10, bed.top() + 70)
        painter.rotate(-90)
        painter.drawText(QPointF(0, 0), f"Y 0–{travel_y:.0f} mm")
        painter.restore()


# ---------------------------------------------------------------- 首页


class HomePage(QWidget):
    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self._camera_mode = "top"
        self._last_camera = 0.0
        self._build()
        self._connect()
        self._on_connection(self.ctx.connected, "")
        self._on_state(self.ctx.machine.state.value)
        self.refresh()

    # ---------------- UI ----------------

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 18, 20, 18)
        outer.setSpacing(12)

        self.header = PageHeader("首页", "相机画面、点动控制与整机状态")
        self.state_chip = make_chip("离线")
        self.connect_button = button("连接设备", "link", "primary")
        self.header.add_action(self.state_chip)
        self.header.add_action(self.connect_button)
        outer.addWidget(self.header)

        self.banner = QFrame()
        self.banner.setStyleSheet(
            f"background: {COLORS['warn']}12; border: 1px solid {COLORS['warn']}44; border-radius: 8px;"
        )
        banner_layout = QHBoxLayout(self.banner)
        banner_layout.setContentsMargins(14, 8, 10, 8)
        banner_layout.setSpacing(10)
        glyph = QLabel("!")
        glyph.setFixedSize(18, 18)
        glyph.setAlignment(Qt.AlignmentFlag.AlignCenter)
        glyph.setStyleSheet(
            f"background: {COLORS['warn']}; color: #1a1205; border-radius: 9px; font-weight: 800;"
        )
        banner_layout.addWidget(glyph)
        banner_text = QLabel("设备未连接：相机、主机、归位与校准尚未就绪，暂时无法点动或生产。")
        banner_text.setStyleSheet(f"color: {COLORS['warn']}; font-size: 12px;")
        banner_layout.addWidget(banner_text)
        banner_layout.addStretch(1)
        self.banner_button = button("连接", "link", "subtle")
        self.banner_button.setFixedHeight(28)
        banner_layout.addWidget(self.banner_button)
        outer.addWidget(self.banner)

        content = QHBoxLayout()
        content.setSpacing(12)

        left = QVBoxLayout()
        left.setSpacing(12)

        camera_card = Card(padding=12)
        camera_top = QHBoxLayout()
        camera_title = QLabel("相机画面")
        camera_title.setProperty("role", "section")
        camera_top.addWidget(camera_title)
        self.camera_top_button = button("顶部相机", "camera", "subtle")
        self.camera_bottom_button = button("底部相机", "camera", "subtle")
        for control in (self.camera_top_button, self.camera_bottom_button):
            control.setProperty("segment", "true")
            control.setCheckable(True)
            control.setFixedHeight(28)
            camera_top.addWidget(control)
        self.camera_group = QButtonGroup(self)
        self.camera_group.setExclusive(True)
        self.camera_group.addButton(self.camera_top_button)
        self.camera_group.addButton(self.camera_bottom_button)
        self.camera_top_button.setChecked(True)
        camera_top.addStretch(1)
        self.camera_chip = make_chip("CAM-TOP")
        camera_top.addWidget(self.camera_chip)
        camera_card.body.addLayout(camera_top)
        self.camera_view = CameraView()
        self.camera_view.setMinimumHeight(230)
        camera_card.body.addWidget(self.camera_view, 1)
        self.camera_hint = QLabel("")
        self.camera_hint.setProperty("role", "hint")
        self.camera_hint.setWordWrap(True)
        camera_card.body.addWidget(self.camera_hint)
        left.addWidget(camera_card, 5)

        left.addWidget(self._build_jog_card(), 4)
        content.addLayout(left, 5)

        scene_card = Card(padding=12)
        scene_top = QHBoxLayout()
        scene_title = QLabel("整机总览")
        scene_title.setProperty("role", "section")
        scene_top.addWidget(scene_title)
        self.bank_chip = make_chip("")
        scene_top.addWidget(self.bank_chip)
        scene_top.addStretch(1)
        self.scene_state = make_chip("离线")
        scene_top.addWidget(self.scene_state)
        scene_card.body.addLayout(scene_top)
        self.scene = MachineScene(self.ctx)
        scene_card.body.addWidget(self.scene, 1)
        legend = QHBoxLayout()
        legend.setSpacing(14)
        for text, color, dashed in (
            ("已装料 / 已连接", MachineScene.GREEN, False),
            ("低料 / 停用", MachineScene.AMBER, False),
            ("空位", "#2a3a44", True),
        ):
            legend.addWidget(self._legend_item(text, color, dashed))
        legend.addStretch(1)
        tip = QLabel("点击左上设备图片可切换机型")
        tip.setProperty("role", "faint")
        legend.addWidget(tip)
        scene_card.body.addLayout(legend)
        content.addWidget(scene_card, 7)

        outer.addLayout(content, 1)

        self.connect_button.clicked.connect(self._open_connect)
        self.banner_button.clicked.connect(self._open_connect)
        self.camera_top_button.clicked.connect(lambda: self._set_camera("top"))
        self.camera_bottom_button.clicked.connect(lambda: self._set_camera("bottom"))

    def _build_jog_card(self) -> Card:
        card = Card(padding=12)
        top = QHBoxLayout()
        title = QLabel("点动控制")
        title.setProperty("role", "section")
        top.addWidget(title)
        top.addStretch(1)
        self.jog_speed_label = QLabel("40%")
        self.jog_speed_label.setProperty("role", "mono")
        self.jog_speed = QSlider(Qt.Orientation.Horizontal)
        self.jog_speed.setRange(10, 100)
        self.jog_speed.setValue(40)
        self.jog_speed.setFixedWidth(110)
        self.jog_speed.valueChanged.connect(lambda value: self.jog_speed_label.setText(f"{value}%"))
        top.addWidget(QLabel("速度"))
        top.addWidget(self.jog_speed)
        top.addWidget(self.jog_speed_label)
        card.body.addLayout(top)

        coords = QHBoxLayout()
        coords.setSpacing(8)
        self.coord_labels: dict[str, QLabel] = {}
        for axis in ("X", "Y", "Z"):
            box = QWidget()
            set_css(box, "inset")
            box_layout = QHBoxLayout(box)
            box_layout.setContentsMargins(10, 4, 10, 4)
            box_layout.setSpacing(6)
            name = QLabel(axis)
            name.setStyleSheet(f"color: {COLORS['faint']}; font-weight: 700; font-size: 11px;")
            value = QLabel("0.00")
            value.setStyleSheet("font-family: 'Cascadia Mono'; font-size: 16px; font-weight: 600;")
            box_layout.addWidget(name)
            box_layout.addWidget(value)
            box_layout.addStretch(1)
            self.coord_labels[axis] = value
            coords.addWidget(box, 1)
        card.body.addLayout(coords)

        step_row = QHBoxLayout()
        step_row.setSpacing(6)
        step_label = QLabel("步长")
        step_label.setProperty("role", "muted")
        step_row.addWidget(step_label)
        self.step_group = QButtonGroup(self)
        self.step_group.setExclusive(True)
        self._step = 1.0
        for step in (0.1, 1.0, 10.0):
            control = button(f"{step:g}", variant="subtle")
            control.setProperty("segment", "true")
            control.setCheckable(True)
            control.setFixedSize(48, 26)
            if step == 1.0:
                control.setChecked(True)
            control.clicked.connect(lambda checked=False, value=step: self._set_step(value))
            self.step_group.addButton(control)
            step_row.addWidget(control)
        step_row.addSpacing(6)
        step_row.addWidget(QLabel("mm"))
        step_row.addStretch(1)
        self.vacuum_button = button("真空", "zap", "subtle")
        self.vacuum_button.setCheckable(True)
        self.vacuum_button.setFixedHeight(26)
        self.vacuum_button.setMinimumWidth(66)
        step_row.addWidget(self.vacuum_button)
        card.body.addLayout(step_row)

        pad = QHBoxLayout()
        pad.setSpacing(10)
        grid = QGridLayout()
        grid.setSpacing(6)
        self._jog_buttons: list[Any] = []
        for label, icon_name, row, col, direction in (
            ("Y+", "arrow-up", 0, 1, (0, 1, 0)),
            ("X-", "arrow-left", 1, 0, (-1, 0, 0)),
            ("HOME", "home", 1, 1, None),
            ("X+", "arrow-right", 1, 2, (1, 0, 0)),
            ("Y-", "arrow-down", 2, 1, (0, -1, 0)),
        ):
            control = button("", icon_name, "subtle")
            control.setProperty("jog", "true")
            control.setMinimumSize(52, 40)
            control.setIconSize(QSize(18, 18))
            control.setToolTip(label)
            if direction is None:
                control.clicked.connect(self._home)
                self.home_button = control
            else:
                control.clicked.connect(
                    lambda checked=False, d=direction: self._jog(
                        d[0] * self._step, d[1] * self._step, d[2] * self._step
                    )
                )
            grid.addWidget(control, row, col)
            self._jog_buttons.append(control)

        z_up = button("Z+", "arrow-up", "subtle")
        z_down = button("Z-", "arrow-down", "subtle")
        for index, (control, sign) in enumerate(((z_up, 1), (z_down, -1))):
            control.setMinimumSize(52, 40)
            control.setToolTip(f"Z{'轴上升' if sign > 0 else '轴下降'}")
            control.clicked.connect(
                lambda checked=False, s=sign: self._jog(0.0, 0.0, s * self._step)
            )
            grid.addWidget(control, index, 3)
            self._jog_buttons.append(control)
        pad.addLayout(grid)
        pad.addStretch(1)
        card.body.addLayout(pad)

        self.jog_hint = QLabel("连接设备后可点动；生产运行时手动轴控被锁定。")
        self.jog_hint.setProperty("role", "faint")
        card.body.addWidget(self.jog_hint)
        return card

    def _legend_item(self, text: str, color: str, dashed: bool) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        swatch = QLabel()
        swatch.setFixedSize(14, 10)
        style = "dashed" if dashed else "solid"
        fill = "transparent" if dashed else color
        swatch.setStyleSheet(f"border: 1px {style} {color}; background: {fill}; border-radius: 2px;")
        label = QLabel(text)
        label.setProperty("role", "faint")
        layout.addWidget(swatch)
        layout.addWidget(label)
        return widget

    # ---------------- 信号 ----------------

    def _connect(self) -> None:
        self.ctx.machine.connection_changed.connect(self._on_connection)
        self.ctx.machine.state_changed.connect(self._on_state)
        self.ctx.machine.position_changed.connect(self._on_position)
        self.ctx.machine.vacuum_changed.connect(self._on_vacuum)
        self.ctx.signals.feeders_changed.connect(self.refresh)
        self.ctx.signals.components_changed.connect(self.refresh)
        self.ctx.signals.product_changed.connect(lambda *_: self.refresh())
        self.ctx.signals.profile_changed.connect(lambda *_: self.refresh(profile_changed=True))
        self.ctx.signals.settings_changed.connect(lambda *_: self.refresh())
        self._timer = QTimer(self)
        self._timer.setInterval(800)
        self._timer.timeout.connect(self._tick_camera)

    def showEvent(self, event: Any) -> None:  # noqa: N802
        super().showEvent(event)
        self._timer.start()
        QTimer.singleShot(120, self._tick_camera)

    def hideEvent(self, event: Any) -> None:  # noqa: N802
        self._timer.stop()
        super().hideEvent(event)

    # ---------------- 状态 ----------------

    def refresh(self, profile_changed: bool = False) -> None:
        profile = self.ctx.profile
        feeders = self.ctx.feeders()
        loaded = sum(1 for feeder in feeders if feeder.enabled)
        self.bank_chip.setText(
            f"已装 {loaded} · 上料 {profile.feeders.top_count or profile.feeders.slot_count // 2} · "
            f"下料 {profile.feeders.bottom_count or profile.feeders.slot_count - profile.feeders.top_count}"
        )
        self.scene.refresh()
        if profile_changed:
            self._camera_mode = "top"
            self.camera_top_button.setChecked(True)
            self._tick_camera()
        self._apply_connection_state(self.ctx.connected)

    def _apply_connection_state(self, connected: bool) -> None:
        self.banner.setVisible(not connected)
        self.connect_button.setText("重新连接" if connected else "连接设备")
        for control in self._jog_buttons:
            control.setEnabled(connected)
        self.vacuum_button.setEnabled(connected)
        self.jog_hint.setText(
            "点动已启用；生产运行时手动轴控会被锁定。"
            if connected
            else "设备未连接：点动、真空与生产不可用。"
        )

    def _on_connection(self, connected: bool, label: str) -> None:
        self.scene.set_connection(connected)
        self._apply_connection_state(connected)
        self.camera_hint.setText(label or ("已连接" if connected else "未连接"))
        if connected:
            self.ctx.toast("设备已连接", "success")

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
            "border-radius: 10px; padding: 3px 9px; font-size: 11px;"
        )
        self.scene_state.setText(label)
        self.scene_state.setStyleSheet(
            f"background: {color}16; border: 1px solid {color}55; color: {color};"
            "border-radius: 10px; padding: 3px 9px; font-size: 11px;"
        )

    def _on_position(self, x: float, y: float, z: float) -> None:
        self.coord_labels["X"].setText(f"{x:6.2f}")
        self.coord_labels["Y"].setText(f"{y:6.2f}")
        self.coord_labels["Z"].setText(f"{z:5.2f}")
        self.scene.set_head(x, y, z)

    def _on_vacuum(self, on: bool) -> None:
        self.vacuum_button.setChecked(on)
        self.vacuum_button.setText("真空开" if on else "真空")

    # ---------------- 相机 ----------------

    def _camera_config(self, mode: str | None = None) -> Any:
        mode = mode or self._camera_mode
        cameras = [camera for camera in self.ctx.profile.cameras if camera.enabled]
        if mode == "bottom":
            for camera in cameras:
                if "bottom" in camera.id.lower() or camera.pipeline.startswith("bottom"):
                    return camera
        for camera in cameras:
            if camera.mount == "head" and "bottom" not in camera.id.lower():
                return camera
        return cameras[0] if cameras else None

    def _set_camera(self, mode: str) -> None:
        self._camera_mode = mode
        self.camera_top_button.setChecked(mode == "top")
        self.camera_bottom_button.setChecked(mode == "bottom")
        self._tick_camera()

    def _tick_camera(self) -> None:
        config = self._camera_config()
        if config is None:
            self.camera_view.set_frame(None)
            self.camera_view.set_hud(["无相机"], "机型未配置相机")
            return
        camera = SimulatedCamera(config, seed=23)
        product = self.ctx.current_product
        head_x, head_y, _ = self.ctx.head
        detections: list[dict[str, Any]] = []
        if self._camera_mode == "bottom":
            frame = camera.capture_part(None, tip_diameter_mm=0.6, seed=19)
            hud = [f"{config.id}  BOTTOM  ·  {config.resolution[0]}x{config.resolution[1]}", "空吸嘴 · 等待吸料"]
            state_text = "底部相机 · 预览"
        else:
            ppm = None
            center = Point2(head_x or 0.0, head_y or 0.0)
            if product is not None:
                center = Point2(
                    product.board_origin_x_mm + product.board_width_mm / 2.0,
                    product.board_origin_y_mm + product.board_height_mm / 2.0,
                )
                ppm = min(
                    config.resolution[0] / max(1.0, product.board_width_mm * 1.15),
                    config.resolution[1] / max(1.0, product.board_height_mm * 1.15),
                )
            frame = camera.capture_board(
                center,
                product=product,
                components=self.ctx.components(),
                packages=self.ctx.package_map(),
                pixels_per_mm=ppm,
            )
            if product is not None:
                calibration = frame.calibration
                for fiducial in product.fiducials:
                    dx = product.board_origin_x_mm + fiducial.x_mm - center.x
                    dy = product.board_origin_y_mm + fiducial.y_mm - center.y
                    px, py = calibration.mm_to_pixel(dx, dy)
                    if 0 <= px < calibration.width and 0 <= py < calibration.height:
                        detections.append(
                            {
                                "x": px,
                                "y": py,
                                "radius": calibration.mm_to_pixel_size(fiducial.radius_mm * 2 + 1.2) / 2,
                                "label": fiducial.name,
                                "color": COLORS["warn"],
                            }
                        )
            hud = [
                f"{config.id}  TOP  ·  {config.resolution[0]}x{config.resolution[1]}",
                "整板预览" if ppm else "随头视野",
                f"HEAD {head_x:.1f}, {head_y:.1f} mm",
            ]
            state_text = "顶部相机 · 预览"
        self.camera_chip.setText(config.id)
        self.camera_view.set_frame(frame, detections)
        self.camera_view.set_hud(hud, state_text)
        self.camera_hint.setText(
            ("相机已连接 · " if self.ctx.connected else "设备未连接 · 仿真预览 · ") + config.id
        )

    # ---------------- 操作 ----------------

    def _set_step(self, value: float) -> None:
        self._step = value
        for action in self._jog_buttons:
            action.setToolTip(f"点动步长 {value:g} mm")

    def _jog(self, dx: float, dy: float, dz: float) -> None:
        if not self.ctx.connected:
            self.ctx.toast("设备未连接", "warning")
            return
        speed = self.ctx.settings.max_speed_mm_s * self.jog_speed.value() / 100.0
        self.ctx.machine.jog(dx=dx, dy=dy, dz=dz, speed=speed)

    def _home(self) -> None:
        if not self.ctx.connected:
            self.ctx.toast("设备未连接", "warning")
            return
        self.ctx.machine.home()

    def _open_connect(self) -> None:
        from ..connect_dialog import ConnectDialog

        dialog = ConnectDialog(self.ctx, parent=self)
        dialog.exec()
        self._tick_camera()

    def _toggle_vacuum(self) -> None:
        if not self.ctx.connected:
            self.ctx.toast("设备未连接", "warning")
            self.vacuum_button.setChecked(False)
            return
        self.ctx.machine.vacuum(self.vacuum_button.isChecked())

    # ---------------- 兼容旧接口 ----------------

    def _start_or_connect(self) -> None:
        if not self.ctx.connected:
            self._open_connect()
        else:
            self.ctx.signals.start_production.emit()
