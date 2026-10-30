"""视觉对位页：仿真相机采集、基准点识别、板卡补偿与底部对中。

页面所有结果都来自真实算法（`midpnp/core/vision`），不再是随机数：
- 基准点识别：逐点移动相机 → 圆形对称检测 → 机器坐标换算（Y/角度取反）；
- 板卡补偿：多基准点最小二乘仿射 → 校验 → 存到产品 `alignment`；
- 底部对中：底部相机 → 元件矩形 → 中心/角度补偿。
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from ...core.models import MachineState, VisionMode
from ...core.vision import (
    Affine,
    BoardAlignResult,
    BoardAlignment,
    FiducialTolerances,
    Frame,
    PartAlignment,
    Point2,
    SimulatedCamera,
    align_board,
    align_part,
    measure_fiducials_by_capture,
)
from ..context import AppContext
from ..theme import COLORS
from ..widgets import Card, InfoRow, PageHeader, button, hline, make_chip


class CameraView(QWidget):
    """把 numpy 灰度图渲染到界面，并叠加检测结果。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(520, 380)
        self._frame: Frame | None = None
        self._detections: list[dict[str, Any]] = []
        self._hud: list[str] = []
        self._state_text = "等待采集"
        self._top_aligned = False

    def set_top_aligned(self, aligned: bool) -> None:
        self._top_aligned = bool(aligned)
        self.update()

    def set_frame(self, frame: Frame | None, detections: list[dict[str, Any]] | None = None) -> None:
        self._frame = frame
        self._detections = detections or []
        self.update()

    def set_hud(self, lines: list[str], state_text: str = "") -> None:
        self._hud = lines
        if state_text:
            self._state_text = state_text
        self.update()

    def paintEvent(self, event: Any) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.rect(), QColor("#080f0d"))
        if self._frame is None:
            painter.setPen(QColor(COLORS["faint"]))
            painter.setFont(QFont("Microsoft YaHei UI", 10))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "点击“采集图像”获取相机画面")
            painter.end()
            return
        image = np.asarray(self._frame.image, dtype=np.float32)
        if image.ndim == 3:
            image = image[..., :3].mean(axis=2)
        image = np.clip(image, 0.0, 1.0)
        height, width = image.shape
        buffer = (image * 255.0).astype(np.uint8)
        qimage = QImage(buffer.data, width, height, width, QImage.Format.Format_Grayscale8).copy()
        if self._top_aligned:
            # 相机卡片被拉高时，用暗化的填充图填满多余留白，避免大片纯黑
            backdrop = qimage.scaled(
                self.size(),
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            painter.setOpacity(0.22)
            painter.drawImage(QPointF(0, 0), backdrop)
            painter.setOpacity(1.0)
        scaled = qimage.scaled(
            self.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        offset_x = (self.width() - scaled.width()) / 2.0
        offset_y = 0.0 if self._top_aligned else (self.height() - scaled.height()) / 2.0
        painter.drawImage(QPointF(offset_x, offset_y), scaled)
        scale = scaled.width() / max(1, width)

        for detection in self._detections:
            color = QColor(detection.get("color", COLORS["accent"]))
            x = offset_x + float(detection.get("x", 0)) * scale
            y = offset_y + float(detection.get("y", 0)) * scale
            radius = max(6.0, float(detection.get("radius", 16)) * scale)
            painter.setPen(QPen(color, 1.6))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QPointF(x, y), radius, radius)
            painter.drawLine(QPointF(x - radius * 1.5, y), QPointF(x - radius * 1.2, y))
            painter.drawLine(QPointF(x + radius * 1.2, y), QPointF(x + radius * 1.5, y))
            painter.drawLine(QPointF(x, y - radius * 1.5), QPointF(x, y - radius * 1.2))
            painter.drawLine(QPointF(x, y + radius * 1.2), QPointF(x, y + radius * 1.5))
            if detection.get("label"):
                painter.setPen(QColor(color))
                painter.setFont(QFont("Cascadia Mono", 8))
                painter.drawText(QPointF(x + radius + 4, y - 4), str(detection["label"]))

        # 十字线（相机光轴）
        cx = offset_x + scaled.width() / 2.0
        cy = offset_y + scaled.height() / 2.0
        painter.setPen(QPen(QColor(255, 255, 255, 60), 1))
        painter.drawLine(QPointF(cx - 22, cy), QPointF(cx + 22, cy))
        painter.drawLine(QPointF(cx, cy - 22), QPointF(cx, cy + 22))

        painter.setFont(QFont("Cascadia Mono", 8))
        painter.setPen(QColor(COLORS["accent"]))
        y_text = offset_y + 16
        for line in self._hud:
            painter.drawText(QPointF(offset_x + 10, y_text), line)
            y_text += 13
        painter.setPen(QColor(COLORS["muted"]))
        painter.drawText(
            QRectF(offset_x, offset_y + scaled.height() - 24, scaled.width(), 18),
            Qt.AlignmentFlag.AlignCenter,
            self._state_text,
        )
        painter.setPen(QPen(QColor(COLORS["border"]), 1))
        painter.drawRect(QRectF(offset_x, offset_y, scaled.width(), scaled.height()))
        painter.end()


class VisionPage(QWidget):
    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self._frame: Frame | None = None
        self._align_result: BoardAlignResult | None = None
        self._part_alignment: PartAlignment | None = None
        self._build()
        self._connect()
        self._refresh_fiducials()

    # ---------------- UI ----------------

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(14)
        self.header = PageHeader("视觉对位", "基准点识别、板卡补偿与元件底部对中")
        self.camera_chip = make_chip("离线仿真")
        self.pipeline_chip = make_chip("—")
        self.capture_button = button("采集图像", "camera", "subtle")
        self.align_button = button("执行对位", "target", "primary")
        self.header.add_action(self.pipeline_chip)
        self.header.add_action(self.camera_chip)
        self.header.add_action(self.capture_button)
        self.header.add_action(self.align_button)
        outer.addWidget(self.header)

        content = QHBoxLayout()
        content.setSpacing(12)

        camera_card = Card(padding=12)
        top = QHBoxLayout()
        title = QLabel("相机画面")
        title.setProperty("role", "section")
        top.addWidget(title)
        self.camera_combo = QComboBox()
        self.camera_combo.setMinimumWidth(180)
        for camera in self.ctx.profile.cameras:
            self.camera_combo.addItem(f"{camera.id} · {camera.name}", camera.id)
        top.addWidget(self.camera_combo)
        top.addStretch(1)
        self.resolution_label = QLabel("")
        self.resolution_label.setProperty("role", "faint")
        top.addWidget(self.resolution_label)
        camera_card.body.addLayout(top)
        self.view = CameraView()
        camera_card.body.addWidget(self.view, 1)
        hint = QLabel(
            "仿真相机按机型配置的分辨率与像素当量（px/mm）渲染画面；算法链路与真实相机一致："
            "采集 → 预处理 → 特征检测 → 像素/机器坐标换算 → 仿射补偿。"
        )
        hint.setProperty("role", "hint")
        hint.setWordWrap(True)
        camera_card.body.addWidget(hint)
        content.addWidget(camera_card, 1)

        panel = QVBoxLayout()
        panel.setSpacing(12)

        control = Card()
        title_row = QHBoxLayout()
        title = QLabel("对位控制")
        title.setProperty("role", "section")
        title_row.addWidget(title)
        title_row.addStretch(1)
        self.mode_chip = make_chip("基准点")
        title_row.addWidget(self.mode_chip)
        control.body.addLayout(title_row)
        mode_row = QHBoxLayout()
        mode_label = QLabel("模式")
        mode_label.setProperty("role", "muted")
        self.mode = QComboBox()
        self.mode.addItem("基准点对位", "fiducial")
        self.mode.addItem("元件底部对中", "component")
        mode_row.addWidget(mode_label)
        mode_row.addStretch(1)
        mode_row.addWidget(self.mode)
        control.body.addLayout(mode_row)
        self.simulate_error = QCheckBox("仿真板卡偏移（0.35, -0.22 mm / 0.25°）")
        self.simulate_error.setChecked(True)
        control.body.addWidget(self.simulate_error)
        control.body.addWidget(hline())
        self.component_combo = QComboBox()
        self.component_combo.setMinimumWidth(200)
        component_row = QHBoxLayout()
        component_label = QLabel("对中元件")
        component_label.setProperty("role", "muted")
        component_row.addWidget(component_label)
        component_row.addStretch(1)
        component_row.addWidget(self.component_combo)
        control.body.addLayout(component_row)
        self.bottom_button = button("执行底部对中", "camera", "subtle")
        control.body.addWidget(self.bottom_button)
        panel.addWidget(control)

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
        self.info_score = InfoRow("残差 RMS", "—")
        self.info_state = InfoRow("状态", "未对位")
        for row in (self.info_dx, self.info_dy, self.info_theta, self.info_score, self.info_state):
            result.body.addWidget(row)
        result.body.addWidget(hline())
        self.apply_button = button("应用补偿到产品", "save", "subtle")
        self.clear_button = button("清除补偿", "trash", "subtle")
        result.body.addWidget(self.apply_button)
        result.body.addWidget(self.clear_button)
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
        self.compensation_label = QLabel("未应用视觉补偿")
        self.compensation_label.setProperty("role", "faint")
        self.compensation_label.setWordWrap(True)
        fiducial.body.addWidget(self.compensation_label)
        panel.addWidget(fiducial)
        panel.addStretch(1)
        content.addLayout(panel, 0)
        outer.addLayout(content, 1)

        self.capture_button.clicked.connect(self._capture)
        self.align_button.clicked.connect(self._align)
        self.bottom_button.clicked.connect(self._align_part)
        self.apply_button.clicked.connect(self._apply_alignment)
        self.clear_button.clicked.connect(self._clear_alignment)
        self.mode.currentIndexChanged.connect(self._on_mode_changed)
        self.camera_combo.currentIndexChanged.connect(self._on_camera_changed)
        self._on_mode_changed()
        self._on_camera_changed()

    def _connect(self) -> None:
        self.ctx.signals.product_changed.connect(lambda *_: self._refresh_fiducials())
        self.ctx.signals.profile_changed.connect(self._on_profile_changed)
        self.ctx.signals.settings_changed.connect(self._on_profile_changed)
        for component in self.ctx.components():
            self.component_combo.addItem(f"{component.name} · {component.package}", component.id)

    # ---------------- 状态 ----------------

    def _camera_config(self) -> Any:
        camera_id = str(self.camera_combo.currentData() or "")
        return self.ctx.profile.camera(camera_id)

    def _camera(self) -> SimulatedCamera:
        config = self._camera_config()
        if config is None:
            raise ValueError("机型没有配置相机")
        return SimulatedCamera(config)

    def _on_camera_changed(self, *_: object) -> None:
        config = self._camera_config()
        if config is None:
            return
        self.resolution_label.setText(
            f"{config.resolution[0]}×{config.resolution[1]} · {config.pixels_per_mm:.1f} px/mm · "
            f"视场 {config.resolution[0] / config.pixels_per_mm:.0f}×{config.resolution[1] / config.pixels_per_mm:.0f} mm"
        )
        self.pipeline_chip.setText(config.pipeline)
        pipeline = self.ctx.vision_pipeline(config.pipeline)
        self.view.set_hud(
            [
                f"{config.id}  SIMULATED  ·  {config.resolution[0]}x{config.resolution[1]}  ·  {config.pixels_per_mm:.1f} px/mm",
                "pipeline: " + " → ".join(stage.NAME for stage in pipeline.stages),
            ],
            "等待采集",
        )

    def _on_mode_changed(self, *_: object) -> None:
        mode = str(self.mode.currentData())
        is_component = mode == "component"
        self.mode_chip.setText("底部对中" if is_component else "基准点")
        self.component_combo.setVisible(is_component)
        self.bottom_button.setVisible(is_component)
        self.simulate_error.setVisible(not is_component)

    def _on_profile_changed(self, *_: object) -> None:
        self.camera_combo.blockSignals(True)
        self.camera_combo.clear()
        for camera in self.ctx.profile.cameras:
            self.camera_combo.addItem(f"{camera.id} · {camera.name}", camera.id)
        self.camera_combo.blockSignals(False)
        self._on_camera_changed()
        self._refresh_fiducials()
        self.compensation_label.setText(self._compensation_text())

    # ---------------- 采集 ----------------

    def _head_center(self) -> Point2:
        return Point2(float(self.ctx.head[0]), float(self.ctx.head[1]))

    def _capture(self) -> None:
        camera = self._camera()
        config = self._camera_config()
        center = self._head_center()
        product = self.ctx.current_product
        if config.mount == "fixed" and config.location.x:
            center = Point2(config.location.x, config.location.y)
        elif abs(center.x) < 1e-6 and abs(center.y) < 1e-6 and product is not None:
            # 头在原点时给一个整板视野，避免新机开局是一片黑
            center = Point2(
                product.board_origin_x_mm + product.board_width_mm / 2.0,
                product.board_origin_y_mm + product.board_height_mm / 2.0,
            )
        ppm = None
        if product is not None and abs(self.ctx.head[0]) < 1e-6 and abs(self.ctx.head[1]) < 1e-6:
            ppm = self._overview_ppm(product, config)
        frame = camera.capture_board(
            center,
            product=product,
            components=self.ctx.components(),
            packages=self.ctx.package_map(),
            alignment=self._demo_alignment(product) if self.simulate_error.isChecked() else None,
            pixels_per_mm=ppm,
        )
        self._frame = frame
        self.view.set_frame(frame, [])
        self.view.set_hud(
            [
                f"{config.id}  {config.resolution[0]}x{config.resolution[1]}  ·  {config.pixels_per_mm:.1f} px/mm",
                f"center {center.x:.2f}, {center.y:.2f} mm",
                "pipeline: " + " → ".join(stage.NAME for stage in self.ctx.vision_pipeline(config.pipeline).stages),
            ],
            "图像已采集",
        )
        self.result_chip.setText("已采集")
        self.info_state.set("图像已采集", COLORS["accent"])
        self.ctx.log("INFO", "VISION", f"{config.id} 采集一帧（{config.resolution[0]}×{config.resolution[1]}）")

    def _overview_ppm(self, product: Any, config: Any) -> float:
        """把整块板框（含 12% 边距）塞进一帧所需的像素当量。"""
        width = max(1.0, float(product.board_width_mm) * 1.12)
        height = max(1.0, float(product.board_height_mm) * 1.12)
        return min(config.resolution[0] / width, config.resolution[1] / height)

    def _demo_alignment(self, product: Any) -> BoardAlignment | None:
        if product is None:
            return None
        angle = math.radians(0.25)
        transform = Affine(
            a=math.cos(angle),
            b=-math.sin(angle),
            c=math.sin(angle),
            d=math.cos(angle),
            e=product.board_origin_x_mm + 0.35,
            f=product.board_origin_y_mm - 0.22,
        )
        return BoardAlignment(transform=transform)

    # ---------------- 基准点对位 ----------------

    def _align(self) -> None:
        product = self.ctx.current_product
        if product is None:
            self.ctx.toast("请先选择产品", "warning")
            return
        if not product.fiducials:
            self.ctx.toast("当前产品未定义基准点", "warning")
            return
        camera_config = self._camera_config()
        if camera_config is None:
            self.ctx.toast("机型未配置相机", "warning")
            return
        camera = self._camera()
        demo = self._demo_alignment(product) if self.simulate_error.isChecked() else None
        components = self.ctx.components()
        packages = self.ctx.package_map()

        def capture(center: Point2) -> Frame:
            return camera.capture_board(
                center,
                product=product,
                components=components,
                packages=packages,
                alignment=demo,
            )

        pipeline = self.ctx.vision_pipeline(camera_config.pipeline)
        params = self.ctx.profile.vision.fiducial
        tolerance = FiducialTolerances(
            scaling=0.05,
            shearing=0.05,
            translation_mm=max(5.0, params.search_radius_mm),
        )
        self.result_chip.setText("计算中")
        self.info_state.set("正在搜索基准点…", COLORS["warn"])
        measurements = measure_fiducials_by_capture(
            product,
            capture,
            pipeline,
            search_radius_mm=params.search_radius_mm,
            min_score=params.min_score,
        )
        result = align_board(measurements, side="Top", tolerances=tolerance)
        self._align_result = result
        self._render_alignment(measurements, result, camera_config)

    def _render_alignment(self, measurements: list[Any], result: BoardAlignResult, camera_config: Any) -> None:
        detections: list[dict[str, Any]] = []
        frame = None
        product = self.ctx.current_product
        if product is not None:
            # 整板预览：临时降低像素当量，把整块板框放进一帧里
            camera = self._camera()
            ppm = self._overview_ppm(product, camera_config)
            center = Point2(
                product.board_origin_x_mm + product.board_width_mm / 2.0,
                product.board_origin_y_mm + product.board_height_mm / 2.0,
            )
            frame = camera.capture_board(
                center,
                product=product,
                components=self.ctx.components(),
                packages=self.ctx.package_map(),
                alignment=self._demo_alignment(product) if self.simulate_error.isChecked() else None,
                pixels_per_mm=ppm,
            )
            calibration = frame.calibration
            for measurement in measurements:
                if not measurement.found:
                    continue
                offset_x = measurement.measured.x - center.x
                offset_y = measurement.measured.y - center.y
                detections.append(
                    {
                        "x": calibration.mm_to_pixel(offset_x, offset_y)[0],
                        "y": calibration.mm_to_pixel(offset_x, offset_y)[1],
                        "radius": calibration.mm_to_pixel_size(measurement.diameter_mm or 2.4) / 2,
                        "label": measurement.name,
                        "color": COLORS["accent"] if result.ok else COLORS["danger"],
                    }
                )
        if frame is not None:
            self._frame = frame
            self.view.set_frame(frame, detections)
        self.view.set_hud(
            [
                f"{camera_config.id}  {camera_config.resolution[0]}x{camera_config.resolution[1]}  ·  整板预览",
                f"pixels_per_mm {frame.calibration.pixels_per_mm:.2f}（预览缩放）"
                if frame is not None
                else "",
                "pipeline: " + " → ".join(stage.NAME for stage in self.ctx.vision_pipeline(camera_config.pipeline).stages),
            ],
            result.summary(),
        )

        found = [item for item in measurements if item.found]
        if result.ok and result.alignment is not None:
            alignment = result.alignment
            self.result_chip.setText("已锁定")
            self._set_chip(self.result_chip, COLORS["accent"])
            self.info_dx.set(f"{alignment.dx_mm - (product.board_origin_x_mm if product else 0):+.3f} mm")
            self.info_dy.set(f"{alignment.dy_mm - (product.board_origin_y_mm if product else 0):+.3f} mm")
            self.info_theta.set(f"{alignment.theta_deg:+.3f}°")
            self.info_score.set(f"RMS {alignment.rms_mm:.3f} mm", COLORS["accent"])
            self.info_state.set(f"{len(found)} 点对齐完成", COLORS["accent"])
            self.ctx.log(
                "INFO",
                "VISION",
                f"板卡对位完成：θ {alignment.theta_deg:+.3f}° · "
                f"原点 ({alignment.dx_mm:.3f}, {alignment.dy_mm:.3f}) · RMS {alignment.rms_mm:.3f} mm",
            )
            self.ctx.toast("视觉对位完成，可应用补偿", "success")
        else:
            self.result_chip.setText("失败")
            self._set_chip(self.result_chip, COLORS["danger"])
            self.info_state.set("；".join(result.problems) or "未识别到基准点", COLORS["danger"])
            self.info_score.set("—")
            self.ctx.log("WARN", "VISION", "板卡对位失败：" + "；".join(result.problems))
            self.ctx.toast("对位失败：" + ("；".join(result.problems) or "未识别到基准点"), "error")
        self._refresh_fiducials(measurements)

    # ---------------- 底部对中 ----------------

    def _align_part(self) -> None:
        component_id = str(self.component_combo.currentData() or "")
        components = {component.id: component for component in self.ctx.components()}
        component = components.get(component_id)
        if component is None:
            self.ctx.toast("元件库为空，无法对中", "warning")
            return
        bottom = self.ctx.bottom_camera()
        if bottom is None:
            self.ctx.toast("机型未配置底部相机", "warning")
            return
        camera = SimulatedCamera(bottom, seed=31)
        frame = camera.capture_part(
            component,
            offset_mm=(0.12, -0.08),
            angle_deg=1.2,
            tip_diameter_mm=0.6,
        )
        pipeline = self.ctx.vision_pipeline(bottom.pipeline)
        alignment = align_part(frame, pipeline, self.ctx.profile.vision.bottom, component=component)
        self._part_alignment = alignment
        detections = []
        if alignment.passed or alignment.width_mm:
            calibration = frame.calibration
            detections.append(
                {
                    "x": calibration.width / 2 + calibration.mm_to_pixel_size(alignment.dx_mm),
                    "y": calibration.height / 2 - calibration.mm_to_pixel_size(alignment.dy_mm),
                    "radius": calibration.mm_to_pixel_size(max(alignment.width_mm, alignment.height_mm)) / 2,
                    "label": component.name,
                    "color": COLORS["accent"] if alignment.passed else COLORS["danger"],
                }
            )
        self._frame = frame
        self.view.set_frame(frame, detections)
        self.view.set_hud(
            [
                f"{bottom.id}  {bottom.resolution[0]}x{bottom.resolution[1]}  ·  {bottom.pixels_per_mm:.1f} px/mm",
                "pipeline: " + " → ".join(stage.NAME for stage in pipeline.stages),
                f"part {alignment.width_mm:.2f} × {alignment.height_mm:.2f} mm",
            ],
            alignment.message,
        )
        self.result_chip.setText("通过" if alignment.passed else "超差")
        self._set_chip(self.result_chip, COLORS["accent"] if alignment.passed else COLORS["danger"])
        self.info_dx.set(f"{alignment.dx_mm:+.3f} mm", COLORS["accent"] if alignment.passed else None)
        self.info_dy.set(f"{alignment.dy_mm:+.3f} mm")
        self.info_theta.set(f"{alignment.theta_deg:+.3f}°")
        self.info_score.set(f"{alignment.score:.0%}")
        self.info_state.set(alignment.message, COLORS["accent"] if alignment.passed else COLORS["danger"])
        self.ctx.log(
            "INFO" if alignment.passed else "WARN",
            "VISION",
            f"底部对中 {component.name}：dX {alignment.dx_mm:+.3f} dY {alignment.dy_mm:+.3f} "
            f"θ {alignment.theta_deg:+.3f}° · {alignment.message}",
        )
        self.ctx.toast(
            "底部对中通过" if alignment.passed else f"底部对中失败：{alignment.message}",
            "success" if alignment.passed else "error",
        )

    # ---------------- 补偿 ----------------

    def _apply_alignment(self) -> None:
        product = self.ctx.current_product
        if product is None:
            return
        result = self._align_result
        if result is None or result.alignment is None or not result.ok:
            self.ctx.toast("请先完成一次成功的基准点对位", "warning")
            return
        product.alignment = result.alignment.to_dict()
        self.ctx.save_product(product)
        self._refresh_fiducials()
        self.ctx.toast("补偿已应用到产品，后续规划按补偿后坐标执行", "success")
        self.ctx.log(
            "INFO",
            "VISION",
            f"应用板卡补偿：θ {result.alignment.theta_deg:+.3f}° · RMS {result.alignment.rms_mm:.3f} mm",
        )

    def _clear_alignment(self) -> None:
        product = self.ctx.current_product
        if product is None or not product.alignment:
            self.ctx.toast("当前产品没有视觉补偿", "info")
            return
        product.alignment = None
        self.ctx.save_product(product)
        self._refresh_fiducials()
        self.ctx.toast("已清除视觉补偿", "info")

    def _compensation_text(self) -> str:
        product = self.ctx.current_product
        alignment = BoardAlignment.from_dict(product.alignment) if product and product.alignment else None
        if alignment is None:
            return "未应用视觉补偿"
        return (
            f"已应用补偿：θ {alignment.theta_deg:+.3f}° · "
            f"原点 ({alignment.dx_mm:.3f}, {alignment.dy_mm:.3f}) mm"
        )

    # ---------------- 基准点列表 ----------------

    def _refresh_fiducials(self, measurements: list[Any] | None = None) -> None:
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
        else:
            measurement_map = {item.name: item for item in measurements or []}
            for fiducial in fiducials:
                row = QWidget()
                layout = QHBoxLayout(row)
                layout.setContentsMargins(4, 3, 4, 3)
                measurement = measurement_map.get(fiducial.name)
                marker = QLabel("◎")
                found = bool(measurement and measurement.found)
                color = COLORS["accent"] if found else (COLORS["danger"] if measurement else COLORS["warn"])
                marker.setStyleSheet(f"color: {color}; font-size: 16px;")
                name = QLabel(fiducial.name)
                name.setStyleSheet("font-family: 'Cascadia Mono';")
                coords = QLabel(f"{fiducial.x_mm:.1f}, {fiducial.y_mm:.1f}")
                coords.setProperty("role", "faint")
                layout.addWidget(marker)
                layout.addWidget(name)
                layout.addStretch(1)
                if measurement is not None:
                    detail = QLabel(
                        f"{measurement.score:.0%} · Δ{measurement.error_mm:.2f} mm"
                        if measurement.found
                        else (measurement.reason or "未识别")
                    )
                    detail.setProperty("role", "faint")
                    layout.addWidget(detail)
                layout.addWidget(coords)
                self.fid_container.addWidget(row)
        self.compensation_label.setText(self._compensation_text())

    def _set_chip(self, chip: QLabel, color: str) -> None:
        chip.setStyleSheet(
            f"background: {color}16; border: 1px solid {color}55; color: {color};"
            "border-radius: 10px; padding: 3px 9px; font-size: 11px;"
        )
