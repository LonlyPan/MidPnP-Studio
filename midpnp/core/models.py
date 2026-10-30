"""领域模型：产品、元件、供料器、贴装点与生产记录。

所有模型均为纯 Python 数据对象，不依赖 Qt，便于单元测试和后续复用。
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Iterable


def new_id(prefix: str = "") -> str:
    token = uuid.uuid4().hex[:10]
    return f"{prefix}{token}" if prefix else token


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


class MachineState(str, Enum):
    OFFLINE = "offline"
    CONNECTING = "connecting"
    IDLE = "idle"
    HOMING = "homing"
    READY = "ready"
    RUNNING = "running"
    PAUSED = "paused"
    ERROR = "error"
    ESTOP = "estop"

    @property
    def can_produce(self) -> bool:
        return self in {MachineState.READY, MachineState.PAUSED}

    @property
    def is_busy(self) -> bool:
        return self in {MachineState.RUNNING, MachineState.PAUSED, MachineState.HOMING}


class Side(str, Enum):
    TOP = "Top"
    BOTTOM = "Bottom"

    @property
    def zh(self) -> str:
        return "正面" if self is Side.TOP else "反面"


class VisionMode(str, Enum):
    NONE = "None"
    CHIP = "Chip"
    IC = "IC"
    FIDUCIAL = "Fiducial"

    @property
    def zh(self) -> str:
        return {
            VisionMode.NONE: "不检测",
            VisionMode.CHIP: "芯片对中",
            VisionMode.IC: "IC 对中",
            VisionMode.FIDUCIAL: "基准点",
        }[self]


@dataclass
class Point:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    def distance_to(self, other: "Point", include_z: bool = False) -> float:
        distance = math.hypot(self.x - other.x, self.y - other.y)
        if include_z:
            distance = math.hypot(distance, self.z - other.z)
        return distance

    def to_dict(self) -> dict[str, float]:
        return {"x": round(self.x, 3), "y": round(self.y, 3), "z": round(self.z, 3)}


@dataclass
class Fiducial:
    name: str
    x_mm: float
    y_mm: float
    radius_mm: float = 1.2

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "x_mm": round(self.x_mm, 3),
            "y_mm": round(self.y_mm, 3),
            "radius_mm": round(self.radius_mm, 3),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Fiducial":
        return cls(
            name=str(data.get("name", "FID")),
            x_mm=float(data.get("x_mm", 0)),
            y_mm=float(data.get("y_mm", 0)),
            radius_mm=float(data.get("radius_mm", 1.2)),
        )


@dataclass
class Component:
    id: str
    name: str
    package: str
    length_mm: float = 1.6
    width_mm: float = 0.8
    height_mm: float = 0.8
    nozzle: str = "N1"
    vision_mode: VisionMode = VisionMode.NONE
    speed_pct: int = 100
    color: str = "#c9a227"
    notes: str = ""
    package_id: str = ""
    match_score: float = 0.0
    value: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "package": self.package,
            "length_mm": self.length_mm,
            "width_mm": self.width_mm,
            "height_mm": self.height_mm,
            "nozzle": self.nozzle,
            "vision_mode": self.vision_mode.value,
            "speed_pct": self.speed_pct,
            "color": self.color,
            "notes": self.notes,
            "package_id": self.package_id,
            "match_score": round(self.match_score, 3),
            "value": self.value,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Component":
        try:
            vision = VisionMode(str(data.get("vision_mode", "None")))
        except ValueError:
            vision = VisionMode.NONE
        return cls(
            id=str(data.get("id") or new_id("CMP-")),
            name=str(data.get("name", "未命名元件")),
            package=str(data.get("package", "")),
            length_mm=float(data.get("length_mm", 1.6)),
            width_mm=float(data.get("width_mm", 0.8)),
            height_mm=float(data.get("height_mm", 0.8)),
            nozzle=str(data.get("nozzle", "N1")),
            vision_mode=vision,
            speed_pct=max(10, min(100, int(data.get("speed_pct", 100)))),
            color=str(data.get("color", "#c9a227")),
            notes=str(data.get("notes", "")),
            package_id=str(data.get("package_id", "")),
            match_score=float(data.get("match_score", 0.0)),
            value=str(data.get("value", "")),
        )


@dataclass
class Feeder:
    id: str
    slot: int
    component_id: str
    label: str = ""
    capacity: int = 4000
    remaining: int = 4000
    pitch_mm: float = 4.0
    pick_x_mm: float = 0.0
    pick_y_mm: float = 0.0
    pick_z_mm: float = 0.0
    enabled: bool = True
    low_threshold_pct: int = 15
    tape_width_mm: int = 8

    @property
    def remaining_pct(self) -> int:
        if self.capacity <= 0:
            return 0
        return max(0, min(100, round(self.remaining / self.capacity * 100)))

    @property
    def is_low(self) -> bool:
        return self.remaining_pct <= self.low_threshold_pct

    @property
    def is_empty(self) -> bool:
        return self.remaining <= 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "slot": self.slot,
            "component_id": self.component_id,
            "label": self.label,
            "capacity": self.capacity,
            "remaining": self.remaining,
            "pitch_mm": self.pitch_mm,
            "pick_x_mm": self.pick_x_mm,
            "pick_y_mm": self.pick_y_mm,
            "pick_z_mm": self.pick_z_mm,
            "enabled": self.enabled,
            "low_threshold_pct": self.low_threshold_pct,
            "tape_width_mm": self.tape_width_mm,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Feeder":
        return cls(
            id=str(data.get("id") or new_id("FDR-")),
            slot=int(data.get("slot", 1)),
            component_id=str(data.get("component_id", "")),
            label=str(data.get("label", "")),
            capacity=max(0, int(data.get("capacity", 4000))),
            remaining=max(0, int(data.get("remaining", 4000))),
            pitch_mm=float(data.get("pitch_mm", 4.0)),
            pick_x_mm=float(data.get("pick_x_mm", 0.0)),
            pick_y_mm=float(data.get("pick_y_mm", 0.0)),
            pick_z_mm=float(data.get("pick_z_mm", 0.0)),
            enabled=bool(data.get("enabled", True)),
            low_threshold_pct=int(data.get("low_threshold_pct", 15)),
            tape_width_mm=int(data.get("tape_width_mm", 8)),
        )


@dataclass
class Placement:
    refdes: str
    component_id: str
    x_mm: float
    y_mm: float
    rotation_deg: float = 0.0
    side: Side = Side.TOP
    skip: bool = False
    locked: bool = False
    feeder_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "refdes": self.refdes,
            "component_id": self.component_id,
            "x_mm": round(self.x_mm, 3),
            "y_mm": round(self.y_mm, 3),
            "rotation_deg": round(self.rotation_deg, 2),
            "side": self.side.value,
            "skip": self.skip,
            "locked": self.locked,
            "feeder_id": self.feeder_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Placement":
        try:
            side = Side(str(data.get("side", "Top")))
        except ValueError:
            side = Side.TOP
        return cls(
            refdes=str(data.get("refdes", "")),
            component_id=str(data.get("component_id", "")),
            x_mm=float(data.get("x_mm", 0.0)),
            y_mm=float(data.get("y_mm", 0.0)),
            rotation_deg=float(data.get("rotation_deg", 0.0)),
            side=side,
            skip=bool(data.get("skip", False)),
            locked=bool(data.get("locked", False)),
            feeder_id=str(data.get("feeder_id", "")),
        )


@dataclass
class Product:
    id: str
    name: str
    revision: str = "A"
    board_width_mm: float = 160.0
    board_height_mm: float = 100.0
    board_thickness_mm: float = 1.6
    board_origin_x_mm: float = 120.0
    board_origin_y_mm: float = 125.0
    fiducials: list[Fiducial] = field(default_factory=list)
    placements: list[Placement] = field(default_factory=list)
    notes: str = ""
    updated_at: str = field(default_factory=now_iso)
    alignment: dict[str, Any] | None = None

    @property
    def active_placements(self) -> list[Placement]:
        return [p for p in self.placements if not p.skip]

    @property
    def board_center(self) -> Point:
        return Point(
            self.board_origin_x_mm + self.board_width_mm / 2,
            self.board_origin_y_mm + self.board_height_mm / 2,
        )

    @property
    def board_bounds(self) -> tuple[float, float, float, float]:
        return (
            self.board_origin_x_mm,
            self.board_origin_y_mm,
            self.board_origin_x_mm + self.board_width_mm,
            self.board_origin_y_mm + self.board_height_mm,
        )

    def placement_counts(self, components: Iterable[Component] | None = None) -> dict[str, int]:
        counts: dict[str, int] = {}
        for placement in self.active_placements:
            counts[placement.component_id] = counts.get(placement.component_id, 0) + 1
        return counts

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "revision": self.revision,
            "board_width_mm": self.board_width_mm,
            "board_height_mm": self.board_height_mm,
            "board_thickness_mm": self.board_thickness_mm,
            "board_origin_x_mm": self.board_origin_x_mm,
            "board_origin_y_mm": self.board_origin_y_mm,
            "fiducials": [f.to_dict() for f in self.fiducials],
            "placements": [p.to_dict() for p in self.placements],
            "notes": self.notes,
            "updated_at": self.updated_at,
            "alignment": self.alignment,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Product":
        return cls(
            id=str(data.get("id") or new_id("PRD-")),
            name=str(data.get("name", "未命名产品")),
            revision=str(data.get("revision", "A")),
            board_width_mm=float(data.get("board_width_mm", 160.0)),
            board_height_mm=float(data.get("board_height_mm", 100.0)),
            board_thickness_mm=float(data.get("board_thickness_mm", 1.6)),
            board_origin_x_mm=float(data.get("board_origin_x_mm", 120.0)),
            board_origin_y_mm=float(data.get("board_origin_y_mm", 125.0)),
            fiducials=[Fiducial.from_dict(x) for x in data.get("fiducials", [])],
            placements=[Placement.from_dict(x) for x in data.get("placements", [])],
            notes=str(data.get("notes", "")),
            updated_at=str(data.get("updated_at") or now_iso()),
            alignment=data.get("alignment") if isinstance(data.get("alignment"), dict) else None,
        )


@dataclass
class MachineLimits:
    travel_x_mm: float = 420.0
    travel_y_mm: float = 360.0
    travel_z_mm: float = 30.0
    safe_z_mm: float = 12.0
    max_speed_mm_s: float = 320.0
    nozzle_count: int = 4
    min_x_mm: float = 0.0
    min_y_mm: float = 0.0
    min_z_mm: float = 0.0

    def contains(self, x: float, y: float, z: float = 0.0) -> bool:
        return (
            self.min_x_mm <= x <= self.travel_x_mm
            and self.min_y_mm <= y <= self.travel_y_mm
            and self.min_z_mm <= z <= self.travel_z_mm
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "travel_x_mm": self.travel_x_mm,
            "travel_y_mm": self.travel_y_mm,
            "travel_z_mm": self.travel_z_mm,
            "safe_z_mm": self.safe_z_mm,
            "max_speed_mm_s": self.max_speed_mm_s,
            "nozzle_count": self.nozzle_count,
            "min_x_mm": self.min_x_mm,
            "min_y_mm": self.min_y_mm,
            "min_z_mm": self.min_z_mm,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MachineLimits":
        return cls(
            travel_x_mm=float(data.get("travel_x_mm", 420.0)),
            travel_y_mm=float(data.get("travel_y_mm", 360.0)),
            travel_z_mm=float(data.get("travel_z_mm", 30.0)),
            safe_z_mm=float(data.get("safe_z_mm", 12.0)),
            max_speed_mm_s=float(data.get("max_speed_mm_s", 320.0)),
            nozzle_count=int(data.get("nozzle_count", 4)),
            min_x_mm=float(data.get("min_x_mm", 0.0)),
            min_y_mm=float(data.get("min_y_mm", 0.0)),
            min_z_mm=float(data.get("min_z_mm", 0.0)),
        )


@dataclass
class ValidationIssue:
    level: str  # error / warning
    code: str
    message: str
    refdes: str = ""

    @property
    def is_error(self) -> bool:
        return self.level == "error"


@dataclass
class JobStep:
    index: int
    refdes: str
    component_id: str
    component_name: str
    nozzle: str
    feeder_id: str
    feeder_slot: int
    pick: Point
    place: Point
    rotation_deg: float
    vision_mode: str = "None"


@dataclass
class JobPlan:
    product_id: str
    product_name: str
    steps: list[JobStep]
    estimated_cycle_s: float
    created_at: str = field(default_factory=now_iso)
    optimized: bool = True

    @property
    def total(self) -> int:
        return len(self.steps)

    @property
    def feeder_usage(self) -> dict[str, int]:
        usage: dict[str, int] = {}
        for step in self.steps:
            usage[step.feeder_id] = usage.get(step.feeder_id, 0) + 1
        return usage

    def to_dict(self) -> dict[str, Any]:
        return {
            "product_id": self.product_id,
            "product_name": self.product_name,
            "steps": [
                {
                    "index": s.index,
                    "refdes": s.refdes,
                    "component_id": s.component_id,
                    "component_name": s.component_name,
                    "nozzle": s.nozzle,
                    "feeder_id": s.feeder_id,
                    "feeder_slot": s.feeder_slot,
                    "pick": s.pick.to_dict(),
                    "place": s.place.to_dict(),
                    "rotation_deg": s.rotation_deg,
                    "vision_mode": s.vision_mode,
                }
                for s in self.steps
            ],
            "estimated_cycle_s": round(self.estimated_cycle_s, 2),
            "created_at": self.created_at,
            "optimized": self.optimized,
        }


@dataclass
class RunRecord:
    id: str
    product_id: str
    product_name: str
    started_at: str
    finished_at: str
    total: int
    placed: int
    failed: int
    skipped: int
    status: str
    duration_s: float
    notes: str = ""

    @property
    def yield_pct(self) -> float:
        attempted = self.placed + self.failed
        return self.placed / attempted * 100 if attempted else 0.0

    @property
    def cph(self) -> float:
        return self.placed / (self.duration_s / 3600) if self.duration_s > 0 else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "product_id": self.product_id,
            "product_name": self.product_name,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "total": self.total,
            "placed": self.placed,
            "failed": self.failed,
            "skipped": self.skipped,
            "status": self.status,
            "duration_s": round(self.duration_s, 1),
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RunRecord":
        return cls(
            id=str(data.get("id") or new_id("RUN-")),
            product_id=str(data.get("product_id", "")),
            product_name=str(data.get("product_name", "")),
            started_at=str(data.get("started_at", now_iso())),
            finished_at=str(data.get("finished_at", now_iso())),
            total=int(data.get("total", 0)),
            placed=int(data.get("placed", 0)),
            failed=int(data.get("failed", 0)),
            skipped=int(data.get("skipped", 0)),
            status=str(data.get("status", "Completed")),
            duration_s=float(data.get("duration_s", 0)),
            notes=str(data.get("notes", "")),
        )


@dataclass
class LogEntry:
    id: int
    timestamp: str
    level: str
    source: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "level": self.level,
            "source": self.source,
            "message": self.message,
        }
