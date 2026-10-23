"""元件库页。"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...core.models import Component
from ..context import AppContext
from ..dialogs import ComponentDialog, ConfirmDeleteDialog
from ..theme import COLORS
from ..widgets import (
    Card,
    InfoRow,
    MetricCard,
    PageHeader,
    button,
    hline,
    make_chip,
)


class ComponentPreview(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(170)
        self._component: Component | None = None

    def set_component(self, component: Component | None) -> None:
        self._component = component
        self.update()

    def paintEvent(self, event: Any) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QPen(QColor(COLORS["border_soft"]), 1))
        painter.setBrush(QColor(COLORS["bg_soft"]))
        painter.drawRoundedRect(QRectF(0.5, 0.5, self.width() - 1, self.height() - 1), 8, 8)
        if self._component is None:
            painter.setPen(QColor(COLORS["faint"]))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "选择元件查看封装预览")
            painter.end()
            return
        component = self._component
        painter.setPen(QColor(COLORS["faint"]))
        painter.setFont(QFont("Cascadia Mono", 8))
        painter.drawText(12, 20, "TOP VIEW / SCALE EXAGGERATED")
        scale = min((self.width() - 100) / max(component.length_mm, 0.5), (self.height() - 80) / max(component.width_mm, 0.5))
        scale = min(scale, 22.0)
        width = max(34.0, component.length_mm * scale)
        height = max(20.0, component.width_mm * scale)
        center = QRectF(self.width() / 2 - width / 2, self.height() / 2 - height / 2, width, height)
        color = QColor(component.color)
        is_ic = any(token in component.package.upper() for token in ("SOP", "SOIC", "QFN", "QFP", "BGA"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#b9c0b8"))
        if is_ic:
            pin = max(4.0, width * 0.1)
            for i in range(5):
                offset = center.left() + width * (0.14 + i * 0.17)
                painter.drawRect(QRectF(offset, center.top() - pin * 0.8, pin * 0.5, pin * 0.8))
                painter.drawRect(QRectF(offset, center.bottom(), pin * 0.5, pin * 0.8))
        else:
            painter.drawRect(QRectF(center.left() - width * 0.12, center.top() + height * 0.12, width * 0.18, height * 0.76))
            painter.drawRect(QRectF(center.right() - width * 0.06, center.top() + height * 0.12, width * 0.18, height * 0.76))
        painter.setBrush(color)
        painter.setPen(QPen(QColor(0, 0, 0, 100), 1))
        painter.drawRoundedRect(center, 3, 3)
        painter.setPen(QPen(QColor(255, 255, 255, 45), 1))
        painter.drawLine(center.topLeft(), center.bottomRight())
        painter.setPen(QColor(COLORS["text"]))
        painter.setFont(QFont("Microsoft YaHei UI", 9, QFont.Weight.DemiBold))
        painter.drawText(center, Qt.AlignmentFlag.AlignCenter, component.package)
        painter.setPen(QColor(COLORS["muted"]))
        painter.setFont(QFont("Cascadia Mono", 8))
        painter.drawText(
            QRectF(0, self.height() - 34, self.width(), 18),
            Qt.AlignmentFlag.AlignCenter,
            f"{component.length_mm:.2f} × {component.width_mm:.2f} × {component.height_mm:.2f} mm",
        )
        painter.end()


class ComponentsPage(QWidget):
    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self._components: list[Component] = []
        self._selected_id = ""
        self._usage: dict[str, tuple[int, int]] = {}
        self._build()
        self._connect()
        self.refresh()

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(14)
        self.header = PageHeader("元件库", "维护封装、吸嘴、视觉策略与工艺参数")
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索名称 / 封装…")
        self.search.setFixedWidth(220)
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._apply_filter)
        self.add_button = button("新建元件", "plus", "primary")
        self.refresh_button = button("刷新", "refresh", "subtle")
        self.header.add_action(self.search)
        self.header.add_action(self.refresh_button)
        self.header.add_action(self.add_button)
        outer.addWidget(self.header)

        metrics = QHBoxLayout()
        metrics.setSpacing(12)
        self.metric_count = MetricCard("元件种类", "0", "种", "component", COLORS["accent"])
        self.metric_points = MetricCard("贴装点覆盖", "0", "点", "target", COLORS["blue"])
        self.metric_feeders = MetricCard("供料器引用", "0", "台", "feeder", COLORS["purple"])
        self.metric_ic = MetricCard("IC 类元件", "0", "种", "layers", COLORS["warn"])
        for card in (self.metric_count, self.metric_points, self.metric_feeders, self.metric_ic):
            metrics.addWidget(card, 1)
        outer.addLayout(metrics)

        body = QHBoxLayout()
        body.setSpacing(12)
        table_card = Card(padding=12)
        table_top = QHBoxLayout()
        title = QLabel("元件清单")
        title.setProperty("role", "section")
        table_top.addWidget(title)
        self.count_chip = make_chip("0 种")
        table_top.addWidget(self.count_chip)
        table_top.addStretch(1)
        hint = QLabel("双击行编辑")
        hint.setProperty("role", "faint")
        table_top.addWidget(hint)
        table_card.body.addLayout(table_top)
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["元件", "封装", "尺寸 (mm)", "吸嘴", "视觉", "贴装点", "供料器"])
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setDefaultSectionSize(34)
        self.table.doubleClicked.connect(lambda *_: self._edit())
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column, width in ((1, 100), (2, 150), (3, 64), (4, 100), (5, 76), (6, 76)):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
            header.resizeSection(column, width)
        self.table.itemSelectionChanged.connect(self._on_selection)
        table_card.body.addWidget(self.table, 1)
        body.addWidget(table_card, 1)

        detail = Card(padding=16)
        detail.setFixedWidth(340)
        detail_top = QHBoxLayout()
        detail_title = QLabel("元件详情")
        detail_title.setProperty("role", "section")
        detail_top.addWidget(detail_title)
        detail_top.addStretch(1)
        self.detail_chip = make_chip("—")
        detail_top.addWidget(self.detail_chip)
        detail.body.addLayout(detail_top)
        self.preview = ComponentPreview()
        detail.body.addWidget(self.preview)
        self.detail_name = QLabel("未选择元件")
        self.detail_name.setStyleSheet("font-size: 18px; font-weight: 700;")
        self.detail_name.setWordWrap(True)
        detail.body.addWidget(self.detail_name)
        self.detail_package = QLabel("")
        self.detail_package.setProperty("role", "muted")
        detail.body.addWidget(self.detail_package)
        detail.body.addWidget(hline())
        self.info_size = InfoRow("尺寸 L×W×H", "—")
        self.info_nozzle = InfoRow("吸嘴", "—")
        self.info_vision = InfoRow("视觉策略", "—")
        self.info_speed = InfoRow("贴装速度", "—")
        self.info_points = InfoRow("产品引用", "—")
        self.info_feeders = InfoRow("供料器引用", "—")
        for row in (
            self.info_size,
            self.info_nozzle,
            self.info_vision,
            self.info_speed,
            self.info_points,
            self.info_feeders,
        ):
            detail.body.addWidget(row)
        self.notes_label = QLabel("")
        self.notes_label.setProperty("role", "hint")
        self.notes_label.setWordWrap(True)
        detail.body.addWidget(self.notes_label)
        detail.body.addStretch(1)
        self.edit_button = button("编辑元件", "edit", "primary")
        self.delete_button = button("删除", "trash", "danger")
        detail.body.addWidget(self.edit_button)
        detail.body.addWidget(self.delete_button)
        body.addWidget(detail)
        outer.addLayout(body, 1)

        self.add_button.clicked.connect(self._add)
        self.refresh_button.clicked.connect(self.refresh)
        self.edit_button.clicked.connect(self._edit)
        self.delete_button.clicked.connect(self._delete)
        self._set_detail(None)

    def _connect(self) -> None:
        self.ctx.signals.components_changed.connect(self.refresh)

    def refresh(self) -> None:
        self._components = self.ctx.storage.list_components()
        self._usage = {
            component.id: self.ctx.storage.component_usage(component.id) for component in self._components
        }
        self._populate()
        total_points = sum(points for _, points in self._usage.values())
        total_feeders = sum(feeders for feeders, _ in self._usage.values())
        ic_count = sum(
            1
            for component in self._components
            if any(token in component.package.upper() for token in ("SOP", "SOIC", "QFN", "QFP", "BGA"))
        )
        self.metric_count.set(str(len(self._components)), "元件主数据")
        self.metric_points.set(str(total_points), "全部产品中的贴装点")
        self.metric_feeders.set(str(total_feeders), "已装载料站")
        self.metric_ic.set(str(ic_count), "需要视觉对中")
        if self._components and not self._selected_id:
            self.table.selectRow(0)
        if self._selected_id:
            component = next((c for c in self._components if c.id == self._selected_id), None)
            self._set_detail(component)
        else:
            self._set_detail(None)

    def _populate(self) -> None:
        self.table.setRowCount(len(self._components))
        for row, component in enumerate(self._components):
            feeders, points = self._usage.get(component.id, (0, 0))
            values = [
                component.name,
                component.package,
                f"{component.length_mm:.2f} × {component.width_mm:.2f} × {component.height_mm:.2f}",
                component.nozzle,
                component.vision_mode.zh,
                str(points),
                str(feeders),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column in (3, 4, 5, 6):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(row, column, item)
            swatch = QPixmap(10, 10)
            swatch.fill(QColor(component.color))
            self.table.item(row, 0).setIcon(swatch)
        self.count_chip.setText(f"{len(self._components)} 种")
        self._apply_filter()

    def _apply_filter(self) -> None:
        needle = self.search.text().strip().lower()
        for row, component in enumerate(self._components):
            haystack = f"{component.name} {component.package} {component.nozzle}".lower()
            self.table.setRowHidden(row, bool(needle) and needle not in haystack)

    def _on_selection(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            self._selected_id = ""
            self._set_detail(None)
            return
        row = rows[0].row()
        if row >= len(self._components):
            return
        self._selected_id = self._components[row].id
        self._set_detail(self._components[row])

    def _set_detail(self, component: Component | None) -> None:
        for control in (self.edit_button, self.delete_button):
            control.setEnabled(component is not None)
        self.preview.set_component(component)
        if component is None:
            self.detail_name.setText("未选择元件")
            self.detail_package.setText("从左侧列表选择一个元件")
            self.detail_chip.setText("—")
            for row in (
                self.info_size,
                self.info_nozzle,
                self.info_vision,
                self.info_speed,
                self.info_points,
                self.info_feeders,
            ):
                row.set("—")
            self.notes_label.setText("元件的尺寸与视觉策略会用于板卡预览和生产前检查。")
            return
        self.detail_name.setText(component.name)
        self.detail_package.setText(f"{component.package} · {component.id}")
        feeders, points = self._usage.get(component.id, (0, 0))
        self.detail_chip.setText("IC" if component.vision_mode.value in {"IC", "Fiducial"} else "被动件")
        self.info_size.set(
            f"{component.length_mm:.2f} × {component.width_mm:.2f} × {component.height_mm:.2f}"
        )
        self.info_nozzle.set(component.nozzle)
        self.info_vision.set(component.vision_mode.zh)
        self.info_speed.set(f"{component.speed_pct}%")
        self.info_points.set(f"{points} 点")
        self.info_feeders.set(f"{feeders} 台")
        self.notes_label.setText(component.notes or "暂无备注")

    def _add(self) -> None:
        dialog = ComponentDialog(None, self)
        if dialog.exec():
            component = dialog.result_component()
            self.ctx.storage.save_component(component)
            self._selected_id = component.id
            self.ctx.signals.components_changed.emit()
            self.ctx.log("INFO", "COMPONENT", f"创建元件 {component.name}（{component.package}）")
            self.ctx.toast("元件已创建", "success")
            self.refresh()

    def _edit(self) -> None:
        component = next((c for c in self._components if c.id == self._selected_id), None)
        if component is None:
            self.ctx.toast("请先选择元件", "warning")
            return
        dialog = ComponentDialog(component, self)
        if dialog.exec():
            self.ctx.storage.save_component(dialog.result_component())
            self.ctx.signals.components_changed.emit()
            self.ctx.log("INFO", "COMPONENT", f"更新元件 {component.name}")
            self.ctx.toast("元件已更新", "success")
            self.refresh()

    def _delete(self) -> None:
        component = next((c for c in self._components if c.id == self._selected_id), None)
        if component is None:
            return
        feeders, points = self._usage.get(component.id, (0, 0))
        if feeders or points:
            QMessageBox.warning(
                self,
                "无法删除",
                f"元件“{component.name}”仍被 {feeders} 台供料器和 {points} 个贴装点引用。\n"
                "请先移除相关供料器与贴装点。",
            )
            return
        dialog = ConfirmDeleteDialog(
            "删除元件",
            f"确定删除“{component.name}”？",
            self,
        )
        if dialog.exec():
            self.ctx.storage.delete_component(component.id)
            self._selected_id = ""
            self.ctx.signals.components_changed.emit()
            self.ctx.log("WARN", "COMPONENT", f"删除元件 {component.name}")
            self.ctx.toast("元件已删除", "info")
            self.refresh()
