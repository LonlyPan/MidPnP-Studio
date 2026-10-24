"""底部视觉对中（对应 OpenPnP ReferenceBottomVision）。

流程：相机从下往上拍吸嘴上的元件 → 求元件中心的像素偏移与角度 →
换算成机器坐标偏移（Y 取反、角度取反）→ 把角度解缠到 ±45°/±90° →
输出补偿量，由贴装动作叠加到目标坐标/角度。

注意：矩形元件在 180° 下对称，芯片在 90° 下也可能近似对称，因此角度
必须做周期折叠；这也是 OpenPnP 用 `maxRotation` + 解缠的原因。
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from ..models import Component
from ..profiles.schema import BottomVisionParams
from .cameras import Frame
from .geometry import Point2, fold_angle, normalize_angle
from .pipeline import Pipeline


@dataclass
class PartAlignment:
    dx_mm: float = 0.0
    dy_mm: float = 0.0
    theta_deg: float = 0.0
    score: float = 0.0
    passed: bool = False
    width_mm: float = 0.0
    height_mm: float = 0.0
    message: str = ""

    def corrected_position(
        self,
        x_mm: float,
        y_mm: float,
        rotation_deg: float,
        mode: str = "both",
    ) -> tuple[float, float, float]:
        """把对中补偿叠加到贴装目标上。"""
        if not self.passed:
            return x_mm, y_mm, rotation_deg
        new_x, new_y, new_rotation = x_mm, y_mm, rotation_deg
        if mode in {"both", "offset"}:
            new_x += self.dx_mm
            new_y += self.dy_mm
        if mode in {"both", "angle"}:
            new_rotation = normalize_angle(rotation_deg + self.theta_deg)
        return new_x, new_y, new_rotation

    def to_dict(self) -> dict[str, float | bool | str]:
        return {
            "dx_mm": round(self.dx_mm, 4),
            "dy_mm": round(self.dy_mm, 4),
            "theta_deg": round(self.theta_deg, 4),
            "score": round(self.score, 4),
            "passed": self.passed,
            "width_mm": round(self.width_mm, 4),
            "height_mm": round(self.height_mm, 4),
            "message": self.message,
        }


def align_part(
    frame: Frame,
    pipeline: Pipeline,
    params: BottomVisionParams | None = None,
    expected_angle_deg: float = 0.0,
    component: Component | None = None,
) -> PartAlignment:
    """对一帧底部相机图像做元件对中。"""
    params = params or BottomVisionParams()
    calibration = frame.calibration
    result = pipeline.run(frame.image, {"pixels_per_mm": calibration.pixels_per_mm})
    rect = result.rect()
    if rect is None:
        return PartAlignment(passed=False, message="未识别到元件本体（矩形）")

    offset = calibration.pixel_to_mm_offset(rect.cx, rect.cy)
    width_mm = calibration.pixel_to_mm_size(min(rect.width_px, rect.height_px))
    height_mm = calibration.pixel_to_mm_size(max(rect.width_px, rect.height_px))
    machine_angle = calibration.angle_to_machine(rect.angle_deg)
    theta = fold_angle(machine_angle - expected_angle_deg, 180.0)
    if abs(theta) > 90.0:
        theta = fold_angle(theta, 180.0)

    limit_width = float(getattr(params, "max_offset_mm", 2.0))
    limit_angle = float(getattr(params, "max_angle_deg", 20.0))
    min_score = float(getattr(params, "min_score", 0.55))

    problems: list[str] = []
    if abs(offset.x) > limit_width or abs(offset.y) > limit_width:
        problems.append(
            f"偏移 ({offset.x:+.3f}, {offset.y:+.3f}) mm 超出 ±{limit_width:g} mm"
        )
    if abs(theta) > limit_angle:
        problems.append(f"角度 {theta:+.2f}° 超出 ±{limit_angle:g}°")
    if rect.score < min_score:
        problems.append(f"拟合置信度 {rect.score:.2f} 低于 {min_score:.2f}")

    alignment = PartAlignment(
        dx_mm=offset.x,
        dy_mm=offset.y,
        theta_deg=theta,
        score=rect.score,
        passed=not problems,
        width_mm=width_mm,
        height_mm=height_mm,
        message="；".join(problems) if problems else "对中通过",
    )
    if component is not None and alignment.passed:
        expected_length = max(0.2, float(component.length_mm))
        measured = max(width_mm, height_mm)
        if measured > 0 and abs(measured - expected_length) / expected_length > 0.35:
            alignment.passed = False
            alignment.message = (
                f"元件尺寸异常（测得 {measured:.2f} mm，标称 {expected_length:.2f} mm），请检查吸料"
            )
    return alignment


def alignment_offset_error(frame: Frame, alignment: PartAlignment) -> Point2:
    """把补偿量换算回像素，便于界面画箭头。"""
    px = frame.calibration.mm_to_pixel_size(alignment.dx_mm)
    py = -frame.calibration.mm_to_pixel_size(alignment.dy_mm)
    return Point2(px, py)


def angle_within(theta_deg: float, limit_deg: float) -> bool:
    return abs(math.remainder(theta_deg, 360.0)) <= limit_deg
