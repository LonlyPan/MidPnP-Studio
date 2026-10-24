"""基准点识别与板卡对齐（对应 OpenPnP ReferenceFiducialLocator）。

流程与 OpenPnP 一致：
1. 以基准点标称位置为中心，用流水线在图像里找圆/特征，取离中心最近的一个；
2. 像素偏移 → 机器坐标偏移（Y 取反、角度取反）；
3. 多个基准点求仿射（≥3 点最小二乘，2 点相似变换）；
4. 校验缩放/剪切/平移是否合理，不合理就拒绝本次对齐；
5. 补偿只落在 `BoardAlignment`（板内坐标 → 机器坐标）上，**不修改贴装点**。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime

from ..models import Fiducial, Product, Side
from .cameras import Frame
from .geometry import (
    Affine,
    AlignmentError,
    BoardAlignment,
    FiducialTolerances,
    Point2,
    affine_info,
    check_alignment,
    derive_affine,
)
from .pipeline import KeyPoint, Pipeline, PipelineResult


@dataclass
class FiducialMeasurement:
    """单个基准点的识别结果。

    `board` 是板内坐标（用于求板卡仿射），`nominal`/`measured` 是机器坐标。
    """

    name: str
    nominal: Point2
    measured: Point2
    score: float = 0.0
    found: bool = False
    error_mm: float = 0.0
    diameter_mm: float = 0.0
    reason: str = ""
    board: Point2 = field(default_factory=Point2)

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "board": self.board.to_dict(),
            "nominal": self.nominal.to_dict(),
            "measured": self.measured.to_dict(),
            "score": round(self.score, 4),
            "found": self.found,
            "error_mm": round(self.error_mm, 4),
            "diameter_mm": round(self.diameter_mm, 4),
            "reason": self.reason,
        }


@dataclass
class BoardAlignResult:
    alignment: BoardAlignment | None
    measurements: list[FiducialMeasurement]
    problems: list[str] = field(default_factory=list)
    pipeline_ms: float = 0.0

    @property
    def ok(self) -> bool:
        return self.alignment is not None and not self.problems

    def summary(self) -> str:
        if self.alignment is None:
            return "对齐失败：" + ("；".join(self.problems) if self.problems else "未识别到基准点")
        return (
            f"{len([m for m in self.measurements if m.found])} 点对齐 · "
            f"θ {self.alignment.theta_deg:+.3f}° · RMS {self.alignment.rms_mm:.3f} mm"
        )


def locate_fiducial(
    frame: Frame,
    fiducial: Fiducial,
    nominal: Point2,
    pipeline: Pipeline,
    camera_center: Point2 | None = None,
    search_radius_mm: float = 12.0,
    min_score: float = 0.35,
    board: Point2 | None = None,
) -> FiducialMeasurement:
    """在单帧图像中定位一个基准点（以标称位置为中心的搜索窗口）。"""
    calibrated = board or Point2(fiducial.x_mm, fiducial.y_mm)
    calibration = frame.calibration
    camera_center = camera_center or frame.center
    pixels_per_mm = calibration.pixels_per_mm
    offset = Point2(nominal.x - camera_center.x, nominal.y - camera_center.y)
    center_px = calibration.mm_to_pixel(offset.x, offset.y)
    radius_px = max(8.0, search_radius_mm * pixels_per_mm)
    x0 = int(max(0, math.floor(center_px[0] - radius_px)))
    x1 = int(min(calibration.width, math.ceil(center_px[0] + radius_px)))
    y0 = int(max(0, math.floor(center_px[1] - radius_px)))
    y1 = int(min(calibration.height, math.ceil(center_px[1] + radius_px)))
    if x1 - x0 < 8 or y1 - y0 < 8:
        return FiducialMeasurement(
            name=fiducial.name,
            nominal=nominal,
            measured=nominal,
            found=False,
            reason="基准点不在相机视场内",
            board=calibrated,
        )

    crop = frame.image[y0:y1, x0:x1]
    crop_center_px = (x0 + crop.shape[1] / 2.0, y0 + crop.shape[0] / 2.0)
    offset_mm = calibration.pixel_to_mm_offset(crop_center_px[0], crop_center_px[1])
    crop_center_machine = Point2(camera_center.x + offset_mm.x, camera_center.y + offset_mm.y)
    from .calibration import CameraCalibration  # 局部导入避免循环

    crop_calibration = CameraCalibration(pixels_per_mm, crop.shape[1], crop.shape[0])
    result = pipeline.run(crop, {"pixels_per_mm": pixels_per_mm})
    keypoints: list[KeyPoint] = result.keypoints(crop_calibration, crop_center_machine)

    best: KeyPoint | None = None
    best_error = math.inf
    for keypoint in keypoints:
        error = math.hypot(keypoint.x - nominal.x, keypoint.y - nominal.y)
        if error < best_error and keypoint.score >= min_score:
            best = keypoint
            best_error = error
    if best is None:
        return FiducialMeasurement(
            name=fiducial.name,
            nominal=nominal,
            measured=nominal,
            found=False,
            reason="搜索窗口内未识别到有效特征",
            board=calibrated,
        )
    if best_error > search_radius_mm:
        return FiducialMeasurement(
            name=fiducial.name,
            nominal=nominal,
            measured=Point2(best.x, best.y),
            score=best.score,
            found=False,
            error_mm=best_error,
            reason=f"最近特征距离 {best_error:.2f} mm 超出搜索半径",
            board=calibrated,
        )
    return FiducialMeasurement(
        name=fiducial.name,
        nominal=nominal,
        measured=Point2(best.x, best.y),
        score=best.score,
        found=True,
        error_mm=best_error,
        diameter_mm=best.diameter_mm,
        board=calibrated,
    )


def measure_fiducials(
    frame: Frame,
    product: Product,
    pipeline: Pipeline,
    camera_center: Point2 | None = None,
    search_radius_mm: float = 12.0,
    min_score: float = 0.35,
) -> list[FiducialMeasurement]:
    """单帧（宽视场）内定位产品的所有基准点。"""
    measurements: list[FiducialMeasurement] = []
    for fiducial in product.fiducials:
        nominal = Point2(
            product.board_origin_x_mm + fiducial.x_mm,
            product.board_origin_y_mm + fiducial.y_mm,
        )
        measurements.append(
            locate_fiducial(
                frame,
                fiducial,
                nominal,
                pipeline,
                camera_center=camera_center,
                search_radius_mm=search_radius_mm,
                min_score=min_score,
                board=Point2(fiducial.x_mm, fiducial.y_mm),
            )
        )
    return measurements


def measure_fiducials_by_capture(
    product: Product,
    capture: object,
    pipeline: Pipeline,
    search_radius_mm: float = 12.0,
    min_score: float = 0.35,
) -> list[FiducialMeasurement]:
    """逐点移动相机再拍摄：`capture(center) -> Frame`。

    对应 OpenPnP 的做法——相机移动到每个基准点的标称位置上方，拍一张，
    在标称点附近搜索。这是小视场工业相机的正确用法。
    """
    measurements: list[FiducialMeasurement] = []
    for fiducial in product.fiducials:
        nominal = Point2(
            product.board_origin_x_mm + fiducial.x_mm,
            product.board_origin_y_mm + fiducial.y_mm,
        )
        try:
            frame = capture(nominal)  # type: ignore[operator]
        except Exception as exc:  # 采集失败不应中断其它点
            measurements.append(
                FiducialMeasurement(
                    name=fiducial.name,
                    nominal=nominal,
                    measured=nominal,
                    found=False,
                    reason=f"图像采集失败：{exc}",
                    board=Point2(fiducial.x_mm, fiducial.y_mm),
                )
            )
            continue
        measurements.append(
            locate_fiducial(
                frame,
                fiducial,
                nominal,
                pipeline,
                camera_center=frame.center,
                search_radius_mm=search_radius_mm,
                min_score=min_score,
                board=Point2(fiducial.x_mm, fiducial.y_mm),
            )
        )
    return measurements


def align_board(
    measurements: list[FiducialMeasurement],
    side: Side | str = Side.TOP,
    tolerances: FiducialTolerances | None = None,
    min_points: int = 1,
) -> BoardAlignResult:
    """由基准点测量值求板卡变换。"""
    side_value = side.value if isinstance(side, Side) else str(side)
    found = [item for item in measurements if item.found]
    if len(found) < min_points:
        problems = [f"有效基准点不足（{len(found)}/{min_points}）"]
        problems.extend(item.reason for item in measurements if not item.found and item.reason)
        return BoardAlignResult(None, measurements, problems)

    expected = [item.board for item in found]
    measured = [item.measured for item in found]
    nominal_origin = Point2(
        found[0].nominal.x - found[0].board.x,
        found[0].nominal.y - found[0].board.y,
    )
    try:
        transform, residuals = derive_affine(expected, measured)
    except AlignmentError as exc:
        return BoardAlignResult(None, measurements, [str(exc)])
    except Exception as exc:  # numpy 缺失或数值问题
        return BoardAlignResult(None, measurements, [f"仿射求解失败：{exc}"])

    problems = check_alignment(transform, residuals, tolerances, expected_translation=nominal_origin)
    if problems:
        return BoardAlignResult(None, measurements, problems)

    alignment = BoardAlignment(
        transform=transform,
        residuals_mm=[round(value, 4) for value in residuals],
        fiducial_names=[item.name for item in found],
        side=side_value,
        affine=affine_info(transform),
        created_at=datetime.now().isoformat(timespec="seconds"),
    )
    return BoardAlignResult(alignment, measurements)


def align_product_with_frame(
    frame: Frame,
    product: Product,
    pipeline: Pipeline,
    side: Side | str = Side.TOP,
    search_radius_mm: float = 12.0,
    tolerances: FiducialTolerances | None = None,
    camera_center: Point2 | None = None,
) -> BoardAlignResult:
    """一把梭：测量 + 求解 + 校验（单帧宽视场）。"""
    measurements = measure_fiducials(
        frame,
        product,
        pipeline,
        camera_center=camera_center,
        search_radius_mm=search_radius_mm,
    )
    return align_board(measurements, side=side, tolerances=tolerances)


def align_product_by_capture(
    product: Product,
    capture: object,
    pipeline: Pipeline,
    side: Side | str = Side.TOP,
    search_radius_mm: float = 12.0,
    tolerances: FiducialTolerances | None = None,
    min_score: float = 0.35,
) -> BoardAlignResult:
    """逐点拍摄 + 求解 + 校验（小视场相机的标准用法）。"""
    measurements = measure_fiducials_by_capture(
        product,
        capture,
        pipeline,
        search_radius_mm=search_radius_mm,
        min_score=min_score,
    )
    return align_board(measurements, side=side, tolerances=tolerances)


def verify_board_alignment(alignment: BoardAlignment | None, product: Product) -> list[str]:
    """检查存储的补偿是否仍可应用（例如板框尺寸变化后）。"""
    if alignment is None:
        return []
    problems: list[str] = []
    if len(alignment.transform.to_dict()) < 6:
        problems.append("补偿数据不完整")
    corners = [
        alignment.machine_point(0.0, 0.0),
        alignment.machine_point(product.board_width_mm, 0.0),
        alignment.machine_point(0.0, product.board_height_mm),
        alignment.machine_point(product.board_width_mm, product.board_height_mm),
    ]
    width = math.dist((corners[0].x, corners[0].y), (corners[1].x, corners[1].y))
    if abs(width - product.board_width_mm) > 5.0:
        problems.append(f"补偿后板宽 {width:.1f} mm 与产品尺寸差异过大，建议重新对位")
    return problems


def fiducial_defaults() -> dict[str, float]:
    return {"search_radius_mm": 12.0, "min_score": 0.35}


def nominal_machine_point(product: Product, fiducial: Fiducial) -> Point2:
    return Point2(
        product.board_origin_x_mm + fiducial.x_mm,
        product.board_origin_y_mm + fiducial.y_mm,
    )


def affine_from_dict(data: object) -> Affine:
    return Affine.from_dict(data)
