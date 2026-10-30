"""机型配置（Machine Profile）。

参考 OpenPnP 的 `machine.xml` 设计：整台机器由「轴 → 头/吸嘴 → 相机 → 供料器
→ 驱动 → 视觉参数 → 安全参数」描述，加载不同配置文件即可切换机型，业务代码
（规划、生产、视觉）只依赖抽象对象，不写死任何一家的行程或吸嘴。

与 OpenPnP 的差异：OpenPnP 用 XML + 反射序列化（`sp` 包），这里用 JSON，
字段名尽量保持语义一致（axes / heads / nozzles / cameras / feeders / driver），
便于对照阅读与迁移。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from ..models import MachineLimits

SCHEMA_ID = "midpnp.machine-profile/1"

DRIVER_TYPES = {
    "simulator",
    "jsonl-tcp",
    "jsonl-serial",
    "gcode-tcp",
    "gcode-serial",
}
CAMERA_MOUNTS = {"head", "fixed", "gantry"}
HOME_MODES = {"min", "max", "zero", "center", "none"}


@dataclass
class Point3:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    def to_dict(self) -> dict[str, float]:
        return {"x": round(self.x, 3), "y": round(self.y, 3), "z": round(self.z, 3)}

    @classmethod
    def from_dict(cls, data: Any) -> "Point3":
        if not isinstance(data, dict):
            return cls()
        return cls(
            x=float(data.get("x", 0.0)),
            y=float(data.get("y", 0.0)),
            z=float(data.get("z", 0.0)),
        )


@dataclass
class ProfileIssue:
    level: str  # error / warning
    field: str
    message: str

    @property
    def is_error(self) -> bool:
        return self.level == "error"


@dataclass
class AxisConfig:
    id: str
    name: str = ""
    unit: str = "mm"  # mm / deg
    min: float = 0.0
    max: float = 400.0
    home: str = "min"
    max_speed: float = 300.0
    accel: float = 2000.0
    steps_per_mm: float = 80.0
    inverted: bool = False
    soft_limit: bool = True

    @property
    def travel(self) -> float:
        return max(0.0, self.max - self.min)

    @property
    def is_linear(self) -> bool:
        return self.unit == "mm"

    def clamp(self, value: float) -> float:
        if not self.soft_limit:
            return value
        return max(self.min, min(self.max, value))

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name or self.id.upper(),
            "unit": self.unit,
            "min": self.min,
            "max": self.max,
            "home": self.home,
            "max_speed": self.max_speed,
            "accel": self.accel,
            "steps_per_mm": self.steps_per_mm,
            "inverted": self.inverted,
            "soft_limit": self.soft_limit,
        }

    @classmethod
    def from_dict(cls, axis_id: str, data: dict[str, Any]) -> "AxisConfig":
        return cls(
            id=str(data.get("id") or axis_id),
            name=str(data.get("name", axis_id.upper())),
            unit=str(data.get("unit", "deg" if axis_id.lower() == "c" else "mm")),
            min=float(data.get("min", -180.0 if axis_id.lower() == "c" else 0.0)),
            max=float(data.get("max", 180.0 if axis_id.lower() == "c" else 400.0)),
            home=str(data.get("home", "zero" if axis_id.lower() == "c" else "min")),
            max_speed=float(data.get("max_speed", 300.0)),
            accel=float(data.get("accel", 2000.0)),
            steps_per_mm=float(data.get("steps_per_mm", 80.0)),
            inverted=bool(data.get("inverted", False)),
            soft_limit=bool(data.get("soft_limit", True)),
        )


@dataclass
class NozzleConfig:
    id: str
    name: str = ""
    tip_diameter_mm: float = 0.4
    tip_length_mm: float = 8.0
    max_part_height_mm: float = 6.0
    offset: Point3 = field(default_factory=Point3)
    rotation_axis: str = "c"
    rotation_offset_deg: float = 0.0
    vision_pipeline: str = "bottom-default"
    vacuum: bool = True
    blow_off: bool = True
    pick_dwell_ms: int = 60
    place_dwell_ms: int = 80
    compatible_tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name or self.id,
            "tip_diameter_mm": self.tip_diameter_mm,
            "tip_length_mm": self.tip_length_mm,
            "max_part_height_mm": self.max_part_height_mm,
            "offset": self.offset.to_dict(),
            "rotation_axis": self.rotation_axis,
            "rotation_offset_deg": self.rotation_offset_deg,
            "vision_pipeline": self.vision_pipeline,
            "vacuum": self.vacuum,
            "blow_off": self.blow_off,
            "pick_dwell_ms": self.pick_dwell_ms,
            "place_dwell_ms": self.place_dwell_ms,
            "compatible_tags": list(self.compatible_tags),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], index: int = 0) -> "NozzleConfig":
        return cls(
            id=str(data.get("id") or f"N{index + 1}"),
            name=str(data.get("name", "")),
            tip_diameter_mm=float(data.get("tip_diameter_mm", 0.4)),
            tip_length_mm=float(data.get("tip_length_mm", 8.0)),
            max_part_height_mm=float(data.get("max_part_height_mm", 6.0)),
            offset=Point3.from_dict(data.get("offset", {})),
            rotation_axis=str(data.get("rotation_axis", "c")),
            rotation_offset_deg=float(data.get("rotation_offset_deg", 0.0)),
            vision_pipeline=str(data.get("vision_pipeline", "bottom-default")),
            vacuum=bool(data.get("vacuum", True)),
            blow_off=bool(data.get("blow_off", True)),
            pick_dwell_ms=int(data.get("pick_dwell_ms", 60)),
            place_dwell_ms=int(data.get("place_dwell_ms", 80)),
            compatible_tags=[str(item) for item in data.get("compatible_tags", [])],
        )


@dataclass
class HeadConfig:
    id: str
    name: str = ""
    axis_x: str = "x"
    axis_y: str = "y"
    axis_z: str = "z"
    nozzle_change: str = "manual"  # manual / automatic / none
    nozzles: list[NozzleConfig] = field(default_factory=list)

    def nozzle(self, nozzle_id: str) -> NozzleConfig | None:
        for nozzle in self.nozzles:
            if nozzle.id == nozzle_id:
                return nozzle
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name or self.id,
            "axis_x": self.axis_x,
            "axis_y": self.axis_y,
            "axis_z": self.axis_z,
            "nozzle_change": self.nozzle_change,
            "nozzles": [nozzle.to_dict() for nozzle in self.nozzles],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], index: int = 0) -> "HeadConfig":
        return cls(
            id=str(data.get("id") or f"H{index + 1}"),
            name=str(data.get("name", "")),
            axis_x=str(data.get("axis_x", "x")),
            axis_y=str(data.get("axis_y", "y")),
            axis_z=str(data.get("axis_z", "z")),
            nozzle_change=str(data.get("nozzle_change", "manual")),
            nozzles=[
                NozzleConfig.from_dict(item, position)
                for position, item in enumerate(data.get("nozzles", []))
            ],
        )


@dataclass
class CameraConfig:
    id: str
    name: str = ""
    mount: str = "head"  # head / fixed / gantry
    resolution: tuple[int, int] = (1280, 720)
    pixels_per_mm: float = 22.0
    offset: Point3 = field(default_factory=Point3)
    location: Point3 = field(default_factory=Point3)
    pipeline: str = "fiducial-default"
    lighting: str = "ring"
    exposure_ms: float = 8.0
    enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name or self.id,
            "mount": self.mount,
            "resolution": [int(self.resolution[0]), int(self.resolution[1])],
            "pixels_per_mm": self.pixels_per_mm,
            "offset": self.offset.to_dict(),
            "location": self.location.to_dict(),
            "pipeline": self.pipeline,
            "lighting": self.lighting,
            "exposure_ms": self.exposure_ms,
            "enabled": self.enabled,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], index: int = 0) -> "CameraConfig":
        resolution = data.get("resolution") or [1280, 720]
        try:
            width, height = int(resolution[0]), int(resolution[1])
        except (TypeError, ValueError, IndexError):
            width, height = 1280, 720
        return cls(
            id=str(data.get("id") or f"CAM-{index + 1:02d}"),
            name=str(data.get("name", "")),
            mount=str(data.get("mount", "head")),
            resolution=(width, height),
            pixels_per_mm=float(data.get("pixels_per_mm", 22.0)),
            offset=Point3.from_dict(data.get("offset", {})),
            location=Point3.from_dict(data.get("location", {})),
            pipeline=str(data.get("pipeline", "fiducial-default")),
            lighting=str(data.get("lighting", "ring")),
            exposure_ms=float(data.get("exposure_ms", 8.0)),
            enabled=bool(data.get("enabled", True)),
        )


@dataclass
class FeederBankConfig:
    type: str = "slot"  # slot / tray
    slot_count: int = 32
    first_slot: int = 1
    slot_pitch_mm: float = 12.0
    tape_pitch_mm: float = 4.0
    origin: Point3 = field(default_factory=lambda: Point3(18.0, 330.0, 0.0))
    direction: str = "x"  # x / y
    top_count: int = 0  # 上排电动飞达数量（0 = 不分区）
    bottom_count: int = 0  # 下排电动飞达数量

    def slot_position(self, slot: int) -> tuple[float, float]:
        index = max(0, int(slot) - self.first_slot)
        offset = index * self.slot_pitch_mm
        if self.direction == "y":
            return (self.origin.x, self.origin.y - offset)
        return (self.origin.x + offset, self.origin.y)

    def bank_of(self, slot: int) -> str:
        """返回槽位所在料区：top / bottom / both。"""
        index = max(0, int(slot) - self.first_slot)
        if self.top_count > 0 and index < self.top_count:
            return "top"
        if self.bottom_count > 0 and index >= self.top_count:
            return "bottom"
        return "both"

    def bank_slots(self, bank: str) -> tuple[int, int]:
        """返回某料区的槽位区间 [start, end)。"""
        if bank == "top":
            return (self.first_slot, self.first_slot + max(0, self.top_count))
        if bank == "bottom":
            start = self.first_slot + max(0, self.top_count)
            return (start, start + max(0, self.bottom_count))
        return (self.first_slot, self.first_slot + max(0, self.slot_count))

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "slot_count": self.slot_count,
            "first_slot": self.first_slot,
            "slot_pitch_mm": self.slot_pitch_mm,
            "tape_pitch_mm": self.tape_pitch_mm,
            "origin": self.origin.to_dict(),
            "direction": self.direction,
            "top_count": self.top_count,
            "bottom_count": self.bottom_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FeederBankConfig":
        return cls(
            type=str(data.get("type", "slot")),
            slot_count=int(data.get("slot_count", 32)),
            first_slot=int(data.get("first_slot", 1)),
            slot_pitch_mm=float(data.get("slot_pitch_mm", 12.0)),
            tape_pitch_mm=float(data.get("tape_pitch_mm", 4.0)),
            origin=Point3.from_dict(data.get("origin", {"x": 18.0, "y": 330.0})),
            direction=str(data.get("direction", "x")),
            top_count=int(data.get("top_count", 0)),
            bottom_count=int(data.get("bottom_count", 0)),
        )


@dataclass
class DriverConfig:
    type: str = "simulator"
    protocol: str = "jsonl"
    host: str = "192.168.1.50"
    port: int = 5025
    serial_port: str = "COM3"
    baud_rate: int = 115200
    timeout_s: float = 10.0
    connect_delay_ms: int = 0
    commands: dict[str, str] = field(default_factory=dict)
    ok_responses: list[str] = field(default_factory=lambda: ["ok", "Ok", "OK", "done"])

    @property
    def transport(self) -> str:
        if self.type == "simulator":
            return "simulator"
        if self.type.endswith("serial"):
            return "serial"
        return "tcp"

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "protocol": self.protocol,
            "host": self.host,
            "port": self.port,
            "serial_port": self.serial_port,
            "baud_rate": self.baud_rate,
            "timeout_s": self.timeout_s,
            "connect_delay_ms": self.connect_delay_ms,
            "commands": dict(self.commands),
            "ok_responses": list(self.ok_responses),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DriverConfig":
        return cls(
            type=str(data.get("type", "simulator")),
            protocol=str(data.get("protocol", "jsonl")),
            host=str(data.get("host", "192.168.1.50")),
            port=int(data.get("port", 5025)),
            serial_port=str(data.get("serial_port", "COM3")),
            baud_rate=int(data.get("baud_rate", 115200)),
            timeout_s=float(data.get("timeout_s", 10.0)),
            connect_delay_ms=int(data.get("connect_delay_ms", 0)),
            commands={str(k): str(v) for k, v in (data.get("commands") or {}).items()},
            ok_responses=[str(item) for item in data.get("ok_responses", ["ok", "OK"])],
        )


@dataclass
class FiducialParams:
    search_radius_mm: float = 12.0
    threshold: float = 0.45
    min_area_mm2: float = 0.3
    max_area_mm2: float = 80.0
    shape: str = "circle"  # circle / square / any
    min_score: float = 0.55
    required: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "search_radius_mm": self.search_radius_mm,
            "threshold": self.threshold,
            "min_area_mm2": self.min_area_mm2,
            "max_area_mm2": self.max_area_mm2,
            "shape": self.shape,
            "min_score": self.min_score,
            "required": self.required,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FiducialParams":
        return cls(
            search_radius_mm=float(data.get("search_radius_mm", 12.0)),
            threshold=float(data.get("threshold", 0.45)),
            min_area_mm2=float(data.get("min_area_mm2", 0.3)),
            max_area_mm2=float(data.get("max_area_mm2", 80.0)),
            shape=str(data.get("shape", "circle")),
            min_score=float(data.get("min_score", 0.55)),
            required=int(data.get("required", 1)),
        )


@dataclass
class BottomVisionParams:
    max_offset_mm: float = 2.0
    max_angle_deg: float = 20.0
    angle_step_deg: float = 1.0
    min_score: float = 0.55
    correction: str = "both"  # both / offset / angle / none

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_offset_mm": self.max_offset_mm,
            "max_angle_deg": self.max_angle_deg,
            "angle_step_deg": self.angle_step_deg,
            "min_score": self.min_score,
            "correction": self.correction,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BottomVisionParams":
        return cls(
            max_offset_mm=float(data.get("max_offset_mm", 2.0)),
            max_angle_deg=float(data.get("max_angle_deg", 20.0)),
            angle_step_deg=float(data.get("angle_step_deg", 1.0)),
            min_score=float(data.get("min_score", 0.55)),
            correction=str(data.get("correction", "both")),
        )


@dataclass
class VisionConfig:
    fiducial: FiducialParams = field(default_factory=FiducialParams)
    bottom: BottomVisionParams = field(default_factory=BottomVisionParams)

    def to_dict(self) -> dict[str, Any]:
        return {"fiducial": self.fiducial.to_dict(), "bottom": self.bottom.to_dict()}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "VisionConfig":
        return cls(
            fiducial=FiducialParams.from_dict(data.get("fiducial", {})),
            bottom=BottomVisionParams.from_dict(data.get("bottom", {})),
        )


@dataclass
class SafetyConfig:
    safe_z_mm: float = 12.0
    max_speed_mm_s: float = 320.0
    soft_limits: bool = True
    estop: str = "software"
    vacuum_settle_ms: int = 80

    def to_dict(self) -> dict[str, Any]:
        return {
            "safe_z_mm": self.safe_z_mm,
            "max_speed_mm_s": self.max_speed_mm_s,
            "soft_limits": self.soft_limits,
            "estop": self.estop,
            "vacuum_settle_ms": self.vacuum_settle_ms,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SafetyConfig":
        return cls(
            safe_z_mm=float(data.get("safe_z_mm", 12.0)),
            max_speed_mm_s=float(data.get("max_speed_mm_s", 320.0)),
            soft_limits=bool(data.get("soft_limits", True)),
            estop=str(data.get("estop", "software")),
            vacuum_settle_ms=int(data.get("vacuum_settle_ms", 80)),
        )


@dataclass
class MachineProfile:
    id: str
    name: str
    description: str = ""
    vendor: str = ""
    image: str = ""  # assets 下的设备图片，例如 machines/m1.png
    schema: str = SCHEMA_ID
    axes: dict[str, AxisConfig] = field(default_factory=dict)
    heads: list[HeadConfig] = field(default_factory=list)
    cameras: list[CameraConfig] = field(default_factory=list)
    feeders: FeederBankConfig = field(default_factory=FeederBankConfig)
    driver: DriverConfig = field(default_factory=DriverConfig)
    vision: VisionConfig = field(default_factory=VisionConfig)
    safety: SafetyConfig = field(default_factory=SafetyConfig)
    tags: list[str] = field(default_factory=list)
    builtin: bool = False
    source_path: str = ""

    # ---------------- 便捷访问 ----------------

    @property
    def primary_head(self) -> HeadConfig | None:
        return self.heads[0] if self.heads else None

    def head(self, head_id: str = "") -> HeadConfig | None:
        if not head_id:
            return self.primary_head
        for head in self.heads:
            if head.id == head_id:
                return head
        return None

    def nozzle_ids(self) -> list[str]:
        return [nozzle.id for head in self.heads for nozzle in head.nozzles]

    def nozzle(self, nozzle_id: str) -> NozzleConfig | None:
        for head in self.heads:
            found = head.nozzle(nozzle_id)
            if found is not None:
                return found
        return None

    def camera(self, camera_id: str = "") -> CameraConfig | None:
        cameras = [camera for camera in self.cameras if camera.enabled]
        if not camera_id:
            return cameras[0] if cameras else (self.cameras[0] if self.cameras else None)
        for camera in self.cameras:
            if camera.id == camera_id:
                return camera
        return None

    def axis(self, axis_id: str) -> AxisConfig | None:
        return self.axes.get(axis_id.lower())

    # ---------------- 映射 ----------------

    def limits(self) -> MachineLimits:
        """转换为业务层使用的行程/速度限制。"""
        x = self.axis("x")
        y = self.axis("y")
        z = self.axis("z")
        return MachineLimits(
            travel_x_mm=x.max if x else 420.0,
            travel_y_mm=y.max if y else 360.0,
            travel_z_mm=z.max if z else 30.0,
            safe_z_mm=self.safety.safe_z_mm,
            max_speed_mm_s=self.safety.max_speed_mm_s,
            nozzle_count=max(1, len(self.nozzle_ids())),
            min_x_mm=x.min if x and x.soft_limit else 0.0,
            min_y_mm=y.min if y and y.soft_limit else 0.0,
            min_z_mm=z.min if z and z.soft_limit else 0.0,
        )

    def settings_values(self) -> dict[str, Any]:
        """投影到 AppSettings，保持旧页面/旧逻辑兼容。"""
        limits = self.limits()
        return {
            "machine_name": self.name,
            "connection_mode": self.driver.transport,
            "host": self.driver.host,
            "port": self.driver.port,
            "serial_port": self.driver.serial_port,
            "baud_rate": self.driver.baud_rate,
            "travel_x_mm": limits.travel_x_mm,
            "travel_y_mm": limits.travel_y_mm,
            "travel_z_mm": limits.travel_z_mm,
            "safe_z_mm": limits.safe_z_mm,
            "max_speed_mm_s": limits.max_speed_mm_s,
            "nozzle_count": limits.nozzle_count,
        }

    # ---------------- 校验 ----------------

    def validate(self) -> list[ProfileIssue]:
        issues: list[ProfileIssue] = []
        if not self.id.strip():
            issues.append(ProfileIssue("error", "id", "机型 ID 不能为空"))
        if not self.name.strip():
            issues.append(ProfileIssue("error", "name", "机型名称不能为空"))
        if self.schema != SCHEMA_ID:
            issues.append(
                ProfileIssue("warning", "schema", f"schema 版本不符（{self.schema}），已按当前版本读取")
            )

        for axis_id in ("x", "y", "z"):
            axis = self.axes.get(axis_id)
            if axis is None:
                issues.append(ProfileIssue("error", f"axes.{axis_id}", f"缺少 {axis_id.upper()} 轴定义"))
                continue
            issues.extend(self._validate_axis(axis))

        if not self.heads:
            issues.append(ProfileIssue("error", "heads", "至少需要一个贴装头"))
        head_ids: set[str] = set()
        nozzle_ids: set[str] = set()
        for head in self.heads:
            if head.id in head_ids:
                issues.append(ProfileIssue("error", f"heads.{head.id}", f"贴装头 ID 重复：{head.id}"))
            head_ids.add(head.id)
            if not head.nozzles:
                issues.append(ProfileIssue("error", f"heads.{head.id}.nozzles", f"{head.id} 没有吸嘴"))
            for nozzle in head.nozzles:
                if nozzle.id in nozzle_ids:
                    issues.append(ProfileIssue("error", f"nozzle.{nozzle.id}", f"吸嘴 ID 重复：{nozzle.id}"))
                nozzle_ids.add(nozzle.id)
                if nozzle.tip_diameter_mm <= 0:
                    issues.append(ProfileIssue("error", f"nozzle.{nozzle.id}", "吸嘴直径必须大于 0"))
                if nozzle.rotation_axis and nozzle.rotation_axis not in self.axes:
                    issues.append(
                        ProfileIssue(
                            "warning",
                            f"nozzle.{nozzle.id}.rotation_axis",
                            f"旋转轴 {nozzle.rotation_axis} 未定义",
                        )
                    )

        if not self.cameras:
            issues.append(ProfileIssue("warning", "cameras", "未配置相机，视觉功能不可用"))
        camera_ids: set[str] = set()
        for camera in self.cameras:
            if camera.id in camera_ids:
                issues.append(ProfileIssue("error", f"camera.{camera.id}", f"相机 ID 重复：{camera.id}"))
            camera_ids.add(camera.id)
            if camera.mount not in CAMERA_MOUNTS:
                issues.append(
                    ProfileIssue("warning", f"camera.{camera.id}.mount", f"未知安装方式：{camera.mount}")
                )
            if camera.pixels_per_mm <= 0:
                issues.append(
                    ProfileIssue("error", f"camera.{camera.id}", "pixels_per_mm（像素/毫米）必须大于 0")
                )
            if camera.resolution[0] <= 0 or camera.resolution[1] <= 0:
                issues.append(ProfileIssue("error", f"camera.{camera.id}", "相机分辨率必须大于 0"))

        if self.driver.type not in DRIVER_TYPES:
            issues.append(ProfileIssue("error", "driver.type", f"不支持的驱动类型：{self.driver.type}"))
        if self.driver.port <= 0 or self.driver.port > 65535:
            issues.append(ProfileIssue("error", "driver.port", "端口必须在 1–65535"))
        if self.driver.timeout_s <= 0:
            issues.append(ProfileIssue("error", "driver.timeout_s", "超时必须大于 0"))
        if self.driver.type.startswith("gcode"):
            required = {"move", "home", "pick", "place"}
            missing = sorted(required - set(self.driver.commands))
            if missing:
                issues.append(
                    ProfileIssue(
                        "warning",
                        "driver.commands",
                        "G-code 设备缺少命令模板：" + "、".join(missing),
                    )
                )

        if self.feeders.slot_count <= 0:
            issues.append(ProfileIssue("error", "feeders.slot_count", "料站数量必须大于 0"))
        if self.feeders.slot_pitch_mm <= 0:
            issues.append(ProfileIssue("error", "feeders.slot_pitch_mm", "料站间距必须大于 0"))
        if self.feeders.type not in {"slot", "tray"}:
            issues.append(ProfileIssue("warning", "feeders.type", f"未知供料器类型：{self.feeders.type}"))

        z_axis = self.axes.get("z")
        if z_axis and self.safety.safe_z_mm > z_axis.max:
            issues.append(
                ProfileIssue("error", "safety.safe_z_mm", f"安全高度 {self.safety.safe_z_mm:g} 超出 Z 行程")
            )
        if z_axis and self.safety.safe_z_mm < z_axis.min:
            issues.append(ProfileIssue("error", "safety.safe_z_mm", "安全高度低于 Z 轴下限"))
        if self.safety.max_speed_mm_s <= 0:
            issues.append(ProfileIssue("error", "safety.max_speed_mm_s", "最大速度必须大于 0"))

        fiducial = self.vision.fiducial
        if fiducial.search_radius_mm <= 0:
            issues.append(ProfileIssue("error", "vision.fiducial", "搜索半径必须大于 0"))
        if not 0 < fiducial.threshold < 1:
            issues.append(ProfileIssue("error", "vision.fiducial", "阈值必须在 0–1 之间"))
        if fiducial.min_area_mm2 >= fiducial.max_area_mm2:
            issues.append(ProfileIssue("error", "vision.fiducial", "最小面积必须小于最大面积"))
        if self.vision.bottom.angle_step_deg <= 0:
            issues.append(ProfileIssue("error", "vision.bottom", "角度搜索步长必须大于 0"))
        return issues

    @staticmethod
    def _validate_axis(axis: AxisConfig) -> list[ProfileIssue]:
        issues: list[ProfileIssue] = []
        if axis.min >= axis.max:
            issues.append(ProfileIssue("error", f"axes.{axis.id}", f"{axis.id.upper()} 轴下限必须小于上限"))
        if axis.home not in HOME_MODES:
            issues.append(ProfileIssue("warning", f"axes.{axis.id}.home", f"未知回零方式：{axis.home}"))
        if axis.max_speed <= 0:
            issues.append(ProfileIssue("error", f"axes.{axis.id}.max_speed", "轴速度必须大于 0"))
        if axis.steps_per_mm <= 0:
            issues.append(ProfileIssue("error", f"axes.{axis.id}.steps_per_mm", "步进当量必须大于 0"))
        return issues

    # ---------------- 序列化 ----------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA_ID,
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "vendor": self.vendor,
            "image": self.image,
            "tags": list(self.tags),
            "axes": {axis_id: axis.to_dict() for axis_id, axis in self.axes.items()},
            "heads": [head.to_dict() for head in self.heads],
            "cameras": [camera.to_dict() for camera in self.cameras],
            "feeders": self.feeders.to_dict(),
            "driver": self.driver.to_dict(),
            "vision": self.vision.to_dict(),
            "safety": self.safety.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MachineProfile":
        axes: dict[str, AxisConfig] = {}
        for axis_id, axis_data in (data.get("axes") or {}).items():
            if isinstance(axis_data, dict):
                axes[str(axis_id).lower()] = AxisConfig.from_dict(str(axis_id).lower(), axis_data)
        heads = [
            HeadConfig.from_dict(item, index)
            for index, item in enumerate(data.get("heads") or [])
            if isinstance(item, dict)
        ]
        cameras = [
            CameraConfig.from_dict(item, index)
            for index, item in enumerate(data.get("cameras") or [])
            if isinstance(item, dict)
        ]
        return cls(
            id=str(data.get("id", "")),
            name=str(data.get("name", "")),
            description=str(data.get("description", "")),
            vendor=str(data.get("vendor", "")),
            image=str(data.get("image", "")),
            schema=str(data.get("schema", SCHEMA_ID)),
            axes=axes,
            heads=heads,
            cameras=cameras,
            feeders=FeederBankConfig.from_dict(data.get("feeders") or {}),
            driver=DriverConfig.from_dict(data.get("driver") or {}),
            vision=VisionConfig.from_dict(data.get("vision") or {}),
            safety=SafetyConfig.from_dict(data.get("safety") or {}),
            tags=[str(item) for item in data.get("tags", [])],
        )

    # ---------------- 由旧设置生成 ----------------

    @classmethod
    def from_settings(cls, settings: Any) -> "MachineProfile":
        """没有选择机型配置时，用旧版 AppSettings 合成一个等价配置。"""
        nozzle_count = max(1, int(getattr(settings, "nozzle_count", 4)))
        mode = str(getattr(settings, "connection_mode", "simulator"))
        driver_type = {
            "simulator": "simulator",
            "tcp": "jsonl-tcp",
            "serial": "jsonl-serial",
        }.get(mode, "simulator")
        return cls(
            id="legacy-settings",
            name=str(getattr(settings, "machine_name", "MidPnP")),
            description="由旧版设置自动生成（未选择机型配置文件）",
            axes={
                "x": AxisConfig("x", "X", min=0.0, max=float(getattr(settings, "travel_x_mm", 420.0)),
                                max_speed=float(getattr(settings, "max_speed_mm_s", 320.0))),
                "y": AxisConfig("y", "Y", min=0.0, max=float(getattr(settings, "travel_y_mm", 360.0)),
                                max_speed=float(getattr(settings, "max_speed_mm_s", 320.0))),
                "z": AxisConfig("z", "Z", min=0.0, max=float(getattr(settings, "travel_z_mm", 30.0)),
                                max_speed=100.0),
                "c": AxisConfig("c", "C", unit="deg", min=-180.0, max=180.0, home="zero", max_speed=720.0),
            },
            heads=[
                HeadConfig(
                    id="H1",
                    name="贴装头 1",
                    nozzles=[
                        NozzleConfig(id=f"N{index + 1}", tip_diameter_mm=0.4 + index * 0.2)
                        for index in range(nozzle_count)
                    ],
                )
            ],
            cameras=[
                CameraConfig(id="CAM-TOP", name="俯视相机", mount="head"),
                CameraConfig(id="CAM-BOTTOM", name="底部对中相机", mount="fixed", pipeline="bottom-default"),
            ],
            feeders=FeederBankConfig(),
            driver=DriverConfig(
                type=driver_type,
                host=str(getattr(settings, "host", "192.168.1.50")),
                port=int(getattr(settings, "port", 5025)),
                serial_port=str(getattr(settings, "serial_port", "COM3")),
                baud_rate=int(getattr(settings, "baud_rate", 115200)),
            ),
            safety=SafetyConfig(
                safe_z_mm=float(getattr(settings, "safe_z_mm", 12.0)),
                max_speed_mm_s=float(getattr(settings, "max_speed_mm_s", 320.0)),
            ),
            builtin=False,
        )


def validate_profile(profile: MachineProfile) -> list[ProfileIssue]:
    return profile.validate()


def profile_summary(profile: MachineProfile) -> dict[str, Any]:
    """用于界面摘要行展示。"""
    limits = profile.limits()
    return {
        "id": profile.id,
        "name": profile.name,
        "axes": f"{limits.travel_x_mm:.0f} × {limits.travel_y_mm:.0f} × {limits.travel_z_mm:.0f} mm",
        "heads": len(profile.heads),
        "nozzles": len(profile.nozzle_ids()),
        "cameras": len(profile.cameras),
        "feeders": profile.feeders.slot_count,
        "driver": profile.driver.type,
        "builtin": profile.builtin,
    }


def iter_nozzles(profile: MachineProfile) -> Iterable[NozzleConfig]:
    for head in profile.heads:
        for nozzle in head.nozzles:
            yield nozzle
