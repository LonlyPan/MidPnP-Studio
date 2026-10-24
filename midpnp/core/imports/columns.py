"""列映射与表头识别。

各家 EDA 导出的坐标表列名差异很大（Designator / Ref / 位号 / Mid X / PosX…），
这里维护一张别名表，把任意表头映射到统一字段，并负责单位换算。
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, fields
from typing import Any, Iterable

# 字段顺序决定匹配优先级：先认位号，再认坐标，避免 "Part" 被当成位号
FIELD_ORDER = ("refdes", "x", "y", "rotation", "component", "package", "side", "skip", "unit")

FIELD_LABELS = {
    "refdes": "位号",
    "x": "X 坐标",
    "y": "Y 坐标",
    "rotation": "旋转角",
    "component": "元件名称/型号",
    "package": "封装",
    "side": "板面",
    "skip": "是否跳过",
    "unit": "单位",
}

_ALIASES: dict[str, set[str]] = {
    "refdes": {
        "refdes", "ref", "reference", "designator", "designators", "componentref",
        "partreference", "componentreference", "symbol", "位号", "元件位号", "器件位号", "编号",
    },
    "x": {
        "x", "xmm", "xmil", "xinch", "midx", "midxmm", "midxmil", "posx", "posxmm",
        "posxmil", "centerx", "centerxmm", "locationx", "locationxmm", "xcoord",
        "x坐标", "坐标x", "中心x",
    },
    "y": {
        "y", "ymm", "ymil", "yinch", "midy", "midymm", "midymil", "posy", "posymm",
        "posymil", "centery", "centerymm", "locationy", "locationymm", "ycoord",
        "y坐标", "坐标y", "中心y",
    },
    "rotation": {
        "rotation", "rot", "rotate", "angle", "rotationdeg", "orientation", "rotdeg",
        "角度", "旋转", "旋转角",
    },
    "component": {
        "component", "comment", "value", "val", "partnumber", "part", "description",
        "元件", "元件名称", "物料", "规格", "型号", "注释",
    },
    "package": {
        "package", "footprint", "pattern", "case", "landpattern", "封装", "封装形式", "焊盘",
    },
    "side": {"side", "layer", "boardside", "mountside", "面", "板面", "层", "面别"},
    "skip": {"skip", "dnp", "donotplace", "do not place", "不贴", "跳过", "省略"},
    "unit": {"unit", "units", "长度单位", "单位"},
}


def normalize_header(name: str) -> str:
    """去掉空格/下划线/标点/括号，统一小写，用于表头比较。"""
    return re.sub(r"[\s_\-\.()/\[\]]+", "", (name or "").strip().lower())


@dataclass
class ColumnMapping:
    """表头 → 字段的映射；空字符串表示该字段不存在。"""

    refdes: str = ""
    x: str = ""
    y: str = ""
    rotation: str = ""
    component: str = ""
    package: str = ""
    side: str = ""
    skip: str = ""
    unit: str = ""

    def __post_init__(self) -> None:
        for item in fields(self):
            value = getattr(self, item.name)
            if value is not None and not isinstance(value, str):
                setattr(self, item.name, str(value))

    @property
    def missing(self) -> list[str]:
        return [name for name in ("refdes", "x", "y") if not getattr(self, name)]

    @property
    def complete(self) -> bool:
        return not self.missing

    def field_for(self, header: str) -> str:
        for item in fields(self):
            if getattr(self, item.name) == header:
                return item.name
        return ""

    def as_dict(self) -> dict[str, str]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ColumnMapping":
        if not isinstance(data, dict):
            return cls()
        known = {item.name for item in fields(cls)}
        return cls(**{key: str(value) for key, value in data.items() if key in known and value is not None})

    def describe(self) -> str:
        if self.complete:
            return "位号 / X / Y 已映射"
        return "缺少必需列：" + "、".join(FIELD_LABELS[name] for name in self.missing)


def detect_columns(headers: Iterable[str]) -> tuple[ColumnMapping, list[str]]:
    """根据表头自动识别列映射，返回 (映射, 缺失字段)。"""
    normalized = {
        normalize_header(header): str(header)
        for header in headers
        if header is not None and str(header).strip()
    }
    values: dict[str, str] = {}
    used: set[str] = set()
    for field_name in FIELD_ORDER:
        for key, original in normalized.items():
            if key in used:
                continue
            if key in _ALIASES[field_name]:
                values[field_name] = original
                used.add(key)
                break
    mapping = ColumnMapping(**values)
    return mapping, mapping.missing


def column_unit(header: str, default: str = "mm") -> str:
    """从表头推断单位（mid x (mil) → mil）。"""
    text = normalize_header(header)
    if "mil" in text or "thou" in text:
        return "mil"
    if "inch" in text or text.endswith("in"):
        return "inch"
    if "mm" in text:
        return "mm"
    return default


_UNIT_TO_MM = {"mm": 1.0, "mil": 0.0254, "thou": 0.0254, "inch": 25.4, "in": 25.4, "um": 0.001}


def parse_number(value: str, default: float = 0.0) -> float:
    """从 `12.5 mm`、`1,234`、`-3.2°` 这类文本里取出数值。"""
    text = (value or "").strip()
    if not text:
        return default
    text = text.replace("，", ",").replace(",", ".")
    match = re.search(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", text)
    if not match:
        return default
    return float(match.group(0))


def convert_to_mm(value: float, unit: str) -> float:
    return value * _UNIT_TO_MM.get((unit or "mm").strip().lower(), 1.0)
