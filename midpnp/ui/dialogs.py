"""业务对话框：可制造性检查、贴装点、供料器与元件编辑。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..core.models import Component, Feeder, Placement, Side, ValidationIssue, VisionMode, new_id
from .icons import icon
from .theme import COLORS
from .widgets import button, hline, set_css


class DialogShell(QDialog):
    def __init__(self, title: str, subtitle: str = "", parent: QWidget | None = None, width: int = 520) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(width)
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 18)
        root.setSpacing(12)
        heading = QLabel(title)
        heading.setProperty("role", "dialogTitle")
        root.addWidget(heading)
        if subtitle:
            sub = QLabel(subtitle)
            sub.setProperty("role", "muted")
            sub.setWordWrap(True)
            root.addWidget(sub)
        root.addWidget(hline())
        self.body = QVBoxLayout()
        self.body.setSpacing(10)
        root.addLayout(self.body, 1)
        self.footer = QHBoxLayout()
        self.footer.setSpacing(8)
        self.footer.addStretch(1)
        root.addLayout(self.footer)

    def add_cancel(self, text: str = "取消") -> QPushButton:
        control = button(text, variant="subtle")
        control.clicked.connect(self.reject)
        self.footer.addWidget(control)
        return control

    def add_accept(self, text: str = "确定", icon_name: str | None = None) -> QPushButton:
        control = button(text, icon_name, "primary")
        control.clicked.connect(self.accept)
        self.footer.addWidget(control)
        return control


class IssuesDialog(DialogShell):
    def __init__(self, issues: list[ValidationIssue], parent: QWidget | None = None) -> None:
        errors = sum(1 for issue in issues if issue.is_error)
        warnings = len(issues) - errors
        subtitle = f"{errors} 个错误 · {warnings} 个提示"
        super().__init__("生产前检查", subtitle, parent, width=600)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMaximumHeight(360)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        for issue in issues:
            row = QFrame()
            set_css(row, "inset")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(10, 8, 10, 8)
            row_layout.setSpacing(8)
            color = COLORS["danger"] if issue.is_error else COLORS["warn"]
            glyph = QLabel()
            glyph.setPixmap(icon("warning", color, 16).pixmap(16, 16))
            glyph.setFixedWidth(18)
            row_layout.addWidget(glyph, 0, Qt.AlignmentFlag.AlignTop)
            text = QLabel(issue.message)
            text.setWordWrap(True)
            text.setStyleSheet(f"color: {COLORS['text']}; font-size: 12px;")
            row_layout.addWidget(text, 1)
            tag = QLabel("错误" if issue.is_error else "提示")
            tag.setStyleSheet(
                f"color: {color}; background: {color}16; border: 1px solid {color}44;"
                "border-radius: 8px; padding: 1px 7px; font-size: 10px;"
            )
            row_layout.addWidget(tag, 0, Qt.AlignmentFlag.AlignTop)
            layout.addWidget(row)
        layout.addStretch(1)
        scroll.setWidget(content)
        self.body.addWidget(scroll)
        self.add_cancel("关闭")


class PlacementDialog(DialogShell):
    def __init__(
        self,
        components: list[Component],
        placement: Placement | None = None,
        parent: QWidget | None = None,
    ) -> None:
        editing = placement is not None
        super().__init__("编辑贴装点" if editing else "添加贴装点", "坐标以板内左下角为原点，单位 mm", parent, 500)
        self._source = placement
        form = QFormLayout()
        form.setSpacing(9)
        self.refdes = QLineEdit(placement.refdes if placement else "")
        self.refdes.setPlaceholderText("例如 R13")
        self.component = QComboBox()
        for item in components:
            self.component.addItem(f"{item.name}  ·  {item.package}", item.id)
        if placement:
            index = self.component.findData(placement.component_id)
            if index >= 0:
                self.component.setCurrentIndex(index)
        self.x = self._spin(0, 2000, placement.x_mm if placement else 0.0)
        self.y = self._spin(0, 2000, placement.y_mm if placement else 0.0)
        self.rotation = self._spin(-360, 360, placement.rotation_deg if placement else 0.0, "°")
        self.side = QComboBox()
        self.side.addItem("正面 Top", Side.TOP.value)
        self.side.addItem("反面 Bottom", Side.BOTTOM.value)
        if placement:
            self.side.setCurrentIndex(max(0, self.side.findData(placement.side.value)))
        self.skip = QCheckBox("跳过此贴装点（DNP）")
        self.skip.setChecked(placement.skip if placement else False)
        form.addRow("位号", self.refdes)
        form.addRow("元件", self.component)
        form.addRow("X 坐标", self.x)
        form.addRow("Y 坐标", self.y)
        form.addRow("旋转角度", self.rotation)
        form.addRow("板面", self.side)
        form.addRow("", self.skip)
        self.body.addLayout(form)
        self.error_label = QLabel("")
        self.error_label.setProperty("role", "error")
        self.error_label.setWordWrap(True)
        self.body.addWidget(self.error_label)
        self.add_cancel()
        self.add_accept("保存" if editing else "添加", "check")
        self.refdes.setFocus()

    def _spin(self, minimum: float, maximum: float, value: float, suffix: str = " mm") -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setDecimals(2)
        spin.setSingleStep(0.5)
        spin.setSuffix(suffix)
        spin.setValue(value)
        return spin

    def accept(self) -> None:
        if not self.refdes.text().strip():
            self.error_label.setText("请输入位号")
            return
        if self.component.currentIndex() < 0:
            self.error_label.setText("请选择元件")
            return
        super().accept()

    def result_placement(self) -> Placement:
        source = self._source
        return Placement(
            refdes=self.refdes.text().strip(),
            component_id=str(self.component.currentData()),
            x_mm=self.x.value(),
            y_mm=self.y.value(),
            rotation_deg=self.rotation.value(),
            side=Side(str(self.side.currentData())),
            skip=self.skip.isChecked(),
            locked=source.locked if source else False,
            feeder_id=source.feeder_id if source else "",
        )


class FeederDialog(DialogShell):
    def __init__(
        self,
        components: list[Component],
        feeder: Feeder | None = None,
        next_slot: int = 1,
        parent: QWidget | None = None,
    ) -> None:
        editing = feeder is not None
        super().__init__("编辑供料器" if editing else "装载供料器", "配置槽位、物料与取料坐标", parent, 520)
        self._source = feeder
        form = QFormLayout()
        form.setSpacing(9)
        self.slot = QSpinBox()
        self.slot.setRange(1, 99)
        self.slot.setValue(feeder.slot if feeder else next_slot)
        self.slot.setPrefix("SLOT ")
        self.component = QComboBox()
        for item in components:
            self.component.addItem(f"{item.name}  ·  {item.package}", item.id)
        if feeder:
            index = self.component.findData(feeder.component_id)
            if index >= 0:
                self.component.setCurrentIndex(index)
        self.label = QLineEdit(feeder.label if feeder else "")
        self.label.setPlaceholderText("可选，例如 0603 电阻盘")
        self.capacity = QSpinBox()
        self.capacity.setRange(0, 100000)
        self.capacity.setSingleStep(100)
        self.capacity.setValue(feeder.capacity if feeder else 4000)
        self.remaining = QSpinBox()
        self.remaining.setRange(0, 100000)
        self.remaining.setSingleStep(100)
        self.remaining.setValue(feeder.remaining if feeder else 4000)
        self.pitch = QDoubleSpinBox()
        self.pitch.setRange(1, 100)
        self.pitch.setDecimals(2)
        self.pitch.setSuffix(" mm")
        self.pitch.setValue(feeder.pitch_mm if feeder else 4.0)
        self.pick_x = self._coord(feeder.pick_x_mm if feeder else 40.0)
        self.pick_y = self._coord(feeder.pick_y_mm if feeder else 332.0)
        self.pick_z = self._coord(feeder.pick_z_mm if feeder else 0.0)
        self.enabled = QCheckBox("启用此供料器")
        self.enabled.setChecked(feeder.enabled if feeder else True)
        self.low = QSpinBox()
        self.low.setRange(0, 100)
        self.low.setSuffix(" %")
        self.low.setValue(feeder.low_threshold_pct if feeder else 15)
        form.addRow("槽位", self.slot)
        form.addRow("元件", self.component)
        form.addRow("标签", self.label)
        form.addRow("容量", self.capacity)
        form.addRow("余料", self.remaining)
        form.addRow("料带间距", self.pitch)
        form.addRow("取料 X", self.pick_x)
        form.addRow("取料 Y", self.pick_y)
        form.addRow("取料 Z", self.pick_z)
        form.addRow("低料阈值", self.low)
        form.addRow("", self.enabled)
        self.body.addLayout(form)
        self.error_label = QLabel("")
        self.error_label.setProperty("role", "error")
        self.body.addWidget(self.error_label)
        self.add_cancel()
        self.add_accept("保存" if editing else "装载", "check")

    def _coord(self, value: float) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(0, 2000)
        spin.setDecimals(2)
        spin.setSuffix(" mm")
        spin.setValue(value)
        return spin

    def accept(self) -> None:
        if self.component.currentIndex() < 0:
            self.error_label.setText("请先创建并选择元件")
            return
        if self.remaining.value() > self.capacity.value() and self.capacity.value() > 0:
            self.error_label.setText("余料不能大于容量")
            return
        super().accept()

    def result_feeder(self) -> Feeder:
        source = self._source
        return Feeder(
            id=source.id if source else new_id("FDR-"),
            slot=self.slot.value(),
            component_id=str(self.component.currentData()),
            label=self.label.text().strip(),
            capacity=self.capacity.value(),
            remaining=self.remaining.value(),
            pitch_mm=self.pitch.value(),
            pick_x_mm=self.pick_x.value(),
            pick_y_mm=self.pick_y.value(),
            pick_z_mm=self.pick_z.value(),
            enabled=self.enabled.isChecked(),
            low_threshold_pct=self.low.value(),
        )


class ComponentDialog(DialogShell):
    def __init__(self, component: Component | None = None, parent: QWidget | None = None) -> None:
        editing = component is not None
        super().__init__("编辑元件" if editing else "新建元件", "封装尺寸用于板卡预览与吸嘴策略", parent, 520)
        self._source = component
        self._color = component.color if component else "#c9a227"
        form = QFormLayout()
        form.setSpacing(9)
        self.name = QLineEdit(component.name if component else "")
        self.name.setPlaceholderText("例如 电阻 0603")
        self.package = QLineEdit(component.package if component else "0603")
        self.length = self._dim(component.length_mm if component else 1.6)
        self.width = self._dim(component.width_mm if component else 0.8)
        self.height = self._dim(component.height_mm if component else 0.5)
        self.nozzle = QComboBox()
        for i in range(1, 9):
            self.nozzle.addItem(f"N{i}")
        if component:
            index = self.nozzle.findText(component.nozzle)
            if index >= 0:
                self.nozzle.setCurrentIndex(index)
        self.vision = QComboBox()
        for mode in VisionMode:
            self.vision.addItem(mode.zh, mode.value)
        if component:
            index = self.vision.findData(component.vision_mode.value)
            if index >= 0:
                self.vision.setCurrentIndex(index)
        self.speed = QSpinBox()
        self.speed.setRange(10, 100)
        self.speed.setSuffix(" %")
        self.speed.setValue(component.speed_pct if component else 100)
        self.color_button = button("选择颜色", variant="subtle")
        self.color_button.clicked.connect(self._pick_color)
        self.color_preview = QLabel()
        self.color_preview.setFixedSize(56, 26)
        self._update_color_preview()
        color_row = QHBoxLayout()
        color_row.addWidget(self.color_button)
        color_row.addWidget(self.color_preview)
        color_row.addStretch(1)
        self.notes = QLineEdit(component.notes if component else "")
        form.addRow("名称", self.name)
        form.addRow("封装", self.package)
        form.addRow("长度", self.length)
        form.addRow("宽度", self.width)
        form.addRow("高度", self.height)
        form.addRow("吸嘴", self.nozzle)
        form.addRow("视觉", self.vision)
        form.addRow("速度", self.speed)
        form.addRow("预览色", color_row)
        form.addRow("备注", self.notes)
        self.body.addLayout(form)
        self.error_label = QLabel("")
        self.error_label.setProperty("role", "error")
        self.body.addWidget(self.error_label)
        self.add_cancel()
        self.add_accept("保存" if editing else "创建", "check")

    def _dim(self, value: float) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(0.1, 200)
        spin.setDecimals(2)
        spin.setSuffix(" mm")
        spin.setValue(value)
        return spin

    def _pick_color(self) -> None:
        color = QColorDialog.getColor(QColor(self._color), self, "选择元件预览色")
        if color.isValid():
            self._color = color.name()
            self._update_color_preview()

    def _update_color_preview(self) -> None:
        self.color_preview.setStyleSheet(
            f"background: {self._color}; border: 1px solid {COLORS['border']}; border-radius: 4px;"
        )

    def accept(self) -> None:
        if not self.name.text().strip():
            self.error_label.setText("请输入元件名称")
            return
        if not self.package.text().strip():
            self.error_label.setText("请输入封装名称")
            return
        super().accept()

    def result_component(self) -> Component:
        source = self._source
        return Component(
            id=source.id if source else new_id("CMP-"),
            name=self.name.text().strip(),
            package=self.package.text().strip(),
            length_mm=self.length.value(),
            width_mm=self.width.value(),
            height_mm=self.height.value(),
            nozzle=self.nozzle.currentText(),
            vision_mode=VisionMode(str(self.vision.currentData())),
            speed_pct=self.speed.value(),
            color=self._color,
            notes=self.notes.text().strip(),
        )


class ConfirmDeleteDialog(DialogShell):
    def __init__(self, title: str, text: str, parent: QWidget | None = None) -> None:
        super().__init__(title, text, parent, 440)
        hint = QLabel("该操作不可撤销。")
        hint.setProperty("role", "warning")
        self.body.addWidget(hint)
        self.add_cancel()
        accept = self.add_accept("删除", "trash")
        accept.setProperty("variant", "danger")
        accept.style().unpolish(accept)
        accept.style().polish(accept)
