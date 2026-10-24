"""相机抽象与离线仿真相机。

`CameraSource` 是相机接口；`SimulatedCamera` 用 numpy 渲染板面/元件画面，
因此基准点识别、板卡补偿与底部对中都能在没有任何硬件的情况下自检。
接入真实相机时只需实现 `capture()` 返回 `Frame`（灰度 0–1 或 0–255）。

渲染坐标约定：`origin` 是相机光轴对应的机器坐标，所有绘制都以它为基准，
这样相机对准板角（板中心在视场外）时也能正确绘制局部画面。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Protocol

import numpy as np

from ..models import Component, Product
from .calibration import CameraCalibration
from .geometry import Point2


@dataclass
class Frame:
    image: np.ndarray
    calibration: CameraCalibration
    camera_id: str = ""
    center: Point2 = field(default_factory=Point2)
    meta: dict[str, Any] = field(default_factory=dict)

    def to_uint8(self) -> np.ndarray:
        array = np.asarray(self.image, dtype=np.float32)
        if array.max(initial=0.0) <= 1.5:
            array = array * 255.0
        return np.clip(array, 0, 255).astype(np.uint8)


class CameraSource(Protocol):
    def capture(self, *args: Any, **kwargs: Any) -> Frame: ...


# ---------------------------------------------------------------- 渲染工具


def _canvas(width: int, height: int, value: float, rng: np.random.Generator, noise: float) -> np.ndarray:
    image = np.full((height, width), value, dtype=np.float32)
    if noise > 0:
        image += rng.normal(0.0, noise, size=(height, width)).astype(np.float32)
    return image


def _bbox(
    calibration: CameraCalibration,
    origin: Point2,
    center: Point2,
    width_mm: float,
    height_mm: float,
) -> tuple[int, int, int, int]:
    radius_mm = math.hypot(width_mm, height_mm) / 2.0
    offset = calibration.mm_to_pixel(center.x - origin.x, center.y - origin.y)
    radius_px = radius_mm * calibration.pixels_per_mm + 3
    return (
        int(max(0, math.floor(offset[0] - radius_px))),
        int(max(0, math.floor(offset[1] - radius_px))),
        int(min(calibration.width, math.ceil(offset[0] + radius_px))),
        int(min(calibration.height, math.ceil(offset[1] + radius_px))),
    )


def fill_rect(
    image: np.ndarray,
    calibration: CameraCalibration,
    origin: Point2,
    center: Point2,
    width_mm: float,
    height_mm: float,
    angle_deg: float,
    value: float,
) -> None:
    """在机器坐标 `center` 处画一个旋转矩形（相机光轴为 `origin`）。"""
    if width_mm <= 0 or height_mm <= 0:
        return
    x0, y0, x1, y1 = _bbox(calibration, origin, center, width_mm, height_mm)
    if x1 <= x0 or y1 <= y0:
        return
    yy, xx = np.mgrid[y0:y1, x0:x1]
    px = origin.x + (xx - calibration.width / 2.0) / calibration.pixels_per_mm
    py = origin.y - (yy - calibration.height / 2.0) / calibration.pixels_per_mm
    dx = px - center.x
    dy = py - center.y
    angle = math.radians(angle_deg)
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    local_x = dx * cos_a + dy * sin_a
    local_y = -dx * sin_a + dy * cos_a
    mask = (np.abs(local_x) <= width_mm / 2.0) & (np.abs(local_y) <= height_mm / 2.0)
    if mask.any():
        image[y0:y1, x0:x1][mask] = value


def fill_circle(
    image: np.ndarray,
    calibration: CameraCalibration,
    origin: Point2,
    center: Point2,
    diameter_mm: float,
    value: float,
) -> None:
    if diameter_mm <= 0:
        return
    x0, y0, x1, y1 = _bbox(calibration, origin, center, diameter_mm, diameter_mm)
    if x1 <= x0 or y1 <= y0:
        return
    yy, xx = np.mgrid[y0:y1, x0:x1]
    px = origin.x + (xx - calibration.width / 2.0) / calibration.pixels_per_mm
    py = origin.y - (yy - calibration.height / 2.0) / calibration.pixels_per_mm
    mask = np.hypot(px - center.x, py - center.y) <= diameter_mm / 2.0
    if mask.any():
        image[y0:y1, x0:x1][mask] = value


# ---------------------------------------------------------------- 仿真相机


class SimulatedCamera:
    """离线仿真相机：按机型配置的分辨率与像素当量渲染场景。"""

    def __init__(self, config: Any, seed: int = 17, noise: float = 0.012) -> None:
        self.config = config
        self.camera_id = str(getattr(config, "id", "CAM-SIM"))
        self.calibration = CameraCalibration.from_camera_config(config)
        self.seed = int(seed)
        self.noise = float(noise)
        self.exposure_ms = float(getattr(config, "exposure_ms", 8.0))

    # ---------------- 板面 ----------------

    def capture_board(
        self,
        center: Point2,
        product: Product | None = None,
        components: list[Component] | None = None,
        packages: dict[str, Any] | None = None,
        alignment: Any = None,
        seed: int | None = None,
        pixels_per_mm: float | None = None,
    ) -> Frame:
        rng = np.random.default_rng(self.seed if seed is None else seed)
        calibration = self.calibration
        if pixels_per_mm is not None and pixels_per_mm > 0:
            calibration = CameraCalibration(pixels_per_mm, calibration.width, calibration.height)
        image = _canvas(calibration.width, calibration.height, 0.055, rng, self.noise)

        if product is not None:
            origin = Point2(
                float(getattr(product, "board_origin_x_mm", 0.0)),
                float(getattr(product, "board_origin_y_mm", 0.0)),
            )
            if alignment is not None and hasattr(alignment, "machine_point"):
                origin = alignment.machine_point(0.0, 0.0)
            width = float(product.board_width_mm)
            height = float(product.board_height_mm)
            angle = float(getattr(alignment, "theta_deg", 0.0)) if alignment is not None else 0.0
            board_center = Point2(origin.x + width / 2.0, origin.y + height / 2.0)
            fill_rect(image, calibration, center, board_center, width, height, angle, 0.24)
            fill_rect(image, calibration, center, board_center, width - 0.4, height - 0.4, angle, 0.29)

            package_map = packages or {}
            component_map = {component.id: component for component in (components or [])}
            for placement in getattr(product, "placements", []):
                if placement.skip:
                    continue
                component = component_map.get(placement.component_id)
                if component is None:
                    continue
                if alignment is not None and hasattr(alignment, "machine_point"):
                    machine = alignment.machine_point(placement.x_mm, placement.y_mm)
                else:
                    machine = Point2(origin.x + placement.x_mm, origin.y + placement.y_mm)
                rotation = float(placement.rotation_deg) + angle
                package = package_map.get(getattr(component, "package_id", ""))
                self._draw_component(image, calibration, center, machine, rotation, component, package)

            for fiducial in getattr(product, "fiducials", []):
                if alignment is not None and hasattr(alignment, "machine_point"):
                    machine = alignment.machine_point(fiducial.x_mm, fiducial.y_mm)
                else:
                    machine = Point2(origin.x + fiducial.x_mm, origin.y + fiducial.y_mm)
                radius = max(0.25, float(getattr(fiducial, "radius_mm", 1.0)))
                fill_circle(image, calibration, center, machine, radius * 2.0 + 0.45, 0.10)
                fill_circle(image, calibration, center, machine, radius * 2.0, 0.88)
                fill_circle(image, calibration, center, machine, radius * 0.85, 0.12)

        # 暗角与噪声
        yy, xx = np.mgrid[0 : calibration.height, 0 : calibration.width]
        nx = (xx - calibration.width / 2.0) / (calibration.width / 2.0)
        ny = (yy - calibration.height / 2.0) / (calibration.height / 2.0)
        vignette = np.clip(1.0 - 0.22 * (nx**2 + ny**2), 0.55, 1.0)
        image = np.clip(image * vignette + rng.normal(0.0, self.noise, size=image.shape), 0.0, 1.0)
        return Frame(
            image=image.astype(np.float32),
            calibration=calibration,
            camera_id=self.camera_id,
            center=center,
            meta={"exposure_ms": self.exposure_ms, "scene": "board"},
        )

    def _draw_component(
        self,
        image: np.ndarray,
        calibration: CameraCalibration,
        origin: Point2,
        machine: Point2,
        rotation_deg: float,
        component: Component,
        package: Any,
    ) -> None:
        if package is not None:
            for pad in package.derived_pads():
                offset = _rotate(pad.x_mm, pad.y_mm, rotation_deg)
                fill_rect(
                    image,
                    calibration,
                    origin,
                    Point2(machine.x + offset[0], machine.y + offset[1]),
                    pad.width_mm,
                    pad.height_mm,
                    rotation_deg + pad.rotation_deg,
                    0.72,
                )
            body_length = package.length_mm
            body_width = package.width_mm
        else:
            body_length = max(0.2, float(component.length_mm))
            body_width = max(0.2, float(component.width_mm))
        fill_rect(image, calibration, origin, machine, body_length * 0.82, body_width * 0.82, rotation_deg, 0.16)

    # ---------------- 元件（底部相机） ----------------

    def capture_part(
        self,
        component: Component | None = None,
        offset_mm: tuple[float, float] = (0.0, 0.0),
        angle_deg: float = 0.0,
        tip_diameter_mm: float = 0.8,
        seed: int | None = None,
    ) -> Frame:
        rng = np.random.default_rng((self.seed + 101) if seed is None else seed)
        calibration = self.calibration
        image = _canvas(calibration.width, calibration.height, 0.045, rng, self.noise)
        origin = Point2(0.0, 0.0)
        yy, xx = np.mgrid[0 : calibration.height, 0 : calibration.width]
        nx = (xx - calibration.width / 2.0) / (calibration.width / 2.0)
        ny = (yy - calibration.height / 2.0) / (calibration.height / 2.0)
        glow = np.clip(1.0 - 0.55 * np.hypot(nx, ny), 0.0, 1.0)
        image = np.clip(image + 0.10 * glow, 0.0, 1.0)

        center = Point2(offset_mm[0], offset_mm[1])
        # 先画吸嘴（在元件下方），否则会遮住元件本体中心
        fill_circle(image, calibration, origin, Point2(0.0, 0.0), max(0.15, tip_diameter_mm), 0.06)
        if component is not None:
            fill_rect(
                image,
                calibration,
                origin,
                center,
                max(0.2, float(component.length_mm)),
                max(0.2, float(component.width_mm)),
                angle_deg,
                0.80,
            )
            for sign in (-1, 1):
                offset = _rotate(sign * float(component.length_mm) * 0.38, 0.0, angle_deg)
                fill_rect(
                    image,
                    calibration,
                    origin,
                    Point2(center.x + offset[0], center.y + offset[1]),
                    max(0.08, float(component.length_mm) * 0.18),
                    max(0.08, float(component.width_mm) * 0.7),
                    angle_deg,
                    0.93,
                )
        image = np.clip(image + rng.normal(0.0, self.noise, size=image.shape), 0.0, 1.0)
        return Frame(
            image=image.astype(np.float32),
            calibration=calibration,
            camera_id=self.camera_id,
            center=Point2(0.0, 0.0),
            meta={"exposure_ms": self.exposure_ms, "scene": "part"},
        )


def _rotate(x: float, y: float, angle_deg: float) -> tuple[float, float]:
    angle = math.radians(angle_deg)
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    return (x * cos_a - y * sin_a, x * sin_a + y * cos_a)


def simulated_camera_for(config: Any, seed: int = 17) -> SimulatedCamera:
    return SimulatedCamera(config, seed=seed)
