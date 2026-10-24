"""视觉流水线 stage 实现。

命名对齐 OpenPnP 的 stage（`vision/pipeline/stages`），但用 numpy 重写，
不依赖 OpenCV：阈值/形态学/连通域/最小外接矩形都在纯 numpy 上完成。
精度足以支撑基准点识别与元件对中；复杂工业场景可替换为 OpenCV 版本。
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from . import pipeline as pl
from .pipeline import CircleResult, Contour, PipelineContext, RectResult, Stage, register_pipeline, register_stage


# ---------------------------------------------------------------- 图像基础运算


def _ensure_binary(image: np.ndarray) -> np.ndarray:
    array = np.asarray(image, dtype=np.float32)
    if array.max(initial=0.0) > 1.5:
        array = array / 255.0
    return array >= 0.5


def _dilate(mask: np.ndarray, kernel: int = 3) -> np.ndarray:
    radius = max(1, int(kernel) // 2)
    result = mask.copy()
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            result |= _shift(mask, dy, dx)
    return result


def _erode(mask: np.ndarray, kernel: int = 3) -> np.ndarray:
    radius = max(1, int(kernel) // 2)
    result = mask.copy()
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            result &= _shift(mask, dy, dx)
    return result


def _shift(mask: np.ndarray, dy: int, dx: int) -> np.ndarray:
    out = np.zeros_like(mask)
    height, width = mask.shape
    if abs(dy) >= height or abs(dx) >= width:
        return out
    src_y0 = max(0, -dy)
    src_y1 = min(height, height - dy)
    src_x0 = max(0, -dx)
    src_x1 = min(width, width - dx)
    out[src_y0 + dy : src_y1 + dy, src_x0 + dx : src_x1 + dx] = mask[src_y0:src_y1, src_x0:src_x1]
    return out


def _gaussian_kernel(kernel: int) -> np.ndarray:
    size = max(1, int(kernel))
    if size % 2 == 0:
        size += 1
    if size <= 1:
        return np.array([1.0])
    sigma = max(0.4, size / 3.0)
    axis = np.arange(size) - (size - 1) / 2
    weights = np.exp(-(axis**2) / (2 * sigma * sigma))
    return weights / weights.sum()


def _blur(image: np.ndarray, kernel: int) -> np.ndarray:
    weights = _gaussian_kernel(kernel)
    if len(weights) == 1:
        return image
    pad = len(weights) // 2
    height, width = image.shape
    padded = np.pad(image, pad, mode="edge")
    vertical = np.zeros_like(image)
    for index, weight in enumerate(weights):
        vertical += weight * padded[index : index + height, pad : pad + width]
    padded_v = np.pad(vertical, pad, mode="edge")
    horizontal = np.zeros_like(image)
    for index, weight in enumerate(weights):
        horizontal += weight * padded_v[pad : pad + height, index : index + width]
    return horizontal


def label_blobs(mask: np.ndarray, min_area: int = 4, max_blobs: int = 400) -> list[Contour]:
    """8 连通域标记，返回每个连通域的全部像素点。"""
    binary = np.asarray(mask, dtype=bool)
    if binary.ndim != 2:
        raise ValueError("连通域标记需要二维掩膜")
    visited = np.zeros_like(binary, dtype=bool)
    height, width = binary.shape
    contours: list[Contour] = []
    for start_y, start_x in zip(*np.nonzero(binary)):
        if visited[start_y, start_x]:
            continue
        visited[start_y, start_x] = True
        stack = [(int(start_y), int(start_x))]
        points: list[tuple[int, int]] = []
        while stack:
            y, x = stack.pop()
            points.append((x, y))
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    if dy == 0 and dx == 0:
                        continue
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < height and 0 <= nx < width and binary[ny, nx] and not visited[ny, nx]:
                        visited[ny, nx] = True
                        stack.append((ny, nx))
        if len(points) < max(1, min_area):
            continue
        array = np.asarray(points, dtype=float)
        contours.append(
            Contour(
                points=array,
                area_px=float(len(points)),
                center=(float(array[:, 0].mean()), float(array[:, 1].mean())),
            )
        )
        if len(contours) >= max_blobs:
            break
    contours.sort(key=lambda contour: contour.area_px, reverse=True)
    return contours


def _contour_radii(contour: Contour) -> np.ndarray:
    points = contour.points
    center = np.asarray(contour.center)
    return np.linalg.norm(points - center, axis=1)


def _circularity(contour: Contour) -> float:
    radii = _contour_radii(contour)
    if len(radii) == 0 or radii.mean() <= 1e-9:
        return 0.0
    compactness = float(np.clip(radii.mean() / radii.max(), 0.0, 1.0))
    variation = float(radii.std() / max(radii.mean(), 1e-9))
    return float(np.clip(compactness * (1.0 - variation), 0.0, 1.0))


# ---------------------------------------------------------------- 基础 stage


@register_stage
class ConvertColor(Stage):
    NAME = "ConvertColor"
    DESCRIPTION = "色彩空间转换（本实现支持转灰度）"
    DEFAULTS = {"mode": "gray"}

    def process(self, ctx: PipelineContext) -> np.ndarray:
        image = ctx.image
        if image.ndim == 3:
            image = image[..., :3].mean(axis=2)
        ctx.image = image.astype(np.float32)
        return None


@register_stage
class BlurGaussian(Stage):
    NAME = "BlurGaussian"
    DESCRIPTION = "高斯模糊"
    DEFAULTS = {"kernel": 3}

    def process(self, ctx: PipelineContext) -> np.ndarray:
        ctx.image = _blur(ctx.image, int(self.num("kernel", 3)))
        return None


@register_stage
class Threshold(Stage):
    NAME = "Threshold"
    DESCRIPTION = "全局阈值 / Otsu 自动阈值"
    DEFAULTS = {"threshold": 0.5, "auto": False, "invert": False}

    def process(self, ctx: PipelineContext) -> np.ndarray:
        image = ctx.image
        level = pl.otsu_threshold(image) if bool(self.get("auto", False)) else self.num("threshold", 0.5)
        invert = bool(self.get("invert", False))
        mask = (image <= level) if invert else (image >= level)
        ctx.image = mask.astype(np.float32)
        ctx.props["_binary"] = True
        ctx.props["_threshold"] = level
        return None


@register_stage
class MorphClose(Stage):
    NAME = "MorphClose"
    DESCRIPTION = "闭运算：先膨胀后腐蚀，填补圆环/孔洞"
    DEFAULTS = {"kernel": 3}

    def process(self, ctx: PipelineContext) -> np.ndarray:
        mask = _ensure_binary(ctx.image)
        ctx.image = _erode(_dilate(mask, int(self.num("kernel", 3))), int(self.num("kernel", 3))).astype(np.float32)
        ctx.props["_binary"] = True
        return None


@register_stage
class MorphOpen(Stage):
    NAME = "MorphOpen"
    DESCRIPTION = "开运算：先腐蚀后膨胀，去除噪点"
    DEFAULTS = {"kernel": 3}

    def process(self, ctx: PipelineContext) -> np.ndarray:
        mask = _ensure_binary(ctx.image)
        ctx.image = _dilate(_erode(mask, int(self.num("kernel", 3))), int(self.num("kernel", 3))).astype(np.float32)
        ctx.props["_binary"] = True
        return None


@register_stage
class MaskCircle(Stage):
    NAME = "MaskCircle"
    DESCRIPTION = "圆形 ROI 遮罩（圆心默认取图像中心）"
    DEFAULTS = {"diameter_mm": 0.0, "cx": None, "cy": None}

    def process(self, ctx: PipelineContext) -> np.ndarray:
        diameter_mm = self.num("diameter_mm", 0.0)
        if diameter_mm <= 0:
            return None
        height, width = ctx.image.shape
        pixels_per_mm = max(ctx.pixels_per_mm, 1e-9)
        radius_px = diameter_mm * pixels_per_mm / 2.0
        cx = self.get("cx")
        cy = self.get("cy")
        cx = width / 2.0 if cx is None else float(cx)
        cy = height / 2.0 if cy is None else float(cy)
        yy, xx = np.ogrid[:height, :width]
        mask = (xx - cx) ** 2 + (yy - cy) ** 2 <= radius_px**2
        ctx.image = np.where(mask, ctx.image, 0.0).astype(np.float32)
        return None


@register_stage
class FindContours(Stage):
    NAME = "FindContours"
    DESCRIPTION = "连通域（等价 OpenCV findContours 的实心区域）"
    DEFAULTS = {"min_area_px": 6}

    def process(self, ctx: PipelineContext) -> list[Contour]:
        mask = _ensure_binary(ctx.image)
        contours = label_blobs(mask, max(1, int(self.num("min_area_px", 6))))
        return contours


@register_stage
class FilterContours(Stage):
    NAME = "FilterContours"
    DESCRIPTION = "按面积（mm²）过滤轮廓"
    DEFAULTS = {"min_area_mm2": 0.0, "max_area_mm2": 0.0, "min_circularity": 0.0}

    def process(self, ctx: PipelineContext) -> list[Contour]:
        contours = ctx.models.get("FindContours") or ctx.models.get(ctx.props.get("_last_model_stage", "")) or []
        if not isinstance(contours, list):
            return []
        pixels_per_mm = max(ctx.pixels_per_mm, 1e-9)
        min_area = self.num("min_area_mm2", 0.0) * pixels_per_mm**2
        max_area = self.num("max_area_mm2", 0.0) * pixels_per_mm**2
        min_circularity = self.num("min_circularity", 0.0)
        selected: list[Contour] = []
        for contour in contours:
            if not isinstance(contour, Contour):
                continue
            if contour.area_px < min_area:
                continue
            if max_area > 0 and contour.area_px > max_area:
                continue
            if min_circularity > 0 and _circularity(contour) < min_circularity:
                continue
            selected.append(contour)
        return selected


@register_stage
class MinEnclosingCircle(Stage):
    NAME = "MinEnclosingCircle"
    DESCRIPTION = "由轮廓求最小外接圆"
    DEFAULTS = {"source": "FilterContours"}

    def process(self, ctx: PipelineContext) -> list[CircleResult]:
        contours = ctx.models.get(str(self.get("source", "FilterContours"))) or []
        circles: list[CircleResult] = []
        for contour in contours:
            if not isinstance(contour, Contour) or len(contour.points) < 3:
                continue
            radii = _contour_radii(contour)
            radius = float(radii.max())
            circles.append(
                CircleResult(
                    cx=contour.center[0],
                    cy=contour.center[1],
                    diameter_px=radius * 2.0,
                    score=_circularity(contour),
                    source="MinEnclosingCircle",
                )
            )
        return circles


@register_stage
class DetectCircularSymmetry(Stage):
    NAME = "DetectCircularSymmetry"
    DESCRIPTION = "圆形对称检测：阈值 + 连通域 + 圆度评分（简化版 stock 基准点检测器）"
    DEFAULTS = {
        "threshold": 0.0,
        "auto": True,
        "min_diameter_mm": 0.3,
        "max_diameter_mm": 8.0,
        "min_score": 0.3,
    }

    def process(self, ctx: PipelineContext) -> list[CircleResult]:
        image = ctx.image
        level = pl.otsu_threshold(image) if bool(self.get("auto", True)) else self.num("threshold", 0.5)
        mask = image >= level
        pixels_per_mm = max(ctx.pixels_per_mm, 1e-9)
        min_diameter = self.num("min_diameter_mm", 0.3) * pixels_per_mm
        max_diameter = self.num("max_diameter_mm", 8.0) * pixels_per_mm
        min_score = self.num("min_score", 0.3)
        circles: list[CircleResult] = []
        for contour in label_blobs(mask, min_area=4):
            radii = _contour_radii(contour)
            diameter = float(radii.max()) * 2.0
            if diameter < min_diameter or diameter > max_diameter:
                continue
            score = _circularity(contour)
            if score < min_score:
                continue
            circles.append(
                CircleResult(
                    cx=contour.center[0],
                    cy=contour.center[1],
                    diameter_px=diameter,
                    score=score,
                    source="DetectCircularSymmetry",
                )
            )
        return circles


@register_stage
class MinAreaRect(Stage):
    NAME = "MinAreaRect"
    DESCRIPTION = "最小外接旋转矩形（PCA + 投影，近似 OpenCV minAreaRect）"
    DEFAULTS = {"source": "FilterContours", "min_fill": 0.0}

    def process(self, ctx: PipelineContext) -> RectResult | None:
        contours = ctx.models.get(str(self.get("source", "FilterContours"))) or []
        candidates = [contour for contour in contours if isinstance(contour, Contour)]
        if not candidates:
            mask = _ensure_binary(ctx.image)
            points = np.column_stack(np.nonzero(mask)[::-1]).astype(float)
            if len(points) < 4:
                return None
            candidates = [Contour(points=points, area_px=float(len(points)), center=tuple(points.mean(axis=0)))]
        contour = max(candidates, key=lambda item: item.area_px)
        points = contour.points
        if len(points) < 4:
            return None
        center = points.mean(axis=0)
        centered = points - center
        covariance = np.cov(centered, rowvar=False)
        try:
            _, eigenvectors = np.linalg.eigh(covariance)
        except np.linalg.LinAlgError:
            return None
        major = eigenvectors[:, -1]
        minor = eigenvectors[:, 0]
        projection_major = centered @ major
        projection_minor = centered @ minor
        width = float(projection_major.max() - projection_major.min())
        height = float(projection_minor.max() - projection_minor.min())
        if width < 1.0 or height < 1.0:
            return None
        angle = math.degrees(math.atan2(float(major[1]), float(major[0])))
        if angle > 90.0:
            angle -= 180.0
        elif angle < -90.0:
            angle += 180.0
        return RectResult(
            cx=float(center[0]),
            cy=float(center[1]),
            width_px=width,
            height_px=height,
            angle_deg=angle,
            score=min(1.0, contour.area_px / max(1.0, width * height)),
            source="MinAreaRect",
        )


@register_stage
class SelectSingle(Stage):
    NAME = "SelectSingle"
    DESCRIPTION = "从候选结果中选一个写入 results"
    DEFAULTS = {"criterion": "center", "index": 0}

    def process(self, ctx: PipelineContext) -> Any:
        model = ctx.models.get(ctx.props.get("_last_model_stage", ""))
        if model is None:
            for key in reversed(list(ctx.models.keys())):
                if key == "results":
                    continue
                candidate = ctx.models[key]
                if isinstance(candidate, (list, tuple)) and candidate:
                    model = candidate
                    break
                if isinstance(candidate, (CircleResult, RectResult)):
                    model = [candidate]
                    break
        if model is None:
            ctx.notes.append("SelectSingle：没有候选结果")
            ctx.models["results"] = None
            return None
        items = list(model) if isinstance(model, (list, tuple)) else [model]
        items = [item for item in items if item is not None]
        if not items:
            ctx.models["results"] = None
            return None
        criterion = str(self.get("criterion", "center"))
        if criterion == "largest" and hasattr(items[0], "diameter_px"):
            chosen = max(items, key=lambda item: item.diameter_px)
        elif criterion == "score":
            chosen = max(items, key=lambda item: getattr(item, "score", 0.0))
        elif criterion == "index":
            index = int(self.num("index", 0))
            chosen = items[min(max(index, 0), len(items) - 1)]
        else:  # center
            height, width = ctx.image.shape
            cx, cy = width / 2.0, height / 2.0
            chosen = min(items, key=lambda item: math.hypot(getattr(item, "cx", cx) - cx, getattr(item, "cy", cy) - cy))
        ctx.models["results"] = chosen
        return None


@register_stage
class SetResult(Stage):
    NAME = "SetResult"
    DESCRIPTION = "把当前模型写入 results"
    DEFAULTS = {"source": ""}

    def process(self, ctx: PipelineContext) -> Any:
        source = str(self.get("source", ""))
        if source:
            model = ctx.models.get(source)
        else:
            model = ctx.models.get(ctx.props.get("_last_model_stage", ""))
            if isinstance(model, list) and len(model) == 1:
                model = model[0]
        ctx.models["results"] = model
        return None


@register_stage
class DrawResult(Stage):
    NAME = "DrawResult"
    DESCRIPTION = "把检测结果叠加到原图上（仅用于界面显示）"
    DEFAULTS = {"show_contours": True}

    def process(self, ctx: PipelineContext) -> np.ndarray:
        image = ctx.original.copy()
        rgb = np.repeat(image[..., None], 3, axis=2)
        if bool(self.get("show_contours", True)):
            for contour in ctx.models.get("FindContours", []) or []:
                if not isinstance(contour, Contour):
                    continue
                points = contour.points.astype(int)
                height, width = image.shape
                for x, y in points[:: max(1, len(points) // 400)]:
                    if 0 <= y < height and 0 <= x < width:
                        rgb[y, x] = (0.15, 0.95, 0.55)
        result = ctx.models.get("results")
        height, width = image.shape
        if isinstance(result, CircleResult):
            _draw_circle(rgb, result.cx, result.cy, result.diameter_px / 2.0, (0.98, 0.75, 0.15))
        elif isinstance(result, RectResult):
            _draw_rect(rgb, result, (0.98, 0.75, 0.15))
        ctx.image = np.clip(rgb, 0.0, 1.0)
        return None


def _draw_circle(rgb: np.ndarray, cx: float, cy: float, radius: float, color: tuple[float, float, float]) -> None:
    height, width = rgb.shape[:2]
    yy, xx = np.ogrid[:height, :width]
    distance = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
    ring = np.abs(distance - radius) <= 1.5
    rgb[ring] = color


def _draw_rect(rgb: np.ndarray, rect: RectResult, color: tuple[float, float, float]) -> None:
    angle = math.radians(rect.angle_deg)
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    half_w, half_h = rect.width_px / 2.0, rect.height_px / 2.0
    corners = [(-half_w, -half_h), (half_w, -half_h), (half_w, half_h), (-half_w, half_h)]
    height, width = rgb.shape[:2]
    points = []
    for x, y in corners:
        px = rect.cx + x * cos_a - y * sin_a
        py = rect.cy + x * sin_a + y * cos_a
        points.append((px, py))
    for index in range(4):
        x0, y0 = points[index]
        x1, y1 = points[(index + 1) % 4]
        steps = int(max(abs(x1 - x0), abs(y1 - y0))) + 1
        for step in range(steps + 1):
            ratio = step / max(steps, 1)
            px = int(round(x0 + (x1 - x0) * ratio))
            py = int(round(y0 + (y1 - y0) * ratio))
            if 0 <= py < height and 0 <= px < width:
                rgb[py, px] = color


# ---------------------------------------------------------------- 默认流水线注册


for _name, _stages in pl.builtin_pipeline_specs().items():
    register_pipeline(_name, _stages)
