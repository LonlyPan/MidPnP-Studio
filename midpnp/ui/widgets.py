"""通用界面组件：板卡视图、指标卡、环状进度、模拟机台与通知。"""

from __future__ import annotations

import math
from typing import Any

from PySide6.QtCore import (
    QEasingCurve,
    QPoint,
    QPointF,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from ..core.models import Component, MachineState, Product
from .icons import icon
from .theme import COLORS


def set_css(widget: QWidget, css_class: str) -> None:
    widget.setProperty("cssClass", css_class)


class Card(QFrame):
    def __init__(self, parent: QWidget | None = None, padding: int = 16) -> None:
        super().__init__(parent)
        set_css(self, "card")
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(padding, padding, padding, padding)
        self.body.setSpacing(12)


class PageHeader(QWidget):
    def __init__(self, title: str, subtitle: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)
        self.title_label = QLabel(title)
        self.title_label.setProperty("role", "pageTitle")
        self.subtitle_label = QLabel(subtitle)
        self.subtitle_label.setProperty("role", "pageSub")
        text_layout.addWidget(self.title_label)
        text_layout.addWidget(self.subtitle_label)
        layout.addLayout(text_layout)
        layout.addStretch(1)
        self.actions = QHBoxLayout()
        self.actions.setSpacing(8)
        layout.addLayout(self.actions)

    def add_action(self, widget: QWidget) -> None:
        self.actions.addWidget(widget)


class PageScroll(QScrollArea):
    """带统一边距的页面滚动容器。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.inner = QWidget()
        self.setWidget(self.inner)
        self.layout = QVBoxLayout(self.inner)
        self.layout.setContentsMargins(24, 20, 24, 24)
        self.layout.setSpacing(16)


class MetricCard(QFrame):
    def __init__(
        self,
        title: str,
        value: str = "0",
        unit: str = "",
        icon_name: str = "dashboard",
        accent: str = COLORS["accent"],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        set_css(self, "card")
        self._accent = accent
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(6)

        top = QHBoxLayout()
        top.setSpacing(8)
        icon_tile = QLabel()
        icon_tile.setPixmap(icon(icon_name, accent, 18).pixmap(18, 18))
        icon_tile.setFixedSize(30, 30)
        icon_tile.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_tile.setStyleSheet(
            f"background: {accent}12; border: 1px solid {accent}30; border-radius: 7px;"
        )
        title_label = QLabel(title)
        title_label.setProperty("role", "muted")
        top.addWidget(icon_tile)
        top.addWidget(title_label)
        top.addStretch(1)
        self.trend = QLabel("")
        self.trend.setProperty("chip", "true")
        self.trend.hide()
        top.addWidget(self.trend)
        layout.addLayout(top)

        row = QHBoxLayout()
        row.setSpacing(5)
        self.value_label = QLabel(value)
        self.value_label.setProperty("role", "metric")
        self.unit_label = QLabel(unit)
        self.unit_label.setProperty("role", "muted")
        self.unit_label.setContentsMargins(0, 8, 0, 0)
        row.addWidget(self.value_label)
        row.addWidget(self.unit_label)
        row.addStretch(1)
        layout.addLayout(row)
        self.sub_label = QLabel("—")
        self.sub_label.setProperty("role", "faint")
        layout.addWidget(self.sub_label)

    def set(self, value: str, sub: str = "", trend: str = "") -> None:
        self.value_label.setText(value)
        self.sub_label.setText(sub)
        if trend:
            self.trend.setText(trend)
            self.trend.show()
        else:
            self.trend.hide()


class RingProgress(QWidget):
    def __init__(self, parent: QWidget | None = None, size: int = 148) -> None:
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._value = 0.0
        self._primary = "0/0"
        self._secondary = "等待任务"
        self._color = QColor(COLORS["accent"])

    def set_progress(self, value: float, primary: str, secondary: str, color: str | None = None) -> None:
        self._value = max(0.0, min(100.0, float(value)))
        self._primary = primary
        self._secondary = secondary
        if color:
            self._color = QColor(color)
        self.update()

    def paintEvent(self, event: Any) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(10, 10, self.width() - 20, self.height() - 20)
        pen = QPen(QColor(COLORS["surface3"]), 10, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawArc(rect, 0, 360 * 16)
        if self._value > 0:
            pen.setColor(self._color)
            painter.setPen(pen)
            painter.drawArc(rect, 90 * 16, int(-360 * 16 * self._value / 100))
        painter.setPen(QColor(COLORS["text"]))
        font = QFont("Cascadia Mono", 19)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(QRectF(0, 46, self.width(), 34), Qt.AlignmentFlag.AlignCenter, self._primary)
        painter.setPen(QColor(COLORS["muted"]))
        font = QFont("Microsoft YaHei UI", 9)
        painter.setFont(font)
        painter.drawText(QRectF(0, 82, self.width(), 24), Qt.AlignmentFlag.AlignCenter, self._secondary)
        painter.end()


class StatusDot(QWidget):
    def __init__(self, color: str = COLORS["muted"], size: int = 9, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._color = QColor(color)
        self._size = size
        self.setFixedSize(size + 6, size + 6)

    def set_color(self, color: str) -> None:
        self._color = QColor(color)
        self.update()

    def paintEvent(self, event: Any) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        glow = QColor(self._color)
        glow.setAlpha(55)
        painter.setBrush(glow)
        painter.drawEllipse(QRectF(0, 0, self.width(), self.height()))
        painter.setBrush(self._color)
        offset = (self.width() - self._size) / 2
        painter.drawEllipse(QRectF(offset, offset, self._size, self._size))
        painter.end()


class EmptyState(QWidget):
    def __init__(self, title: str, hint: str = "", icon_name: str = "layers", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(8)
        glyph = QLabel()
        glyph.setPixmap(icon(icon_name, COLORS["faint"], 34).pixmap(34, 34))
        glyph.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label = QLabel(title)
        title_label.setStyleSheet("font-size: 14px; font-weight: 600; color: #9cb0bc;")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint_label = QLabel(hint)
        hint_label.setProperty("role", "faint")
        hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(glyph)
        layout.addWidget(title_label)
        layout.addWidget(hint_label)


class InfoRow(QWidget):
    def __init__(self, label: str, value: str = "—", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.label = QLabel(label)
        self.label.setProperty("role", "muted")
        self.value = QLabel(value)
        self.value.setStyleSheet("font-family: 'Cascadia Mono', 'Consolas'; font-size: 12px;")
        self.value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.label)
        layout.addStretch(1)
        layout.addWidget(self.value)

    def set(self, value: str, color: str | None = None) -> None:
        self.value.setText(value)
        if color:
            self.value.setStyleSheet(
                f"color: {color}; font-family: 'Cascadia Mono', 'Consolas'; font-size: 12px;"
            )
        else:
            self.value.setStyleSheet("font-family: 'Cascadia Mono', 'Consolas'; font-size: 12px;")


class MachineMiniature(QWidget):
    """总览页的轻量机台示意，跟随真实坐标。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(190)
        self._limits = (420.0, 360.0)
        self._head = (0.0, 0.0)
        self._state = MachineState.OFFLINE
        self._product: Product | None = None
        self._pulse = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(90)

    def _tick(self) -> None:
        self._pulse = (self._pulse + 0.08) % (math.pi * 2)
        self.update()

    def set_machine(self, head: tuple[float, float], limits: tuple[float, float]) -> None:
        self._head = head
        self._limits = limits
        self.update()

    def set_state(self, state: MachineState) -> None:
        self._state = state
        self.update()

    def set_product(self, product: Product | None) -> None:
        self._product = product
        self.update()

    def paintEvent(self, event: Any) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        painter.setPen(QPen(QColor(COLORS["border_soft"]), 1))
        painter.setBrush(QColor(COLORS["bg_soft"]))
        painter.drawRoundedRect(rect, 8, 8)

        area = rect.adjusted(22, 20, -22, -34)
        if area.width() <= 10 or area.height() <= 10:
            painter.end()
            return

        travel_x, travel_y = self._limits
        scale = min(area.width() / travel_x, area.height() / travel_y)
        bed_w, bed_h = travel_x * scale, travel_y * scale
        left = area.center().x() - bed_w / 2
        top = area.center().y() - bed_h / 2
        bed = QRectF(left, top, bed_w, bed_h)

        painter.setPen(QPen(QColor(COLORS["border"]), 1))
        painter.setBrush(QColor("#0a141b"))
        painter.drawRoundedRect(bed, 3, 3)
        grid_pen = QPen(QColor(255, 255, 255, 8), 1)
        painter.setPen(grid_pen)
        for i in range(1, 10):
            x = bed.left() + bed.width() * i / 10
            y = bed.top() + bed.height() * i / 10
            painter.drawLine(QPointF(x, bed.top()), QPointF(x, bed.bottom()))
            painter.drawLine(QPointF(bed.left(), y), QPointF(bed.right(), y))

        painter.setPen(QPen(QColor(COLORS["surface3"]), 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(QPointF(bed.left() + 6, bed.top() - 8), QPointF(bed.right() - 6, bed.top() - 8))
        painter.drawLine(QPointF(bed.left() + 6, bed.bottom() + 8), QPointF(bed.right() - 6, bed.bottom() + 8))

        if self._product:
            board = QRectF(
                bed.left() + self._product.board_origin_x_mm * scale,
                bed.bottom() - (self._product.board_origin_y_mm + self._product.board_height_mm) * scale,
                self._product.board_width_mm * scale,
                self._product.board_height_mm * scale,
            )
            gradient = QLinearGradient(board.topLeft(), board.bottomRight())
            gradient.setColorAt(0, QColor("#123b2e"))
            gradient.setColorAt(1, QColor("#0c2a22"))
            painter.setBrush(gradient)
            painter.setPen(QPen(QColor("#2c6f58"), 1))
            painter.drawRoundedRect(board, 2, 2)
            for placement in self._product.placements[:60]:
                px = board.left() + placement.x_mm * scale
                py = board.bottom() - placement.y_mm * scale
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor("#b9c9c1"))
                painter.drawRect(QRectF(px - 1.1, py - 0.8, 2.2, 1.6))

        head_x = bed.left() + max(0.0, min(travel_x, self._head[0])) * scale
        head_y = bed.bottom() - max(0.0, min(travel_y, self._head[1])) * scale
        accent = QColor(COLORS["accent"])
        if self._state in {MachineState.RUNNING, MachineState.PAUSED}:
            glow = QColor(accent)
            glow.setAlpha(int(40 + 30 * (math.sin(self._pulse) + 1) / 2))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(glow)
            painter.drawEllipse(QPointF(head_x, head_y), 13, 13)
        else:
            accent = QColor(COLORS["muted"])
        painter.setPen(QPen(QColor(COLORS["accent_dim"]), 1, Qt.PenStyle.DashLine))
        painter.drawLine(QPointF(bed.left(), bed.top() - 8), QPointF(head_x, bed.top() - 8))
        painter.setPen(QPen(QColor(accent), 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(QPointF(head_x, bed.top() - 12), QPointF(head_x, bed.top() - 2))
        painter.setBrush(QColor("#111c24"))
        painter.setPen(QPen(QColor(accent), 1.5))
        painter.drawRoundedRect(QRectF(head_x - 13, bed.top() - 20, 26, 17), 4, 4)
        painter.setBrush(QColor(accent))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(head_x, bed.top() - 11.5), 2.4, 2.4)
        painter.setPen(QPen(QColor(accent), 1.5))
        painter.drawLine(QPointF(head_x, bed.top() - 3), QPointF(head_x, head_y - 4))
        painter.setBrush(QColor("#0b141b"))
        painter.drawEllipse(QPointF(head_x, head_y - 2), 4, 4)

        painter.setPen(QColor(COLORS["faint"]))
        painter.setFont(QFont("Cascadia Mono", 7))
        painter.drawText(QRectF(bed.left(), bed.bottom() + 12, bed.width(), 16), Qt.AlignmentFlag.AlignLeft, "X0")
        painter.drawText(
            QRectF(bed.left(), bed.bottom() + 12, bed.width(), 16),
            Qt.AlignmentFlag.AlignRight,
            f"X{travel_x:.0f}",
        )
        painter.end()


class BoardView(QWidget):
    """可缩放/平移的 PCB 与机台视图。"""

    placement_selected = Signal(str)

    def __init__(self, parent: QWidget | None = None, mode: str = "board") -> None:
        super().__init__(parent)
        self.setMinimumSize(360, 260)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._product: Product | None = None
        self._components: dict[str, Component] = {}
        self._mode = mode
        self._limits = (420.0, 360.0)
        self._head = (0.0, 0.0, 0.0)
        self._selected = ""
        self._statuses: dict[str, str] = {}
        self._zoom = 1.0
        self._pan = QPointF(0, 0)
        self._dragging = False
        self._drag_start = QPointF(0, 0)
        self._press_pos: QPoint | None = None
        self._moved = False
        self._pulse = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(100)

    # ---------------- public API ----------------

    def set_product(self, product: Product | None, components: list[Component] | None = None) -> None:
        self._product = product
        if product is None or not any(p.refdes == self._selected for p in product.placements):
            self._selected = ""
        if components is not None:
            self._components = {c.id: c for c in components}
        self.reset_view()
        self.update()

    def set_components(self, components: list[Component]) -> None:
        self._components = {c.id: c for c in components}
        self.update()

    def set_mode(self, mode: str) -> None:
        self._mode = mode
        self.reset_view()

    def set_limits(self, x: float, y: float) -> None:
        self._limits = (max(1.0, x), max(1.0, y))
        self.update()

    def set_head(self, x: float, y: float, z: float = 0.0) -> None:
        self._head = (x, y, z)
        self.update()

    def set_selected(self, refdes: str) -> None:
        self._selected = refdes
        self.update()

    def selected(self) -> str:
        return self._selected

    def set_statuses(self, statuses: dict[str, str]) -> None:
        self._statuses = dict(statuses)
        self.update()

    def set_status(self, refdes: str, status: str) -> None:
        self._statuses[refdes] = status
        self.update()

    def clear_statuses(self) -> None:
        self._statuses.clear()
        self.update()

    def reset_view(self) -> None:
        self._zoom = 1.0
        self._pan = QPointF(0, 0)
        self.update()

    def set_zoom(self, zoom: float) -> None:
        self._zoom = max(0.5, min(6.0, zoom))
        self.update()

    # ---------------- interaction ----------------

    def _tick(self) -> None:
        self._pulse = (self._pulse + 0.1) % (math.pi * 2)
        if self._statuses:
            self.update()

    def wheelEvent(self, event: Any) -> None:  # noqa: N802
        if self._product is None:
            return
        world = self._screen_to_world(event.position())
        factor = 1.18 if event.angleDelta().y() > 0 else 1 / 1.18
        self._zoom = max(0.55, min(6.0, self._zoom * factor))
        center = self._world_center()
        new_scale = self._base_scale() * self._zoom
        self._pan.setX(event.position().x() - self.width() / 2 - (world[0] - center[0]) * new_scale)
        self._pan.setY(event.position().y() - self.height() / 2 + (world[1] - center[1]) * new_scale)
        self.update()

    def mousePressEvent(self, event: Any) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._moved = False
            self._drag_start = event.position()
            self._press_pos = event.position().toPoint()
        elif event.button() == Qt.MouseButton.MiddleButton:
            self.reset_view()

    def mouseMoveEvent(self, event: Any) -> None:  # noqa: N802
        if self._dragging:
            delta = event.position() - self._drag_start
            if delta.manhattanLength() > 3:
                self._moved = True
            if self._moved:
                self._pan += delta
                self._drag_start = event.position()
                self.update()
            return
        if self._product:
            refdes = self._nearest_placement(event.position())
            if refdes:
                placement = next((p for p in self._product.placements if p.refdes == refdes), None)
                component = self._components.get(placement.component_id) if placement else None
                if placement and component:
                    QToolTip.showText(
                        event.globalPosition().toPoint(),
                        f"{placement.refdes} · {component.name}\n"
                        f"X {placement.x_mm:.2f}  Y {placement.y_mm:.2f}  R {placement.rotation_deg:.1f}°",
                        self,
                    )
            else:
                QToolTip.hideText()

    def mouseReleaseEvent(self, event: Any) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            if not self._moved and self._press_pos is not None:
                refdes = self._nearest_placement(event.position())
                if refdes:
                    self._selected = refdes
                    self.update()
                    self.placement_selected.emit(refdes)
            self._dragging = False
            self._press_pos = None

    def mouseDoubleClickEvent(self, event: Any) -> None:  # noqa: N802
        self.reset_view()

    # ---------------- geometry ----------------

    def _world_bounds(self) -> tuple[float, float, float, float]:
        if self._mode == "machine":
            return (0.0, 0.0, self._limits[0], self._limits[1])
        if self._product:
            return (0.0, 0.0, self._product.board_width_mm, self._product.board_height_mm)
        return (0.0, 0.0, 180.0, 110.0)

    def _world_center(self) -> tuple[float, float]:
        min_x, min_y, max_x, max_y = self._world_bounds()
        return ((min_x + max_x) / 2, (min_y + max_y) / 2)

    def _base_scale(self) -> float:
        min_x, min_y, max_x, max_y = self._world_bounds()
        width, height = max(1.0, max_x - min_x), max(1.0, max_y - min_y)
        return min((self.width() - 56) / width, (self.height() - 58) / height) * 0.92

    def _to_screen(self, x: float, y: float) -> QPointF:
        center = self._world_center()
        scale = self._base_scale() * self._zoom
        return QPointF(
            self.width() / 2 + self._pan.x() + (x - center[0]) * scale,
            self.height() / 2 + self._pan.y() - (y - center[1]) * scale,
        )

    def _screen_to_world(self, point: QPointF) -> tuple[float, float]:
        center = self._world_center()
        scale = max(1e-6, self._base_scale() * self._zoom)
        return (
            center[0] + (point.x() - self.width() / 2 - self._pan.x()) / scale,
            center[1] - (point.y() - self.height() / 2 - self._pan.y()) / scale,
        )

    def _placement_world(self, placement: Any) -> tuple[float, float]:
        if self._mode == "machine" and self._product:
            return (
                self._product.board_origin_x_mm + placement.x_mm,
                self._product.board_origin_y_mm + placement.y_mm,
            )
        return (placement.x_mm, placement.y_mm)

    def _nearest_placement(self, point: QPointF) -> str:
        if not self._product:
            return ""
        best = ""
        best_distance = 15.0
        for placement in self._product.placements:
            screen = self._to_screen(*self._placement_world(placement))
            distance = math.hypot(screen.x() - point.x(), screen.y() - point.y())
            if distance < best_distance:
                best_distance = distance
                best = placement.refdes
        return best

    # ---------------- painting ----------------

    def paintEvent(self, event: Any) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.rect(), QColor(COLORS["bg_soft"]))
        self._draw_background(painter)
        if self._product:
            self._draw_board(painter)
            self._draw_placements(painter)
            self._draw_head(painter)
        else:
            painter.setPen(QColor(COLORS["faint"]))
            painter.setFont(QFont("Microsoft YaHei UI", 11))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "尚未选择产品")
        self._draw_hud(painter)
        painter.end()

    def _draw_background(self, painter: QPainter) -> None:
        if self._mode != "machine":
            return
        min_x, min_y, max_x, max_y = self._world_bounds()
        top_left = self._to_screen(min_x, max_y)
        bottom_right = self._to_screen(max_x, min_y)
        machine_rect = QRectF(top_left, bottom_right)
        painter.setPen(QPen(QColor(COLORS["border"]), 1))
        painter.setBrush(QColor("#091117"))
        painter.drawRoundedRect(machine_rect, 4, 4)
        grid_pen = QPen(QColor(255, 255, 255, 10), 1)
        painter.setPen(grid_pen)
        step = 20.0
        x = min_x
        while x <= max_x:
            p1, p2 = self._to_screen(x, min_y), self._to_screen(x, max_y)
            painter.drawLine(p1, p2)
            x += step
        y = min_y
        while y <= max_y:
            p1, p2 = self._to_screen(min_x, y), self._to_screen(max_x, y)
            painter.drawLine(p1, p2)
            y += step

    def _draw_board(self, painter: QPainter) -> None:
        assert self._product is not None
        product = self._product
        if self._mode == "machine":
            left = product.board_origin_x_mm
            bottom = product.board_origin_y_mm
        else:
            left, bottom = 0.0, 0.0
        top_left = self._to_screen(left, bottom + product.board_height_mm)
        bottom_right = self._to_screen(left + product.board_width_mm, bottom)
        board = QRectF(top_left, bottom_right)
        if board.width() < 2 or board.height() < 2:
            return

        shadow = board.adjusted(-5, -5, 5, 6)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 80))
        painter.drawRoundedRect(shadow, 5, 5)

        gradient = QLinearGradient(board.topLeft(), board.bottomRight())
        gradient.setColorAt(0, QColor("#143f30"))
        gradient.setColorAt(0.55, QColor("#0e3328"))
        gradient.setColorAt(1, QColor("#0a2820"))
        painter.setBrush(gradient)
        painter.setPen(QPen(QColor("#2a6a53"), 1.2))
        painter.drawRoundedRect(board, 3, 3)

        painter.save()
        painter.setClipRect(board)
        painter.setPen(QPen(QColor(120, 190, 160, 18), 1))
        pattern = [
            [(0.08, 0.12), (0.22, 0.12), (0.26, 0.18), (0.44, 0.18)],
            [(0.1, 0.5), (0.26, 0.5), (0.3, 0.56), (0.55, 0.56)],
            [(0.5, 0.16), (0.66, 0.16), (0.7, 0.22), (0.92, 0.22)],
            [(0.58, 0.8), (0.8, 0.8), (0.84, 0.74), (0.92, 0.74)],
            [(0.16, 0.72), (0.34, 0.72), (0.38, 0.66), (0.46, 0.66)],
        ]
        for polyline in pattern:
            path = QPainterPath()
            first = True
            for fx, fy in polyline:
                point = QPointF(board.left() + board.width() * fx, board.top() + board.height() * fy)
                if first:
                    path.moveTo(point)
                    first = False
                else:
                    path.lineTo(point)
            painter.drawPath(path)
        painter.setPen(QPen(QColor(255, 255, 255, 9), 1))
        step_mm = 10.0
        x = 0.0
        while x <= product.board_width_mm:
            p1 = self._to_screen(left + x, bottom)
            p2 = self._to_screen(left + x, bottom + product.board_height_mm)
            painter.drawLine(p1, p2)
            x += step_mm
        y = 0.0
        while y <= product.board_height_mm:
            p1 = self._to_screen(left, bottom + y)
            p2 = self._to_screen(left + product.board_width_mm, bottom + y)
            painter.drawLine(p1, p2)
            y += step_mm
        painter.restore()

        painter.setPen(QPen(QColor("#4c8c72"), 1, Qt.PenStyle.DashLine))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(board)
        painter.setPen(QColor(COLORS["faint"]))
        painter.setFont(QFont("Cascadia Mono", 8))
        painter.drawText(
            QRectF(board.left(), board.bottom() + 5, board.width(), 16),
            Qt.AlignmentFlag.AlignLeft,
            f"0,0   {product.board_width_mm:.0f} × {product.board_height_mm:.0f} mm",
        )

        for fiducial in product.fiducials:
            point = self._to_screen(left + fiducial.x_mm, bottom + fiducial.y_mm)
            radius = max(3.5, fiducial.radius_mm * self._base_scale() * self._zoom)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor("#e3b341"), 1.3))
            painter.drawEllipse(point, radius, radius)
            painter.drawLine(QPointF(point.x() - radius * 1.7, point.y()), QPointF(point.x() + radius * 1.7, point.y()))
            painter.drawLine(QPointF(point.x(), point.y() - radius * 1.7), QPointF(point.x(), point.y() + radius * 1.7))
            if radius > 5:
                painter.setPen(QColor(COLORS["muted"]))
                painter.setFont(QFont("Cascadia Mono", 7))
                painter.drawText(QPointF(point.x() + radius + 4, point.y() - 4), fiducial.name)

    def _draw_placements(self, painter: QPainter) -> None:
        assert self._product is not None
        scale = self._base_scale() * self._zoom
        for placement in self._product.placements:
            component = self._components.get(placement.component_id)
            if component is None:
                continue
            point = self._to_screen(*self._placement_world(placement))
            body_w = max(2.2, component.length_mm * scale)
            body_h = max(1.4, component.width_mm * scale)
            status = self._statuses.get(placement.refdes, "skipped" if placement.skip else "pending")
            selected = placement.refdes == self._selected
            self._draw_footprint(painter, point, body_w, body_h, placement.rotation_deg, component, status, selected)
            if selected:
                size = max(body_w, body_h) / 2 + 7
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.setPen(QPen(QColor(COLORS["accent"]), 1.5))
                painter.drawRoundedRect(
                    QRectF(point.x() - size, point.y() - size, size * 2, size * 2), 3, 3
                )
                label = f"{placement.refdes}  {component.name}"
                metrics = QFontMetrics(QFont("Microsoft YaHei UI", 9))
                text_w = metrics.horizontalAdvance(label) + 14
                label_rect = QRectF(
                    point.x() + size + 5,
                    point.y() - 12,
                    text_w,
                    24,
                )
                if label_rect.right() > self.width() - 8:
                    label_rect.moveLeft(point.x() - size - 5 - text_w)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(14, 30, 38, 235))
                painter.drawRoundedRect(label_rect, 4, 4)
                painter.setPen(QColor(COLORS["text"]))
                painter.setFont(QFont("Microsoft YaHei UI", 9))
                painter.drawText(label_rect.adjusted(7, 0, -7, 0), Qt.AlignmentFlag.AlignVCenter, label)

    def _draw_footprint(
        self,
        painter: QPainter,
        center: QPointF,
        width: float,
        height: float,
        rotation: float,
        component: Component,
        status: str,
        selected: bool,
    ) -> None:
        color = QColor(component.color)
        status_color = {
            "placing": QColor(COLORS["warn"]),
            "placed": QColor(COLORS["success"]),
            "failed": QColor(COLORS["danger"]),
            "skipped": QColor(COLORS["faint"]),
        }.get(status)
        painter.save()
        painter.translate(center)
        painter.rotate(-rotation)
        painter.setPen(Qt.PenStyle.NoPen)

        is_ic = any(token in component.package.upper() for token in ("SOP", "SOIC", "QFN", "QFP", "BGA"))
        if is_ic:
            pin_w = max(0.8, width * 0.08)
            pin_len = max(1.2, width * 0.18)
            painter.setBrush(QColor("#c4c8bf"))
            for i in range(4):
                offset = -width * 0.33 + i * width * 0.22
                painter.drawRect(QRectF(offset, -height / 2 - pin_len * 0.45, pin_w, pin_len))
                painter.drawRect(QRectF(offset, height / 2 - pin_len * 0.55, pin_w, pin_len))
            if "QFN" in component.package.upper() or "QFP" in component.package.upper():
                for i in range(4):
                    offset = -height * 0.3 + i * height * 0.2
                    painter.drawRect(QRectF(-width / 2 - pin_len * 0.45, offset, pin_len, pin_w))
                    painter.drawRect(QRectF(width / 2 - pin_len * 0.55, offset, pin_len, pin_w))
            painter.setBrush(color)
            painter.setPen(QPen(QColor(0, 0, 0, 90), 1))
            painter.drawRoundedRect(QRectF(-width / 2, -height / 2, width, height), 1, 1)
            painter.setPen(QPen(QColor(255, 255, 255, 45), 0.8))
            painter.drawEllipse(QPointF(-width * 0.34, -height * 0.3), max(0.8, width * 0.06), max(0.8, width * 0.06))
        elif component.package.upper().startswith("HDR"):
            painter.setBrush(QColor("#1d2226"))
            painter.setPen(QPen(QColor("#39444b"), 0.8))
            painter.drawRoundedRect(QRectF(-width / 2, -height / 2, width, height), 1, 1)
            pins = 4
            for i in range(pins):
                x = -width / 2 + (i + 0.5) * width / pins
                painter.setBrush(QColor("#d6b35b"))
                painter.drawEllipse(QPointF(x, 0), max(0.7, width * 0.035), max(0.7, width * 0.035))
        else:
            painter.setBrush(QColor("#c9cdc4"))
            pad_w = max(1.1, width * 0.28)
            painter.drawRoundedRect(QRectF(-width / 2 - pad_w * 0.2, -height * 0.42, pad_w, height * 0.84), 0.5, 0.5)
            painter.drawRoundedRect(QRectF(width / 2 - pad_w * 0.8, -height * 0.42, pad_w, height * 0.84), 0.5, 0.5)
            painter.setBrush(color)
            painter.setPen(QPen(QColor(0, 0, 0, 80), 0.8))
            painter.drawRoundedRect(QRectF(-width * 0.34, -height / 2, width * 0.68, height), 0.8, 0.8)

        if status_color is not None:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(status_color, 1.0 if status != "placing" else 1.8))
            painter.drawRoundedRect(
                QRectF(-width / 2 - 2, -height / 2 - 2, width + 4, height + 4), 2, 2
            )
        painter.restore()
        if selected:
            painter.setBrush(Qt.BrushStyle.NoBrush)

    def _draw_head(self, painter: QPainter) -> None:
        if not self._product:
            return
        x, y, _ = self._head
        if self._mode == "machine":
            world_x, world_y = x, y
        else:
            world_x = x - self._product.board_origin_x_mm
            world_y = y - self._product.board_origin_y_mm
        point = self._to_screen(world_x, world_y)
        if not self.rect().adjusted(-20, -20, 20, 20).contains(point.toPoint()):
            return
        accent = QColor(COLORS["accent"])
        glow = QColor(accent)
        glow.setAlpha(int(28 + 22 * (math.sin(self._pulse) + 1) / 2))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(glow)
        painter.drawEllipse(point, 22, 22)
        painter.setPen(QPen(QColor(COLORS["accent_dim"]), 1, Qt.PenStyle.DashLine))
        painter.drawLine(QPointF(self.rect().left(), point.y()), QPointF(self.rect().right(), point.y()))
        painter.drawLine(QPointF(point.x(), self.rect().top()), QPointF(point.x(), self.rect().bottom()))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(accent, 1.4))
        painter.drawEllipse(point, 8, 8)
        painter.drawLine(QPointF(point.x() - 13, point.y()), QPointF(point.x() - 4, point.y()))
        painter.drawLine(QPointF(point.x() + 4, point.y()), QPointF(point.x() + 13, point.y()))
        painter.drawLine(QPointF(point.x(), point.y() - 13), QPointF(point.x(), point.y() - 4))
        painter.drawLine(QPointF(point.x(), point.y() + 4), QPointF(point.x(), point.y() + 13))
        painter.setBrush(accent)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(point, 2.2, 2.2)

        label = f"X {self._head[0]:.1f}  Y {self._head[1]:.1f}"
        metrics = QFontMetrics(QFont("Cascadia Mono", 8))
        width = metrics.horizontalAdvance(label) + 14
        rect = QRectF(point.x() + 16, point.y() + 12, width, 21)
        if rect.right() > self.width() - 6:
            rect.moveLeft(point.x() - 16 - width)
        if rect.bottom() > self.height() - 30:
            rect.moveTop(point.y() - 40)
        painter.setBrush(QColor(8, 20, 26, 225))
        painter.setPen(QPen(QColor(COLORS["border"]), 0.8))
        painter.drawRoundedRect(rect, 4, 4)
        painter.setPen(accent)
        painter.setFont(QFont("Cascadia Mono", 8))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, label)

    def _draw_hud(self, painter: QPainter) -> None:
        painter.setFont(QFont("Cascadia Mono", 8))
        mode_text = "MACHINE VIEW" if self._mode == "machine" else "BOARD VIEW"
        painter.setPen(QColor(COLORS["muted"]))
        painter.drawText(14, 22, mode_text)
        painter.setPen(QColor(COLORS["faint"]))
        painter.drawText(self.width() - 68, 22, f"{self._zoom * 100:.0f}%")
        painter.drawText(14, self.height() - 12, "滚轮缩放 · 拖拽平移 · 双击复位")


class Toast(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        set_css(self, "toast")
        self.setFixedWidth(390)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(10)
        self.icon_label = QLabel()
        self.icon_label.setFixedSize(20, 20)
        layout.addWidget(self.icon_label)
        self.text_label = QLabel("")
        self.text_label.setWordWrap(True)
        self.text_label.setStyleSheet("font-size: 12px;")
        layout.addWidget(self.text_label, 1)
        self.close_button = QPushButton()
        self.close_button.setIcon(icon("close", COLORS["muted"], 14))
        self.close_button.setFixedSize(22, 22)
        self.close_button.setProperty("variant", "ghost")
        self.close_button.clicked.connect(self.hide_animated)
        layout.addWidget(self.close_button, 0, Qt.AlignmentFlag.AlignTop)
        self._effect = QGraphicsOpacityEffect(self)
        self._effect.setOpacity(0.0)
        self.setGraphicsEffect(self._effect)
        self._animation = QPropertyAnimation(self._effect, b"opacity", self)
        self._animation.setDuration(180)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide_animated)
        self.hide()

    def show_message(self, text: str, level: str = "info", duration: int = 3800) -> None:
        colors = {
            "info": (COLORS["accent"], "check"),
            "success": (COLORS["success"], "check"),
            "warning": (COLORS["warn"], "warning"),
            "error": (COLORS["danger"], "warning"),
        }
        color, icon_name = colors.get(level, colors["info"])
        self.setStyleSheet(
            f"QFrame[cssClass='toast'] {{ background: {COLORS['surface3']}; border: 1px solid {color}66;"
            f" border-left: 3px solid {color}; border-radius: 8px; }}"
        )
        self.icon_label.setPixmap(icon(icon_name, color, 18).pixmap(18, 18))
        self.text_label.setText(text)
        self.adjustSize()
        self.setFixedWidth(390)
        self.reposition()
        self.show()
        self.raise_()
        self._animation.stop()
        self._animation.setStartValue(self._effect.opacity())
        self._animation.setEndValue(1.0)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._animation.start()
        self._timer.start(duration)

    def hide_animated(self) -> None:
        self._timer.stop()
        self._animation.stop()
        self._animation.setStartValue(self._effect.opacity())
        self._animation.setEndValue(0.0)
        self._animation.finished.connect(self._after_hide)
        self._animation.start()

    def _after_hide(self) -> None:
        try:
            self._animation.finished.disconnect(self._after_hide)
        except (RuntimeError, TypeError):
            pass
        if self._effect.opacity() < 0.05:
            self.hide()

    def reposition(self) -> None:
        if self.parentWidget():
            self.move(self.parentWidget().width() - self.width() - 24, 82)


def hline() -> QFrame:
    line = QFrame()
    set_css(line, "divider")
    line.setFixedHeight(1)
    return line


def vline() -> QFrame:
    line = QFrame()
    set_css(line, "vdivider")
    line.setFixedWidth(1)
    return line


def button(text: str, icon_name: str | None = None, variant: str = "", height: int = 34) -> QPushButton:
    control = QPushButton(text)
    if icon_name:
        control.setIcon(icon(icon_name, COLORS["text"] if variant != "primary" else "#04221d", 16))
        control.setIconSize(QSize(16, 16))
    if variant:
        control.setProperty("variant", variant)
    control.setMinimumHeight(height)
    control.setCursor(Qt.CursorShape.PointingHandCursor)
    return control


def make_chip(text: str, accent: bool = False) -> QLabel:
    label = QLabel(text)
    label.setProperty("chip", "accent" if accent else "true")
    return label


def format_duration(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"
