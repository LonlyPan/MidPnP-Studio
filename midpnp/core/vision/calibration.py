"""相机标定：像素 ↔ 毫米，以及 OpenPnP 的 Y 轴/角度取反约定。"""

from __future__ import annotations

from dataclasses import dataclass

from .geometry import Point2


@dataclass
class CameraCalibration:
    pixels_per_mm: float
    width: int
    height: int

    def __post_init__(self) -> None:
        self.pixels_per_mm = max(1e-6, float(self.pixels_per_mm))
        self.width = max(1, int(self.width))
        self.height = max(1, int(self.height))

    @property
    def center_px(self) -> tuple[float, float]:
        return (self.width / 2.0, self.height / 2.0)

    @property
    def view_width_mm(self) -> float:
        return self.width / self.pixels_per_mm

    @property
    def view_height_mm(self) -> float:
        return self.height / self.pixels_per_mm

    def pixel_to_mm_offset(self, px: float, py: float) -> Point2:
        """像素相对图像中心的偏移 → 机器坐标偏移（Y 取反）。"""
        return Point2(
            (px - self.width / 2.0) / self.pixels_per_mm,
            -(py - self.height / 2.0) / self.pixels_per_mm,
        )

    def mm_to_pixel(self, x: float, y: float) -> tuple[float, float]:
        return (
            self.width / 2.0 + x * self.pixels_per_mm,
            self.height / 2.0 - y * self.pixels_per_mm,
        )

    def pixel_to_mm_size(self, size_px: float) -> float:
        return size_px / self.pixels_per_mm

    def mm_to_pixel_size(self, size_mm: float) -> float:
        return size_mm * self.pixels_per_mm

    def angle_to_machine(self, angle_deg: float) -> float:
        """像素角度（Y 向下）→ 机器角度（Y 向上），取反。"""
        return -angle_deg

    @classmethod
    def from_camera_config(cls, camera: object) -> "CameraCalibration":
        resolution = getattr(camera, "resolution", (1280, 720))
        return cls(
            pixels_per_mm=float(getattr(camera, "pixels_per_mm", 20.0)),
            width=int(resolution[0]),
            height=int(resolution[1]),
        )
