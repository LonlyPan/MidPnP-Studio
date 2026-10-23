"""供料器管理页。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QProgressBar,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...core.models import Feeder
from ..context import AppContext
from ..dialogs import ConfirmDeleteDialog, FeederDialog
from ..icons import icon
from ..theme import COLORS
from ..widgets import (
    Card,
    InfoRow,
    MetricCard,
    PageHeader,
    RingProgress,
    button,
    make_chip,
)


class FeedersPage(QWidget):
    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self._feeders: list[Feeder] = []
        self._selected_id = ""
        self._build()
        self._connect()
        self.refresh()

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(14)
        self.header = PageHeader("供料器", "管理料站、余料与取料坐标")
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索槽位 / 元件…")
        self.search.setFixedWidth(210)
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._apply_filter)
        self.add_button = button("装载供料器", "plus", "primary")
        self.refresh_button = button("刷新", "refresh", "subtle")
        self.header.add_action(self.search)
        self.header.add_action(self.refresh_button)
        self.header.add_action(self.add_button)
        outer.addWidget(self.header)

        metrics = QHBoxLayout()
        metrics.setSpacing(12)
        self.metric_loaded = MetricCard("已装载", "0", "台", "feeder", COLORS["accent"])
        self.metric_low = MetricCard("低料预警", "0", "台", "warning", COLORS["warn"])
        self.metric_empty = MetricCard("空料", "0", "台", "trash", COLORS["danger"])
        self.metric_slots = MetricCard("可用槽位", "0", "个", "layers", COLORS["blue"])
        for card in (self.metric_loaded, self.metric_low, self.metric_empty, self.metric_slots):
            metrics.addWidget(card, 1)
        outer.addLayout(metrics)

        body = QHBoxLayout()
        body.setSpacing(12)
        table_card = Card(padding=12)
        table_top = QHBoxLayout()
        title = QLabel("料站配置")
        title.setProperty("role", "section")
        table_top.addWidget(title)
        self.count_chip = make_chip("0 台")
        table_top.addWidget(self.count_chip)
        table_top.addStretch(1)
        hint = QLabel("双击行编辑 · 低料阈值 15%")
        hint.setProperty("role", "faint")
        table_top.addWidget(hint)
        table_card.body.addLayout(table_top)
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(
            ["槽位", "元件", "封装", "取料点 (mm)", "余料", "状态", "启用", "标签"]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setDefaultSectionSize(48)
        self.table.doubleClicked.connect(lambda *_: self._edit())
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(0, 64)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(2, 90)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(3, 130)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(4, 210)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(5, 88)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(6, 64)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(7, 150)
        self.table.itemSelectionChanged.connect(self._on_selection)
        table_card.body.addWidget(self.table, 1)
        body.addWidget(table_card, 1)

        detail = Card(padding=16)
        detail.setFixedWidth(318)
        detail_top = QHBoxLayout()
        detail_title = QLabel("供料器详情")
        detail_title.setProperty("role", "section")
        detail_top.addWidget(detail_title)
        detail_top.addStretch(1)
        self.detail_chip = make_chip("—")
        detail_top.addWidget(self.detail_chip)
        detail.body.addLayout(detail_top)
        self.detail_slot = QLabel("未选择")
        self.detail_slot.setStyleSheet("font-family: 'Cascadia Mono'; font-size: 28px; font-weight: 700;")
        detail.body.addWidget(self.detail_slot)
        self.detail_component = QLabel("从左侧选择一个料站")
        self.detail_component.setProperty("role", "muted")
        self.detail_component.setWordWrap(True)
        detail.body.addWidget(self.detail_component)
        self.ring = RingProgress(size=130)
        ring_row = QHBoxLayout()
        ring_row.addStretch(1)
        ring_row.addWidget(self.ring)
        ring_row.addStretch(1)
        detail.body.addLayout(ring_row)
        self.info_capacity = InfoRow("容量", "—")
        self.info_pick = InfoRow("取料点", "—")
        self.info_pitch = InfoRow("料带间距", "—")
        self.info_low = InfoRow("低料阈值", "—")
        self.info_enabled = InfoRow("启用状态", "—")
        for row in (self.info_capacity, self.info_pick, self.info_pitch, self.info_low, self.info_enabled):
            detail.body.addWidget(row)
        detail.body.addStretch(1)
        self.refill_button = button("补满余料", "refresh", "primary")
        self.edit_button = button("编辑", "edit", "subtle")
        self.toggle_button = button("停用", "pause", "subtle")
        self.delete_button = button("删除", "trash", "danger")
        detail.body.addWidget(self.refill_button)
        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        action_row.addWidget(self.edit_button, 1)
        action_row.addWidget(self.toggle_button, 1)
        detail.body.addLayout(action_row)
        detail.body.addWidget(self.delete_button)
        body.addWidget(detail)
        outer.addLayout(body, 1)

        self.add_button.clicked.connect(self._add)
        self.refresh_button.clicked.connect(self.refresh)
        self.edit_button.clicked.connect(self._edit)
        self.delete_button.clicked.connect(self._delete)
        self.toggle_button.clicked.connect(self._toggle)
        self.refill_button.clicked.connect(self._refill)
        self._set_detail(None)

    def _connect(self) -> None:
        self.ctx.signals.feeders_changed.connect(self.refresh)
        self.ctx.signals.components_changed.connect(self.refresh)

    def refresh(self) -> None:
        self._feeders = self.ctx.storage.list_feeders()
        self._populate()
        self._update_metrics()
        if self._feeders and not self._selected_id:
            self.table.selectRow(0)
        if self._selected_id:
            feeder = next((f for f in self._feeders if f.id == self._selected_id), None)
            self._set_detail(feeder)
        else:
            self._set_detail(None)

    def _populate(self) -> None:
        components = self.ctx.component_map()
        self.table.setRowCount(len(self._feeders))
        for row, feeder in enumerate(self._feeders):
            component = components.get(feeder.component_id)
            items = [
                f"{feeder.slot:02d}",
                component.name if component else feeder.component_id,
                component.package if component else "—",
                f"{feeder.pick_x_mm:.1f}, {feeder.pick_y_mm:.1f}",
                "",
                "",
                "启用" if feeder.enabled else "停用",
                feeder.label or "—",
            ]
            for column, value in enumerate(items):
                item = QTableWidgetItem(value)
                if column in (0, 2, 3, 4, 5, 6):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if not feeder.enabled:
                    item.setForeground(QColor(COLORS["faint"]))
                self.table.setItem(row, column, item)
            self.table.setCellWidget(row, 4, self._stock_widget(feeder))
            status_item = QTableWidgetItem(
                "空料" if feeder.is_empty else ("低料" if feeder.is_low else "正常")
            )
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            color = COLORS["danger"] if feeder.is_empty else (COLORS["warn"] if feeder.is_low else COLORS["success"])
            status_item.setForeground(QColor(color))
            self.table.setItem(row, 5, status_item)
            self.table.item(row, 0).setData(Qt.ItemDataRole.UserRole, feeder.id)
        self.count_chip.setText(f"{len(self._feeders)} 台")
        self._apply_filter()

    def _stock_widget(self, feeder: Feeder) -> QWidget:
        widget = QWidget()
        widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(6, 5, 6, 5)
        layout.setSpacing(3)
        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(feeder.remaining_pct)
        bar.setTextVisible(False)
        bar.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        color = COLORS["danger"] if feeder.is_empty else (COLORS["warn"] if feeder.is_low else COLORS["accent"])
        bar.setStyleSheet(
            f"QProgressBar {{ background: {COLORS['surface3']}; border-radius: 3px; max-height: 5px; }}"
            f"QProgressBar::chunk {{ background: {color}; border-radius: 3px; }}"
        )
        text = QLabel(f"{feeder.remaining:,} / {feeder.capacity:,}  ·  {feeder.remaining_pct}%")
        text.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        text.setStyleSheet("font-family: 'Cascadia Mono'; font-size: 10px; color: #93a8b4;")
        layout.addWidget(bar)
        layout.addWidget(text)
        return widget

    def _update_metrics(self) -> None:
        low = sum(1 for f in self._feeders if f.is_low and not f.is_empty)
        empty = sum(1 for f in self._feeders if f.is_empty)
        max_slots = 40
        self.metric_loaded.set(str(len(self._feeders)), f"共 {max_slots} 个物理槽位")
        self.metric_low.set(str(low), "建议尽快补料")
        self.metric_empty.set(str(empty), "无余料，无法取料")
        self.metric_slots.set(str(max(0, max_slots - len(self._feeders))), "可继续装载")

    def _apply_filter(self) -> None:
        needle = self.search.text().strip().lower()
        components = self.ctx.component_map()
        for row, feeder in enumerate(self._feeders):
            component = components.get(feeder.component_id)
            haystack = f"{feeder.slot} {feeder.label} {component.name if component else ''} {component.package if component else ''}".lower()
            self.table.setRowHidden(row, bool(needle) and needle not in haystack)

    def _on_selection(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            self._selected_id = ""
            self._set_detail(None)
            return
        row = rows[0].row()
        feeder_id = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        self._selected_id = str(feeder_id)
        feeder = next((f for f in self._feeders if f.id == self._selected_id), None)
        self._set_detail(feeder)

    def _set_detail(self, feeder: Feeder | None) -> None:
        enabled = feeder is not None
        for control in (self.edit_button, self.delete_button, self.toggle_button, self.refill_button):
            control.setEnabled(enabled)
        if feeder is None:
            self.detail_slot.setText("—")
            self.detail_component.setText("从左侧选择一个料站")
            self.detail_chip.setText("未选择")
            self.ring.set_progress(0, "0%", "余料", COLORS["faint"])
            for row in (self.info_capacity, self.info_pick, self.info_pitch, self.info_low, self.info_enabled):
                row.set("—")
            self.toggle_button.setText("停用")
            return
        components = self.ctx.component_map()
        component = components.get(feeder.component_id)
        self.detail_slot.setText(f"SLOT {feeder.slot:02d}")
        self.detail_component.setText(
            f"{component.name if component else feeder.component_id}\n{component.package if component else ''}"
        )
        color = COLORS["danger"] if feeder.is_empty else (COLORS["warn"] if feeder.is_low else COLORS["accent"])
        self.detail_chip.setText("空料" if feeder.is_empty else ("低料" if feeder.is_low else "正常"))
        self.detail_chip.setStyleSheet(
            f"background: {color}16; border: 1px solid {color}55; color: {color};"
            "border-radius: 10px; padding: 3px 9px; font-size: 11px; font-weight: 700;"
        )
        self.ring.set_progress(feeder.remaining_pct, f"{feeder.remaining_pct}%", "余料", color)
        self.info_capacity.set(f"{feeder.remaining:,} / {feeder.capacity:,}")
        self.info_pick.set(f"{feeder.pick_x_mm:.1f}, {feeder.pick_y_mm:.1f}")
        self.info_pitch.set(f"{feeder.pitch_mm:.2f} mm")
        self.info_low.set(f"{feeder.low_threshold_pct}%")
        self.info_enabled.set("已启用" if feeder.enabled else "已停用", COLORS["accent"] if feeder.enabled else COLORS["faint"])
        self.toggle_button.setText("停用" if feeder.enabled else "启用")
        self.toggle_button.setIcon(icon("pause" if feeder.enabled else "play", COLORS["text"], 16))

    def _next_slot(self) -> int:
        used = {f.slot for f in self._feeders}
        for slot in range(1, 41):
            if slot not in used:
                return slot
        return 40

    def _add(self) -> None:
        components = self.ctx.components()
        if not components:
            self.ctx.toast("请先在元件库创建元件", "warning")
            return
        dialog = FeederDialog(components, None, self._next_slot(), self)
        if dialog.exec():
            self._save_feeder(dialog.result_feeder(), editing=False)

    def _edit(self) -> None:
        feeder = next((f for f in self._feeders if f.id == self._selected_id), None)
        if feeder is None:
            self.ctx.toast("请先选择供料器", "warning")
            return
        dialog = FeederDialog(self.ctx.components(), feeder, feeder.slot, self)
        if dialog.exec():
            self._save_feeder(dialog.result_feeder(), editing=True)

    def _save_feeder(self, feeder: Feeder, editing: bool) -> None:
        try:
            self.ctx.storage.save_feeder(feeder)
        except ValueError as exc:
            self.ctx.toast(str(exc), "error")
            return
        self._selected_id = feeder.id
        self.ctx.signals.feeders_changed.emit()
        if self.ctx.connected:
            self.ctx.machine.sync_feeders(self.ctx.feeders())
        self.ctx.log("INFO", "FEEDER", f"{'更新' if editing else '装载'}供料器槽位 {feeder.slot:02d}")
        self.ctx.toast(f"槽位 {feeder.slot:02d} 已{'更新' if editing else '装载'}", "success")
        self.refresh()

    def _delete(self) -> None:
        feeder = next((f for f in self._feeders if f.id == self._selected_id), None)
        if feeder is None:
            return
        dialog = ConfirmDeleteDialog(
            "删除供料器",
            f"确定移除槽位 {feeder.slot:02d} 的供料器配置？",
            self,
        )
        if dialog.exec():
            self.ctx.storage.delete_feeder(feeder.id)
            self._selected_id = ""
            self.ctx.signals.feeders_changed.emit()
            if self.ctx.connected:
                self.ctx.machine.sync_feeders(self.ctx.feeders())
            self.ctx.log("WARN", "FEEDER", f"移除供料器槽位 {feeder.slot:02d}")
            self.ctx.toast("供料器已移除", "info")
            self.refresh()

    def _toggle(self) -> None:
        feeder = next((f for f in self._feeders if f.id == self._selected_id), None)
        if feeder is None:
            return
        feeder.enabled = not feeder.enabled
        self.ctx.storage.save_feeder(feeder)
        self.ctx.signals.feeders_changed.emit()
        if self.ctx.connected:
            self.ctx.machine.sync_feeders(self.ctx.feeders())
        self.ctx.log("INFO", "FEEDER", f"槽位 {feeder.slot:02d} 已{'启用' if feeder.enabled else '停用'}")
        self.refresh()

    def _refill(self) -> None:
        feeder = next((f for f in self._feeders if f.id == self._selected_id), None)
        if feeder is None:
            return
        amount, ok = QInputDialog.getInt(
            self,
            "补料",
            f"槽位 {feeder.slot:02d} 当前余料 {feeder.remaining:,}。\n补料后余料数量：",
            feeder.capacity,
            0,
            100000,
            100,
        )
        if not ok:
            return
        feeder.remaining = amount
        self.ctx.storage.save_feeder(feeder)
        self.ctx.signals.feeders_changed.emit()
        if self.ctx.connected:
            self.ctx.machine.sync_feeders(self.ctx.feeders())
        self.ctx.log("INFO", "FEEDER", f"槽位 {feeder.slot:02d} 补料至 {amount:,}")
        self.ctx.toast("补料完成", "success")
        self.refresh()
