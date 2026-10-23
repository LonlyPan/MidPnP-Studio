"""矢量图标与应用图标（全部由 QPainter 生成，无外部资源依赖）。"""

from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QIcon,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)

from .theme import COLORS


@lru_cache(maxsize=256)
def _pixmap(name: str, color: str, size: int, dpr: float = 2.0) -> QPixmap:
    pixmap = QPixmap(int(size * dpr), int(size * dpr))
    pixmap.fill(Qt.GlobalColor.transparent)
    pixmap.setDevicePixelRatio(dpr)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.scale(size / 24.0, size / 24.0)
    pen = QPen(QColor(color), 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    _draw(painter, name, QColor(color))
    painter.end()
    return pixmap


def _draw(p: QPainter, name: str, color: QColor) -> None:
    if name == "dashboard":
        for x, y in ((3, 3), (14, 3), (3, 14), (14, 14)):
            p.drawRoundedRect(QRectF(x, y, 7, 7), 1.8, 1.8)
    elif name == "production":
        p.drawEllipse(QPointF(12, 12), 8.5, 8.5)
        path = QPainterPath()
        path.moveTo(10, 8.5)
        path.lineTo(16, 12)
        path.lineTo(10, 15.5)
        path.closeSubpath()
        p.setBrush(color)
        p.drawPath(path)
    elif name == "programming":
        p.drawRoundedRect(QRectF(3, 4, 18, 16), 2, 2)
        p.drawLine(QPointF(3, 9), QPointF(21, 9))
        p.drawLine(QPointF(9, 9), QPointF(9, 20))
        for x in (12.5, 16.5):
            p.drawPoint(QPointF(x, 14.5))
    elif name == "feeder":
        p.drawEllipse(QPointF(9.5, 12), 6.5, 6.5)
        p.drawEllipse(QPointF(9.5, 12), 2.0, 2.0)
        path = QPainterPath()
        path.moveTo(15.5, 9)
        path.cubicTo(19, 9, 19, 15, 21.5, 15)
        p.drawPath(path)
        p.drawLine(QPointF(18, 17.5), QPointF(21.5, 17.5))
    elif name == "component":
        p.drawRoundedRect(QRectF(6, 6, 12, 12), 2, 2)
        p.drawLine(QPointF(9, 6), QPointF(9, 3))
        p.drawLine(QPointF(15, 6), QPointF(15, 3))
        p.drawLine(QPointF(9, 21), QPointF(9, 18))
        p.drawLine(QPointF(15, 21), QPointF(15, 18))
        p.drawLine(QPointF(6, 9), QPointF(3, 9))
        p.drawLine(QPointF(6, 15), QPointF(3, 15))
        p.drawLine(QPointF(21, 9), QPointF(18, 9))
        p.drawLine(QPointF(21, 15), QPointF(18, 15))
    elif name == "manual":
        p.drawEllipse(QPointF(12, 12), 2.4, 2.4)
        for start, end in (
            (QPointF(12, 3), QPointF(12, 8.8)),
            (QPointF(12, 15.2), QPointF(12, 21)),
            (QPointF(3, 12), QPointF(8.8, 12)),
            (QPointF(15.2, 12), QPointF(21, 12)),
        ):
            p.drawLine(start, end)
        p.drawLine(QPointF(9.7, 5.3), QPointF(12, 3))
        p.drawLine(QPointF(14.3, 5.3), QPointF(12, 3))
        p.drawLine(QPointF(9.7, 18.7), QPointF(12, 21))
        p.drawLine(QPointF(14.3, 18.7), QPointF(12, 21))
    elif name == "vision":
        path = QPainterPath()
        path.moveTo(2.8, 12)
        path.cubicTo(6.5, 6.4, 17.5, 6.4, 21.2, 12)
        path.cubicTo(17.5, 17.6, 6.5, 17.6, 2.8, 12)
        p.drawPath(path)
        p.setBrush(color)
        p.drawEllipse(QPointF(12, 12), 2.8, 2.8)
    elif name == "logs":
        path = QPainterPath()
        path.moveTo(6, 3.5)
        path.lineTo(15, 3.5)
        path.lineTo(19, 7.5)
        path.lineTo(19, 20.5)
        path.lineTo(6, 20.5)
        path.closeSubpath()
        p.drawPath(path)
        for y in (10, 13, 16):
            p.drawLine(QPointF(9, y), QPointF(16, y))
    elif name == "settings":
        p.drawEllipse(QPointF(12, 12), 3.2, 3.2)
        import math

        for i in range(8):
            angle = i * math.pi / 4
            p.drawLine(
                QPointF(12 + math.cos(angle) * 6.0, 12 + math.sin(angle) * 6.0),
                QPointF(12 + math.cos(angle) * 9.2, 12 + math.sin(angle) * 9.2),
            )
        p.drawEllipse(QPointF(12, 12), 6.0, 6.0)
    elif name == "play":
        path = QPainterPath()
        path.moveTo(7.5, 5)
        path.lineTo(19, 12)
        path.lineTo(7.5, 19)
        path.closeSubpath()
        p.setBrush(color)
        p.drawPath(path)
    elif name == "pause":
        p.setBrush(color)
        p.drawRoundedRect(QRectF(7, 5, 3.5, 14), 1, 1)
        p.drawRoundedRect(QRectF(13.5, 5, 3.5, 14), 1, 1)
    elif name == "stop":
        p.setBrush(color)
        p.drawRoundedRect(QRectF(6, 6, 12, 12), 2, 2)
    elif name == "home":
        path = QPainterPath()
        path.moveTo(3.5, 11)
        path.lineTo(12, 3.5)
        path.lineTo(20.5, 11)
        p.drawPath(path)
        p.drawLine(QPointF(5.5, 10), QPointF(5.5, 20))
        p.drawLine(QPointF(18.5, 10), QPointF(18.5, 20))
        p.drawLine(QPointF(5.5, 20), QPointF(18.5, 20))
        p.drawLine(QPointF(10, 20), QPointF(10, 14))
        p.drawLine(QPointF(14, 20), QPointF(14, 14))
        p.drawLine(QPointF(10, 14), QPointF(14, 14))
    elif name == "plus":
        p.drawLine(QPointF(12, 5), QPointF(12, 19))
        p.drawLine(QPointF(5, 12), QPointF(19, 12))
    elif name == "trash":
        p.drawLine(QPointF(4, 7), QPointF(20, 7))
        p.drawLine(QPointF(9, 4), QPointF(15, 4))
        p.drawRoundedRect(QRectF(6, 7, 12, 13), 1.5, 1.5)
        p.drawLine(QPointF(10, 10.5), QPointF(10, 17))
        p.drawLine(QPointF(14, 10.5), QPointF(14, 17))
    elif name == "edit":
        p.drawLine(QPointF(4, 20), QPointF(7, 19.3))
        p.drawLine(QPointF(5.5, 17), QPointF(17, 5.5))
        p.drawLine(QPointF(16, 4.5), QPointF(19.5, 8))
        p.drawLine(QPointF(4, 20), QPointF(5.5, 17))
    elif name == "save":
        path = QPainterPath()
        path.moveTo(4, 4)
        path.lineTo(17, 4)
        path.lineTo(20, 7)
        path.lineTo(20, 20)
        path.lineTo(4, 20)
        path.closeSubpath()
        p.drawPath(path)
        p.drawRect(QRectF(8, 4, 8, 5))
        p.drawRect(QRectF(7.5, 13, 9, 7))
    elif name == "upload":
        p.drawLine(QPointF(12, 16), QPointF(12, 4))
        p.drawLine(QPointF(7, 9), QPointF(12, 4))
        p.drawLine(QPointF(17, 9), QPointF(12, 4))
        p.drawLine(QPointF(4, 16), QPointF(4, 20))
        p.drawLine(QPointF(4, 20), QPointF(20, 20))
        p.drawLine(QPointF(20, 20), QPointF(20, 16))
    elif name == "download":
        p.drawLine(QPointF(12, 4), QPointF(12, 16))
        p.drawLine(QPointF(7, 11), QPointF(12, 16))
        p.drawLine(QPointF(17, 11), QPointF(12, 16))
        p.drawLine(QPointF(4, 17), QPointF(4, 20))
        p.drawLine(QPointF(4, 20), QPointF(20, 20))
        p.drawLine(QPointF(20, 20), QPointF(20, 17))
    elif name == "refresh":
        p.drawArc(QRectF(5, 5, 14, 14), 35 * 16, 280 * 16)
        p.drawLine(QPointF(17.5, 4.5), QPointF(18.5, 9))
        p.drawLine(QPointF(18.5, 9), QPointF(14, 9.2))
    elif name == "search":
        p.drawEllipse(QPointF(10.5, 10.5), 6.0, 6.0)
        p.drawLine(QPointF(15, 15), QPointF(20, 20))
    elif name == "link":
        p.drawArc(QRectF(3, 8, 12, 8), 70 * 16, 220 * 16)
        p.drawArc(QRectF(9, 8, 12, 8), 250 * 16, 220 * 16)
    elif name == "wifi":
        for radius, start in ((3, 4), (7, 4), (11, 4)):
            p.drawArc(QRectF(12 - radius, 12 - radius, radius * 2, radius * 2), 45 * 16, 90 * 16)
        p.setBrush(color)
        p.drawEllipse(QPointF(12, 18), 1.3, 1.3)
    elif name == "camera":
        p.drawRoundedRect(QRectF(3, 7, 18, 13), 2, 2)
        p.drawEllipse(QPointF(12, 13.5), 3.4, 3.4)
        p.drawLine(QPointF(8, 7), QPointF(9.5, 4.5))
        p.drawLine(QPointF(9.5, 4.5), QPointF(14.5, 4.5))
        p.drawLine(QPointF(14.5, 4.5), QPointF(16, 7))
    elif name == "check":
        p.drawLine(QPointF(4, 12.5), QPointF(9.5, 18))
        p.drawLine(QPointF(9.5, 18), QPointF(20, 6))
    elif name == "warning":
        path = QPainterPath()
        path.moveTo(12, 3.5)
        path.lineTo(21.5, 20)
        path.lineTo(2.5, 20)
        path.closeSubpath()
        p.drawPath(path)
        p.drawLine(QPointF(12, 9), QPointF(12, 14))
        p.setBrush(color)
        p.drawEllipse(QPointF(12, 17), 1.0, 1.0)
    elif name == "close":
        p.drawLine(QPointF(5, 5), QPointF(19, 19))
        p.drawLine(QPointF(19, 5), QPointF(5, 19))
    elif name == "database":
        p.drawEllipse(QRectF(4, 3, 16, 5))
        p.drawLine(QPointF(4, 5.5), QPointF(4, 18.5))
        p.drawLine(QPointF(20, 5.5), QPointF(20, 18.5))
        p.drawArc(QRectF(4, 16, 16, 5), 180 * 16, 180 * 16)
        p.drawArc(QRectF(4, 11, 16, 5), 180 * 16, 180 * 16)
    elif name == "folder":
        path = QPainterPath()
        path.moveTo(3, 6)
        path.lineTo(9, 6)
        path.lineTo(11, 8.5)
        path.lineTo(21, 8.5)
        path.lineTo(21, 19)
        path.lineTo(3, 19)
        path.closeSubpath()
        p.drawPath(path)
    elif name == "zap":
        path = QPainterPath()
        path.moveTo(13, 2.5)
        path.lineTo(5, 13.5)
        path.lineTo(11, 13.5)
        path.lineTo(10, 21.5)
        path.lineTo(19, 10)
        path.lineTo(13, 10)
        path.closeSubpath()
        p.drawPath(path)
    elif name == "target":
        p.drawEllipse(QPointF(12, 12), 8, 8)
        p.drawEllipse(QPointF(12, 12), 3.5, 3.5)
        p.drawLine(QPointF(12, 1.5), QPointF(12, 5))
        p.drawLine(QPointF(12, 19), QPointF(12, 22.5))
        p.drawLine(QPointF(1.5, 12), QPointF(5, 12))
        p.drawLine(QPointF(19, 12), QPointF(22.5, 12))
    elif name in {"arrow-up", "arrow-down", "arrow-left", "arrow-right"}:
        if name == "arrow-up":
            p.drawLine(QPointF(12, 20), QPointF(12, 4))
            p.drawLine(QPointF(6, 10), QPointF(12, 4))
            p.drawLine(QPointF(18, 10), QPointF(12, 4))
        elif name == "arrow-down":
            p.drawLine(QPointF(12, 4), QPointF(12, 20))
            p.drawLine(QPointF(6, 14), QPointF(12, 20))
            p.drawLine(QPointF(18, 14), QPointF(12, 20))
        elif name == "arrow-left":
            p.drawLine(QPointF(20, 12), QPointF(4, 12))
            p.drawLine(QPointF(10, 6), QPointF(4, 12))
            p.drawLine(QPointF(10, 18), QPointF(4, 12))
        else:
            p.drawLine(QPointF(4, 12), QPointF(20, 12))
            p.drawLine(QPointF(14, 6), QPointF(20, 12))
            p.drawLine(QPointF(14, 18), QPointF(20, 12))
    elif name == "chevron-right":
        p.drawLine(QPointF(9, 5), QPointF(16, 12))
        p.drawLine(QPointF(16, 12), QPointF(9, 19))
    elif name == "chevron-down":
        p.drawLine(QPointF(5, 9), QPointF(12, 16))
        p.drawLine(QPointF(12, 16), QPointF(19, 9))
    elif name == "layers":
        p.drawPolygon([QPointF(12, 3), QPointF(21, 8), QPointF(12, 13), QPointF(3, 8)])
        p.drawLine(QPointF(3, 12), QPointF(12, 17))
        p.drawLine(QPointF(12, 17), QPointF(21, 12))
        p.drawLine(QPointF(3, 16), QPointF(12, 21))
        p.drawLine(QPointF(12, 21), QPointF(21, 16))
    elif name == "clock":
        p.drawEllipse(QPointF(12, 12), 8.5, 8.5)
        p.drawLine(QPointF(12, 7), QPointF(12, 12))
        p.drawLine(QPointF(12, 12), QPointF(16, 14))
    elif name == "shield":
        path = QPainterPath()
        path.moveTo(12, 2.8)
        path.lineTo(20, 6)
        path.lineTo(19, 13)
        path.cubicTo(18, 18, 15, 20, 12, 21.5)
        path.cubicTo(9, 20, 6, 18, 5, 13)
        path.lineTo(4, 6)
        path.closeSubpath()
        p.drawPath(path)


def icon(name: str, color: str = COLORS["text"], size: int = 20) -> QIcon:
    return QIcon(_pixmap(name, color, size))


def nav_icon(name: str, size: int = 20) -> QIcon:
    result = QIcon()
    result.addPixmap(_pixmap(name, COLORS["muted"], size), QIcon.Mode.Normal, QIcon.State.Off)
    result.addPixmap(_pixmap(name, COLORS["text"], size), QIcon.Mode.Active, QIcon.State.Off)
    result.addPixmap(_pixmap(name, COLORS["accent"], size), QIcon.Mode.Normal, QIcon.State.On)
    result.addPixmap(_pixmap(name, COLORS["accent"], size), QIcon.Mode.Active, QIcon.State.On)
    return result


@lru_cache(maxsize=8)
def app_icon(size: int = 128) -> QIcon:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    margin = size * 0.04
    rect = QRectF(margin, margin, size - margin * 2, size - margin * 2)
    gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
    gradient.setColorAt(0, QColor("#10242b"))
    gradient.setColorAt(1, QColor("#081015"))
    painter.setBrush(gradient)
    painter.setPen(QPen(QColor("#2ee6c5"), max(1.0, size * 0.02)))
    painter.drawRoundedRect(rect, size * 0.2, size * 0.2)

    painter.setPen(QPen(QColor("#2ee6c5"), size * 0.045, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    center_x = size / 2
    painter.drawLine(QPointF(center_x, size * 0.22), QPointF(center_x, size * 0.46))
    painter.drawLine(QPointF(size * 0.30, size * 0.22), QPointF(size * 0.70, size * 0.22))
    painter.setBrush(QColor("#2ee6c5"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(QRectF(center_x - size * 0.14, size * 0.44, size * 0.28, size * 0.10), size * 0.03, size * 0.03)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(QColor("#2ee6c5"), size * 0.035))
    painter.drawLine(QPointF(center_x, size * 0.54), QPointF(center_x, size * 0.66))
    painter.drawLine(QPointF(center_x - size * 0.08, size * 0.66), QPointF(center_x + size * 0.08, size * 0.66))

    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#4da3ff"))
    for offset in (-0.18, 0.0, 0.18):
        painter.drawRoundedRect(
            QRectF(center_x + size * offset - size * 0.045, size * 0.76, size * 0.09, size * 0.045),
            size * 0.01,
            size * 0.01,
        )
    painter.end()
    return QIcon(pixmap)
