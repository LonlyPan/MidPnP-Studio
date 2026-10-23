"""UI 共享上下文与跨页面事件总线。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Signal

from ..config import AppSettings, save_settings
from ..core.models import Component, Feeder, Product, RunRecord
from ..core.storage import Storage
from ..paths import AppPaths


class AppSignals(QObject):
    products_changed = Signal()
    components_changed = Signal()
    feeders_changed = Signal()
    settings_changed = Signal()
    product_changed = Signal(object)
    navigate = Signal(str)
    start_production = Signal()
    toast = Signal(str, str)
    log_added = Signal(object)
    position_changed = Signal(float, float, float)
    vacuum_changed = Signal(bool)


class AppContext(QObject):
    def __init__(
        self,
        paths: AppPaths,
        storage: Storage,
        settings: AppSettings,
        machine: Any,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.paths = paths
        self.storage = storage
        self.settings = settings
        self.machine = machine
        self.signals = AppSignals(self)
        self.current_product_id = ""
        self.head = (0.0, 0.0, 0.0)
        self.vacuum = False
        self.connected = False
        product_id = settings.last_product_id
        product = storage.get_product(product_id) if product_id else None
        if product is None:
            products = storage.list_products()
            product = products[0] if products else None
        if product is not None:
            self.current_product_id = product.id

    # ---------------- products ----------------

    @property
    def current_product(self) -> Product | None:
        if not self.current_product_id:
            return None
        return self.storage.get_product(self.current_product_id)

    def select_product(self, product_id: str) -> Product | None:
        product = self.storage.get_product(product_id)
        if product is None:
            return None
        self.current_product_id = product.id
        self.settings.last_product_id = product.id
        self.save_settings()
        self.signals.product_changed.emit(product)
        return product

    def save_product(self, product: Product) -> None:
        self.storage.save_product(product)
        self.current_product_id = product.id
        self.settings.last_product_id = product.id
        self.save_settings()
        self.signals.products_changed.emit()
        self.signals.product_changed.emit(product)
        self.log("INFO", "PROGRAM", f"已保存产品 {product.name}（{len(product.placements)} 点）")

    # ---------------- catalog ----------------

    def components(self) -> list[Component]:
        return self.storage.list_components()

    def feeders(self) -> list[Feeder]:
        return self.storage.list_feeders()

    def component_map(self) -> dict[str, Component]:
        return {component.id: component for component in self.components()}

    def feeder_map(self) -> dict[str, Feeder]:
        return {feeder.id: feeder for feeder in self.feeders()}

    # ---------------- settings ----------------

    def save_settings(self) -> None:
        save_settings(self.settings, self.paths.settings)
        self.signals.settings_changed.emit()

    # ---------------- logs & notifications ----------------

    def log(self, level: str, source: str, message: str) -> None:
        entry = self.storage.add_log(level, source, message)
        self.signals.log_added.emit(entry)

    def toast(self, message: str, level: str = "info") -> None:
        self.signals.toast.emit(message, level)

    # ---------------- production records ----------------

    def record_run(self, payload: dict[str, Any]) -> RunRecord:
        record = RunRecord(
            id=str(payload.get("run_id") or ""),
            product_id=str(payload.get("product_id", "")),
            product_name=str(payload.get("product_name", "")),
            started_at=str(payload.get("started_at", "")),
            finished_at=str(payload.get("finished_at", "")),
            total=int(payload.get("total", 0)),
            placed=int(payload.get("placed", 0)),
            failed=int(payload.get("failed", 0)),
            skipped=int(payload.get("skipped", 0)),
            status=str(payload.get("status", "Completed")),
            duration_s=float(payload.get("duration_s", 0)),
        )
        self.storage.save_run(record)
        usage: dict[str, int] = payload.get("feeder_usage", {}) or {}
        if usage:
            for feeder in self.storage.list_feeders():
                used = int(usage.get(feeder.id, 0))
                if used:
                    feeder.remaining = max(0, feeder.remaining - used)
                    self.storage.save_feeder(feeder)
            self.signals.feeders_changed.emit()
        self.log(
            "INFO" if record.status == "Completed" else "WARN",
            "RUN",
            f"生产记录已保存：{record.product_name} · {record.placed}/{record.total} · {record.status}",
        )
        return record

    def open_path(self, path: Path) -> None:
        import os

        os.startfile(str(path))  # type: ignore[attr-defined]
