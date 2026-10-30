"""设备选择画廊：首次启动向导 + 机型配置里的图形化切换。

交互参考拓竹（Bambu Lab）的打印机选择页：一屏卡片、点击预览、双击即用；
首次打开软件时先选设备，之后从「系统设置 → 机型配置」随时打开同一个画廊。
"""

from __future__ import annotations

import math
from typing import Any

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..core.profiles import (
    MachineProfile,
    ProfileError,
    user_profiles_dir,
)
from .assets import asset_path
from .context import AppContext
from .theme import COLORS
from .widgets import StatusDot, button, hline, make_chip


DRIVER_LABELS = {
    "simulator": "内置模拟器",
    "jsonl-tcp": "JSONL · TCP",
    "jsonl-serial": "JSONL · 串口",
    "gcode-tcp": "G-code · TCP",
    "gcode-serial": "G-code · 串口",
}


def _driver_label(profile: MachineProfile) -> str:
    return DRIVER_LABELS.get(profile.driver.type, profile.driver.type)


def _accent(profile: MachineProfile) -> str:
    if profile.driver.type == "simulator":
        return COLORS["accent"]
    if profile.driver.type.startswith("gcode"):
        return COLORS["warn"]
    return "#4db8d8"


_PIXMAP_CACHE: dict[str, QPixmap] = {}


def machine_pixmap(profile: MachineProfile | None) -> QPixmap | None:
    """加载机型配置里的设备照片；缺失时返回 None（退回矢量示意图）。"""
    if profile is None or not profile.image:
        return None
    path = asset_path(profile.image)
    if not path.exists():
        return None
    key = str(path)
    if key not in _PIXMAP_CACHE:
        _PIXMAP_CACHE[key] = QPixmap(key)
    pixmap = _PIXMAP_CACHE[key]
    return None if pixmap.isNull() else pixmap


class MachineArt(QWidget):
    """用 QPainter 画的机型示意图，避免依赖外部图片资源。"""

    def __init__(self, profile: MachineProfile | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._profile = profile
        self.setMinimumHeight(96)

    def set_profile(self, profile: MachineProfile | None) -> None:
        self._profile = profile
        self.update()

    def paintEvent(self, event: Any) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        width, height = self.width(), self.height()
        rect = QRectF(0.5, 0.5, width - 1, height - 1)

        gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
        gradient.setColorAt(0.0, QColor("#0b151b"))
        gradient.setColorAt(1.0, QColor("#0e1c23"))
        painter.setPen(QPen(QColor(COLORS["border_soft"]), 1))
        painter.setBrush(gradient)
        painter.drawRoundedRect(rect, 8, 8)

        # 网格背景
        painter.setPen(QPen(QColor(255, 255, 255, 8), 1))
        step = max(18, int(width / 14))
        for x in range(step, width, step):
            painter.drawLine(QPointF(x, 2), QPointF(x, height - 2))
        for y in range(step, height, step):
            painter.drawLine(QPointF(2, y), QPointF(width - 2, y))

        profile = self._profile
        if profile is None:
            painter.setPen(QColor(COLORS["faint"]))
            painter.setFont(QFont("Microsoft YaHei UI", 9))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "未选择机型")
            painter.end()
            return

        pixmap = machine_pixmap(profile)
        if pixmap is not None:
            painter.save()
            clip = QPainterPath()
            clip.addRoundedRect(rect.adjusted(1, 1, -1, -1), 7, 7)
            painter.setClipPath(clip)
            scaled = pixmap.scaled(
                max(1, int(width - 10)),
                max(1, int(height - 8)),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            painter.drawPixmap(
                int((width - scaled.width()) / 2),
                int((height - scaled.height()) / 2),
                scaled,
            )
            painter.restore()
            painter.end()
            return

        accent = QColor(_accent(profile))
        accent.setAlpha(210)
        limits = profile.limits()
        ratio = limits.travel_x_mm / max(1.0, limits.travel_y_mm)
        bed_ratio = max(0.30, min(0.58, 0.26 + 0.12 * ratio))

        margin_x = width * 0.10
        base_y = height * 0.80
        base_h = height * 0.10
        bed_w = width * bed_ratio
        bed_h = bed_w * 0.62
        bed_x = width * 0.5 - bed_w * 0.62
        bed_y = height * 0.50

        # 底座
        painter.setPen(QPen(QColor("#2a4350"), 1))
        painter.setBrush(QColor("#16262e"))
        painter.drawRoundedRect(QRectF(margin_x, base_y, width - margin_x * 2, base_h), 4, 4)

        # 导轨
        painter.setPen(QPen(QColor("#33505d"), 2))
        painter.drawLine(QPointF(margin_x + 6, base_y + 1), QPointF(width - margin_x - 6, base_y + 1))
        painter.drawLine(
            QPointF(margin_x + 6, base_y + base_h - 2), QPointF(width - margin_x - 6, base_y + base_h - 2)
        )

        # 台面（PCB 绿）
        painter.setPen(QPen(QColor("#2c6a4d"), 1))
        painter.setBrush(QColor("#12382a"))
        painter.drawRoundedRect(QRectF(bed_x, bed_y, bed_w, bed_h), 4, 4)
        painter.setPen(QPen(QColor("#3e8a63"), 1, Qt.PenStyle.DotLine))
        painter.drawRect(QRectF(bed_x + 4, bed_y + 4, bed_w - 8, bed_h - 8))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#5f8f74"))
        for index in range(6):
            px = bed_x + bed_w * (0.18 + index * 0.13)
            py = bed_y + bed_h * (0.32 if index % 2 == 0 else 0.62)
            painter.drawRect(QRectF(px, py, max(3.0, bed_w * 0.035), max(2.0, bed_h * 0.06)))

        # 龙门
        beam_x = bed_x + bed_w * 0.62
        painter.setPen(QPen(QColor("#3a5663"), 1))
        painter.setBrush(QColor("#1d333d"))
        painter.drawRoundedRect(QRectF(beam_x - width * 0.016, height * 0.16, width * 0.032, base_y - height * 0.16), 3, 3)

        # 贴装头（多头时并排画多个）
        heads = max(1, len(profile.heads))
        carriage_w = max(14.0, width * 0.085)
        gap = carriage_w * 0.55
        total = heads * carriage_w + (heads - 1) * gap
        start_x = beam_x - total / 2 + carriage_w / 2
        for index in range(heads):
            cx = start_x + index * (carriage_w + gap)
            painter.setPen(QPen(QColor("#3a5663"), 1))
            painter.setBrush(QColor("#243f4b"))
            painter.drawRoundedRect(QRectF(cx - carriage_w / 2, height * 0.21, carriage_w, height * 0.11), 3, 3)
            # 吸嘴
            nozzle_count = max(1, len(profile.heads[index].nozzles))
            painter.setPen(QPen(QColor("#9fb6c2"), 1.4))
            offset = (nozzle_count - 1) * 4.0
            for nozzle in range(nozzle_count):
                nx = cx - offset / 2 + nozzle * 4.0
                painter.drawLine(QPointF(nx, height * 0.32), QPointF(nx, height * 0.40))
                painter.setBrush(QColor("#c9d6dc"))
                painter.drawEllipse(QPointF(nx, height * 0.41), 1.8, 1.8)
            # 相机（随头）
            painter.setPen(QPen(QColor("#0d1a20"), 1))
            painter.setBrush(QColor(accent))
            painter.drawEllipse(QPointF(cx + carriage_w * 0.58, height * 0.245), 2.6, 2.6)

        # 供料器（左侧料盘）
        reel_radius = min(13.0, width * 0.055)
        for index in range(min(3, max(1, profile.feeders.slot_count // 16))):
            cx = margin_x + reel_radius + index * (reel_radius * 2.1)
            cy = height * 0.22
            painter.setPen(QPen(QColor("#3a5663"), 1))
            painter.setBrush(QColor("#1b2d35"))
            painter.drawEllipse(QPointF(cx, cy), reel_radius, reel_radius)
            painter.setPen(QPen(QColor(accent.red(), accent.green(), accent.blue(), 120), 1))
            painter.drawEllipse(QPointF(cx, cy), reel_radius * 0.45, reel_radius * 0.45)

        # 台面高亮
        painter.setPen(QPen(QColor(accent.red(), accent.green(), accent.blue(), 140), 1.2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawLine(QPointF(bed_x, base_y - 3), QPointF(bed_x + bed_w, base_y - 3))
        painter.end()


class MachineCard(QFrame):
    """一张机型卡片：示意图 + 名称 + 规格 + 徽章。"""

    clicked = Signal(object)
    activated = Signal(object)

    def __init__(self, profile: MachineProfile, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.profile = profile
        self._selected = False
        self.setObjectName("machineCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedWidth(240)
        self.setStyleSheet(
            f"""
            QFrame#machineCard {{
                background: #0c161c;
                border: 1px solid {COLORS['border_soft']};
                border-radius: 12px;
            }}
            QFrame#machineCard:hover {{
                border: 1px solid {COLORS['border']};
                background: #0f1d25;
            }}
            QFrame#machineCard[selected="true"] {{
                border: 2px solid {_accent(profile)};
                background: #0f2129;
            }}
            """
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        self.art = MachineArt(profile)
        self.art.setFixedHeight(112)
        layout.addWidget(self.art)

        name_row = QHBoxLayout()
        name_row.setSpacing(6)
        name = QLabel(profile.name)
        name.setWordWrap(True)
        name.setFixedHeight(34)
        name.setStyleSheet("font-size: 13px; font-weight: 700;")
        name.setToolTip(profile.name)
        name_row.addWidget(name, 1)
        badge = QLabel("内置" if profile.builtin else "自定义")
        badge.setStyleSheet(
            f"color: {COLORS['muted'] if profile.builtin else _accent(profile)};"
            f" border: 1px solid {COLORS['border']}; border-radius: 7px;"
            " padding: 1px 6px; font-size: 9px;"
        )
        name_row.addWidget(badge, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(name_row)

        limits = profile.limits()
        spec = QLabel(
            f"{limits.travel_x_mm:.0f} × {limits.travel_y_mm:.0f} × {limits.travel_z_mm:.0f} mm"
            f" · {len(profile.nozzle_ids())} 吸嘴"
        )
        spec.setProperty("role", "mono")
        spec.setStyleSheet("font-size: 11px;")
        layout.addWidget(spec)
        meta = QLabel(
            f"{len(profile.heads)} 头 · {profile.feeders.slot_count} 料站 · "
            f"{len([c for c in profile.cameras if c.enabled])} 相机 · {_driver_label(profile)}"
        )
        meta.setProperty("role", "faint")
        meta.setStyleSheet("font-size: 10px;")
        layout.addWidget(meta)

        tags = " · ".join(profile.tags[:3])
        if tags:
            tag_label = QLabel(tags)
            tag_label.setProperty("role", "faint")
            tag_label.setStyleSheet("font-size: 9px; letter-spacing: 0.4px;")
            layout.addWidget(tag_label)
        layout.addStretch(1)

    @property
    def selected(self) -> bool:
        return self._selected

    def set_selected(self, selected: bool) -> None:
        if self._selected == selected:
            return
        self._selected = selected
        self.setProperty("selected", "true" if selected else "false")
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def mousePressEvent(self, event: Any) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.profile)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event: Any) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.activated.emit(self.profile)
        super().mouseDoubleClickEvent(event)


class MachineGalleryDialog(QDialog):
    """设备画廊。`first_run=True` 时作为首次启动向导。"""

    def __init__(
        self,
        ctx: AppContext,
        first_run: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.first_run = first_run
        self.selected_profile: MachineProfile | None = None
        self._cards: dict[str, MachineCard] = {}
        self._filter = "all"
        self.setWindowTitle("选择设备" if first_run else "机型配置")
        self.setModal(True)
        self.resize(1200, 820)
        self.setMinimumSize(1060, 720)
        self._build()
        self._refresh()
        self._select(ctx.profile)

    # ---------------- UI ----------------

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(26, 22, 26, 18)
        root.setSpacing(14)

        title = QLabel("选择你的设备" if self.first_run else "更换 / 添加设备")
        title.setProperty("role", "dialogTitle")
        root.addWidget(title)
        subtitle = QLabel(
            "首次使用请选择机型；不同机型对应不同的行程、吸嘴、相机与驱动配置。"
            if self.first_run
            else "选择机型后会按新配置重新连接；也可以导入同事或厂商给的配置文件。"
        )
        subtitle.setProperty("role", "muted")
        subtitle.setWordWrap(True)
        root.addWidget(subtitle)
        root.addWidget(hline())

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        self.filter_buttons: dict[str, QPushButton] = {}
        for key, text in (("all", "全部"), ("builtin", "内置模板"), ("custom", "我的设备")):
            chip = QPushButton(text)
            chip.setCheckable(True)
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.setProperty("variant", "subtle")
            chip.setFixedHeight(28)
            chip.clicked.connect(lambda checked=False, name=key: self._set_filter(name))
            toolbar.addWidget(chip)
            self.filter_buttons[key] = chip
        self.filter_buttons["all"].setChecked(True)
        toolbar.addStretch(1)
        self.import_button = button("导入配置…", "upload", "subtle", height=30)
        self.import_button.setToolTip("导入他人提供的机型 JSON")
        self.import_button.clicked.connect(self._import_profile)
        toolbar.addWidget(self.import_button)
        root.addLayout(toolbar)

        body = QHBoxLayout()
        body.setSpacing(16)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.container = QWidget()
        self.grid = QGridLayout(self.container)
        self.grid.setContentsMargins(0, 0, 6, 0)
        self.grid.setHorizontalSpacing(14)
        self.grid.setVerticalSpacing(14)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.scroll.setWidget(self.container)
        body.addWidget(self.scroll, 1)

        self.detail = QFrame()
        self.detail.setObjectName("galleryDetail")
        self.detail.setFixedWidth(330)
        self.detail.setStyleSheet(
            f"QFrame#galleryDetail {{ background: #0c161c; border: 1px solid {COLORS['border_soft']};"
            " border-radius: 12px; }"
        )
        detail_layout = QVBoxLayout(self.detail)
        detail_layout.setContentsMargins(16, 16, 16, 16)
        detail_layout.setSpacing(8)

        self.detail_art = MachineArt()
        self.detail_art.setFixedHeight(100)
        detail_layout.addWidget(self.detail_art)
        self.detail_name = QLabel("—")
        self.detail_name.setStyleSheet("font-size: 17px; font-weight: 800;")
        detail_layout.addWidget(self.detail_name)
        self.detail_vendor = QLabel("")
        self.detail_vendor.setProperty("role", "faint")
        detail_layout.addWidget(self.detail_vendor)
        self.detail_desc = QLabel("")
        self.detail_desc.setProperty("role", "muted")
        self.detail_desc.setWordWrap(True)
        self.detail_desc.setMinimumHeight(40)
        self.detail_desc.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        detail_layout.addWidget(self.detail_desc)
        detail_layout.addWidget(hline())

        self.specs: dict[str, QLabel] = {}
        for key, label_text in (
            ("axes", "行程"),
            ("heads", "贴装头 / 吸嘴"),
            ("cameras", "相机"),
            ("feeders", "料站"),
            ("driver", "驱动"),
            ("vision", "视觉流水线"),
        ):
            row = QHBoxLayout()
            label = QLabel(label_text)
            label.setProperty("role", "muted")
            value = QLabel("—")
            value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            value.setWordWrap(True)
            row.addWidget(label)
            row.addStretch(1)
            row.addWidget(value, 1)
            detail_layout.addLayout(row)
            self.specs[key] = value
        self.detail_issues = QLabel("")
        self.detail_issues.setWordWrap(True)
        self.detail_issues.setStyleSheet("font-size: 11px;")
        detail_layout.addWidget(self.detail_issues)
        detail_layout.addStretch(1)

        actions = QVBoxLayout()
        actions.setSpacing(6)
        action_grid = QGridLayout()
        action_grid.setHorizontalSpacing(6)
        action_grid.setVerticalSpacing(6)
        self.duplicate_button = button("另存为副本", "layers", "subtle", height=30)
        self.export_button = button("导出配置", "download", "subtle", height=30)
        self.delete_button = button("删除设备", "trash", "subtle", height=30)
        self.open_dir_button = button("配置目录", "folder", "subtle", height=30)
        action_grid.addWidget(self.duplicate_button, 0, 0)
        action_grid.addWidget(self.export_button, 0, 1)
        action_grid.addWidget(self.delete_button, 1, 0)
        action_grid.addWidget(self.open_dir_button, 1, 1)
        actions.addLayout(action_grid)
        detail_layout.addLayout(actions)
        self.duplicate_button.clicked.connect(self._duplicate_profile)
        self.export_button.clicked.connect(self._export_profile)
        self.delete_button.clicked.connect(self._delete_profile)
        self.open_dir_button.clicked.connect(self._open_profile_dir)
        body.addWidget(self.detail)
        root.addLayout(body, 1)

        footer = QHBoxLayout()
        footer.setSpacing(8)
        hint = QLabel("双击卡片可直接使用；机型配置保存在数据目录 profiles/ 下。")
        hint.setProperty("role", "faint")
        footer.addWidget(hint)
        footer.addStretch(1)
        self.cancel_button = button("稍后再说" if self.first_run else "取消", variant="subtle")
        self.cancel_button.clicked.connect(self.reject)
        footer.addWidget(self.cancel_button)
        self.confirm_button = button("开始使用" if self.first_run else "使用此机型", "check", "primary")
        self.confirm_button.clicked.connect(self._confirm)
        footer.addWidget(self.confirm_button)
        root.addLayout(footer)

    # ---------------- 列表 ----------------

    def _set_filter(self, name: str) -> None:
        self._filter = name
        for key, chip in self.filter_buttons.items():
            chip.setChecked(key == name)
        self._refresh()

    def _refresh(self) -> None:
        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._cards = {}
        profiles = self.ctx.profile_library.list()
        if self._filter == "builtin":
            profiles = [profile for profile in profiles if profile.builtin]
        elif self._filter == "custom":
            profiles = [profile for profile in profiles if not profile.builtin]
        columns = 3
        for index, profile in enumerate(profiles):
            card = MachineCard(profile)
            card.clicked.connect(self._select)
            card.activated.connect(self._activate)
            self.grid.addWidget(card, index // columns, index % columns)
            self._cards[profile.id] = card
        if not profiles:
            empty = QLabel("还没有自定义机型。点上方「导入配置…」添加，或先另存一份内置模板。")
            empty.setProperty("role", "hint")
            empty.setWordWrap(True)
            self.grid.addWidget(empty, 0, 0, 1, columns)

    def _select(self, profile: MachineProfile | None) -> None:
        if profile is None:
            return
        self.selected_profile = profile
        for profile_id, card in self._cards.items():
            card.set_selected(profile_id == profile.id)
        self._show_detail(profile)

    def _show_detail(self, profile: MachineProfile) -> None:
        self.detail_art.set_profile(profile)
        self.detail_name.setText(profile.name)
        vendor = profile.vendor or "—"
        self.detail_vendor.setText(f"{vendor} · {'内置模板' if profile.builtin else '我的设备'}")
        self.detail_desc.setText(profile.description or "（无描述）")
        limits = profile.limits()
        self.specs["axes"].setText(
            f"{limits.travel_x_mm:.0f} × {limits.travel_y_mm:.0f} × {limits.travel_z_mm:.0f} mm"
        )
        self.specs["heads"].setText(f"{len(profile.heads)} 头 / {'、'.join(profile.nozzle_ids())}")
        self.specs["cameras"].setText(
            "、".join(camera.id for camera in profile.cameras) or "—"
        )
        self.specs["feeders"].setText(f"{profile.feeders.slot_count} 个 · 间距 {profile.feeders.slot_pitch_mm:g} mm")
        self.specs["driver"].setText(_driver_label(profile))
        self.specs["vision"].setText(
            f"{profile.camera().pipeline if profile.camera() else '—'} / {profile.vision.bottom.correction}"
        )
        issues = profile.validate()
        errors = [issue for issue in issues if issue.is_error]
        if errors:
            self.detail_issues.setText("配置错误：" + "；".join(issue.message for issue in errors))
            self.detail_issues.setStyleSheet(f"color: {COLORS['danger']}; font-size: 11px;")
        else:
            warnings = [issue for issue in issues if not issue.is_error]
            text = "配置校验通过" if not warnings else f"配置校验通过（{len(warnings)} 条提示）"
            self.detail_issues.setText(text)
            self.detail_issues.setStyleSheet(f"color: {COLORS['accent']}; font-size: 11px;")
        self.delete_button.setEnabled(not profile.builtin)

    def _activate(self, profile: MachineProfile) -> None:
        self._select(profile)
        self._confirm()

    def _confirm(self) -> None:
        if self.selected_profile is None:
            return
        errors = [issue for issue in self.selected_profile.validate() if issue.is_error]
        if errors:
            QMessageBox.warning(
                self,
                "机型配置有误",
                "该机型配置存在错误，无法使用：\n" + "\n".join(issue.message for issue in errors),
            )
            return
        self.accept()

    # ---------------- 配置管理 ----------------

    def _import_profile(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "导入机型配置", str(self.ctx.paths.root), "机型配置 (*.json)")
        if not path:
            return
        try:
            profile = self.ctx.profile_library.import_file(path)
        except ProfileError as exc:
            QMessageBox.critical(self, "导入失败", str(exc))
            return
        self.ctx.log("INFO", "MACHINE", f"导入机型配置 {profile.name}（{profile.id}）")
        self._refresh()
        self._select(profile)
        self.ctx.toast("机型配置已导入，确认后即可使用", "success")

    def _duplicate_profile(self) -> None:
        source = self.selected_profile or self.ctx.profile
        new_id, ok = QInputDialog.getText(self, "另存机型", "新机型 ID（文件名）：", text=f"{source.id}-copy")
        if not ok or not new_id.strip():
            return
        name, ok = QInputDialog.getText(self, "另存机型", "机型名称：", text=f"{source.name} 副本")
        if not ok:
            return
        try:
            clone = self.ctx.profile_library.duplicate(source.id, new_id.strip(), name.strip())
        except ProfileError as exc:
            QMessageBox.critical(self, "保存失败", str(exc))
            return
        self.ctx.log("INFO", "MACHINE", f"另存机型配置 {clone.name}（{clone.id}）")
        self._refresh()
        self._select(clone)
        self.ctx.toast("已另存为新机型，可编辑 JSON 后重新加载", "success")

    def _export_profile(self) -> None:
        profile = self.selected_profile or self.ctx.profile
        default = self.ctx.paths.exports / f"{profile.id}.json"
        path, _ = QFileDialog.getSaveFileName(self, "导出机型配置", str(default), "机型配置 (*.json)")
        if not path:
            return
        try:
            self.ctx.profile_library.export(profile, path)
        except OSError as exc:
            QMessageBox.critical(self, "导出失败", str(exc))
            return
        self.ctx.toast("机型配置已导出", "success")

    def _delete_profile(self) -> None:
        profile = self.selected_profile
        if profile is None or profile.builtin:
            return
        answer = QMessageBox.question(
            self,
            "删除设备",
            f"确定删除机型 {profile.name}（{profile.id}）？配置文件会从数据目录移除。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.ctx.profile_library.delete(profile.id)
        except ProfileError as exc:
            QMessageBox.critical(self, "删除失败", str(exc))
            return
        self.ctx.log("WARN", "MACHINE", f"删除机型配置 {profile.name}（{profile.id}）")
        self._refresh()
        fallback = self.ctx.profile_library.default()
        if fallback is not None:
            self._select(fallback)

    def _open_profile_dir(self) -> None:
        directory = user_profiles_dir(self.ctx.paths.root)
        directory.mkdir(parents=True, exist_ok=True)
        self.ctx.open_path(directory)


def select_machine(
    ctx: AppContext,
    first_run: bool = False,
    parent: QWidget | None = None,
) -> MachineProfile | None:
    """打开画廊；返回用户确认的机型（取消返回 None）。"""
    dialog = MachineGalleryDialog(ctx, first_run=first_run, parent=parent)
    if dialog.exec() == QDialog.DialogCode.Accepted and dialog.selected_profile is not None:
        return dialog.selected_profile
    return None


class DeviceCard(QFrame):
    """侧边栏设备卡：设备照片 + 状态，点击打开设备画廊。"""

    clicked = Signal()

    def __init__(self, profile: MachineProfile, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._profile = profile
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setObjectName("deviceCard")
        self.setStyleSheet(
            f"""
            QFrame#deviceCard {{
                background: #0b151b;
                border: 1px solid {COLORS['border_soft']};
                border-radius: 8px;
            }}
            QFrame#deviceCard:hover {{
                border: 1px solid {COLORS['accent']}66;
                background: #0e1c24;
            }}
            """
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 7)
        layout.setSpacing(5)
        self.art = MachineArt(profile)
        self.art.setFixedHeight(100)
        layout.addWidget(self.art)

        top = QHBoxLayout()
        top.setSpacing(6)
        self.dot = StatusDot(COLORS["muted"], 7)
        self.state = QLabel("设备离线")
        self.state.setStyleSheet("font-size: 11px; font-weight: 600;")
        top.addWidget(self.dot)
        top.addWidget(self.state)
        top.addStretch(1)
        self.shift = QLabel("白班")
        self.shift.setStyleSheet(
            f"color: {COLORS['muted']}; font-size: 9px; border: 1px solid {COLORS['border']};"
            "border-radius: 7px; padding: 0px 5px;"
        )
        top.addWidget(self.shift)
        layout.addLayout(top)

        self.name = QLabel(profile.name)
        self.name.setWordWrap(True)
        self.name.setStyleSheet("font-size: 10px; color: #a9bbc5;")
        self.name.setToolTip(profile.name)
        layout.addWidget(self.name)

        self.conn = QLabel("未连接")
        self.conn.setStyleSheet(f"color: {COLORS['faint']}; font-size: 9px;")
        layout.addWidget(self.conn)

        hint = QLabel("点击图片切换设备")
        hint.setStyleSheet(f"color: {COLORS['faint']}; font-size: 9px;")
        layout.addWidget(hint)

    def set_profile(self, profile: MachineProfile) -> None:
        self._profile = profile
        self.art.set_profile(profile)
        self.name.setText(profile.name)
        self.name.setToolTip(profile.name)

    def set_connection(self, label: str) -> None:
        text = label or "未连接"
        if len(text) > 26:
            text = text[:24] + "…"
        self.conn.setText(text)
        self.conn.setToolTip(label)

    def mouseReleaseEvent(self, event: Any) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(event)
