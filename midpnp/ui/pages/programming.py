"""产品编程页：板卡布局、贴装点编辑与坐标导入导出。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...core.importers import export_centroid_csv
from ...core.imports import ImportResult, read_position_file
from ...core.models import Fiducial, Product, ValidationIssue, VisionMode, new_id, now_iso
from ..context import AppContext
from ..dialogs import ConfirmDeleteDialog, ImportWizardDialog, IssuesDialog, PlacementDialog
from ..theme import COLORS
from ..widgets import (
    BoardView,
    Card,
    PageHeader,
    button,
    hline,
    make_chip,
)


class ProgrammingPage(QWidget):
    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self._product: Product | None = None
        self._dirty = False
        self._loading = False
        self._row_by_ref: dict[str, int] = {}
        self._build()
        self._connect()
        self.refresh(force=True)

    # ---------------- UI ----------------

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(14)
        self.header = PageHeader("产品编程", "维护板卡布局、贴装坐标与工艺数据")
        self.dirty_chip = make_chip("已保存")
        self.product_combo = QComboBox()
        self.product_combo.setMinimumWidth(220)
        self.product_combo.currentIndexChanged.connect(self._on_combo_changed)
        self.new_button = button("新建", "plus", "subtle")
        self.dup_button = button("复制", "layers", "subtle")
        self.delete_button = button("删除", "trash", "subtle")
        self.import_button = button("导入坐标", "upload", "subtle")
        self.export_button = button("导出", "download", "subtle")
        self.save_button = button("保存产品", "save", "primary")
        for widget in (
            self.product_combo,
            self.new_button,
            self.dup_button,
            self.delete_button,
            self.import_button,
            self.export_button,
        ):
            self.header.add_action(widget)
        self.header.add_action(self.dirty_chip)
        self.header.add_action(self.save_button)
        outer.addWidget(self.header)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        board_card = Card(padding=12)
        board_top = QHBoxLayout()
        board_title = QLabel("板卡布局")
        board_title.setProperty("role", "section")
        board_top.addWidget(board_title)
        board_top.addWidget(make_chip("TOP VIEW"))
        board_top.addStretch(1)
        self.board_points_chip = make_chip("0 点", accent=True)
        board_top.addWidget(self.board_points_chip)
        fit = button("适应", "target", "ghost")
        fit.clicked.connect(lambda: self.board.reset_view())
        board_top.addWidget(fit)
        board_card.body.addLayout(board_top)
        self.board = BoardView(mode="board")
        self.board.setMinimumWidth(380)
        self.board.placement_selected.connect(self._on_board_selected)
        board_card.body.addWidget(self.board, 1)
        board_footer = QHBoxLayout()
        self.board_hint = QLabel("单击元件选择 · 滚轮缩放 · 拖拽平移")
        self.board_hint.setProperty("role", "faint")
        board_footer.addWidget(self.board_hint)
        board_footer.addStretch(1)
        self.board_size_label = QLabel("")
        self.board_size_label.setProperty("role", "mono")
        board_footer.addWidget(self.board_size_label)
        board_card.body.addLayout(board_footer)
        splitter.addWidget(board_card)

        editor = Card(padding=16)
        editor_top = QHBoxLayout()
        product_title = QLabel("产品参数")
        product_title.setProperty("role", "section")
        editor_top.addWidget(product_title)
        editor_top.addStretch(1)
        self.product_id_label = QLabel("")
        self.product_id_label.setProperty("role", "faint")
        editor_top.addWidget(self.product_id_label)
        editor.body.addLayout(editor_top)

        meta = QGridLayout()
        meta.setHorizontalSpacing(12)
        meta.setVerticalSpacing(8)
        self.name_edit = QLineEdit()
        self.revision_edit = QLineEdit()
        self.width_spin = self._dim_spin()
        self.height_spin = self._dim_spin()
        self.thickness_spin = self._dim_spin()
        self.origin_x_spin = self._coord_spin()
        self.origin_y_spin = self._coord_spin()
        self.notes_edit = QLineEdit()
        self.notes_edit.setPlaceholderText("可选")
        meta.addWidget(self._field_label("产品名称"), 0, 0)
        meta.addWidget(self.name_edit, 0, 1, 1, 3)
        meta.addWidget(self._field_label("版本"), 0, 4)
        meta.addWidget(self.revision_edit, 0, 5)
        meta.addWidget(self._field_label("板宽"), 1, 0)
        meta.addWidget(self.width_spin, 1, 1)
        meta.addWidget(self._field_label("板高"), 1, 2)
        meta.addWidget(self.height_spin, 1, 3)
        meta.addWidget(self._field_label("板厚"), 1, 4)
        meta.addWidget(self.thickness_spin, 1, 5)
        meta.addWidget(self._field_label("原点 X"), 2, 0)
        meta.addWidget(self.origin_x_spin, 2, 1)
        meta.addWidget(self._field_label("原点 Y"), 2, 2)
        meta.addWidget(self.origin_y_spin, 2, 3)
        meta.addWidget(self._field_label("备注"), 2, 4)
        meta.addWidget(self.notes_edit, 2, 5)
        for column in (1, 3, 5):
            meta.setColumnStretch(column, 1)
        editor.body.addLayout(meta)
        editor.body.addWidget(hline())

        table_top = QHBoxLayout()
        self.table_title = QLabel("贴装点")
        self.table_title.setProperty("role", "section")
        table_top.addWidget(self.table_title)
        self.table_count_chip = make_chip("0", accent=True)
        table_top.addWidget(self.table_count_chip)
        table_top.addStretch(1)
        self.add_point_button = button("添加", "plus", "subtle")
        self.edit_point_button = button("编辑", "edit", "subtle")
        self.remove_point_button = button("删除", "trash", "subtle")
        for control in (self.add_point_button, self.edit_point_button, self.remove_point_button):
            table_top.addWidget(control)
        editor.body.addLayout(table_top)

        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(["#", "位号", "元件", "X (mm)", "Y (mm)", "角度", "板面", "状态"])
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.doubleClicked.connect(lambda *_: self._edit_point())
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(0, 34)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(1, 64)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        for column, width in ((3, 68), (4, 68), (5, 48), (6, 48), (7, 52)):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
            header.resizeSection(column, width)
        self.table.itemSelectionChanged.connect(self._on_table_selected)
        editor.body.addWidget(self.table, 1)
        footer = QLabel("提示：双击表格行或点击“编辑”修改坐标；编辑后需保存产品。")
        footer.setProperty("role", "faint")
        editor.body.addWidget(footer)
        splitter.addWidget(editor)
        splitter.setStretchFactor(0, 5)
        splitter.setStretchFactor(1, 7)
        splitter.setSizes([540, 760])
        outer.addWidget(splitter, 1)

        self.save_button.clicked.connect(self._save)
        self.new_button.clicked.connect(self._new_product)
        self.dup_button.clicked.connect(self._duplicate_product)
        self.delete_button.clicked.connect(self._delete_product)
        self.import_button.clicked.connect(self._import_csv)
        self.export_button.clicked.connect(self._export_csv)
        self.add_point_button.clicked.connect(self._add_point)
        self.edit_point_button.clicked.connect(self._edit_point)
        self.remove_point_button.clicked.connect(self._remove_point)
        for field in (self.name_edit, self.revision_edit, self.notes_edit):
            field.textEdited.connect(self._mark_dirty)
        for field in (
            self.width_spin,
            self.height_spin,
            self.thickness_spin,
            self.origin_x_spin,
            self.origin_y_spin,
        ):
            field.valueChanged.connect(self._mark_dirty)

    def _field_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setProperty("role", "muted")
        return label

    def _dim_spin(self) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(1, 2000)
        spin.setDecimals(1)
        spin.setSuffix(" mm")
        spin.setSingleStep(1)
        return spin

    def _coord_spin(self) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(0, 2000)
        spin.setDecimals(1)
        spin.setSuffix(" mm")
        spin.setSingleStep(1)
        return spin

    def _connect(self) -> None:
        self.ctx.signals.products_changed.connect(self._on_products_changed)
        self.ctx.signals.product_changed.connect(self._on_product_changed)
        self.ctx.signals.components_changed.connect(self._on_components_changed)
        self.ctx.machine.position_changed.connect(self.board.set_head)

    # ---------------- loading ----------------

    def refresh(self, force: bool = False) -> None:
        products = self.ctx.storage.list_products()
        self._loading = True
        self.product_combo.blockSignals(True)
        self.product_combo.clear()
        for product in products:
            self.product_combo.addItem(f"{product.name} · {product.revision}", product.id)
        current = self._product.id if self._product else self.ctx.current_product_id
        index = self.product_combo.findData(current)
        if index < 0 and self.product_combo.count():
            index = 0
        if index >= 0:
            self.product_combo.setCurrentIndex(index)
            product_id = str(self.product_combo.itemData(index))
        else:
            product_id = ""
        self.product_combo.blockSignals(False)
        self._loading = False
        if force or self._product is None or product_id != self._product.id:
            product = self.ctx.storage.get_product(product_id) if product_id else None
            self._load_product(product)

    def _load_product(self, product: Product | None) -> None:
        self._product = product
        self._loading = True
        self._dirty = False
        if product:
            self.ctx.current_product_id = product.id
            self.name_edit.setText(product.name)
            self.revision_edit.setText(product.revision)
            self.width_spin.setValue(product.board_width_mm)
            self.height_spin.setValue(product.board_height_mm)
            self.thickness_spin.setValue(product.board_thickness_mm)
            self.origin_x_spin.setValue(product.board_origin_x_mm)
            self.origin_y_spin.setValue(product.board_origin_y_mm)
            self.notes_edit.setText(product.notes)
            self.notes_edit.setCursorPosition(0)
            self.notes_edit.setToolTip(product.notes)
            self.product_id_label.setText(product.id)
            self.board.set_product(product, self.ctx.components())
            self.board.set_limits(self.ctx.settings.limits.travel_x_mm, self.ctx.settings.limits.travel_y_mm)
            self.board_size_label.setText(
                f"{product.board_width_mm:.0f} × {product.board_height_mm:.0f} mm · {len(product.placements)} 点"
            )
            self.board_points_chip.setText(f"{len(product.placements)} 点")
            self.table_count_chip.setText(str(len(product.placements)))
            self._populate_table()
            if product.placements and not self.board.selected():
                self.table.selectRow(0)
            self.save_button.setEnabled(True)
        else:
            self.name_edit.clear()
            self.revision_edit.clear()
            self.product_id_label.setText("")
            self.board.set_product(None)
            self.table.setRowCount(0)
            self.save_button.setEnabled(False)
        self._loading = False
        self._update_dirty_ui()

    def _populate_table(self) -> None:
        if not self._product:
            self.table.setRowCount(0)
            return
        components = self.ctx.component_map()
        selected = self.board.selected()
        self.table.setRowCount(len(self._product.placements))
        self._row_by_ref = {}
        for row, placement in enumerate(self._product.placements):
            component = components.get(placement.component_id)
            values = [
                f"{row + 1:02d}",
                placement.refdes,
                component.name if component else placement.component_id,
                f"{placement.x_mm:.2f}",
                f"{placement.y_mm:.2f}",
                f"{placement.rotation_deg:.1f}°",
                placement.side.zh,
                "跳过" if placement.skip else "贴装",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column in (0, 3, 4, 5, 6, 7):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if placement.skip:
                    item.setForeground(QColor(COLORS["faint"]))
                elif column == 7:
                    item.setForeground(QColor(COLORS["success"]))
                self.table.setItem(row, column, item)
            self._row_by_ref[placement.refdes] = row
            if placement.refdes == selected:
                self.table.selectRow(row)
        self.table_count_chip.setText(str(len(self._product.placements)))
        self.board_points_chip.setText(f"{len(self._product.placements)} 点")

    # ---------------- dirty ----------------

    def _mark_dirty(self, *_: Any) -> None:
        if self._loading or self._product is None:
            return
        self._dirty = True
        self._update_dirty_ui()

    def _update_dirty_ui(self) -> None:
        if self._dirty:
            self.dirty_chip.setText("有未保存修改")
            self.dirty_chip.setProperty("chip", "true")
            self.dirty_chip.setStyleSheet(
                f"background: {COLORS['warn']}18; border: 1px solid {COLORS['warn']}55;"
                f" color: {COLORS['warn']}; border-radius: 10px; padding: 3px 9px; font-size: 11px;"
            )
            self.save_button.setText("保存产品 *")
        else:
            self.dirty_chip.setText("已保存")
            self.dirty_chip.setStyleSheet("")
            self.dirty_chip.setProperty("chip", "accent")
            self.save_button.setText("保存产品")
        self.dirty_chip.style().unpolish(self.dirty_chip)
        self.dirty_chip.style().polish(self.dirty_chip)

    def _collect(self) -> Product:
        assert self._product is not None
        product = self._product
        product.name = self.name_edit.text().strip() or "未命名产品"
        product.revision = self.revision_edit.text().strip() or "A"
        product.board_width_mm = self.width_spin.value()
        product.board_height_mm = self.height_spin.value()
        product.board_thickness_mm = self.thickness_spin.value()
        product.board_origin_x_mm = self.origin_x_spin.value()
        product.board_origin_y_mm = self.origin_y_spin.value()
        product.notes = self.notes_edit.text().strip()
        product.updated_at = now_iso()
        return product

    # ---------------- product actions ----------------

    def _save(self) -> None:
        if self._product is None:
            return
        if not self.name_edit.text().strip():
            self.ctx.toast("产品名称不能为空", "warning")
            self.name_edit.setFocus()
            return
        product = self._collect()
        self._dirty = False
        self.ctx.save_product(product)
        self._loading = True
        self._populate_table()
        self.board.set_product(product, self.ctx.components())
        self.board.set_limits(self.ctx.settings.limits.travel_x_mm, self.ctx.settings.limits.travel_y_mm)
        self._loading = False
        self._update_dirty_ui()
        self.ctx.toast(f"产品 {product.name} 已保存", "success")

    def _new_product(self) -> None:
        name, ok = QInputDialog.getText(self, "新建产品", "产品名称：", text="新产品")
        if not ok or not name.strip():
            return
        if self._dirty and not self._confirm_discard():
            return
        travel = self.ctx.settings.limits
        width, height = 160.0, 100.0
        product = Product(
            id=new_id("PRD-"),
            name=name.strip(),
            revision="A",
            board_width_mm=width,
            board_height_mm=height,
            board_origin_x_mm=max(0.0, (travel.travel_x_mm - width) / 2),
            board_origin_y_mm=max(0.0, (travel.travel_y_mm - height) / 2),
            fiducials=[
                Fiducial("FID1", 6.0, 6.0, 1.2),
                Fiducial("FID2", width - 6.0, 6.0, 1.2),
                Fiducial("FID3", width / 2, height - 6.0, 1.2),
            ],
            notes="新建产品",
        )
        self.ctx.save_product(product)
        self._load_product(product)
        self.ctx.toast("产品已创建，请添加贴装点或导入 CSV", "success")

    def _duplicate_product(self) -> None:
        if self._product is None:
            return
        try:
            clone = self.ctx.storage.duplicate_product(self._product.id)
        except ValueError as exc:
            self.ctx.toast(str(exc), "error")
            return
        self.ctx.signals.products_changed.emit()
        self.ctx.select_product(clone.id)
        self._load_product(clone)
        self.ctx.toast("已复制产品", "success")

    def _delete_product(self) -> None:
        if self._product is None:
            return
        dialog = ConfirmDeleteDialog(
            "删除产品",
            f"确定删除“{self._product.name}”？所有贴装点数据将被移除。",
            self,
        )
        if dialog.exec():
            self.ctx.storage.delete_product(self._product.id)
            self.ctx.log("WARN", "PROGRAM", f"删除产品 {self._product.name}")
            self.ctx.signals.products_changed.emit()
            self._product = None
            self.ctx.current_product_id = ""
            self.refresh(force=True)
            self.ctx.toast("产品已删除", "info")

    def _confirm_discard(self) -> bool:
        answer = QMessageBox.question(
            self,
            "未保存修改",
            "当前产品有未保存修改，是否保存？",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
        )
        if answer == QMessageBox.StandardButton.Cancel:
            return False
        if answer == QMessageBox.StandardButton.Save:
            self._save()
        return True

    # ---------------- points ----------------

    def _selected_row(self) -> int:
        rows = self.table.selectionModel().selectedRows()
        return rows[0].row() if rows else -1

    def _add_point(self) -> None:
        if self._product is None:
            self.ctx.toast("请先新建或选择产品", "warning")
            return
        components = self.ctx.components()
        if not components:
            self.ctx.toast("请先在元件库创建元件", "warning")
            return
        dialog = PlacementDialog(components, None, self)
        if dialog.exec():
            placement = dialog.result_placement()
            if any(p.refdes == placement.refdes for p in self._product.placements):
                self.ctx.toast(f"位号 {placement.refdes} 已存在", "error")
                return
            self._product.placements.append(placement)
            self._mark_dirty()
            self._populate_table()
            self.board.set_product(self._product, components)
            self.board.set_selected(placement.refdes)
            row = self._row_by_ref.get(placement.refdes, 0)
            self.table.selectRow(row)
            self.table.scrollToItem(self.table.item(row, 0), QAbstractItemView.ScrollHint.PositionAtCenter)

    def _edit_point(self) -> None:
        if self._product is None:
            return
        row = self._selected_row()
        if row < 0:
            self.ctx.toast("请先选择贴装点", "warning")
            return
        if row >= len(self._product.placements):
            return
        source = self._product.placements[row]
        dialog = PlacementDialog(self.ctx.components(), source, self)
        if dialog.exec():
            update = dialog.result_placement()
            if update.refdes != source.refdes and any(p.refdes == update.refdes for p in self._product.placements):
                self.ctx.toast(f"位号 {update.refdes} 已存在", "error")
                return
            self._product.placements[row] = update
            self._mark_dirty()
            self._populate_table()
            self.board.set_product(self._product, self.ctx.components())
            self.board.set_selected(update.refdes)
            self.table.selectRow(row)

    def _remove_point(self) -> None:
        if self._product is None:
            return
        row = self._selected_row()
        if row < 0 or row >= len(self._product.placements):
            self.ctx.toast("请先选择贴装点", "warning")
            return
        placement = self._product.placements[row]
        answer = QMessageBox.question(
            self,
            "删除贴装点",
            f"删除 {placement.refdes}？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            del self._product.placements[row]
            self._mark_dirty()
            self._populate_table()
            self.board.set_product(self._product, self.ctx.components())

    # ---------------- selection ----------------

    def _on_table_selected(self) -> None:
        row = self._selected_row()
        if row < 0 or not self._product or row >= len(self._product.placements):
            return
        refdes = self._product.placements[row].refdes
        self.board.set_selected(refdes)

    def _on_board_selected(self, refdes: str) -> None:
        row = self._row_by_ref.get(refdes)
        if row is not None:
            self.table.selectRow(row)
            self.table.scrollToItem(self.table.item(row, 0), QAbstractItemView.ScrollHint.PositionAtCenter)

    # ---------------- combo / signals ----------------

    def _on_combo_changed(self, index: int) -> None:
        if self._loading:
            return
        product_id = self.product_combo.itemData(index)
        if not product_id or (self._product and product_id == self._product.id):
            return
        if self._dirty and not self._confirm_discard():
            self._loading = True
            current = self.product_combo.findData(self._product.id if self._product else "")
            if current >= 0:
                self.product_combo.setCurrentIndex(current)
            self._loading = False
            return
        self.ctx.select_product(str(product_id))
        product = self.ctx.storage.get_product(str(product_id))
        self._load_product(product)

    def _on_products_changed(self) -> None:
        if self._dirty:
            return
        self.refresh()

    def _on_product_changed(self, product: Any) -> None:
        if product is None or self._dirty:
            return
        if self._product is None or product.id != self._product.id:
            self._load_product(product)

    def _on_components_changed(self) -> None:
        self.board.set_components(self.ctx.components())
        self._populate_table()

    # ---------------- import / export ----------------

    def _ensure_product(self) -> bool:
        if self._product is None:
            self.ctx.toast("请先新建或选择产品", "warning")
            return False
        return True

    def _import_csv(self) -> None:
        if not self._ensure_product():
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            "导入贴装坐标",
            str(self.ctx.paths.exports),
            "坐标文件 (*.csv *.txt *.tsv *.pos *.xml);;所有文件 (*)",
        )
        if not path:
            return
        try:
            text, encoding = read_position_file(path)
        except Exception as exc:  # PositionImportError / OSError
            QMessageBox.critical(self, "导入失败", str(exc))
            return
        dialog = ImportWizardDialog(text, Path(path).name, self)
        if not dialog.exec() or dialog.result_data is None:
            return
        result: ImportResult = dialog.result_data
        assert self._product is not None
        existing = {p.refdes for p in self._product.placements}
        duplicates = [p.refdes for p in result.placements if p.refdes in existing]
        mode = "replace"
        if self._product.placements:
            box = QMessageBox(self)
            box.setWindowTitle("导入方式")
            box.setText(
                f"解析到 {len(result.placements)} 个贴装点、{len(result.components)} 种元件。\n"
                f"当前产品已有 {len(self._product.placements)} 个点，选择导入方式："
            )
            replace_button = box.addButton("替换现有", QMessageBox.ButtonRole.DestructiveRole)
            append_button = box.addButton("追加合并", QMessageBox.ButtonRole.AcceptRole)
            box.addButton("取消", QMessageBox.ButtonRole.RejectRole)
            box.exec()
            if box.clickedButton() is replace_button:
                mode = "replace"
            elif box.clickedButton() is append_button:
                mode = "append"
            else:
                return
        if mode == "replace":
            self._product.placements = list(result.placements)
        else:
            by_ref = {p.refdes: i for i, p in enumerate(self._product.placements)}
            for placement in result.placements:
                if placement.refdes in by_ref:
                    self._product.placements[by_ref[placement.refdes]] = placement
                else:
                    self._product.placements.append(placement)

        # 元件落库 + 封装自动匹配
        existing_components = {c.id for c in self.ctx.storage.list_components()}
        added = matched = likely = 0
        unmatched: list[str] = []
        for component in result.components:
            if component.id in existing_components:
                continue
            match = self.ctx.package_library.match(
                component.package,
                body_hint=(component.length_mm, component.width_mm),
            )
            if match.package is not None:
                component.package_id = match.package.id
                component.match_score = match.score
                if match.status == "matched":
                    component.length_mm = match.package.length_mm
                    component.width_mm = match.package.width_mm
                    component.height_mm = match.package.height_mm
                    if match.package.nozzle:
                        component.nozzle = match.package.nozzle
                    try:
                        component.vision_mode = VisionMode(match.package.vision_mode)
                    except ValueError:
                        pass
                    matched += 1
                else:
                    likely += 1
                    unmatched.append(f"{component.package} → {match.package.name}（{match.score:.0%}，未自动套用）")
            else:
                unmatched.append(component.package or component.name)
            self.ctx.storage.save_component(component)
            added += 1
        self.ctx.signals.components_changed.emit()

        if result.fiducials and not self._product.fiducials:
            self._product.fiducials = list(result.fiducials)
            self.ctx.log("INFO", "IMPORT", f"导入 {len(result.fiducials)} 个基准点")

        self._mark_dirty()
        self._populate_table()
        self.board.set_product(self._product, self.ctx.components())
        self.board_points_chip.setText(f"{len(self._product.placements)} 点")
        message = f"已导入 {len(result.placements)} 点"
        if added:
            message += f"，新建 {added} 种元件"
        if matched:
            message += f"，{matched} 种封装匹配"
        if duplicates and mode == "append":
            message += f"，覆盖 {len(duplicates)} 个同位号点"
        self.ctx.toast(message + "，请检查后保存", "success")
        self.ctx.log(
            "INFO",
            "IMPORT",
            f"{result.format} 导入 {path}（{encoding}）：{len(result.placements)} 点 · "
            f"封装匹配 {matched}/{added} · 疑似 {likely} · 未知 {len(unmatched) - likely}",
        )
        issues = [ValidationIssue("warning", "IMPORT", warning) for warning in result.warnings]
        if unmatched:
            preview = "；".join(unmatched[:6])
            issues.append(
                ValidationIssue(
                    "warning",
                    "PACKAGE_MATCH",
                    f"{len(unmatched)} 种封装未确认或未匹配：{preview}"
                    + ("…" if len(unmatched) > 6 else "")
                    + "。可在“封装库”页做批量匹配。",
                )
            )
        if issues:
            IssuesDialog(issues, self).exec()

    def _export_csv(self) -> None:
        if not self._ensure_product():
            return
        product = self._collect()
        default = self.ctx.paths.exports / f"{product.name.replace(' ', '_')}_centroid.csv"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "导出贴装坐标",
            str(default),
            "CSV 文件 (*.csv)",
        )
        if not path:
            return
        try:
            content = export_centroid_csv(product, self.ctx.components())
            Path(path).write_text(content, encoding="utf-8-sig")
        except OSError as exc:
            QMessageBox.critical(self, "导出失败", str(exc))
            return
        self.ctx.log("INFO", "EXPORT", f"导出贴装坐标 {path}")
        self.ctx.toast(f"已导出 {len(product.placements)} 个贴装点", "success")
