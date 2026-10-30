"""贴装坐标 CSV 导入/导出。

兼容常见 EDA 输出（Altium / KiCad / PADS / 嘉立创等）的中英文表头，
并自动创建缺失的元件定义，导入后可在元件库中继续完善尺寸与吸嘴。
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from typing import Iterable

from .models import Component, Placement, Product, Side, VisionMode


class ImportError_(ValueError):
    """导入失败。"""


@dataclass
class ImportResult:
    placements: list[Placement] = field(default_factory=list)
    components: list[Component] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    skipped_rows: int = 0
    delimiter: str = ","


_ALIASES: dict[str, set[str]] = {
    "refdes": {
        "refdes", "ref", "reference", "designator", "componentref", "partreference",
        "位号", "元件位号", "器件位号",
    },
    "x": {
        "x", "xmm", "xmil", "midx", "midxmm", "midxmil", "posx", "posxmm", "posxmil",
        "centerx", "centerxmm", "locationx", "x坐标", "坐标x",
    },
    "y": {
        "y", "ymm", "ymil", "midy", "midymm", "midymil", "posy", "posymm", "posymil",
        "centery", "centerymm", "locationy", "y坐标", "坐标y",
    },
    "rotation": {"rotation", "rot", "angle", "rotationdeg", "orientation", "角度", "旋转"},
    "component": {
        "component", "comment", "value", "part", "partnumber", "description",
        "元件", "元件名称", "物料", "规格", "注释",
    },
    "package": {"package", "footprint", "pattern", "case", "封装", "封装形式"},
    "side": {"side", "layer", "boardside", "面", "层", "板面"},
    "skip": {"skip", "dnp", "donotplace", "不贴", "跳过"},
    "unit": {"unit", "units", "单位"},
}

_PACKAGE_SIZES: dict[str, tuple[float, float, float]] = {
    "0201": (0.6, 0.3, 0.3),
    "0402": (1.0, 0.5, 0.5),
    "0603": (1.6, 0.8, 0.8),
    "0805": (2.0, 1.25, 0.9),
    "1206": (3.2, 1.6, 1.1),
    "1210": (3.2, 2.5, 1.5),
    "SOT23": (2.9, 1.3, 1.1),
    "SOT-23": (2.9, 1.3, 1.1),
    "SOP8": (4.9, 3.9, 1.5),
    "SOIC8": (4.9, 3.9, 1.5),
    "SOIC-8": (4.9, 3.9, 1.5),
    "QFN24": (5.0, 5.0, 0.9),
    "QFP": (7.0, 7.0, 1.6),
    "HDR": (10.16, 2.54, 2.5),
}


def _normalize_header(name: str) -> str:
    return re.sub(r"[\s_\-\.()/]+", "", name.strip().lower())


def _match_columns(headers: Iterable[str]) -> tuple[dict[str, str], list[str]]:
    mapping: dict[str, str] = {}
    normalized = {_normalize_header(h): h for h in headers if h is not None}
    for field_name, aliases in _ALIASES.items():
        for header in normalized:
            if header in aliases:
                mapping[field_name] = normalized[header]
                break
    missing = [key for key in ("refdes", "x", "y") if key not in mapping]
    return mapping, missing


def _number(value: str, unit_hint: str = "mm") -> float:
    text = (value or "").strip().replace(",", ".")
    if not text:
        raise ValueError("空数值")
    match = re.search(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", text)
    if not match:
        raise ValueError(f"非法数值: {value!r}")
    number = float(match.group(0))
    lowered = text.lower()
    if "mil" in lowered or unit_hint.lower() in {"mil", "mils", "thou"}:
        number *= 0.0254
    elif "in" in lowered or unit_hint.lower() in {"in", "inch", "inches"}:
        number *= 25.4
    return number


def _side(value: str) -> Side:
    lowered = (value or "").strip().lower()
    if lowered in {"bottom", "b", "back", "bottomlayer", "底", "反面", "背面"}:
        return Side.BOTTOM
    return Side.TOP


def _component_id(name: str, package: str) -> str:
    base = re.sub(r"[^A-Za-z0-9]+", "-", f"{name}-{package}".strip("-")).strip("-").upper()
    return f"CMP-{base[:40] or 'IMPORTED'}"


def _component_for(name: str, package: str) -> Component:
    dimensions = _PACKAGE_SIZES.get(package.strip().upper(), (2.0, 1.2, 1.0))
    vision = VisionMode.IC if any(token in package.upper() for token in ("SOP", "SOIC", "QFN", "QFP", "BGA")) else VisionMode.NONE
    nozzle = "N3" if vision is VisionMode.IC else ("N2" if dimensions[0] >= 2.0 else "N1")
    return Component(
        id=_component_id(name, package),
        name=name or package or "导入元件",
        package=package or "UNKNOWN",
        length_mm=dimensions[0],
        width_mm=dimensions[1],
        height_mm=dimensions[2],
        nozzle=nozzle,
        vision_mode=vision,
        color="#8a939c",
        notes="由 CSV 自动创建",
        value=name or package,
    )


def parse_centroid_csv(text: str) -> ImportResult:
    if not text.strip():
        raise ImportError_("CSV 文件为空")
    sample = text[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = ","
    reader = csv.DictReader(io.StringIO(text), dialect=dialect if delimiter else "excel")
    if not reader.fieldnames:
        raise ImportError_("CSV 缺少表头")
    mapping, missing = _match_columns(reader.fieldnames)
    if missing:
        friendly = {"refdes": "位号", "x": "X 坐标", "y": "Y 坐标"}
        raise ImportError_(
            "无法识别必需列：" + "、".join(friendly[m] for m in missing)
            + "。支持表头如 Designator / Mid X / Mid Y / Rotation。"
        )

    result = ImportResult(delimiter=delimiter or ",")
    component_cache: dict[str, Component] = {}
    x_is_mil = "mil" in mapping["x"].lower()
    y_is_mil = "mil" in mapping["y"].lower()
    unit_hint = "mm"
    for row in reader:
        try:
            refdes = (row.get(mapping["refdes"]) or "").strip()
            if not refdes:
                result.skipped_rows += 1
                continue
            row_unit = (row.get(mapping.get("unit", ""), "") or "").strip().lower()
            unit_hint = row_unit or ("mil" if x_is_mil or y_is_mil else "mm")
            x = _number(row.get(mapping["x"], ""), "mil" if x_is_mil else unit_hint)
            y = _number(row.get(mapping["y"], ""), "mil" if y_is_mil else unit_hint)
            rotation = _number(row.get(mapping.get("rotation", ""), "0") or "0")
            component_name = (row.get(mapping.get("component", ""), "") or "").strip()
            package = (row.get(mapping.get("package", ""), "") or "").strip()
            if not component_name and not package:
                component_name = "未命名元件"
            component = _component_for(component_name, package)
            component_cache[component.id] = component
            skip_raw = (row.get(mapping.get("skip", ""), "") or "").strip().lower()
            skip = skip_raw in {"1", "true", "yes", "y", "dnp", "不贴"}
            result.placements.append(
                Placement(
                    refdes=refdes,
                    component_id=component.id,
                    x_mm=x,
                    y_mm=y,
                    rotation_deg=rotation % 360.0,
                    side=_side(row.get(mapping.get("side", ""), "")),
                    skip=skip,
                )
            )
        except (ValueError, TypeError) as exc:
            result.skipped_rows += 1
            result.warnings.append(f"第 {reader.line_num} 行跳过：{exc}")

    if not result.placements:
        raise ImportError_("没有解析到有效贴装点")
    result.components = sorted(component_cache.values(), key=lambda c: c.name)
    if result.skipped_rows:
        result.warnings.append(f"共跳过 {result.skipped_rows} 行无效数据")
    if any(p.x_mm < 0 or p.y_mm < 0 for p in result.placements):
        result.warnings.append("存在负坐标，请确认板原点设置")
    return result


def export_centroid_csv(product: Product, components: Iterable[Component]) -> str:
    component_map = {c.id: c for c in components}
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(["Designator", "Comment", "Footprint", "Mid X (mm)", "Mid Y (mm)", "Rotation", "Layer", "Skip"])
    for placement in product.placements:
        component = component_map.get(placement.component_id)
        writer.writerow(
            [
                placement.refdes,
                component.name if component else placement.component_id,
                component.package if component else "",
                f"{placement.x_mm:.3f}",
                f"{placement.y_mm:.3f}",
                f"{placement.rotation_deg:.1f}",
                placement.side.value,
                "1" if placement.skip else "0",
            ]
        )
    return output.getvalue()
