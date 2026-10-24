"""封装库页：封装定义浏览、同义名维护与封装自动匹配。"""

from __future__ import annotations

from collections import Counter
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...core.models import VisionMode
from ...core.packages import PackageDef, default_package_paths
from ..context import AppContext
from ..dialogs import PackageDialog
from ..theme import COLORS
from ..widgets import Card, InfoRow, PageHeader, button, hline, make_chip


def _vision_label(mode: str) -> str:
    try:
        return VisionMode(mode).zh
    except ValueError:
        return mode or "—"


class PackagesPage(QWidget):
    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self._packages: list[PackageDef] = []
        self._selected_id = ""
        self._build()
        self._connect()
        self.refresh()

    # ---------------- UI ----------------

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(14)
        self.header = PageHeader("封装库", "封装定义、同义名归一与导入自动匹配")
        self.count_chip = make_chip("0")
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索封装名 / 同义名…")
        self.search.setFixedWidth(210)
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._apply_filter)
        self.new_button = button("新建封装", "plus", "primary")
        self.reload_button = button("重新加载", "refresh", "subtle")
        self.match_library_button = button("匹配元件库", "target", "subtle")
        for widget in (self.count_chip, self.search, self.match_library_button, self.reload_button, self.new_button):
            self.header.add_action(widget)
        outer.addWidget(self.header)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        table_card = Card(padding=12)
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(["封装", "类别", "本体 L×W×H", "引脚", "吸嘴", "视觉", "来源", "说明"])
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(0, 120)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(1, 72)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(2, 172)
        for column, width in ((3, 48), (4, 50), (5, 82), (6, 58)):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
            header.resizeSection(column, width)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self._on_selected)
        table_card.body.addWidget(self.table, 1)
        hint = QLabel("封装库为 JSON 配置：内置库随程序发布，自定义封装保存在数据目录 packages.json。")
        hint.setProperty("role", "faint")
        hint.setWordWrap(True)
        table_card.body.addWidget(hint)
        splitter.addWidget(table_card)

        panel = QWidget()
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(12)

        tester = Card()
        title_row = QHBoxLayout()
        title = QLabel("封装匹配")
        title.setProperty("role", "section")
        title_row.addWidget(title)
        title_row.addStretch(1)
        title_row.addWidget(make_chip("模糊匹配"))
        tester.body.addLayout(title_row)
        tester_hint = QLabel("输入 EDA 导出的封装名（如 R-0603_1608Metric、SOP8、QFN32_5x5），按同义名与尺寸打分。")
        tester_hint.setProperty("role", "hint")
        tester_hint.setWordWrap(True)
        tester.body.addWidget(tester_hint)
        self.match_input = QLineEdit()
        self.match_input.setPlaceholderText("封装名，例如 0603 / SOIC-8 / USB-C")
        self.match_input.returnPressed.connect(self._run_match)
        tester.body.addWidget(self.match_input)
        size_row = QHBoxLayout()
        size_row.setSpacing(8)
        size_label = QLabel("本体提示")
        size_label.setProperty("role", "muted")
        size_row.addWidget(size_label)
        self.match_length = self._dim_spin(1.6)
        self.match_width = self._dim_spin(0.8)
        size_row.addWidget(self.match_length)
        size_row.addWidget(QLabel("×"))
        size_row.addWidget(self.match_width)
        size_row.addWidget(QLabel("mm"))
        size_row.addStretch(1)
        tester.body.addLayout(size_row)
        self.match_button = button("执行匹配", "target", "subtle")
        self.match_button.clicked.connect(self._run_match)
        tester.body.addWidget(self.match_button)
        self.match_result = QLabel("等待输入封装名")
        self.match_result.setProperty("role", "muted")
        self.match_result.setWordWrap(True)
        tester.body.addWidget(self.match_result)
        self.match_rows: list[InfoRow] = []
        for _ in range(3):
            row = InfoRow("候选", "—")
            self.match_rows.append(row)
            tester.body.addWidget(row)
        panel_layout.addWidget(tester)

        detail = Card()
        detail_top = QHBoxLayout()
        title = QLabel("封装详情")
        title.setProperty("role", "section")
        detail_top.addWidget(title)
        detail_top.addStretch(1)
        self.detail_chip = make_chip("未选择")
        detail_top.addWidget(self.detail_chip)
        detail.body.addLayout(detail_top)
        self.info_name = InfoRow("名称", "—")
        self.info_category = InfoRow("类别", "—")
        self.info_body = InfoRow("本体尺寸", "—")
        self.info_pads = InfoRow("焊盘", "—")
        self.info_nozzle = InfoRow("默认吸嘴", "—")
        self.info_vision = InfoRow("视觉策略", "—")
        self.info_aliases = InfoRow("同义名", "—")
        for row in (
            self.info_name,
            self.info_category,
            self.info_body,
            self.info_pads,
            self.info_nozzle,
            self.info_vision,
            self.info_aliases,
        ):
            detail.body.addWidget(row)
        detail.body.addWidget(hline())
        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.edit_button = button("编辑", "edit", "subtle")
        self.delete_button = button("删除", "trash", "subtle")
        actions.addWidget(self.edit_button)
        actions.addWidget(self.delete_button)
        actions.addStretch(1)
        detail.body.addLayout(actions)
        panel_layout.addWidget(detail)
        panel_layout.addStretch(1)
        splitter.addWidget(panel)
        splitter.setStretchFactor(0, 7)
        splitter.setStretchFactor(1, 4)
        splitter.setSizes([760, 460])
        outer.addWidget(splitter, 1)

        self.new_button.clicked.connect(self._new_package)
        self.reload_button.clicked.connect(self._reload)
        self.match_library_button.clicked.connect(self._match_component_library)
        self.edit_button.clicked.connect(self._edit_package)
        self.delete_button.clicked.connect(self._delete_package)

    def _dim_spin(self, value: float) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(0.0, 100.0)
        spin.setDecimals(2)
        spin.setSingleStep(0.05)
        spin.setValue(value)
        spin.setSuffix(" mm")
        spin.setFixedWidth(86)
        return spin

    def _connect(self) -> None:
        self.ctx.signals.packages_changed.connect(self.refresh)
        self.ctx.signals.components_changed.connect(self.refresh)

    # ---------------- 数据 ----------------

    def refresh(self) -> None:
        selected = self._selected_id
        self._packages = self.ctx.package_library.list()
        self.count_chip.setText(str(len(self._packages)))
        self._populate()
        if selected:
            self._select(selected)

    def _populate(self) -> None:
        query = self.search.text().strip().lower()
        visible = [
            package
            for package in self._packages
            if not query
            or query in package.name.lower()
            or any(query in alias.lower() for alias in package.aliases)
            or query in package.category.lower()
        ]
        self.table.setRowCount(len(visible))
        for row, package in enumerate(visible):
            pads = len(package.derived_pads())
            values = [
                package.name,
                self._category_label(package.category),
                f"{package.length_mm:.2f} × {package.width_mm:.2f} × {package.height_mm:.2f}",
                str(package.pin_count) if package.pin_count else "—",
                package.nozzle or "—",
                _vision_label(package.vision_mode),
                "内置" if package.builtin else "自定义",
                package.notes or (f"焊盘 {pads} 个" if pads else ""),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column in (1, 3, 4, 5, 6):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if column == 6:
                    item.setForeground(Qt.GlobalColor.gray if package.builtin else Qt.GlobalColor.white)
                self.table.setItem(row, column, item)
            if package.id == self._selected_id:
                self.table.selectRow(row)

    def _apply_filter(self) -> None:
        self._populate()

    def _category_label(self, category: str) -> str:
        return {
            "chip": "片式",
            "ic": "IC",
            "transistor": "管类",
            "led": "LED",
            "inductor": "电感",
            "connector": "连接器",
            "fiducial": "基准点",
            "other": "其他",
        }.get(category, category)

    def _select(self, package_id: str) -> None:
        self._selected_id = package_id
        package = self.ctx.package_library.get(package_id)
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item and item.text() == (package.name if package else ""):
                self.table.selectRow(row)
                break
        self._show_detail(package)

    def _selected_package(self) -> PackageDef | None:
        if not self._selected_id:
            return None
        return self.ctx.package_library.get(self._selected_id)

    def _on_selected(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
        name = self.table.item(rows[0].row(), 0).text()
        for package in self._packages:
            if package.name == name:
                self._selected_id = package.id
                self._show_detail(package)
                self.match_input.setText(package.name)
                self.match_length.setValue(package.length_mm)
                self.match_width.setValue(package.width_mm)
                break

    def _show_detail(self, package: PackageDef | None) -> None:
        if package is None:
            self.detail_chip.setText("未选择")
            for row in (self.info_name, self.info_category, self.info_body, self.info_pads, self.info_nozzle, self.info_vision, self.info_aliases):
                row.set("—")
            self.edit_button.setEnabled(False)
            self.delete_button.setEnabled(False)
            return
        self.detail_chip.setText("内置" if package.builtin else "自定义")
        self.info_name.set(package.name)
        self.info_category.set(self._category_label(package.category))
        self.info_body.set(f"{package.length_mm:.2f} × {package.width_mm:.2f} × {package.height_mm:.2f} mm")
        self.info_pads.set(
            f"{len(package.derived_pads())} 个 · {package.pin_count} 引脚 · 间距 {package.pad_pitch_mm:.2f} mm"
        )
        self.info_nozzle.set(package.nozzle or "—")
        self.info_vision.set(_vision_label(package.vision_mode))
        self.info_aliases.set("、".join(package.aliases) if package.aliases else "—")
        self.edit_button.setEnabled(True)
        self.delete_button.setEnabled(not package.builtin)

    # ---------------- 操作 ----------------

    def _new_package(self) -> None:
        dialog = PackageDialog(None, self)
        if not dialog.exec():
            return
        try:
            self.ctx.save_package(dialog.result_package())
        except OSError as exc:
            QMessageBox.critical(self, "保存失败", str(exc))
            return
        self._selected_id = dialog.result_package().id
        self.refresh()
        self.ctx.toast("封装已创建", "success")

    def _edit_package(self) -> None:
        package = self._selected_package()
        if package is None:
            return
        if package.builtin:
            answer = QMessageBox.question(
                self,
                "编辑内置封装",
                "内置封装随程序发布。保存会生成同 ID 的用户封装覆盖它，继续？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        dialog = PackageDialog(package, self)
        if not dialog.exec():
            return
        try:
            self.ctx.save_package(dialog.result_package())
        except OSError as exc:
            QMessageBox.critical(self, "保存失败", str(exc))
            return
        self._selected_id = dialog.result_package().id
        self.refresh()
        self.ctx.toast("封装已保存", "success")

    def _delete_package(self) -> None:
        package = self._selected_package()
        if package is None:
            return
        if package.builtin:
            self.ctx.toast("内置封装不能删除，可改同义名或另建封装", "warning")
            return
        answer = QMessageBox.question(
            self,
            "删除封装",
            f"确定删除封装 {package.name}？引用它的元件会保留封装名但丢失封装 ID。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.ctx.package_library.remove(package.id)
        try:
            _builtin, user = default_package_paths(self.ctx.paths.root)
            self.ctx.package_library.save_user_file(user)
        except OSError as exc:
            QMessageBox.critical(self, "保存失败", str(exc))
            return
        self._selected_id = ""
        self.refresh()
        self.ctx.log("WARN", "PACKAGE", f"删除封装 {package.name}")
        self.ctx.toast("封装已删除", "info")

    def _reload(self) -> None:
        self.ctx.reload_packages()
        self.refresh()
        self.ctx.toast(f"已重新加载 {len(self.ctx.package_library)} 个封装", "info")

    # ---------------- 匹配 ----------------

    def _run_match(self) -> None:
        name = self.match_input.text().strip()
        if not name:
            self.match_result.setText("请输入封装名")
            return
        hint = None
        if self.match_length.value() > 0 and self.match_width.value() > 0:
            hint = (self.match_length.value(), self.match_width.value())
        candidates = self.ctx.package_library.suggest(name, hint, limit=3)
        if not candidates:
            self.match_result.setText(f"未找到与「{name}」相似的封装")
            for row in self.match_rows:
                row.set("—")
            return
        best = candidates[0]
        self.match_result.setText(
            f"最佳匹配 {best.package.name} · 得分 {best.score:.0%} · {best.reason}"
        )
        for row, candidate in zip(self.match_rows, candidates):
            row.set(
                f"{candidate.package.name} · {candidate.score:.0%} · {candidate.reason}",
                COLORS["accent"] if candidate is best else None,
            )
        if len(candidates) < len(self.match_rows):
            for row in self.match_rows[len(candidates):]:
                row.set("—")
        self.ctx.log("INFO", "PACKAGE", f"封装匹配 {name} → {best.package.name}（{best.score:.2f}）")

    def _match_component_library(self) -> None:
        components = self.ctx.components()
        if not components:
            self.ctx.toast("元件库为空", "warning")
            return
        counter = Counter(component.package for component in components)
        report = self.ctx.package_library.match_report(counter)
        matched = 0
        widened = 0
        for component in components:
            package = self.ctx.package_library.match(
                component.package,
                body_hint=(component.length_mm, component.width_mm),
            )
            if package.package is None:
                continue
            component.package_id = package.package.id
            component.match_score = package.score
            if package.status == "matched":
                component.length_mm = package.package.length_mm
                component.width_mm = package.package.width_mm
                component.height_mm = package.package.height_mm
                if package.package.nozzle:
                    component.nozzle = package.package.nozzle
                if package.package.vision_mode in VisionMode._value2member_map_:
                    component.vision_mode = VisionMode(package.package.vision_mode)
                self.ctx.storage.save_component(component)
                matched += 1
            else:
                widened += 1
        self.ctx.signals.components_changed.emit()
        message = f"封装匹配完成：确认 {matched} 个元件"
        if widened:
            message += f"，{widened} 个仅找到相似封装（未自动套用）"
        if report.unknown:
            message += f"，{len(report.unknown)} 种封装未知"
        self.ctx.log("INFO", "PACKAGE", message)
        self.ctx.toast(message, "success" if not report.unknown else "warning")
        self.match_result.setText(report.summary())
