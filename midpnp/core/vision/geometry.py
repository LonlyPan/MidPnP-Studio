"""几何与仿射变换（对齐 OpenPnP 的坐标约定）。

约定（与 OpenPnP 一致）：
- 机器坐标系为右手系：X 向右、Y 向上、角度逆时针为正；
- 图像/像素坐标系 Y 向下，因此像素 Y → 机器 Y 需取反，角度也需取反；
- 板卡补偿不写回贴装点，而是算一个 `Affine`（板内坐标 → 机器坐标），
  由规划器在生成作业时套用。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence


@dataclass(frozen=True)
class Point2:
    x: float = 0.0
    y: float = 0.0

    def to_dict(self) -> dict[str, float]:
        return {"x": round(self.x, 4), "y": round(self.y, 4)}

    @classmethod
    def from_dict(cls, data: Any) -> "Point2":
        if isinstance(data, dict):
            return cls(float(data.get("x", 0.0)), float(data.get("y", 0.0)))
        if isinstance(data, (list, tuple)) and len(data) >= 2:
            return cls(float(data[0]), float(data[1]))
        return cls()

    def __add__(self, other: "Point2") -> "Point2":
        return Point2(self.x + other.x, self.y + other.y)

    def __sub__(self, other: "Point2") -> "Point2":
        return Point2(self.x - other.x, self.y - other.y)

    def distance_to(self, other: "Point2") -> float:
        return math.hypot(self.x - other.x, self.y - other.y)


@dataclass(frozen=True)
class Affine:
    """二维仿射：x' = a·x + b·y + e，y' = c·x + d·y + f。"""

    a: float = 1.0
    b: float = 0.0
    c: float = 0.0
    d: float = 1.0
    e: float = 0.0
    f: float = 0.0

    # ---------------- 基本运算 ----------------

    @property
    def determinant(self) -> float:
        return self.a * self.d - self.b * self.c

    def apply(self, x: float, y: float) -> Point2:
        return Point2(self.a * x + self.b * y + self.e, self.c * x + self.d * y + self.f)

    def apply_point(self, point: Point2) -> Point2:
        return self.apply(point.x, point.y)

    def apply_angle(self, angle_deg: float) -> float:
        return angle_deg + self.rotation_deg

    def translate(self, dx: float, dy: float) -> "Affine":
        return Affine(self.a, self.b, self.c, self.d, self.e + dx, self.f + dy)

    def scale(self, sx: float, sy: float) -> "Affine":
        return Affine(self.a * sx, self.b * sy, self.c * sx, self.d * sy, self.e * sx, self.f * sy)

    def compose(self, inner: "Affine") -> "Affine":
        """先施加 inner，再施加 self。"""
        return Affine(
            a=self.a * inner.a + self.b * inner.c,
            b=self.a * inner.b + self.b * inner.d,
            c=self.c * inner.a + self.d * inner.c,
            d=self.c * inner.b + self.d * inner.d,
            e=self.a * inner.e + self.b * inner.f + self.e,
            f=self.c * inner.e + self.d * inner.f + self.f,
        )

    def inverse(self) -> "Affine":
        det = self.determinant
        if abs(det) < 1e-12:
            raise ValueError("仿射矩阵不可逆（行列式为 0）")
        a = self.d / det
        b = -self.b / det
        c = -self.c / det
        d = self.a / det
        e = -(a * self.e + b * self.f)
        f = -(c * self.e + d * self.f)
        return Affine(a, b, c, d, e, f)

    # ---------------- 分解 ----------------

    @property
    def scale_x(self) -> float:
        return math.hypot(self.a, self.c)

    @property
    def scale_y(self) -> float:
        return math.hypot(self.b, self.d)

    @property
    def rotation_deg(self) -> float:
        return math.degrees(math.atan2(self.c, self.a))

    @property
    def shear(self) -> float:
        denominator = self.scale_x * self.scale_y
        if denominator < 1e-12:
            return 0.0
        sin_value = (self.a * self.b + self.c * self.d) / denominator
        return max(-1.0, min(1.0, sin_value))

    def to_dict(self) -> dict[str, float]:
        return {
            "a": round(self.a, 6),
            "b": round(self.b, 6),
            "c": round(self.c, 6),
            "d": round(self.d, 6),
            "e": round(self.e, 4),
            "f": round(self.f, 4),
        }

    @classmethod
    def from_dict(cls, data: Any) -> "Affine":
        if not isinstance(data, dict):
            return cls()
        return cls(
            a=float(data.get("a", 1.0)),
            b=float(data.get("b", 0.0)),
            c=float(data.get("c", 0.0)),
            d=float(data.get("d", 1.0)),
            e=float(data.get("e", 0.0)),
            f=float(data.get("f", 0.0)),
        )

    @classmethod
    def identity(cls) -> "Affine":
        return cls()


@dataclass
class AffineInfo:
    x_scale: float
    y_scale: float
    shear: float
    rotation_deg: float
    translation: Point2
    determinant: float

    def describe(self) -> str:
        return (
            f"缩放 {self.x_scale:.3f}/{self.y_scale:.3f} · 剪切 {self.shear:+.3f} · "
            f"旋转 {self.rotation_deg:+.3f}° · 平移 ({self.translation.x:+.3f}, {self.translation.y:+.3f}) mm"
        )


def affine_info(transform: Affine) -> AffineInfo:
    return AffineInfo(
        x_scale=transform.scale_x,
        y_scale=transform.scale_y,
        shear=transform.shear,
        rotation_deg=transform.rotation_deg,
        translation=Point2(transform.e, transform.f),
        determinant=transform.determinant,
    )


@dataclass
class FiducialTolerances:
    """对齐结果的合理性阈值（对应 OpenPnP FiducialLocatorTolerances）。"""

    scaling: float = 0.05
    shearing: float = 0.05
    translation_mm: float = 5.0


class AlignmentError(ValueError):
    """视觉对齐结果不合理（缩放/剪切/平移超限）。"""


def derive_affine(
    expected: Sequence[Point2],
    measured: Sequence[Point2],
) -> tuple[Affine, list[float]]:
    """由「板内标称点 → 机器实测点」求仿射，返回 (变换, 每个点的残差 mm)。

    - n ≥ 3：最小二乘仿射（可解出各向异性缩放与剪切）；
    - n == 2：相似变换（旋转 + 单一缩放 + 平移）；
    - n == 1：仅平移。
    """
    if len(expected) != len(measured):
        raise AlignmentError("标称点与实测点数量不一致")
    count = len(expected)
    if count == 0:
        raise AlignmentError("没有可用的基准点测量结果")
    if count == 1:
        transform = Affine(e=measured[0].x - expected[0].x, f=measured[0].y - expected[0].y)
        return transform, [0.0]

    if count == 2:
        dx_expected = expected[1].x - expected[0].x
        dy_expected = expected[1].y - expected[0].y
        dx_measured = measured[1].x - measured[0].x
        dy_measured = measured[1].y - measured[0].y
        if abs(dx_expected) < 1e-9 and abs(dy_expected) < 1e-9:
            raise AlignmentError("两个基准点重合，无法求解")
        ratio = complex(dx_measured, dy_measured) / complex(dx_expected, dy_expected)
        scale = abs(ratio)
        angle = math.atan2(ratio.imag, ratio.real)
        cos_a, sin_a = math.cos(angle), math.sin(angle)
        a, b = scale * cos_a, -scale * sin_a
        c, d = scale * sin_a, scale * cos_a
        e = measured[0].x - (a * expected[0].x + b * expected[0].y)
        f = measured[0].y - (c * expected[0].x + d * expected[0].y)
        transform = Affine(a, b, c, d, e, f)
        residuals = [transform.apply_point(point).distance_to(target) for point, target in zip(expected, measured)]
        return transform, residuals

    # n ≥ 3：最小二乘
    matrix = [[point.x, point.y, 1.0] for point in expected]
    target_x = [point.x for point in measured]
    target_y = [point.y for point in measured]
    try:
        import numpy as np

        mat = np.asarray(matrix, dtype=float)
        coeff_x, *_ = np.linalg.lstsq(mat, np.asarray(target_x, dtype=float), rcond=None)
        coeff_y, *_ = np.linalg.lstsq(mat, np.asarray(target_y, dtype=float), rcond=None)
        a, b, e = (float(value) for value in coeff_x)
        c, d, f = (float(value) for value in coeff_y)
    except ImportError:  # 退化路径：没有 numpy 时用相似变换
        return derive_affine(expected[:2], measured[:2])

    transform = Affine(a, b, c, d, e, f)
    residuals = [transform.apply_point(point).distance_to(target) for point, target in zip(expected, measured)]
    return transform, residuals


def fit_similarity(expected: Sequence[Point2], measured: Sequence[Point2]) -> Affine:
    """强制相似变换（无剪切/各向异性），用于点少或需要更稳健的场合。"""
    count = min(len(expected), len(measured))
    if count == 0:
        raise AlignmentError("没有可用的基准点测量结果")
    ex = sum(point.x for point in expected[:count]) / count
    ey = sum(point.y for point in expected[:count]) / count
    mx = sum(point.x for point in measured[:count]) / count
    my = sum(point.y for point in measured[:count]) / count
    numerator = 0.0
    denominator = 0.0
    for point, target in zip(expected[:count], measured[:count]):
        px, py = point.x - ex, point.y - ey
        qx, qy = target.x - mx, target.y - my
        numerator += px * qx + py * qy
        denominator += px * px + py * py
    scale = numerator / denominator if denominator > 1e-12 else 1.0
    angle = 0.0
    if denominator > 1e-12:
        cos_a = numerator / denominator
        sin_a = sum(
            (point.x - ex) * (target.y - my) - (point.y - ey) * (target.x - mx)
            for point, target in zip(expected[:count], measured[:count])
        ) / denominator
        angle = math.atan2(sin_a, cos_a)
    a = scale * math.cos(angle)
    b = -scale * math.sin(angle)
    c = scale * math.sin(angle)
    d = scale * math.cos(angle)
    return Affine(a, b, c, d, mx - (a * ex + b * ey), my - (c * ex + d * ey))


def normalize_angle(angle_deg: float) -> float:
    """归一到 [0, 360)。"""
    return angle_deg % 360.0


def fold_angle(angle_deg: float, period_deg: float = 180.0) -> float:
    """把角度折叠到 (-period/2, period/2]，用于处理矩形/芯片的对称性。"""
    folded = (angle_deg + period_deg / 2) % period_deg - period_deg / 2
    return folded


@dataclass
class BoardAlignment:
    """板卡视觉对齐结果：板内坐标 → 机器坐标。"""

    transform: Affine
    residuals_mm: list[float] = field(default_factory=list)
    fiducial_names: list[str] = field(default_factory=list)
    side: str = "Top"
    affine: AffineInfo | None = None
    created_at: str = ""

    @property
    def rms_mm(self) -> float:
        if not self.residuals_mm:
            return 0.0
        return math.sqrt(sum(value * value for value in self.residuals_mm) / len(self.residuals_mm))

    @property
    def max_error_mm(self) -> float:
        return max(self.residuals_mm) if self.residuals_mm else 0.0

    @property
    def theta_deg(self) -> float:
        return self.transform.rotation_deg

    @property
    def dx_mm(self) -> float:
        return self.transform.e

    @property
    def dy_mm(self) -> float:
        return self.transform.f

    @property
    def scale(self) -> float:
        return (self.transform.scale_x + self.transform.scale_y) / 2

    def machine_point(self, board_x: float, board_y: float) -> Point2:
        return self.transform.apply(board_x, board_y)

    def machine_angle(self, board_angle: float) -> float:
        return normalize_angle(board_angle + self.transform.rotation_deg)

    def to_dict(self) -> dict[str, Any]:
        payload = self.transform.to_dict()
        payload.update(
            {
                "theta_deg": round(self.theta_deg, 4),
                "rms_mm": round(self.rms_mm, 4),
                "max_error_mm": round(self.max_error_mm, 4),
                "fiducials": list(self.fiducial_names),
                "side": self.side,
                "created_at": self.created_at,
            }
        )
        if self.affine is not None:
            payload["info"] = self.affine.describe()
        return payload

    @classmethod
    def from_dict(cls, data: Any) -> "BoardAlignment | None":
        if not isinstance(data, dict):
            return None
        transform = Affine.from_dict(data)
        if "a" not in data:
            return None
        return cls(
            transform=transform,
            residuals_mm=[],
            fiducial_names=[str(item) for item in data.get("fiducials", [])],
            side=str(data.get("side", "Top")),
            created_at=str(data.get("created_at", "")),
        )


def check_alignment(
    transform: Affine,
    residuals: Sequence[float],
    tolerances: FiducialTolerances | None = None,
    expected_translation: Point2 | None = None,
) -> list[str]:
    """检查仿射是否合理，返回问题列表（空表示通过）。

    `expected_translation` 是板卡标称原点（板内 0,0 在机器坐标系的位置）。
    给出时按「相对标称原点的偏移」判定，而不是看绝对平移量——否则大板、
    小板都会被绝对值阈值误判。
    """
    tolerances = tolerances or FiducialTolerances()
    info = affine_info(transform)
    problems: list[str] = []
    if abs(info.x_scale - 1.0) > tolerances.scaling:
        problems.append(f"X 缩放 {info.x_scale:.3f} 偏离 1 超过 {tolerances.scaling:.0%}")
    if abs(info.y_scale - 1.0) > tolerances.scaling:
        problems.append(f"Y 缩放 {info.y_scale:.3f} 偏离 1 超过 {tolerances.scaling:.0%}")
    if abs(info.shear) > tolerances.shearing:
        problems.append(f"剪切 {info.shear:+.3f} 超过 {tolerances.shearing:.0%}")
    offset_x, offset_y = info.translation.x, info.translation.y
    if expected_translation is not None:
        offset_x -= expected_translation.x
        offset_y -= expected_translation.y
    if math.hypot(offset_x, offset_y) > tolerances.translation_mm:
        problems.append(
            f"板原点偏移 ({offset_x:+.1f}, {offset_y:+.1f}) mm "
            f"超过 {tolerances.translation_mm:g} mm"
        )
    if residuals and max(residuals) > tolerances.translation_mm:
        problems.append(f"单点残差 {max(residuals):.2f} mm 过大")
    return problems


def polygon_area(points: Iterable[Point2]) -> float:
    pts = list(points)
    if len(pts) < 3:
        return 0.0
    total = 0.0
    for index, point in enumerate(pts):
        nxt = pts[(index + 1) % len(pts)]
        total += point.x * nxt.y - nxt.x * point.y
    return abs(total) / 2.0
