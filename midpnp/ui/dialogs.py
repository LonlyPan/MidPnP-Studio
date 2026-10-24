"""业务对话框：可制造性检查、贴装点、供料器与元件编辑。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..core.imports import (
    ColumnMapping,
    ImportOptions,
    ImportResult,
    PositionImportError,
    header_preview,
    parse_positions,
)
from ..core.models import Component, Feeder, Placement, Side, ValidationIssue, VisionMode, new_id
from ..core.packages import PackageDef, compact_key
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


_MAPPING_FIELDS = [
    ("refdes", "位号"),
    ("x", "X 坐标"),
    ("y", "Y 坐标"),
    ("rotation", "旋转角"),
    ("component", "元件名称"),
    ("package", "封装"),
    ("side", "板面"),
    ("skip", "跳过标记"),
]


class PackageDialog(DialogShell):
    """封装编辑：名称/同义名/本体尺寸/焊盘排布/吸嘴与视觉策略。"""

    def __init__(self, package: PackageDef | None = None, parent: QWidget | None = None) -> None:
        editing = package is not None
        super().__init__(
            "编辑封装" if editing else "新建封装",
            "封装几何用于吸嘴选择、视觉模板与坐标导入匹配",
            parent,
            580,
        )
        self._source = package
        form = QFormLayout()
        form.setSpacing(9)

        self.name = QLineEdit(package.name if package else "")
        self.name.setPlaceholderText("例如 0603 / SOIC-8 / QFN-32")
        self.aliases = QLineEdit(", ".join(package.aliases) if package else "")
        self.aliases.setPlaceholderText("可选，逗号分隔，例如 1608, R0603")
        self.category = QComboBox()
        for value, label in (
            ("chip", "片式元件"),
            ("ic", "IC"),
            ("transistor", "三极管 / 二极管"),
            ("led", "LED"),
            ("inductor", "电感"),
            ("connector", "连接器"),
            ("fiducial", "基准点"),
            ("other", "其他"),
        ):
            self.category.addItem(label, value)
        if package is not None:
            index = self.category.findData(package.category)
            self.category.setCurrentIndex(max(0, index))

        self.length = self._dim(package.length_mm if package else 1.6)
        self.width = self._dim(package.width_mm if package else 0.8)
        self.height = self._dim(package.height_mm if package else 0.8)
        self.pin_count = QSpinBox()
        self.pin_count.setRange(0, 256)
        self.pin_count.setValue(package.pin_count if package else 2)
        self.pad_rows = QComboBox()
        for value, label in ((1, "两端各一（片式）"), (2, "两侧双列（SOIC/TSSOP）"), (4, "四边（QFP/QFN）"), (0, "自定义/无焊盘")):
            self.pad_rows.addItem(label, value)
        if package is not None:
            index = self.pad_rows.findData(package.pad_rows)
            self.pad_rows.setCurrentIndex(max(0, index))
        self.pitch = self._dim(package.pad_pitch_mm if package else 0.0, maximum=100)
        self.pad_width = self._dim(package.pad_width_mm if package else 0.0, maximum=50)
        self.pad_height = self._dim(package.pad_height_mm if package else 0.0, maximum=50)
        self.nozzle = QComboBox()
        self.nozzle.addItem("（不指定）", "")
        for index in range(1, 9):
            self.nozzle.addItem(f"N{index}", f"N{index}")
        if package is not None:
            index = self.nozzle.findData(package.nozzle)
            self.nozzle.setCurrentIndex(max(0, index))
        self.vision = QComboBox()
        for mode in VisionMode:
            self.vision.addItem(mode.zh, mode.value)
        if package is not None:
            index = self.vision.findData(package.vision_mode)
            self.vision.setCurrentIndex(max(0, index))
        self.notes = QLineEdit(package.notes if package else "")
        self.notes.setPlaceholderText("可选：焊盘来源、工艺备注")

        form.addRow("封装名", self.name)
        form.addRow("同义名", self.aliases)
        form.addRow("类别", self.category)
        form.addRow("长度 L", self.length)
        form.addRow("宽度 W", self.width)
        form.addRow("高度 H", self.height)
        form.addRow("引脚数", self.pin_count)
        form.addRow("焊盘排布", self.pad_rows)
        form.addRow("焊盘间距", self.pitch)
        form.addRow("焊盘宽", self.pad_width)
        form.addRow("焊盘高", self.pad_height)
        form.addRow("默认吸嘴", self.nozzle)
        form.addRow("视觉策略", self.vision)
        form.addRow("备注", self.notes)
        self.body.addLayout(form)

        hint = QLabel("焊盘尺寸为近似值，用于绘图与视觉演示；实际钢网/焊盘请按工艺文件填写。")
        hint.setProperty("role", "hint")
        hint.setWordWrap(True)
        self.body.addWidget(hint)
        self.error_label = QLabel("")
        self.error_label.setProperty("role", "error")
        self.body.addWidget(self.error_label)
        self.add_cancel()
        self.add_accept("保存" if editing else "创建", "check")

    def _dim(self, value: float, maximum: float = 200.0) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(0.0, maximum)
        spin.setDecimals(2)
        spin.setSingleStep(0.05)
        spin.setSuffix(" mm")
        spin.setValue(value)
        return spin

    def accept(self) -> None:
        if not self.name.text().strip():
            self.error_label.setText("请输入封装名称")
            return
        super().accept()

    def result_package(self) -> PackageDef:
        source = self._source
        name = self.name.text().strip()
        aliases = [item.strip() for item in self.aliases.text().split(",") if item.strip()]
        package_id = source.id if source else f"PKG-{compact_key(name) or new_id()}"
        return PackageDef(
            id=package_id,
            name=name,
            aliases=aliases,
            category=str(self.category.currentData()),
            length_mm=self.length.value(),
            width_mm=self.width.value(),
            height_mm=self.height.value(),
            pin_count=self.pin_count.value(),
            pad_rows=int(self.pad_rows.currentData()),
            pad_pitch_mm=self.pitch.value(),
            pad_width_mm=self.pad_width.value(),
            pad_height_mm=self.pad_height.value(),
            nozzle=str(self.nozzle.currentData() or ""),
            vision_mode=str(self.vision.currentData()),
            notes=self.notes.text().strip(),
            builtin=False,
        )


class ImportWizardDialog(DialogShell):
    """坐标导入向导：格式识别 → 列映射 → 单位/镜像/偏移 → 预览。"""

    PREVIEW_LIMIT = 10

    def __init__(self, text: str, filename: str = "", parent: QWidget | None = None) -> None:
        super().__init__("导入坐标文件", filename or "未选择文件", parent, 880)
        self.text = text
        self.filename = filename
        self.result_data: ImportResult | None = None
        fmt, headers, mapping = header_preview(text, filename)
        self._format = fmt
        self._headers = headers
        self._mapping_combos: dict[str, QComboBox] = {}
        self._last_result: ImportResult | None = None

        info = QHBoxLayout()
        info.setSpacing(8)
        label = QLabel("识别格式")
        label.setProperty("role", "muted")
        info.addWidget(label)
        self.format_chip = QLabel({"csv": "通用坐标表 CSV/TSV", "kicad-pos": "KiCad .pos", "openpnp-board": "OpenPnP 板文件"}.get(fmt, fmt))
        self.format_chip.setStyleSheet(
            f"background: {COLORS['accent']}16; border: 1px solid {COLORS['accent']}55;"
            f" color: {COLORS['accent']}; border-radius: 10px; padding: 3px 9px; font-size: 11px;"
        )
        info.addWidget(self.format_chip)
        header_label = QLabel(f"表头 {len(headers)} 列" if headers else "未识别到表头")
        header_label.setProperty("role", "faint")
        info.addWidget(header_label)
        info.addStretch(1)
        self.body.addLayout(info)

        if fmt == "csv":
            grid = QGridLayout()
            grid.setHorizontalSpacing(12)
            grid.setVerticalSpacing(7)
            for index, (field_name, title) in enumerate(_MAPPING_FIELDS):
                row, column = divmod(index, 2)
                label = QLabel(title)
                label.setProperty("role", "muted")
                combo = QComboBox()
                combo.addItem("（不映射）", "")
                for header in headers:
                    combo.addItem(header, header)
                current = getattr(mapping, field_name, "")
                target = combo.findData(current)
                if target < 0 and current:
                    combo.addItem(current, current)
                    target = combo.count() - 1
                combo.setCurrentIndex(max(0, target))
                combo.currentIndexChanged.connect(self._refresh)
                self._mapping_combos[field_name] = combo
                grid.addWidget(label, row, column * 2)
                grid.addWidget(combo, row, column * 2 + 1)
            grid.setColumnStretch(1, 1)
            grid.setColumnStretch(3, 1)
            self.body.addLayout(grid)
        else:
            hint = QLabel("该格式字段固定（位号/型号/封装/X/Y/角度/板面），无需手动映射；下方可调整单位与坐标变换。")
            hint.setProperty("role", "hint")
            hint.setWordWrap(True)
            self.body.addWidget(hint)

        options = QFormLayout()
        options.setSpacing(9)
        self.unit = QComboBox()
        for value, label_text in (("", "自动（按表头/文件）"), ("mm", "毫米 mm"), ("mil", "密耳 mil"), ("inch", "英寸 inch")):
            self.unit.addItem(label_text, value)
        self.unit.currentIndexChanged.connect(self._refresh)
        self.rotation_offset = QDoubleSpinBox()
        self.rotation_offset.setRange(-360.0, 360.0)
        self.rotation_offset.setDecimals(1)
        self.rotation_offset.setSuffix(" °")
        self.rotation_offset.valueChanged.connect(self._refresh)
        self.offset_x = QDoubleSpinBox()
        self.offset_x.setRange(-1000.0, 1000.0)
        self.offset_x.setDecimals(3)
        self.offset_x.setSuffix(" mm")
        self.offset_x.valueChanged.connect(self._refresh)
        self.offset_y = QDoubleSpinBox()
        self.offset_y.setRange(-1000.0, 1000.0)
        self.offset_y.setDecimals(3)
        self.offset_y.setSuffix(" mm")
        self.offset_y.valueChanged.connect(self._refresh)
        transform_row = QHBoxLayout()
        transform_row.setSpacing(14)
        self.mirror_x = QCheckBox("镜像 X")
        self.mirror_y = QCheckBox("镜像 Y")
        self.swap_xy = QCheckBox("交换 X/Y")
        self.mirror_bottom = QCheckBox("底面 X 取反")
        for control in (self.mirror_x, self.mirror_y, self.swap_xy, self.mirror_bottom):
            control.stateChanged.connect(self._refresh)
            transform_row.addWidget(control)
        transform_row.addStretch(1)
        options.addRow("默认单位", self.unit)
        options.addRow("角度补偿", self.rotation_offset)
        options.addRow("X 偏移", self.offset_x)
        options.addRow("Y 偏移", self.offset_y)
        options.addRow("坐标变换", transform_row)
        self.body.addLayout(options)

        self.status = QLabel("")
        self.status.setWordWrap(True)
        self.status.setProperty("role", "muted")
        self.body.addWidget(self.status)

        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(["位号", "元件", "封装", "X (mm)", "Y (mm)", "角度", "板面", "跳过"])
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.setMaximumHeight(230)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(0, 70)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        for column, width in ((3, 74), (4, 74), (5, 56), (6, 50), (7, 46)):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
            header.resizeSection(column, width)
        self.body.addWidget(self.table)

        self.add_cancel("取消")
        self.import_button = self.add_accept("导入", "upload")
        self._refresh()

    def _current_mapping(self) -> ColumnMapping | None:
        if not self._mapping_combos:
            return None
        values = {key: str(combo.currentData() or "") for key, combo in self._mapping_combos.items()}
        return ColumnMapping(**values)

    def _current_options(self) -> ImportOptions:
        return ImportOptions(
            unit=str(self.unit.currentData() or ""),
            rotation_offset_deg=self.rotation_offset.value(),
            offset_x_mm=self.offset_x.value(),
            offset_y_mm=self.offset_y.value(),
            mirror_x=self.mirror_x.isChecked(),
            mirror_y=self.mirror_y.isChecked(),
            swap_xy=self.swap_xy.isChecked(),
            mirror_bottom_x=self.mirror_bottom.isChecked(),
        )

    def _refresh(self, *_: object) -> None:
        try:
            result = parse_positions(
                self.text,
                self.filename,
                self._current_mapping(),
                self._current_options(),
            )
        except PositionImportError as exc:
            self._last_result = None
            self.status.setText(f"无法解析：{exc}")
            self.status.setStyleSheet(f"color: {COLORS['danger']}; font-size: 12px;")
            self.table.setRowCount(0)
            self.import_button.setEnabled(False)
            return
        self._last_result = result
        self.table.setRowCount(min(len(result.placements), self.PREVIEW_LIMIT))
        for row, placement in enumerate(result.placements[: self.PREVIEW_LIMIT]):
            values = [
                placement.refdes,
                "",
                "",
                f"{placement.x_mm:.3f}",
                f"{placement.y_mm:.3f}",
                f"{placement.rotation_deg:.1f}°",
                placement.side.zh,
                "是" if placement.skip else "",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column in (3, 4, 5, 6, 7):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(row, column, item)
        warnings = f"；{result.warnings[0]}" if result.warnings else ""
        self.status.setText(f"已解析 {result.summary()}{warnings}")
        self.status.setStyleSheet(f"color: {COLORS['accent']}; font-size: 12px;")
        self.import_button.setEnabled(bool(result.placements))

    def accept(self) -> None:
        if self._last_result is None or not self._last_result.placements:
            return
        self.result_data = self._last_result
        super().accept()
