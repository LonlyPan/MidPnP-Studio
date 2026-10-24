"""图像流水线：Stage 链、结果模型与 JSON 序列化。

对应 OpenPnP 的 `CvPipeline`：一条流水线由若干 stage 顺序执行，最后一个
结果写入 `results` 通道；stage 返回空表示「本阶段不改变图像」。差异是
OpenPnP 用 XML 序列化，这里用等价 JSON，便于随界面保存和版本管理。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

import numpy as np


# ---------------------------------------------------------------- 结果模型


@dataclass
class Contour:
    points: np.ndarray  # (N, 2)，像素坐标
    area_px: float = 0.0
    center: tuple[float, float] = (0.0, 0.0)

    @property
    def area_mm2(self) -> float:
        return self.area_px

    def __len__(self) -> int:
        return int(len(self.points))


@dataclass
class CircleResult:
    cx: float
    cy: float
    diameter_px: float
    score: float = 1.0
    source: str = ""

    @property
    def radius_px(self) -> float:
        return self.diameter_px / 2.0

    def to_keypoint(self, calibration: Any, camera_center: Any) -> "KeyPoint":
        offset = calibration.pixel_to_mm_offset(self.cx, self.cy)
        return KeyPoint(
            x=camera_center.x + offset.x,
            y=camera_center.y + offset.y,
            angle_deg=0.0,
            score=self.score,
            diameter_mm=self.diameter_px / max(calibration.pixels_per_mm, 1e-9),
        )


@dataclass
class RectResult:
    cx: float
    cy: float
    width_px: float
    height_px: float
    angle_deg: float  # 图像坐标系角度（OpenCV 约定，Y 向下）
    score: float = 1.0
    source: str = ""

    @property
    def aspect(self) -> float:
        small = min(self.width_px, self.height_px)
        return max(self.width_px, self.height_px) / small if small > 1e-9 else 0.0

    def to_keypoint(self, calibration: Any, camera_center: Any) -> "KeyPoint":
        offset = calibration.pixel_to_mm_offset(self.cx, self.cy)
        return KeyPoint(
            x=camera_center.x + offset.x,
            y=camera_center.y + offset.y,
            angle_deg=calibration.angle_to_machine(self.angle_deg),
            score=self.score,
            width_mm=self.width_px / max(calibration.pixels_per_mm, 1e-9),
            height_mm=self.height_px / max(calibration.pixels_per_mm, 1e-9),
        )


@dataclass
class KeyPoint:
    x: float
    y: float
    angle_deg: float = 0.0
    score: float = 1.0
    diameter_mm: float = 0.0
    width_mm: float = 0.0
    height_mm: float = 0.0

    def to_dict(self) -> dict[str, float]:
        return {
            "x": round(self.x, 4),
            "y": round(self.y, 4),
            "angle_deg": round(self.angle_deg, 3),
            "score": round(self.score, 4),
            "diameter_mm": round(self.diameter_mm, 4),
            "width_mm": round(self.width_mm, 4),
            "height_mm": round(self.height_mm, 4),
        }


# ---------------------------------------------------------------- 上下文


@dataclass
class PipelineContext:
    image: np.ndarray
    original: np.ndarray
    models: dict[str, Any] = field(default_factory=dict)
    props: dict[str, Any] = field(default_factory=dict)
    timings: list[tuple[str, float]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def pixels_per_mm(self) -> float:
        return float(self.props.get("pixels_per_mm", 1.0) or 1.0)

    @property
    def model(self) -> Any:
        return self.models.get("results", self.models.get(self.props.get("_last_stage", ""), None))


@dataclass
class PipelineResult:
    image: np.ndarray
    models: dict[str, Any]
    results: Any = None
    duration_ms: float = 0.0
    timings: list[tuple[str, float]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def keypoints(self, calibration: Any, camera_center: Any) -> list[KeyPoint]:
        model = self.results
        if model is None:
            return []
        if isinstance(model, (list, tuple)):
            return [item.to_keypoint(calibration, camera_center) for item in model]
        if hasattr(model, "to_keypoint"):
            return [model.to_keypoint(calibration, camera_center)]
        return []

    def circles(self) -> list[CircleResult]:
        model = self.results
        if isinstance(model, CircleResult):
            return [model]
        if isinstance(model, (list, tuple)):
            return [item for item in model if isinstance(item, CircleResult)]
        return []

    def rect(self) -> RectResult | None:
        return self.results if isinstance(self.results, RectResult) else None


# ---------------------------------------------------------------- Stage


StageFactory = Callable[[dict[str, Any]], "Stage"]


class Stage:
    """流水线 stage 基类。子类实现 `process(ctx)`，返回模型（可选）。"""

    NAME = "Stage"
    DESCRIPTION = ""
    DEFAULTS: dict[str, Any] = {}

    def __init__(self, **params: Any) -> None:
        self.params: dict[str, Any] = dict(self.DEFAULTS)
        self.params.update(params)
        self.enabled = bool(self.params.pop("enabled", True))

    # ---------------- 参数 ----------------

    def get(self, name: str, default: Any = None) -> Any:
        value = self.params.get(name, default)
        return value

    def num(self, name: str, default: float = 0.0) -> float:
        try:
            return float(self.params.get(name, default))
        except (TypeError, ValueError):
            return default

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"name": self.NAME}
        clean = {
            key: value
            for key, value in self.params.items()
            if value != self.DEFAULTS.get(key) or key not in self.DEFAULTS
        }
        if not self.enabled:
            clean["enabled"] = False
        if clean:
            payload["params"] = clean
        return payload

    def describe(self) -> str:
        if not self.params:
            return self.NAME
        summary = ", ".join(
            f"{key}={value}" for key, value in list(self.params.items())[:3] if not isinstance(value, (dict, list))
        )
        return f"{self.NAME}({summary})" if summary else self.NAME

    # ---------------- 执行 ----------------

    def process(self, ctx: PipelineContext) -> Any:
        raise NotImplementedError


REGISTRY: dict[str, type[Stage]] = {}
PIPELINES: dict[str, list[dict[str, Any]]] = {}


def register_stage(cls: type[Stage]) -> type[Stage]:
    REGISTRY[cls.NAME] = cls
    return cls


def register_pipeline(name: str, stages: Iterable[dict[str, Any]]) -> None:
    PIPELINES[name] = [dict(item) for item in stages]


def stage_from_dict(data: dict[str, Any]) -> Stage:
    name = str(data.get("name", ""))
    cls = REGISTRY.get(name)
    if cls is None:
        raise ValueError(f"未知的视觉 stage：{name}")
    params = data.get("params") or {}
    if not isinstance(params, dict):
        params = {}
    return cls(**params)


class Pipeline:
    def __init__(self, stages: Iterable[Stage] | None = None, name: str = "") -> None:
        self.stages: list[Stage] = list(stages or [])
        self.name = name

    # ---------------- 构建 / 序列化 ----------------

    def add(self, stage: Stage) -> "Pipeline":
        self.stages.append(stage)
        return self

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "stages": [stage.to_dict() for stage in self.stages]}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Pipeline":
        stages = [stage_from_dict(item) for item in data.get("stages", []) if isinstance(item, dict)]
        return cls(stages, name=str(data.get("name", "")))

    def copy(self) -> "Pipeline":
        return Pipeline([type(stage)(**dict(stage.params, enabled=stage.enabled)) for stage in self.stages], self.name)

    def __len__(self) -> int:
        return len(self.stages)

    # ---------------- 执行 ----------------

    def run(self, image: np.ndarray, props: dict[str, Any] | None = None) -> PipelineResult:
        if image is None:
            raise ValueError("流水线输入图像为空")
        array = _as_gray(image)
        ctx = PipelineContext(image=array.copy(), original=array.copy(), props=dict(props or {}))
        started = time.perf_counter()
        for stage in self.stages:
            if not stage.enabled:
                ctx.notes.append(f"stage {stage.NAME} 已禁用，跳过")
                continue
            ctx.props["_last_stage"] = stage.NAME
            stage_started = time.perf_counter()
            try:
                model = stage.process(ctx)
            except _StageAbort:
                ctx.notes.append(f"stage {stage.NAME} 中止流水线")
                break
            if model is not None:
                ctx.models[stage.NAME] = model
                ctx.props["_last_model_stage"] = stage.NAME
                if stage.NAME != "results":
                    ctx.props["_last_model"] = model
            ctx.timings.append((stage.NAME, (time.perf_counter() - stage_started) * 1000))
        duration = (time.perf_counter() - started) * 1000
        results = ctx.models.get("results")
        if results is None:
            results = ctx.models.get(ctx.props.get("_last_stage", ""), None)
        return PipelineResult(
            image=ctx.image,
            models=ctx.models,
            results=results,
            duration_ms=duration,
            timings=ctx.timings,
            notes=ctx.notes,
        )


class _StageAbort(Exception):
    """stage 主动中止流水线（对应 OpenPnP 的 TerminalException）。"""


# ---------------------------------------------------------------- 默认流水线


def builtin_pipeline_specs() -> dict[str, list[dict[str, Any]]]:
    return {
        "fiducial-default": [
            {"name": "ConvertColor", "params": {"mode": "gray"}},
            {"name": "BlurGaussian", "params": {"kernel": 3}},
            {"name": "DetectCircularSymmetry", "params": {"auto": False, "threshold": 0.6, "min_diameter_mm": 0.4, "max_diameter_mm": 6.0, "min_score": 0.3}},
            {"name": "SelectSingle", "params": {"criterion": "center"}},
        ],
        "fiducial-simple": [
            {"name": "ConvertColor", "params": {"mode": "gray"}},
            {"name": "Threshold", "params": {"threshold": 0.6}},
            {"name": "MorphClose", "params": {"kernel": 3}},
            {"name": "FindContours", "params": {"min_area_px": 10}},
            {"name": "FilterContours", "params": {"min_area_mm2": 0.3, "max_area_mm2": 80.0}},
            {"name": "MinEnclosingCircle"},
            {"name": "SelectSingle", "params": {"criterion": "center"}},
        ],
        "bottom-default": [
            {"name": "BlurGaussian", "params": {"kernel": 3}},
            {"name": "MaskCircle", "params": {"diameter_mm": 10.0}},
            {"name": "Threshold", "params": {"threshold": 0.5}},
            {"name": "FindContours", "params": {"min_area_px": 20}},
            {"name": "FilterContours", "params": {"min_area_mm2": 0.05}},
            {"name": "MinAreaRect"},
            {"name": "SetResult"},
        ],
        "bottom-ic": [
            {"name": "BlurGaussian", "params": {"kernel": 3}},
            {"name": "MaskCircle", "params": {"diameter_mm": 14.0}},
            {"name": "Threshold", "params": {"threshold": 0.5}},
            {"name": "FindContours", "params": {"min_area_px": 20}},
            {"name": "FilterContours", "params": {"min_area_mm2": 0.2}},
            {"name": "MinAreaRect"},
            {"name": "SetResult"},
        ],
    }


def build_pipeline(spec: str | dict[str, Any] | list[dict[str, Any]]) -> Pipeline:
    """按名称 / 定义列表 / 序列化字典构建流水线。"""
    if isinstance(spec, str):
        stages = PIPELINES.get(spec)
        if stages is None:
            stages = builtin_pipeline_specs().get(spec)
        if stages is None:
            raise ValueError(f"未知的视觉流水线：{spec}")
        return Pipeline([stage_from_dict(item) for item in stages], name=spec)
    if isinstance(spec, dict):
        return Pipeline.from_dict(spec)
    return Pipeline([stage_from_dict(item) for item in spec])


# ---------------------------------------------------------------- 图像工具


def _as_gray(image: np.ndarray) -> np.ndarray:
    array = np.asarray(image)
    if array.ndim == 3:
        array = array[..., :3].astype(np.float32).mean(axis=2)
    array = array.astype(np.float32)
    if array.max(initial=0.0) > 1.5:
        array = array / 255.0
    return np.clip(array, 0.0, 1.0)


def otsu_threshold(image: np.ndarray, bins: int = 128) -> float:
    array = np.clip(np.asarray(image, dtype=np.float32).ravel(), 0.0, 1.0)
    histogram, edges = np.histogram(array, bins=bins, range=(0.0, 1.0))
    total = histogram.sum()
    if total <= 0:
        return 0.5
    probabilities = histogram / total
    centers = (edges[:-1] + edges[1:]) / 2
    omega = np.cumsum(probabilities)
    mu = np.cumsum(probabilities * centers)
    mu_total = mu[-1]
    with np.errstate(divide="ignore", invalid="ignore"):
        between = (mu_total * omega - mu) ** 2 / (omega * (1.0 - omega))
    between = np.nan_to_num(between)
    index = int(np.argmax(between))
    return float(centers[index])
