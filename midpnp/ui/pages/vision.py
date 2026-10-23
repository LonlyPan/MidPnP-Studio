"""视觉对位页（内置离线仿真，预留工业相机接入点）。"""

from __future__ import annotations

import math
import random
from typing import Any

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from ..context import AppContext
from ..theme import COLORS
from ..widgets import Card, InfoRow, PageHeader, button, hline, make_chip


class VisionView(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(520, 420)
        self._phase = 0.0
        self._scan = 0.0
        self._aligning = False
        self._locked = False
        self._dx = 0.0
        self._dy = 0.0
        self._score = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(50)
        self._noise = [(random.random(), random.random(), random.random()) for _ in range(42)]

    def _tick(self) -> None:
        self._phase = (self._phase + 0.05) % (math.pi * 2)
        self._scan = (self._scan + (0.025 if self._aligning else 0.006)) % 1.0
        self.update()

    def set_aligning(self, aligning: bool) -> None:
        self._aligning = aligning
        self.update()

    def set_result(self, dx: float, dy: float, score: float) -> None:
        self._dx = dx
        self._dy = dy
        self._score = score
        self._locked = score > 0.8
        self.update()

    def reset_result(self) -> None:
        self._locked = False
        self._score = 0.0
        self.update()

    def paintEvent(self, event: Any) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
        gradient.setColorAt(0, QColor("#183a2d"))
        gradient.setColorAt(0.55, QColor("#102b22"))
        gradient.setColorAt(1, QColor("#0a1d17"))
        painter.setBrush(gradient)
        painter.setPen(QPen(QColor(COLORS["border"]), 1))
        painter.drawRoundedRect(rect, 8, 8)
        painter.save()
        painter.setClipRect(rect.adjusted(1, 1, -1, -1))

        # PCB trace texture
        painter.setPen(QPen(QColor(120, 200, 165, 28), 2))
        for i in range(7):
            y = self.height() * (0.15 + i * 0.12)
            path_y = [y, y - 12, y + 14, y - 8]
            for j in range(3):
                painter.drawLine(
                    QPointF(self.width() * (0.04 + j * 0.32), path_y[j]),
                    QPointF(self.width() * (0.28 + j * 0.32), path_y[j + 1]),
                )
        painter.setPen(QPen(QColor(255, 255, 255, 12), 1))
        for gx in range(0, self.width(), 42):
            painter.drawLine(QPointF(gx, 0), QPointF(gx, self.height()))
        for gy in range(0, self.height(), 42):
            painter.drawLine(QPointF(0, gy), QPointF(self.width(), gy))

        # pads / component silhouettes
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(210, 190, 120, 70))
        for i in range(9):
            x = self.width() * (0.16 + (i % 3) * 0.11)
            y = self.height() * (0.72 + (i // 3) * 0.07)
            painter.drawRoundedRect(QRectF(x, y, 34, 12), 2, 2)
        painter.setBrush(QColor(35, 42, 47, 160))
        painter.drawRoundedRect(QRectF(self.width() * 0.14, self.height() * 0.55, self.width() * 0.23, self.height() * 0.12), 3, 3)

        # fiducial
        center = QPointF(self.width() * 0.62 + self._dx * 22, self.height() * 0.4 + self._dy * 22)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(214, 178, 72, 28))
        painter.drawEllipse(center, 34, 34)
        painter.setBrush(QColor(190, 155, 58))
        painter.drawEllipse(center, 22, 22)
        painter.setBrush(QColor(232, 204, 120))
        painter.drawEllipse(center, 18, 18)
        painter.setBrush(QColor("#14251d"))
        painter.drawEllipse(center, 5.5, 5.5)
        painter.setPen(QPen(QColor(214, 178, 72, 50), 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(center, 38, 38)

        # scan line
        scan_y = rect.top() + rect.height() * self._scan
        scan_color = QColor(COLORS["accent"])
        scan_color.setAlpha(130 if self._aligning else 55)
        painter.setPen(QPen(scan_color, 1.5))
        painter.drawLine(QPointF(rect.left(), scan_y), QPointF(rect.right(), scan_y))
        glow = QColor(COLORS["accent"])
        glow.setAlpha(18)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(glow)
        painter.drawRect(QRectF(rect.left(), scan_y - 18, rect.width(), 36))

        # crosshair
        cx, cy = self.width() / 2, self.height() / 2
        accent = QColor(COLORS["accent"] if self._locked else COLORS["muted"])
        painter.setPen(QPen(QColor(accent.red(), accent.green(), accent.blue(), 200), 1.2))
        painter.drawLine(QPointF(cx - 34, cy), QPointF(cx - 8, cy))
        painter.drawLine(QPointF(cx + 8, cy), QPointF(cx + 34, cy))
        painter.drawLine(QPointF(cx, cy - 34), QPointF(cx, cy - 8))
        painter.drawLine(QPointF(cx, cy + 8), QPointF(cx, cy + 34))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QPointF(cx, cy), 7, 7)

        # ROI and lock box
        roi = QRectF(center.x() - 62, center.y() - 62, 124, 124)
        painter.setPen(QPen(QColor(COLORS["accent"] if self._locked else COLORS["warn"]), 1.2, Qt.PenStyle.DashLine))
        painter.drawRect(roi)
        for corner in (
            roi.topLeft(), roi.topRight(), roi.bottomLeft(), roi.bottomRight()
        ):
            painter.setPen(QPen(QColor(COLORS["accent"] if self._locked else COLORS["warn"]), 2.5))
            dx = 10 if corner.x() < center.x() else -10
            dy = 10 if corner.y() < center.y() else -10
            painter.drawLine(corner, QPointF(corner.x() + dx, corner.y()))
            painter.drawLine(corner, QPointF(corner.x(), corner.y() + dy))

        # noise specks
        painter.setPen(Qt.PenStyle.NoPen)
        for nx, ny, intensity in self._noise:
            painter.setBrush(QColor(255, 255, 255, int(10 + 16 * intensity)))
            painter.drawRect(QRectF(nx * self.width(), (ny + self._scan * 0.08) % 1.0 * self.height(), 1.5, 1.5))

        # HUD
        painter.setFont(QFont("Cascadia Mono", 8))
        painter.setPen(QColor(COLORS["accent"]))
        painter.drawText(16, 22, "CAM-01  SIMULATED  ·  1280 × 720  ·  30 FPS")
        painter.setPen(QColor(COLORS["muted"]))
        painter.drawText(16, self.height() - 18, "EXP 8.0ms   GAIN 2.0   TRIGGER FREE")
        painter.drawText(
            self.width() - 188,
            self.height() - 18,
            f"DX {self._dx:+.3f}   DY {self._dy:+.3f}",
        )
        if self._aligning:
            painter.setPen(QColor(COLORS["warn"]))
            painter.drawText(QRectF(0, self.height() - 52, self.width(), 20), Qt.AlignmentFlag.AlignCenter, "正在搜索基准点…")
        elif self._locked:
            painter.setPen(QColor(COLORS["accent"]))
            painter.drawText(
                QRectF(0, self.height() - 52, self.width(), 20),
                Qt.AlignmentFlag.AlignCenter,
                f"对位锁定  ·  置信度 {self._score * 100:.1f}%",
            )
        painter.restore()
        painter.end()


class VisionPage(QWidget):
    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self._align_timer = QTimer(self)
        self._align_timer.setSingleShot(True)
        self._align_timer.timeout.connect(self._finish_align)
        self._build()
        self._connect()
        self._refresh_fiducials()

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(14)
        self.header = PageHeader("视觉对位", "基准点识别、元件对中与贴装补偿")
        self.camera_chip = make_chip("离线仿真")
        self.connect_button = button("连接相机", "camera", "subtle")
        self.header.add_action(self.camera_chip)
        self.header.add_action(self.connect_button)
        outer.addWidget(self.header)

        content = QHBoxLayout()
        content.setSpacing(12)
        camera_card = Card(padding=12)
        camera_top = QHBoxLayout()
        title = QLabel("相机画面")
        title.setProperty("role", "section")
        camera_top.addWidget(title)
        camera_top.addWidget(make_chip("CAM-01"))
        camera_top.addStretch(1)
        self.fps = QLabel("30 FPS · 1280×720")
        self.fps.setProperty("role", "faint")
        camera_top.addWidget(self.fps)
        camera_card.body.addLayout(camera_top)
        self.view = VisionView()
        camera_card.body.addWidget(self.view, 1)
        hint = QLabel("当前为离线仿真画面：用于演示对位流程与界面布局，未连接工业相机。")
        hint.setProperty("role", "hint")
        hint.setWordWrap(True)
        camera_card.body.addWidget(hint)
        content.addWidget(camera_card, 1)

        panel = QVBoxLayout()
        panel.setSpacing(12)
        align = Card()
        title = QLabel("对位控制")
        title.setProperty("role", "section")
        align.body.addWidget(title)
        mode_row = QHBoxLayout()
        mode_label = QLabel("模式")
        mode_label.setProperty("role", "muted")
        self.mode = QComboBox()
        self.mode.addItem("基准点对位", "fiducial")
        self.mode.addItem("元件对中", "component")
        self.mode.addItem("手动对位", "manual")
        mode_row.addWidget(mode_label)
        mode_row.addStretch(1)
        mode_row.addWidget(self.mode)
        align.body.addLayout(mode_row)

        exposure_row = QHBoxLayout()
        exposure_label = QLabel("曝光")
        exposure_label.setProperty("role", "muted")
        self.exposure = QSlider(Qt.Orientation.Horizontal)
        self.exposure.setRange(1, 30)
        self.exposure.setValue(8)
        self.exposure_value = QLabel("8.0 ms")
        self.exposure_value.setProperty("role", "mono")
        self.exposure.valueChanged.connect(lambda value: self.exposure_value.setText(f"{value:.1f} ms"))
        exposure_row.addWidget(exposure_label)
        exposure_row.addWidget(self.exposure, 1)
        exposure_row.addWidget(self.exposure_value)
        align.body.addLayout(exposure_row)
        align.body.addWidget(hline())
        self.capture_button = button("采集图像", "camera", "subtle")
        self.align_button = button("执行对位", "target", "primary")
        self.teach_button = button("示教基准点", "target", "subtle")
        self.capture_button.clicked.connect(self._capture)
        self.align_button.clicked.connect(self._align)
        self.teach_button.clicked.connect(self._teach)
        align.body.addWidget(self.capture_button)
        align.body.addWidget(self.align_button)
        align.body.addWidget(self.teach_button)
        panel.addWidget(align)

        result = Card()
        result_title = QHBoxLayout()
        title = QLabel("对位结果")
        title.setProperty("role", "section")
        result_title.addWidget(title)
        result_title.addStretch(1)
        self.result_chip = make_chip("等待")
        result_title.addWidget(self.result_chip)
        result.body.addLayout(result_title)
        self.info_dx = InfoRow("X 偏差", "—")
        self.info_dy = InfoRow("Y 偏差", "—")
        self.info_theta = InfoRow("角度偏差", "—")
        self.info_score = InfoRow("置信度", "—")
        self.info_state = InfoRow("状态", "未对位")
        for row in (self.info_dx, self.info_dy, self.info_theta, self.info_score, self.info_state):
            result.body.addWidget(row)
        panel.addWidget(result)

        fiducial = Card()
        fid_title = QHBoxLayout()
        title = QLabel("基准点")
        title.setProperty("role", "section")
        fid_title.addWidget(title)
        fid_title.addStretch(1)
        self.fid_count = make_chip("0")
        fid_title.addWidget(self.fid_count)
        fiducial.body.addLayout(fid_title)
        self.fid_container = QVBoxLayout()
        self.fid_container.setSpacing(4)
        fiducial.body.addLayout(self.fid_container)
        panel.addWidget(fiducial)
        panel.addStretch(1)
        content.addLayout(panel, 0)
        outer.addLayout(content, 1)

        self.connect_button.clicked.connect(self._connect_camera)

    def _connect(self) -> None:
        self.ctx.signals.product_changed.connect(lambda *_: self._refresh_fiducials())

    def _refresh_fiducials(self) -> None:
        while self.fid_container.count():
            item = self.fid_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        product = self.ctx.current_product
        fiducials = product.fiducials if product else []
        self.fid_count.setText(str(len(fiducials)))
        if not fiducials:
            empty = QLabel("当前产品未定义基准点")
            empty.setProperty("role", "hint")
            self.fid_container.addWidget(empty)
            return
        for fiducial in fiducials:
            row = QWidget()
            layout = QHBoxLayout(row)
            layout.setContentsMargins(4, 3, 4, 3)
            marker = QLabel("◎")
            marker.setStyleSheet(f"color: {COLORS['warn']}; font-size: 16px;")
            name = QLabel(fiducial.name)
            name.setStyleSheet("font-family: 'Cascadia Mono';")
            coords = QLabel(f"{fiducial.x_mm:.1f}, {fiducial.y_mm:.1f}")
            coords.setProperty("role", "faint")
            layout.addWidget(marker)
            layout.addWidget(name)
            layout.addStretch(1)
            layout.addWidget(coords)
            self.fid_container.addWidget(row)

    def _connect_camera(self) -> None:
        self.ctx.toast("工业相机驱动未配置，当前使用离线仿真画面", "warning")
        self.ctx.log("WARN", "VISION", "相机连接请求：未配置工业相机，保持离线仿真")

    def _capture(self) -> None:
        self.result_chip.setText("已采集")
        self.result_chip.setStyleSheet(
            f"background: {COLORS['accent']}16; border: 1px solid {COLORS['accent']}55;"
            f" color: {COLORS['accent']}; border-radius: 10px; padding: 3px 9px; font-size: 11px;"
        )
        self.info_state.set("图像已采集", COLORS["accent"])
        self.ctx.log("INFO", "VISION", "采集一帧仿真图像（CAM-01）")
        self.ctx.toast("已采集图像", "success")

    def _align(self) -> None:
        self.view.reset_result()
        self.view.set_aligning(True)
        self.align_button.setEnabled(False)
        self.capture_button.setEnabled(False)
        self.result_chip.setText("搜索中")
        self.result_chip.setStyleSheet(
            f"background: {COLORS['warn']}16; border: 1px solid {COLORS['warn']}55;"
            f" color: {COLORS['warn']}; border-radius: 10px; padding: 3px 9px; font-size: 11px;"
        )
        self.info_state.set("正在搜索基准点…", COLORS["warn"])
        self._align_timer.start(900)

    def _finish_align(self) -> None:
        product = self.ctx.current_product
        if not product or not product.fiducials:
            self.view.set_aligning(False)
            self.align_button.setEnabled(True)
            self.capture_button.setEnabled(True)
            self.info_state.set("未找到基准点", COLORS["danger"])
            self.result_chip.setText("失败")
            self.ctx.toast("当前产品未定义基准点", "warning")
            return
        fiducial = product.fiducials[0]
        dx = round(0.018 + random.uniform(-0.012, 0.012), 3)
        dy = round(-0.024 + random.uniform(-0.012, 0.012), 3)
        theta = round(random.uniform(-0.04, 0.04), 3)
        score = round(random.uniform(0.965, 0.994), 3)
        self.view.set_aligning(False)
        self.view.set_result(dx, dy, score)
        self.align_button.setEnabled(True)
        self.capture_button.setEnabled(True)
        self.result_chip.setText("已锁定")
        self.result_chip.setStyleSheet(
            f"background: {COLORS['accent']}16; border: 1px solid {COLORS['accent']}55;"
            f" color: {COLORS['accent']}; border-radius: 10px; padding: 3px 9px; font-size: 11px;"
        )
        self.info_dx.set(f"{dx:+.3f} mm")
        self.info_dy.set(f"{dy:+.3f} mm")
        self.info_theta.set(f"{theta:+.3f}°")
        self.info_score.set(f"{score * 100:.1f}%", COLORS["accent"])
        self.info_state.set(f"{fiducial.name} 对位锁定", COLORS["accent"])
        self.ctx.log("INFO", "VISION", f"{fiducial.name} 对位完成：dX={dx:+.3f} dY={dy:+.3f} score={score:.3f}")
        self.ctx.toast("视觉对位完成，补偿量已计算", "success")

    def _teach(self) -> None:
        product = self.ctx.current_product
        if not product or not product.fiducials:
            self.ctx.toast("当前产品未定义基准点", "warning")
            return
        head = self.ctx.head
        local_x = head[0] - product.board_origin_x_mm
        local_y = head[1] - product.board_origin_y_mm
        if not (0 <= local_x <= product.board_width_mm and 0 <= local_y <= product.board_height_mm):
            self.ctx.toast("请先将贴装头移动到板内基准点附近", "warning")
            return
        fiducial = product.fiducials[0]
        fiducial.x_mm = round(local_x, 2)
        fiducial.y_mm = round(local_y, 2)
        self.ctx.save_product(product)
        self._refresh_fiducials()
        self.ctx.log(
            "INFO",
            "VISION",
            f"示教基准点 {fiducial.name} 更新为 ({fiducial.x_mm:.2f}, {fiducial.y_mm:.2f})",
        )
        self.ctx.toast(f"{fiducial.name} 已示教并保存", "success")
