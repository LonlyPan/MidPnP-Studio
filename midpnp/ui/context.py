"""UI 共享上下文与跨页面事件总线。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Signal

from ..config import AppSettings, save_settings
from ..core.models import Component, Feeder, Product, RunRecord
from ..core.packages import (
    PackageDef,
    PackageLibrary,
    default_package_paths,
)
from ..core.profiles import MachineProfile, ProfileError, ProfileLibrary
from ..core.storage import Storage
from ..core.vision import Pipeline, Point2, build_pipeline
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
    profile_changed = Signal(object)
    packages_changed = Signal()


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

        # 机型配置与封装库：配置文件驱动，切换机型只需改 settings.machine_profile_id
        self._pipeline_cache: dict[str, Pipeline] = {}
        self.profile_library = ProfileLibrary(paths.root)
        self.profile: MachineProfile = self._resolve_profile()
        self._apply_profile_values(self.profile)
        builtin_packages, user_packages = default_package_paths(paths.root)
        self.package_library = PackageLibrary.load(builtin_packages, user_packages)

        product_id = settings.last_product_id
        product = storage.get_product(product_id) if product_id else None
        if product is None:
            products = storage.list_products()
            product = products[0] if products else None
        if product is not None:
            self.current_product_id = product.id

    # ---------------- 作业规划 ----------------

    def alignment_for(self, product: Product | None = None) -> Any:
        """取产品上保存的视觉补偿（板内 → 机器坐标）。"""
        product = product or self.current_product
        if product is None or not product.alignment:
            return None
        from ..core.vision import BoardAlignment

        return BoardAlignment.from_dict(product.alignment)

    def build_plan(self, product: Product | None = None, optimize: bool | None = None) -> Any:
        """统一入口：带机型、封装库与视觉补偿的作业规划。"""
        from ..core.planner import build_job

        product = product or self.current_product
        if product is None:
            raise ValueError("请先选择产品")
        return build_job(
            product,
            self.components(),
            self.feeders(),
            self.settings.limits,
            optimize=self.settings.optimize_route if optimize is None else optimize,
            profile=self.profile,
            packages=self.package_map(),
            alignment=self.alignment_for(product),
        )

    # ---------------- 机型配置 ----------------

    def _resolve_profile(self) -> MachineProfile:
        profile = None
        if self.settings.machine_profile_id:
            profile = self.profile_library.get(self.settings.machine_profile_id)
        if profile is None:
            profile = self.profile_library.default()
        if profile is None:
            profile = MachineProfile.from_settings(self.settings)
        return profile

    def _apply_profile_values(self, profile: MachineProfile, keep_name: bool = True) -> None:
        values = profile.settings_values()
        for key, value in values.items():
            if key == "machine_name" and keep_name:
                continue
            setattr(self.settings, key, value)
        self.settings.machine_profile_id = profile.id
        self.profile = profile
        self._pipeline_cache.clear()

    def apply_profile(self, profile_or_id: MachineProfile | str, persist: bool = True) -> MachineProfile:
        """切换机型：更新行程/连接参数，标记需要重连，并通知界面。"""
        if isinstance(profile_or_id, str):
            profile = self.profile_library.get(profile_or_id)
            if profile is None:
                raise ProfileError(f"未找到机型配置：{profile_or_id}")
        else:
            profile = profile_or_id
        self._apply_profile_values(profile)
        if persist:
            self.save_settings()
        self.signals.profile_changed.emit(profile)
        self.log(
            "INFO",
            "MACHINE",
            f"已切换机型：{profile.name}（{profile.id}）· "
            f"{profile.limits().travel_x_mm:.0f}×{profile.limits().travel_y_mm:.0f} mm · "
            f"{len(profile.nozzle_ids())} 吸嘴 · {profile.feeders.slot_count} 料站",
        )
        return profile

    def reload_profiles(self) -> None:
        self.profile_library.refresh()

    # ---------------- 封装库 ----------------

    @property
    def packages(self) -> PackageLibrary:
        return self.package_library

    def package_map(self) -> dict[str, PackageDef]:
        return {package.id: package for package in self.package_library.list()}

    def save_package(self, package: PackageDef) -> None:
        self.package_library.add(package)
        _, user_file = default_package_paths(self.paths.root)
        try:
            self.package_library.save_user_file(user_file)
        except OSError as exc:
            self.log("ERROR", "PACKAGE", f"封装库保存失败：{exc}")
            raise
        self.signals.packages_changed.emit()
        self.log("INFO", "PACKAGE", f"已保存封装 {package.name}（{package.id}）")

    def reload_packages(self) -> None:
        builtin, user = default_package_paths(self.paths.root)
        self.package_library = PackageLibrary.load(builtin, user)
        self.signals.packages_changed.emit()

    # ---------------- 视觉流水线 ----------------

    def vision_pipeline(self, name: str = "") -> Pipeline:
        """按名称取流水线（带缓存）；空名称取当前机型相机的默认流水线。"""
        if not name:
            camera = self.profile.camera() if self.profile else None
            name = camera.pipeline if camera else "fiducial-default"
        key = name or "fiducial-default"
        if key not in self._pipeline_cache:
            self._pipeline_cache[key] = build_pipeline(key)
        return self._pipeline_cache[key]

    @property
    def head_camera(self) -> Any:
        return self.profile.camera("") if self.profile else None

    def bottom_camera(self) -> Any:
        for camera in self.profile.cameras:
            if "bottom" in camera.id.lower() or camera.pipeline.startswith("bottom"):
                return camera
        cameras = [camera for camera in self.profile.cameras if camera.enabled]
        return cameras[-1] if cameras else None

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
