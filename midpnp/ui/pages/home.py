"""首页：相机画面 + 点动面板 + 机器线稿总览。

布局：
- 左侧上：单相机画面（顶部 / 底部切换）；
- 左侧下：Jog 点动（竖置步距/速度、吸嘴/相机选择、Z 单独归位）；
- 右侧：整机线稿（外框 = 整机范围、中间底板、上下各 25 个电动飞达）。
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ...core.models import MachineState
from ...core.vision import Point2, SimulatedCamera
from ..assets import assets_root
from ..context import AppContext
from ..status import state_color, state_label
from ..theme import COLORS
from ..widgets import (
    Card,
    button,
    make_chip,
)
from .vision import CameraView


# ---------------------------------------------------------------- 竖向标尺


class VerticalScale(QWidget):
    """竖置刻度控件：步距选择（离散）或速度（连续）。"""

    valueChanged = Signal(float)

    def __init__(
        self,
        title: str,
        labels: list[str],
        values: list[float] | None = None,
        index: int = 0,
        continuous: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._title = title
        self._labels = labels
        self._values = values or []
        self._continuous = continuous
        self._index = max(0, min(index, len(self._labels) - 1))
        self._value = self._values[self._index] if self._values else 0.0
        self.setFixedWidth(100)
        self.setMinimumHeight(150)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    # ---------------- 取值 ----------------

    def value(self) -> float:
        return self._value

    def set_value(self, value: float) -> None:
        if self._continuous:
            self._value = max(0.0, min(100.0, float(value)))
        else:
            if value in self._values:
                self._index = self._values.index(value)
            else:
                self._index = min(self._index, len(self._values) - 1)
            self._value = self._values[self._index]
        self.update()

    # ---------------- 几何 ----------------

    def _track(self) -> tuple[float, float, float]:
        return 50.0, max(70.0, self.height() - 10.0), self.width() - 20.0

    def _y_for_index(self, index: int) -> float:
        top, bottom, _ = self._track()
        count = max(1, len(self._labels) - 1)
        return top + (bottom - top) * index / count

    def _y_for_value(self) -> float:
        top, bottom, _ = self._track()
        if self._continuous:
            return bottom - (bottom - top) * (self._value / 100.0)
        return self._y_for_index(self._index)

    # ---------------- 绘制 ----------------

    def paintEvent(self, event: Any) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        top, bottom, rail_x = self._track()

        painter.setPen(QColor(COLORS["faint"]))
        painter.setFont(QFont("Microsoft YaHei UI", 8))
        lines = self._title.split("\n")
        y_text = 13
        for line in lines:
            painter.drawText(QPointF(2, y_text), line)
            y_text += 13

        painter.setPen(QPen(QColor("#2a3b44"), 3))
        painter.drawLine(QPointF(rail_x, top), QPointF(rail_x, bottom))

        painter.setFont(QFont("Cascadia Mono", 9))
        for index, label in enumerate(self._labels):
            y = self._y_for_index(index)
            painter.setPen(QPen(QColor("#3a505c"), 1))
            painter.drawLine(QPointF(rail_x - 4, y), QPointF(rail_x + 4, y))
            painter.setPen(QColor(COLORS["muted"]))
            painter.drawText(
                QRectF(0, y - 8, rail_x - 10, 16),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                label,
            )

        handle_y = self._y_for_value()
        painter.setPen(QPen(QColor("#8ecbff"), 1))
        painter.setBrush(QColor("#2f8fe0"))
        painter.drawRoundedRect(QRectF(rail_x - 8, handle_y - 6, 16, 12), 3, 3)
        painter.end()

    # ---------------- 交互 ----------------

    def mousePressEvent(self, event: Any) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._update_from_position(event.position().y())

    def mouseMoveEvent(self, event: Any) -> None:  # noqa: N802
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._update_from_position(event.position().y())

    def wheelEvent(self, event: Any) -> None:  # noqa: N802
        delta = 1 if event.angleDelta().y() < 0 else -1
        if self._continuous:
            self._set_value(self._value + 5 if delta > 0 else self._value - 5)
        else:
            self._set_index(self._index + delta)

    def _update_from_position(self, y: float) -> None:
        top, bottom, _ = self._track()
        ratio = max(0.0, min(1.0, (bottom - y) / max(1.0, bottom - top)))
        if self._continuous:
            self._set_value(round(ratio * 100.0))
        else:
            index = round(ratio * (len(self._labels) - 1))
            self._set_index(index)

    def _set_index(self, index: int) -> None:
        index = max(0, min(index, len(self._values) - 1))
        if index == self._index:
            return
        self._index = index
        self._value = self._values[index]
        self.update()
        self.valueChanged.emit(self._value)

    def _set_value(self, value: float) -> None:
        value = max(0.0, min(100.0, float(value)))
        if abs(value - self._value) < 0.5:
            return
        self._value = value
        self.update()
        self.valueChanged.emit(self._value)


# ---------------------------------------------------------------- 线稿总览


class MachineScene(QWidget):
    """整机俯视线稿：外框为整机范围，上下两排电动飞达 + 中间底板。"""

    GREEN = "#37d67a"
    AMBER = "#f0b429"
    DIM = "#24343d"

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.setMinimumSize(560, 500)
        self.setMouseTracking(True)
        self._profile = ctx.profile
        self._inner_rect = QRectF()
        self._travel = (1.0, 1.0)
        self._bed_image_cache: tuple[str, QImage | None] = ("", None)
        self._feeders: dict[int, Any] = {}
        self._components: dict[str, Any] = {}
        self._product: Any = None
        self._head = (0.0, 0.0, 0.0)
        self._state = MachineState.OFFLINE
        self._connected = False
        self._last_paint = 0.0
        self._lane_rects: dict[int, QRectF] = {}
        self._hover_slot = 0
        self.refresh()

    # ---------------- 数据 ----------------

    def refresh(self) -> None:
        self._profile = self.ctx.profile
        self._feeders = {feeder.slot: feeder for feeder in self.ctx.feeders()}
        self._components = self.ctx.component_map()
        self._product = self.ctx.current_product
        self._state = self.ctx.machine.state
        self._connected = self.ctx.connected
        self._bed_image_cache = ("", None)
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
        lane_h = min(170.0, max(120.0, height * 0.23))
        top_y = 46.0
        bottom_y = height - 30.0 - lane_h
        bed = QRectF(
            margin_x,
            top_y + lane_h + 20.0,
            width - margin_x * 2,
            max(80.0, bottom_y - (top_y + lane_h) - 40.0),
        )
        frame = QRectF(margin_x - 10, top_y - 16, width - margin_x * 2 + 20, bottom_y + lane_h + 20 - (top_y - 16))
        painter.setPen(QPen(QColor("#2b4652"), 1.4))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(frame, 8, 8)

        limits = profile.limits()
        travel_x = max(1.0, limits.travel_x_mm)
        travel_y = max(1.0, limits.travel_y_mm)
        inner = frame.adjusted(14, 14, -14, -14)
        self._inner_rect = inner
        self._travel = (travel_x, travel_y)
        self._lane_rects = {}
        self._draw_bank(
            painter,
            QRectF(margin_x, top_y, width - margin_x * 2, lane_h),
            bottom_count,
            first_slot + top_count,
            "上排飞达",
            True,
        )
        self._draw_bank(
            painter,
            QRectF(margin_x, bottom_y, width - margin_x * 2, lane_h),
            top_count,
            first_slot,
            "下排飞达",
            False,
        )
        self._draw_bed(painter, bed)
        self._draw_head(painter, frame)

        if not self._connected:
            painter.setBrush(QColor(5, 10, 13, 60))
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

    def _draw_bank(
        self,
        painter: QPainter,
        area: QRectF,
        count: int,
        first_slot: int,
        title: str,
        reverse: bool,
    ) -> None:
        if count <= 0:
            return
        # 左右各留一个空位作为盲区，其余 25 个槽位铺满整排
        cells = count + 2
        cell_w = area.width() / cells
        painter.setPen(QColor(COLORS["faint"]))
        painter.setFont(QFont("Microsoft YaHei UI", 8))
        painter.drawText(QPointF(area.left() + 4, area.top() - 7), title)

        for cell in range(cells):
            lane = QRectF(
                area.left() + cell * cell_w + 1,
                area.top() + 6,
                max(8.0, cell_w - 2),
                area.height() - 12,
            )
            if cell == 0 or cell == cells - 1:
                continue
            index = cell - 1
            slot = first_slot + (count - 1 - index if reverse else index)
            feeder = self._feeders.get(slot)
            component = self._components.get(feeder.component_id) if feeder else None
            self._lane_rects[slot] = lane
            self._draw_lane(painter, lane, slot, feeder, component)

    def _draw_lane(
        self,
        painter: QPainter,
        lane: QRectF,
        slot: int,
        feeder: Any,
        component: Any,
    ) -> None:
        installed = feeder is not None and feeder.enabled and component is not None
        low = bool(feeder is not None and (feeder.is_empty or feeder.is_low))
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
        if slot == self._hover_slot:
            border = QColor(COLORS["accent"])

        # 图 1 样式：圆角飞达框、顶部圆点、方形窗口、下部规格，序号在框外底部
        frame = lane.adjusted(1, 1, -1, -24)
        painter.setPen(QPen(border, 1.3, style))
        painter.setBrush(fill)
        painter.drawRoundedRect(frame, 7, 7)

        if feeder is not None:
            cx = frame.center().x()
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(text_color)
            painter.drawEllipse(QPointF(cx, frame.top() + 14), 2.8, 2.8)

            window_w = max(10.0, min(16.0, frame.width() - 12))
            window = QRectF(cx - window_w / 2, frame.top() + 25, window_w, 12)
            painter.setPen(QPen(text_color, 1.2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(window, 1, 1)

            painter.setPen(text_color)
            num_text = f"{feeder.tape_width_mm:g}"
            num_size = 18 if len(num_text) == 1 else 16
            painter.setFont(QFont("Cascadia Mono", num_size, QFont.Weight.Bold))
            painter.drawText(
                QRectF(frame.left(), frame.bottom() - 62, frame.width(), 28),
                Qt.AlignmentFlag.AlignCenter,
                num_text,
            )
            painter.setFont(QFont("Cascadia Mono", 9))
            painter.drawText(
                QRectF(frame.left(), frame.bottom() - 33, frame.width(), 13),
                Qt.AlignmentFlag.AlignCenter,
                "mm",
            )

        if slot > 0:
            painter.setPen(QColor(COLORS["muted"]))
            painter.setFont(QFont("Cascadia Mono", 16 if slot < 10 else 14, QFont.Weight.Bold))
            painter.drawText(
                QRectF(lane.left() + 1, lane.bottom() - 20, lane.width() - 2, 18),
                Qt.AlignmentFlag.AlignCenter,
                f"{slot}",
            )

    @staticmethod
    def _feeder_texts(feeder: Any, component: Any) -> tuple[str, str]:
        value = ""
        if component is not None:
            value = str(getattr(component, "value", "") or "")
        if not value:
            raw = (feeder.label or "").strip()
            if "·" in raw:
                raw = raw.split("·")[-1].strip()
            value = raw or (str(component.name) if component is not None else "")
        package = str(getattr(component, "package", "") or "")
        return value, package

    # ---------------- 底板 ----------------

    def _draw_bed(self, painter: QPainter, bed: QRectF) -> None:
        profile = self._profile
        limits = profile.limits() if profile else None
        if limits is None:
            return
        travel_x = max(1.0, limits.travel_x_mm)
        travel_y = max(1.0, limits.travel_y_mm)

        painter.save()
        painter.setClipRect(bed)
        painter.setPen(QPen(QColor("#2b4652"), 1.2))
        painter.setBrush(QColor("#0a1216"))
        painter.drawRoundedRect(bed, 8, 8)
        image = self._bed_image()
        if image is not None:
            scaled = image.scaled(
                bed.size().toSize(),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            src = QRectF(
                (scaled.width() - bed.width()) / 2,
                (scaled.height() - bed.height()) / 2,
                bed.width(),
                bed.height(),
            )
            painter.drawImage(bed, scaled, src)
        else:
            self._draw_default_bed(painter, bed)
        painter.restore()
        painter.setPen(QPen(QColor("#2b4652"), 1.2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(bed, 8, 8)

        def to_bed(mx: float, my: float) -> QPointF:
            return QPointF(
                bed.left() + max(0.0, min(1.0, mx / travel_x)) * bed.width(),
                bed.bottom() - max(0.0, min(1.0, my / travel_y)) * bed.height(),
            )

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

        painter.setPen(QPen(QColor(COLORS["faint"]), 1))
        painter.setFont(QFont("Cascadia Mono", 7))
        painter.drawText(QPointF(bed.left() + 8, bed.top() + 14), f"X 0–{travel_x:.0f} mm")
        painter.save()
        painter.translate(bed.right() - 10, bed.top() + 70)
        painter.rotate(-90)
        painter.drawText(QPointF(0, 0), f"Y 0–{travel_y:.0f} mm")
        painter.restore()

    def _bed_image(self) -> QImage | None:
        raw = str(getattr(self._profile, "bed_image", "") or "")
        if not raw:
            return None
        if self._bed_image_cache[0] == raw:
            return self._bed_image_cache[1]
        path = Path(raw)
        if not path.is_absolute():
            path = assets_root() / raw
        image = QImage(str(path))
        if image.isNull():
            image = None
        self._bed_image_cache = (raw, image)
        return image

    def _draw_default_bed(self, painter: QPainter, bed: QRectF) -> None:
        # 平台外框与角部安装孔
        painter.setPen(QPen(QColor("#4a6674"), 1.2))
        painter.setBrush(QColor("#0a1216"))
        painter.drawRoundedRect(bed.adjusted(6, 6, -6, -6), 10, 10)
        for corner in (
            QPointF(bed.left() + 20, bed.top() + 20),
            QPointF(bed.right() - 20, bed.top() + 20),
            QPointF(bed.left() + 20, bed.bottom() - 20),
            QPointF(bed.right() - 20, bed.bottom() - 20),
        ):
            painter.setPen(QPen(QColor("#5c7682"), 1.1))
            painter.setBrush(QColor("#05090b"))
            painter.drawEllipse(corner, 5.2, 5.2)

        # 成排固定孔
        step = max(22, int(bed.width() / 24))
        y = bed.top() + 18
        row = 0
        while y < bed.bottom() - 10:
            x = bed.left() + 18 + (step / 2 if row % 2 else 0)
            while x < bed.right() - 10:
                painter.setPen(QPen(QColor("#31505c"), 1))
                painter.setBrush(QColor("#05090b"))
                painter.drawEllipse(QPointF(x, y), 2.2, 2.2)
                x += step
            y += step
            row += 1

        # 平台中缝（中央带斜切）
        divider = bed.top() + bed.height() * 0.52
        cx = bed.center().x()
        painter.setPen(QPen(QColor("#3c5663"), 1.1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawLine(QPointF(bed.left() + 10, divider), QPointF(cx - 72, divider))
        painter.drawLine(QPointF(cx - 72, divider), QPointF(cx - 62, divider - 8))
        painter.drawLine(QPointF(cx - 62, divider - 8), QPointF(cx + 62, divider - 8))
        painter.drawLine(QPointF(cx + 62, divider - 8), QPointF(cx + 72, divider))
        painter.drawLine(QPointF(cx + 72, divider), QPointF(bed.right() - 10, divider))

        lower_top = divider
        lower_h = max(1.0, bed.bottom() - lower_top)

        # 校准板（八角形 PCB + 棋盘标定图案）
        cal_w = min(140.0, bed.width() * 0.21)
        cal_h = max(52.0, cal_w * 0.52)
        cal = QPointF(cx, lower_top + lower_h * 0.53)
        cut = min(12.0, cal_w * 0.12)
        poly = QPolygonF(
            [
                QPointF(cal.x() - cal_w / 2 + cut, cal.y() - cal_h / 2),
                QPointF(cal.x() + cal_w / 2 - cut, cal.y() - cal_h / 2),
                QPointF(cal.x() + cal_w / 2, cal.y() - cal_h / 2 + cut),
                QPointF(cal.x() + cal_w / 2, cal.y() + cal_h / 2 - cut),
                QPointF(cal.x() + cal_w / 2 - cut, cal.y() + cal_h / 2),
                QPointF(cal.x() - cal_w / 2 + cut, cal.y() + cal_h / 2),
                QPointF(cal.x() - cal_w / 2, cal.y() + cal_h / 2 - cut),
                QPointF(cal.x() - cal_w / 2, cal.y() - cal_h / 2 + cut),
            ]
        )
        painter.setPen(QPen(QColor("#87979e"), 1.1))
        painter.setBrush(QColor("#c8d0d3"))
        painter.drawPolygon(poly)
        painter.setPen(QPen(QColor("#4c5b62"), 0.9))
        painter.setBrush(QColor("#7f8b90"))
        inner = QRectF(cal.x() - cal_w * 0.20, cal.y() - cal_h * 0.24, cal_w * 0.40, cal_h * 0.48)
        painter.drawRect(inner)
        cell = max(2.0, inner.width() / 8)
        for row in range(4):
            for col in range(4):
                if (row + col) % 2:
                    continue
                painter.setBrush(QColor("#2c383d"))
                painter.drawRect(
                    QRectF(inner.left() + col * cell, inner.top() + row * cell, cell, cell)
                )
        painter.setPen(QPen(QColor("#4c5b62"), 1.0))
        painter.setBrush(QColor("#05090b"))
        for dx in (-cal_w * 0.38, cal_w * 0.38):
            painter.drawEllipse(QPointF(cal.x() + dx, cal.y()), 3.2, 3.2)

        # 底部相机
        cam = QPointF(cx, lower_top + lower_h * 0.85)
        painter.setPen(QPen(QColor("#58727e"), 1.2))
        painter.setBrush(QColor("#070d11"))
        painter.drawEllipse(cam, 28, 28)
        painter.setPen(QPen(QColor("#3c5663"), 1.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(cam, 21, 21)
        painter.drawEllipse(cam, 14, 14)
        painter.setBrush(QColor("#020506"))
        painter.setPen(QPen(QColor("#75909b"), 1.1))
        painter.drawEllipse(cam, 8, 8)
        painter.setBrush(QColor("#2b4652"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(cam.x() - 3, cam.y() - 3), 2.4, 2.4)

    def _draw_head(self, painter: QPainter, frame: QRectF) -> None:
        profile = self._profile
        if profile is None:
            return
        limits = profile.limits()
        travel_x = max(1.0, limits.travel_x_mm)
        travel_y = max(1.0, limits.travel_y_mm)
        inner = frame.adjusted(14, 14, -14, -14)
        head_x, head_y, _ = self._head
        x = inner.left() + max(0.0, min(1.0, head_x / travel_x)) * inner.width()
        y = inner.bottom() - max(0.0, min(1.0, head_y / travel_y)) * inner.height()

        painter.setPen(QPen(QColor(63, 98, 112, 90), 1.2))
        painter.drawLine(QPointF(inner.left() + 2, y), QPointF(inner.right() - 2, y))
        painter.setPen(QPen(QColor("#243d49"), 1.0, Qt.PenStyle.DashLine))
        painter.drawLine(QPointF(x, inner.top() + 2), QPointF(x, inner.bottom() - 2))

        # 贴装头：十字线 + 原点
        painter.setPen(QPen(QColor(COLORS["accent"]), 1.4))
        painter.drawLine(QPointF(x - 16, y), QPointF(x + 16, y))
        painter.drawLine(QPointF(x, y - 16), QPointF(x, y + 16))
        painter.setBrush(QColor(COLORS["accent"]))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(x, y), 3.0, 3.0)

    # ---------------- 交互 ----------------

    def _slot_at(self, position: QPointF) -> int:
        for slot, rect in self._lane_rects.items():
            if rect.contains(position):
                return slot
        return 0

    def mouseMoveEvent(self, event: Any) -> None:  # noqa: N802
        slot = self._slot_at(event.position())
        if slot != self._hover_slot:
            self._hover_slot = slot
            self.setCursor(Qt.CursorShape.PointingHandCursor if slot else Qt.CursorShape.ArrowCursor)
            self.update()
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event: Any) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            slot = self._slot_at(event.position())
            if slot:
                self._activate_slot(slot)
        super().mousePressEvent(event)

    def _activate_slot(self, slot: int) -> None:
        feeder = self._feeders.get(slot)
        if not self._connected:
            self.ctx.toast("设备未连接，无法移动到飞达", "warning")
            return
        if feeder is None:
            self.ctx.toast(f"{slot:02d} 号槽位未装载供料器", "warning")
            return
        if not feeder.enabled:
            self.ctx.toast(f"{slot:02d} 号供料器已停用", "warning")
            return
        lane = self._lane_rects.get(slot)
        inner = self._inner_rect
        if lane is not None and not inner.isEmpty():
            travel_x, travel_y = self._travel
            x = (lane.center().x() - inner.left()) / inner.width() * travel_x
            y = (inner.bottom() - lane.center().y()) / inner.height() * travel_y
        else:
            x = float(feeder.pick_x_mm)
            y = float(feeder.pick_y_mm)
            if abs(x) < 1e-6 and abs(y) < 1e-6:
                x, y = self._profile.feeders.slot_position(slot)
        z = float(self.ctx.settings.safe_z_mm)
        self.ctx.machine.move_to(x, y, z)
        self.ctx.log("INFO", "MACHINE", f"移动到 {slot:02d} 号飞达取料点 ({x:.1f}, {y:.1f})")
        self.ctx.toast(f"移动到 {slot:02d} 号飞达 ({x:.1f}, {y:.1f})", "info")


# ---------------------------------------------------------------- 首页


class HomePage(QWidget):
    STEP_VALUES = [100.0, 10.0, 1.0, 0.1, 0.01]

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self._camera_mode = "top"
        self._step = 0.1
        self._speed_pct = 40.0
        self._target = "left"
        self._vacuum_by_nozzle: dict[str, bool] = {}
        self._total_nozzles = max(1, len(ctx.profile.nozzle_ids()))
        self._nozzle_ids = ctx.profile.nozzle_ids()
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
        self.camera_view.setMinimumSize(320, 180)
        camera_card.body.addWidget(self.camera_view, 1)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)
        left_split = QSplitter(Qt.Orientation.Vertical)
        left_split.setChildrenCollapsible(False)
        left_split.setHandleWidth(3)
        left_split.setStyleSheet(
            "QSplitter::handle { background: #22343e; }"
            "QSplitter::handle:hover { background: #2f8fe0; }"
        )
        left_split.addWidget(camera_card)
        left_split.addWidget(self._build_jog_card())
        left_split.setStretchFactor(0, 3)
        left_split.setStretchFactor(1, 2)
        left_split.setSizes([520, 346])
        left_layout.addWidget(left_split)
        self.left_split = left_split

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
        tip = QLabel("单击飞达可移动吸嘴 · 点击左上设备图切换机型")
        tip.setProperty("role", "faint")
        legend.addWidget(tip)
        scene_card.body.addLayout(legend)
        content = QSplitter(Qt.Orientation.Horizontal)
        content.setChildrenCollapsible(False)
        content.setHandleWidth(3)
        content.setStyleSheet(
            "QSplitter::handle { background: #22343e; }"
            "QSplitter::handle:hover { background: #2f8fe0; }"
        )
        content.addWidget(left_panel)
        content.addWidget(scene_card)
        content.setStretchFactor(0, 3)
        content.setStretchFactor(1, 7)
        content.setSizes([430, 1002])
        outer.addWidget(content, 1)
        self.content_split = content

        self.banner_button.clicked.connect(self._open_connect)
        self.camera_top_button.clicked.connect(lambda: self._set_camera("top"))
        self.camera_bottom_button.clicked.connect(lambda: self._set_camera("bottom"))
        self.vacuum_button.clicked.connect(self._toggle_vacuum)

    def _build_jog_card(self) -> Card:
        card = Card(padding=10)
        top = QHBoxLayout()
        title = QLabel("点动控制")
        title.setProperty("role", "section")
        top.addWidget(title)
        top.addStretch(1)
        card.body.addLayout(top)

        body = QHBoxLayout()
        body.setSpacing(14)

        left_col = QVBoxLayout()
        left_col.setSpacing(8)

        target_row = QHBoxLayout()
        target_row.setSpacing(6)
        self.target_group = QButtonGroup(self)
        self.target_group.setExclusive(True)
        self.target_buttons: dict[str, Any] = {}
        target_defs = (
            ("left", f"左吸嘴 {self._nozzle_ids[0] if self._nozzle_ids else 'N1'}"),
            ("right", f"右吸嘴 {self._nozzle_ids[1] if len(self._nozzle_ids) > 1 else 'N2'}"),
            ("camera", "顶部相机"),
        )
        for key, label in target_defs:
            control = button(label, variant="subtle")
            control.setProperty("segment", "true")
            control.setCheckable(True)
            control.setFixedHeight(26)
            control.clicked.connect(lambda checked=False, name=key: self._set_target(name))
            self.target_group.addButton(control)
            self.target_buttons[key] = control
            target_row.addWidget(control)
        self.target_buttons["left"].setChecked(True)
        if self._total_nozzles < 2:
            self.target_buttons["right"].setEnabled(False)
        left_col.addLayout(target_row)

        grid = QGridLayout()
        grid.setSpacing(4)
        self._jog_buttons: list[Any] = []
        for label, icon_name, row, col, direction in (
            ("Y+", "arrow-up", 0, 1, (0, 1, 0)),
            ("X-", "arrow-left", 1, 0, (-1, 0, 0)),
            ("回零", None, 1, 1, None),
            ("X+", "arrow-right", 1, 2, (1, 0, 0)),
            ("Y-", "arrow-down", 2, 1, (0, -1, 0)),
        ):
            control = button(label, icon_name, "subtle")
            control.setProperty("jog", "true")
            control.setMinimumSize(44, 34)
            if icon_name:
                control.setIconSize(QSize(18, 18))
            else:
                control.setStyleSheet("font-size: 10px; font-weight: 600;")
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
        z_home = button("Z归位", variant="subtle")
        z_down = button("Z-", "arrow-down", "subtle")
        z_home.setStyleSheet("font-size: 10px; font-weight: 600;")
        z_home.setToolTip("Z 轴单独归位")
        for row, control in enumerate((z_up, z_home, z_down)):
            control.setMinimumSize(44, 34)
            if row == 1:
                control.setIconSize(QSize(0, 0))
            grid.addWidget(control, row, 3)
            self._jog_buttons.append(control)
        z_up.clicked.connect(lambda: self._jog(0.0, 0.0, self._step))
        z_down.clicked.connect(lambda: self._jog(0.0, 0.0, -self._step))
        z_home.clicked.connect(self._home_z)
        left_col.addLayout(grid)

        vacuum_row = QHBoxLayout()
        vacuum_row.setSpacing(8)
        self.vacuum_button = button("真空", "zap", "subtle")
        self.vacuum_button.setCheckable(True)
        self.vacuum_button.setFixedHeight(26)
        self.vacuum_button.setMinimumWidth(88)
        vacuum_row.addWidget(self.vacuum_button)
        self.target_hint = QLabel("真空跟随所选吸嘴")
        self.target_hint.setProperty("role", "faint")
        vacuum_row.addWidget(self.target_hint)
        vacuum_row.addStretch(1)
        left_col.addLayout(vacuum_row)
        left_col.addStretch(1)
        body.addLayout(left_col, 1)

        scales = QHBoxLayout()
        scales.setSpacing(10)
        self.step_scale = VerticalScale(
            "距离/角度\n[mm/deg]",
            ["100", "10", "1.0", "0.1", "0.01"],
            self.STEP_VALUES,
            index=3,
        )
        self.step_scale.valueChanged.connect(self._on_step_changed)
        self.speed_scale = VerticalScale(
            "全局速度\n[%]",
            ["100", "75", "50", "25", "0"],
            continuous=True,
        )
        self.speed_scale.set_value(self._speed_pct)
        self.speed_scale.valueChanged.connect(self._on_speed_changed)
        scales.addWidget(self.step_scale)
        scales.addWidget(self.speed_scale)
        body.addLayout(scales)
        card.body.addLayout(body)

        self.jog_hint = QLabel("连接设备后可点动；生产运行时手动轴控被锁定。")
        self.jog_hint.setProperty("role", "faint")
        self.jog_hint.hide()
        card.setToolTip("连接设备后可点动；生产运行时手动轴控被锁定。")
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
        self.ctx.machine.vacuum_state.connect(self._on_vacuum_state)
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
        for control in self._jog_buttons:
            control.setEnabled(connected)
        self.vacuum_button.setVisible(self._target != "camera")
        self.vacuum_button.setEnabled(connected and self._target != "camera")
        for key, control in self.target_buttons.items():
            control.setEnabled(connected)
        self.jog_hint.setText(
            "点动已启用；生产运行时手动轴控会被锁定。"
            if connected
            else "设备未连接：点动、真空与生产不可用。"
        )

    def _on_connection(self, connected: bool, label: str) -> None:
        self.scene.set_connection(connected)
        self._apply_connection_state(connected)
        if connected:
            self.ctx.toast("设备已连接", "success")

    def _on_state(self, state_value: str) -> None:
        try:
            state = MachineState(state_value)
        except ValueError:
            state = MachineState.OFFLINE
        color = state_color(state)
        label = state_label(state)
        chip = self.scene_state
        chip.setText(label)
        chip.setStyleSheet(
            f"background: {color}16; border: 1px solid {color}55; color: {color};"
            "border-radius: 10px; padding: 3px 9px; font-size: 11px;"
        )

    def _on_position(self, x: float, y: float, z: float) -> None:
        self.scene.set_head(x, y, z)

    def _on_vacuum_state(self, nozzle: str, on: bool) -> None:
        if nozzle:
            self._vacuum_by_nozzle[nozzle] = on
        else:
            for key in self._nozzle_ids:
                self._vacuum_by_nozzle[key] = on
        active = self._active_nozzle()
        if not nozzle or nozzle == active:
            self.vacuum_button.setChecked(bool(self._vacuum_by_nozzle.get(active, False)))
            self.vacuum_button.setText("真空开" if self.vacuum_button.isChecked() else "真空")

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

    # ---------------- 操作 ----------------

    def _active_nozzle(self) -> str:
        if self._target == "right" and len(self._nozzle_ids) > 1:
            return self._nozzle_ids[1]
        return self._nozzle_ids[0] if self._nozzle_ids else "N1"

    def _set_target(self, target: str) -> None:
        self._target = target
        self.target_buttons[target].setChecked(True)
        if target == "camera":
            self.vacuum_button.setVisible(False)
            self.vacuum_button.setEnabled(False)
            self.target_hint.setText("顶部相机视图")
            self._set_camera("top")
            return
        nozzle = self._active_nozzle()
        self.vacuum_button.setVisible(True)
        self.vacuum_button.setEnabled(self.ctx.connected)
        self.vacuum_button.setChecked(bool(self._vacuum_by_nozzle.get(nozzle, False)))
        self.vacuum_button.setText("真空开" if self.vacuum_button.isChecked() else "真空")
        self.target_hint.setText(f"真空跟随 {nozzle}")
        if self.ctx.connected:
            self.ctx.machine.nozzle(nozzle)

    def _on_step_changed(self, value: float) -> None:
        self._step = float(value)

    def _on_speed_changed(self, value: float) -> None:
        self._speed_pct = float(value)

    def _jog(self, dx: float, dy: float, dz: float) -> None:
        if not self.ctx.connected:
            self.ctx.toast("设备未连接", "warning")
            return
        speed = self.ctx.settings.max_speed_mm_s * self._speed_pct / 100.0
        self.ctx.machine.jog(dx=dx, dy=dy, dz=dz, speed=speed)

    def _home(self) -> None:
        if not self.ctx.connected:
            self.ctx.toast("设备未连接", "warning")
            return
        self.ctx.machine.home()

    def _home_z(self) -> None:
        if not self.ctx.connected:
            self.ctx.toast("设备未连接", "warning")
            return
        self.ctx.machine.home_axis("z")

    def _open_connect(self) -> None:
        from ..connect_dialog import ConnectDialog

        dialog = ConnectDialog(self.ctx, parent=self)
        dialog.exec()
        self._tick_camera()

    def _toggle_vacuum(self) -> None:
        if not self.ctx.connected or self._target == "camera":
            self.ctx.toast("设备未连接或当前为相机模式", "warning")
            self.vacuum_button.setChecked(False)
            return
        nozzle = self._active_nozzle()
        on = self.vacuum_button.isChecked()
        self.ctx.machine.vacuum(on, nozzle=nozzle)
        self.target_hint.setText(f"{nozzle} 真空{'开' if on else '关'}")

    def _start_or_connect(self) -> None:
        if not self.ctx.connected:
            self._open_connect()
        else:
            self.ctx.signals.start_production.emit()
