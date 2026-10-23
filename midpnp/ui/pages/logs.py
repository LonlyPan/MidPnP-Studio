"""系统日志页。"""

from __future__ import annotations

import csv
import io
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFileDialog,
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

from ...core.models import LogEntry
from ..context import AppContext
from ..theme import COLORS
from ..widgets import Card, InfoRow, MetricCard, PageHeader, button, hline, make_chip


class LogsPage(QWidget):
    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self._entries: list[LogEntry] = []
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(200)
        self._refresh_timer.timeout.connect(self.refresh)
        self._auto_timer = QTimer(self)
        self._auto_timer.setInterval(4000)
        self._auto_timer.timeout.connect(self._auto_refresh)
        self._build()
        self._connect()
        self.refresh()

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(14)
        self.header = PageHeader("系统日志", "设备通信、生产事件与操作审计")
        self.level_combo = QComboBox()
        for level in ("全部", "INFO", "WARN", "ERROR", "DEBUG"):
            self.level_combo.addItem(level)
        self.level_combo.setFixedWidth(104)
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索内容 / 来源…")
        self.search.setFixedWidth(210)
        self.search.setClearButtonEnabled(True)
        self.auto_check = QCheckBox("自动刷新")
        self.auto_check.setChecked(True)
        self.export_button = button("导出 CSV", "download", "subtle")
        self.clear_button = button("清空", "trash", "subtle")
        self.refresh_button = button("刷新", "refresh", "subtle")
        self.header.add_action(self.level_combo)
        self.header.add_action(self.search)
        self.header.add_action(self.auto_check)
        self.header.add_action(self.export_button)
        self.header.add_action(self.clear_button)
        self.header.add_action(self.refresh_button)
        outer.addWidget(self.header)

        metrics = QHBoxLayout()
        metrics.setSpacing(12)
        self.metric_total = MetricCard("当前结果", "0", "条", "logs", COLORS["accent"])
        self.metric_error = MetricCard("错误", "0", "条", "warning", COLORS["danger"])
        self.metric_warn = MetricCard("警告", "0", "条", "warning", COLORS["warn"])
        self.metric_source = MetricCard("涉及模块", "0", "个", "layers", COLORS["blue"])
        for card in (self.metric_total, self.metric_error, self.metric_warn, self.metric_source):
            metrics.addWidget(card, 1)
        outer.addLayout(metrics)

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setChildrenCollapsible(False)
        table_card = Card(padding=12)
        top = QHBoxLayout()
        title = QLabel("事件记录")
        title.setProperty("role", "section")
        top.addWidget(title)
        self.count_chip = make_chip("0 条")
        top.addWidget(self.count_chip)
        top.addStretch(1)
        self.last_refresh = QLabel("")
        self.last_refresh.setProperty("role", "faint")
        top.addWidget(self.last_refresh)
        table_card.body.addLayout(top)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["时间", "级别", "来源", "消息"])
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setDefaultSectionSize(30)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(0, 156)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(1, 78)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(2, 110)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self._on_selection)
        table_card.body.addWidget(self.table, 1)
        splitter.addWidget(table_card)

        detail_card = Card(padding=14)
        detail_top = QHBoxLayout()
        detail_title = QLabel("事件详情")
        detail_title.setProperty("role", "section")
        detail_top.addWidget(detail_title)
        detail_top.addStretch(1)
        self.detail_chip = make_chip("—")
        detail_top.addWidget(self.detail_chip)
        detail_card.body.addLayout(detail_top)
        detail_row = QHBoxLayout()
        detail_row.setSpacing(28)
        self.detail_time = InfoRow("时间", "—")
        self.detail_source = InfoRow("来源", "—")
        self.detail_level = InfoRow("级别", "—")
        for row in (self.detail_time, self.detail_source, self.detail_level):
            detail_row.addWidget(row, 1)
        detail_card.body.addLayout(detail_row)
        detail_card.body.addWidget(hline())
        self.detail_message = QLabel("选择一条日志查看完整内容")
        self.detail_message.setWordWrap(True)
        self.detail_message.setStyleSheet("font-family: 'Cascadia Mono'; font-size: 12px; color: #c7d6dd;")
        detail_card.body.addWidget(self.detail_message, 1)
        splitter.addWidget(detail_card)
        splitter.setSizes([500, 150])
        outer.addWidget(splitter, 1)

        self.level_combo.currentTextChanged.connect(lambda *_: self.refresh())
        self.search.textChanged.connect(lambda *_: self._refresh_timer.start())
        self.auto_check.toggled.connect(self._on_auto_toggled)
        self.export_button.clicked.connect(self._export)
        self.clear_button.clicked.connect(self._clear)
        self.refresh_button.clicked.connect(self.refresh)
        self._auto_timer.start()

    def _connect(self) -> None:
        self.ctx.signals.log_added.connect(lambda *_: self._refresh_timer.start())

    def _on_auto_toggled(self, enabled: bool) -> None:
        if enabled:
            self._auto_timer.start()
        else:
            self._auto_timer.stop()

    def _auto_refresh(self) -> None:
        if self.isVisible() and self.auto_check.isChecked():
            self.refresh()

    def refresh(self) -> None:
        level = self.level_combo.currentText()
        self._entries = self.ctx.storage.list_logs(500, "" if level == "全部" else level, self.search.text().strip())
        self.table.setRowCount(len(self._entries))
        for row, entry in enumerate(self._entries):
            time_item = QTableWidgetItem(entry.timestamp.replace("T", " "))
            level_item = QTableWidgetItem(entry.level)
            source_item = QTableWidgetItem(entry.source)
            message_item = QTableWidgetItem(entry.message)
            color = {
                "ERROR": COLORS["danger"],
                "WARN": COLORS["warn"],
                "INFO": COLORS["accent"],
                "DEBUG": COLORS["faint"],
            }.get(entry.level, COLORS["muted"])
            level_item.setForeground(QColor(color))
            level_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            time_item.setForeground(QColor(COLORS["muted"]))
            source_item.setForeground(QColor(COLORS["blue"]))
            for column, item in enumerate((time_item, level_item, source_item, message_item)):
                self.table.setItem(row, column, item)
        self.count_chip.setText(f"{len(self._entries)} 条")
        self.metric_total.set(str(len(self._entries)), "按当前筛选条件")
        self.metric_error.set(str(sum(1 for e in self._entries if e.level == "ERROR")), "需要关注")
        self.metric_warn.set(str(sum(1 for e in self._entries if e.level == "WARN")), "建议检查")
        self.metric_source.set(str(len({e.source for e in self._entries})), "日志来源")
        self.last_refresh.setText(f"最后刷新 {datetime.now().strftime('%H:%M:%S')}")
        if self._entries:
            self.table.selectRow(0)
        else:
            self._set_detail(None)

    def _on_selection(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            self._set_detail(None)
            return
        row = rows[0].row()
        if 0 <= row < len(self._entries):
            self._set_detail(self._entries[row])

    def _set_detail(self, entry: LogEntry | None) -> None:
        if entry is None:
            self.detail_time.set("—")
            self.detail_source.set("—")
            self.detail_level.set("—")
            self.detail_message.setText("选择一条日志查看完整内容")
            self.detail_chip.setText("—")
            return
        self.detail_time.set(entry.timestamp.replace("T", " "))
        self.detail_source.set(entry.source)
        color = {
            "ERROR": COLORS["danger"],
            "WARN": COLORS["warn"],
            "INFO": COLORS["accent"],
        }.get(entry.level, COLORS["muted"])
        self.detail_level.set(entry.level, color)
        self.detail_message.setText(entry.message)
        self.detail_chip.setText(entry.level)
        self.detail_chip.setStyleSheet(
            f"background: {color}16; border: 1px solid {color}55; color: {color};"
            "border-radius: 10px; padding: 3px 9px; font-size: 11px; font-weight: 700;"
        )

    def _export(self) -> None:
        default = self.ctx.paths.exports / f"midpnp_logs_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
        path, _ = QFileDialog.getSaveFileName(self, "导出日志", str(default), "CSV 文件 (*.csv)")
        if not path:
            return
        try:
            buffer = io.StringIO()
            writer = csv.writer(buffer)
            writer.writerow(["时间", "级别", "来源", "消息"])
            for entry in self._entries:
                writer.writerow([entry.timestamp, entry.level, entry.source, entry.message])
            Path(path).write_text(buffer.getvalue(), encoding="utf-8-sig")
        except OSError as exc:
            QMessageBox.critical(self, "导出失败", str(exc))
            return
        self.ctx.log("INFO", "LOG", f"导出日志 {len(self._entries)} 条")
        self.ctx.toast("日志已导出", "success")

    def _clear(self) -> None:
        answer = QMessageBox.question(
            self,
            "清空日志",
            "确定清空所有日志记录？该操作不可撤销。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.ctx.storage.clear_logs()
        self.ctx.log("WARN", "LOG", "操作员清空日志")
        self.refresh()
        self.ctx.toast("日志已清空", "info")
