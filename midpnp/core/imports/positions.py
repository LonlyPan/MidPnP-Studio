"""位置文件解析：通用坐标表、KiCad .pos、OpenPnP board XML。

参考 OpenPnP `gui/importer` 下的 `KicadPosImporter` / `CsvImporter` /
`BoardImporter` 的设计：解析与「映射/单位/镜像」解耦，先得到原始行列，
再由用户确认列映射后生成贴装点。
"""

from __future__ import annotations

import csv
import io
import re
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

from ..models import Component, Fiducial, Placement, Side
from .columns import ColumnMapping, column_unit, convert_to_mm, detect_columns, parse_number


class PositionImportError(ValueError):
    """位置文件无法解析。"""


@dataclass
class ImportOptions:
    """导入时的坐标变换选项。"""

    unit: str = ""  # 空 = 按表头/文件自动判断；可选 mm / mil / inch
    rotation_offset_deg: float = 0.0
    mirror_x: bool = False
    mirror_y: bool = False
    swap_xy: bool = False
    offset_x_mm: float = 0.0
    offset_y_mm: float = 0.0
    force_side: str = ""  # Top / Bottom，空表示按文件
    mirror_bottom_x: bool = False
    bottom_rotation_flip: bool = False
    max_rows: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ImportOptions":
        if not isinstance(data, dict):
            return cls()
        known = {name for name in cls().__dict__}
        return cls(**{key: value for key, value in data.items() if key in known})

    def transform(
        self, x_mm: float, y_mm: float, rotation_deg: float, side: Side
    ) -> tuple[float, float, float]:
        """按 mm 坐标施加交换/镜像/偏移/旋转补偿。"""
        if self.swap_xy:
            x_mm, y_mm = y_mm, x_mm
        if self.mirror_x:
            x_mm = -x_mm
        if self.mirror_y:
            y_mm = -y_mm
        if side is Side.BOTTOM and self.mirror_bottom_x:
            x_mm = -x_mm
        rotation = rotation_deg
        if side is Side.BOTTOM and self.bottom_rotation_flip:
            rotation = 180.0 - rotation
        rotation += self.rotation_offset_deg
        return x_mm + self.offset_x_mm, y_mm + self.offset_y_mm, rotation % 360.0


@dataclass
class ImportResult:
    format: str = "csv"
    placements: list[Placement] = field(default_factory=list)
    components: list[Component] = field(default_factory=list)
    fiducials: list[Fiducial] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    headers: list[str] = field(default_factory=list)
    mapping: ColumnMapping | None = None
    total_rows: int = 0
    skipped_rows: int = 0
    delimiter: str = ","
    unit: str = "mm"

    def summary(self) -> str:
        parts = [f"{len(self.placements)} 个贴装点", f"{len(self.components)} 种元件"]
        if self.skipped_rows:
            parts.append(f"跳过 {self.skipped_rows} 行")
        return " · ".join(parts)


# ---------------------------------------------------------------- 文件读取


def read_position_file(path: str | Path) -> tuple[str, str]:
    """读取坐标文件，返回 (文本, 编码)。兼容 UTF-8 / UTF-16 / GBK。"""
    file_path = Path(path)
    try:
        raw = file_path.read_bytes()
    except OSError as exc:
        raise PositionImportError(f"无法读取文件：{exc}") from exc
    for encoding in ("utf-8-sig", "utf-16", "gbk", "latin-1"):
        try:
            text = raw.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
        if text.strip():
            return text, encoding
    raise PositionImportError("文件为空或编码无法识别")


def detect_format(text: str, filename: str = "") -> str:
    """识别格式：openpnp-board / kicad-pos / csv。"""
    lowered = text.lower()
    if "<openpnp-board" in lowered or (filename.lower().endswith(".board.xml")):
        return "openpnp-board"
    if "### module positions" in lowered or ("## unit" in lowered and "posx" in lowered):
        return "kicad-pos"
    if filename.lower().endswith(".pos") and "\t" not in text and "," not in text.splitlines()[0]:
        return "kicad-pos"
    return "csv"


# ---------------------------------------------------------------- 统一入口


def parse_positions(
    text: str,
    filename: str = "",
    mapping: ColumnMapping | None = None,
    options: ImportOptions | None = None,
) -> ImportResult:
    """解析坐标文件；`mapping` 为空时自动识别列。"""
    if not (text or "").strip():
        raise PositionImportError("文件为空")
    options = options or ImportOptions()
    fmt = detect_format(text, filename)
    if fmt == "openpnp-board":
        result = _parse_openpnp_board(text, options)
    elif fmt == "kicad-pos":
        result = _parse_kicad_pos(text, options, mapping)
    else:
        result = _parse_delimited(text, options, mapping)
    result.format = fmt
    _post_check(result)
    return result


def preview_positions(
    text: str,
    filename: str = "",
    mapping: ColumnMapping | None = None,
    options: ImportOptions | None = None,
    limit: int = 8,
) -> tuple[ImportResult, list[dict[str, Any]]]:
    """解析并返回前 N 行，供导入向导预览。"""
    result = parse_positions(text, filename, mapping, options)
    rows = [
        {
            "refdes": placement.refdes,
            "x_mm": round(placement.x_mm, 3),
            "y_mm": round(placement.y_mm, 3),
            "rotation_deg": round(placement.rotation_deg, 2),
            "side": placement.side.value,
            "skip": placement.skip,
        }
        for placement in result.placements[:limit]
    ]
    return result, rows


def header_preview(
    text: str, filename: str = ""
) -> tuple[str, list[str], ColumnMapping]:
    """不解析数据、只看表头：给导入向导填充列映射下拉框。"""
    fmt = detect_format(text, filename)
    if fmt == "csv":
        try:
            headers, _rows, _delimiter, _index = _read_delimited_table(text)
        except PositionImportError:
            return fmt, [], ColumnMapping()
        cleaned = [str(header).strip() for header in headers]
        mapping, _missing = detect_columns(cleaned)
        return fmt, cleaned, mapping
    if fmt == "kicad-pos":
        return fmt, ["Ref", "Val", "Package", "PosX", "PosY", "Rot", "Side"], ColumnMapping()
    return (
        fmt,
        ["designator", "part-id", "x", "y", "rotation", "side", "enabled"],
        ColumnMapping(),
    )


# ---------------------------------------------------------------- 通用坐标表


def _split_candidates(line: str) -> list[str]:
    for delimiter in (",", ";", "\t", "|"):
        if delimiter in line:
            return [delimiter]
    return [r"\s{1,}"]


def _read_delimited_table(text: str) -> tuple[list[str], list[list[str]], str, int]:
    """找到表头行并切分；返回 (表头, 数据行, 分隔符, 表头所在行号)。"""
    lines = text.splitlines()
    best: tuple[list[str], list[list[str]], str, int] | None = None
    for index, line in enumerate(lines[:40]):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        for delimiter in _split_candidates(line):
            if delimiter == r"\s{1,}":
                cells = re.split(r"\s{2,}", line.strip())
                if len(cells) < 3:
                    cells = line.split()
                parse_delimiter = None
            else:
                try:
                    cells = next(csv.reader([line], delimiter=delimiter))
                except csv.Error:
                    continue
                parse_delimiter = delimiter
            mapping, missing = detect_columns([cell.strip() for cell in cells])
            if missing:
                continue
            body = _consume_rows(lines[index + 1 :], parse_delimiter)
            best = (cells, body, "," if parse_delimiter is None else parse_delimiter, index)
            break
        if best is not None:
            break
    if best is None:
        # 没有可识别表头：若首行看起来像数据，按位置猜列
        raise PositionImportError(
            "未找到可识别的表头。坐标表至少需要位号、X、Y 三列，例如 "
            "Designator, Mid X, Mid Y。可在向导里手动指定列映射。"
        )
    return best


def _consume_rows(lines: list[str], delimiter: str | None) -> list[list[str]]:
    rows: list[list[str]] = []
    buffer = "\n".join(lines)
    if delimiter is not None:
        reader = csv.reader(io.StringIO(buffer), delimiter=delimiter)
        for row in reader:
            if not any(cell.strip() for cell in row):
                continue
            if row[0].lstrip().startswith("#"):
                continue
            rows.append([cell.strip() for cell in row])
        return rows
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        cells = re.split(r"\s{2,}", stripped)
        if len(cells) < 3:
            cells = stripped.split()
        rows.append([cell.strip() for cell in cells])
    return rows


def _parse_delimited(
    text: str,
    options: ImportOptions,
    mapping: ColumnMapping | None,
) -> ImportResult:
    headers, rows, delimiter, _ = _read_delimited_table(text)
    headers = [str(header).strip() for header in headers]
    if mapping is None or mapping.missing:
        mapping, _missing = detect_columns(headers)
    if mapping.missing:
        raise PositionImportError(
            "缺少必需列：" + "、".join(mapping.missing) + "。请在导入向导中手动映射列。"
        )

    result = ImportResult(headers=headers, mapping=mapping, delimiter=delimiter)
    index = {header: position for position, header in enumerate(headers)}
    unit_columns = {
        field_name: column_unit(getattr(mapping, field_name) or "", options.unit or "mm")
        for field_name in ("x", "y")
    }
    if options.unit:
        unit_columns = {"x": options.unit, "y": options.unit}
    result.unit = unit_columns["x"]
    components: dict[str, Component] = {}
    seen: dict[str, int] = {}

    for row_number, cells in enumerate(rows, start=1):
        if options.max_rows and len(result.placements) >= options.max_rows:
            break
        result.total_rows += 1
        try:
            record = {
                field_name: cells[index[header]] if header in index and index[header] < len(cells) else ""
                for field_name, header in mapping.as_dict().items()
                if header
            }
        except IndexError:
            result.skipped_rows += 1
            result.warnings.append(f"第 {row_number} 行列数不足，已跳过")
            continue
        refdes = str(record.get("refdes", "")).strip()
        if not refdes:
            result.skipped_rows += 1
            continue
        try:
            row_unit = (record.get("unit") or "").strip().lower() or options.unit or ""
            unit_x = row_unit or unit_columns["x"]
            unit_y = row_unit or unit_columns["y"]
            x_mm = convert_to_mm(parse_number(record.get("x", "")), unit_x)
            y_mm = convert_to_mm(parse_number(record.get("y", "")), unit_y)
            rotation = parse_number(record.get("rotation", ""), 0.0)
        except (TypeError, ValueError):
            result.skipped_rows += 1
            result.warnings.append(f"第 {row_number} 行坐标无法解析，已跳过")
            continue

        side = _side_from_text(record.get("side", ""))
        if options.force_side:
            side = Side.BOTTOM if options.force_side.lower().startswith("b") else Side.TOP
        skip_raw = str(record.get("skip", "")).strip().lower()
        skip = skip_raw in {"1", "true", "yes", "y", "dnp", "不贴", "跳过"}
        x_mm, y_mm, rotation = options.transform(x_mm, y_mm, rotation, side)

        component_name = str(record.get("component", "")).strip()
        package = str(record.get("package", "")).strip()
        component = _component_for(component_name, package, "坐标表")
        components[component.id] = component
        if refdes in seen:
            result.warnings.append(f"位号 {refdes} 重复，已保留最后一处")
        seen[refdes] = row_number
        result.placements.append(
            Placement(
                refdes=refdes,
                component_id=component.id,
                x_mm=x_mm,
                y_mm=y_mm,
                rotation_deg=rotation,
                side=side,
                skip=skip,
            )
        )

    result.components = sorted(components.values(), key=lambda item: item.name)
    if not result.placements:
        raise PositionImportError("没有解析到有效贴装点")
    return result


# ---------------------------------------------------------------- KiCad .pos


_KICAD_LINE = re.compile(
    r"^(?P<ref>\S+)\s+(?P<value>.*?)\s+(?P<package>\S+)\s+"
    r"(?P<x>-?\d+(?:\.\d+)?)\s+(?P<y>-?\d+(?:\.\d+)?)\s+"
    r"(?P<rotation>-?\d+(?:\.\d+)?)\s*(?P<side>\S*)\s*$"
)


def _parse_kicad_pos(
    text: str,
    options: ImportOptions,
    mapping: ColumnMapping | None,
) -> ImportResult:
    if mapping is not None and mapping.complete and options.unit:
        # 用户显式给了列映射（KiCad 7 的 CSV 形态），退回通用解析
        return _parse_delimited(text, options, mapping)
    unit = options.unit or "mm"
    for line in text.splitlines()[:30]:
        match = re.search(r"unit\s*=\s*(mm|mil|inch|in)\b", line, re.IGNORECASE)
        if match:
            unit = match.group(1).lower()
            break
    result = ImportResult(format="kicad-pos", unit=unit)
    components: dict[str, Component] = {}
    seen: set[str] = set()
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        result.total_rows += 1
        match = _KICAD_LINE.match(line)
        if not match:
            result.skipped_rows += 1
            result.warnings.append(f"无法解析的行：{line[:60]}")
            continue
        refdes = match.group("ref")
        value = match.group("value").strip()
        package = match.group("package").strip()
        side = _side_from_text(match.group("side"))
        x_mm = convert_to_mm(float(match.group("x")), unit)
        y_mm = convert_to_mm(float(match.group("y")), unit)
        rotation = float(match.group("rotation"))
        # 与 OpenPnP KicadPosImporter 一致：底面坐标按 X 取反、角度按 180-rot 处理
        if side is Side.BOTTOM:
            x_mm = -x_mm
            rotation = 180.0 - rotation
        if options.force_side:
            side = Side.BOTTOM if options.force_side.lower().startswith("b") else Side.TOP
        x_mm, y_mm, rotation = options.transform(x_mm, y_mm, rotation, side)
        component = _component_for(value, package, "KiCad .pos")
        components[component.id] = component
        if refdes in seen:
            result.warnings.append(f"位号 {refdes} 重复，已保留最后一处")
        seen.add(refdes)
        result.placements.append(
            Placement(
                refdes=refdes,
                component_id=component.id,
                x_mm=x_mm,
                y_mm=y_mm,
                rotation_deg=rotation,
                side=side,
            )
        )
    result.components = sorted(components.values(), key=lambda item: item.name)
    if not result.placements:
        raise PositionImportError("KiCad .pos 中没有解析到贴装点")
    return result


# ---------------------------------------------------------------- OpenPnP board XML


def _parse_openpnp_board(text: str, options: ImportOptions) -> ImportResult:
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise PositionImportError(f"OpenPnP 板文件 XML 解析失败：{exc}") from exc
    result = ImportResult(format="openpnp-board", unit="mm")
    components: dict[str, Component] = {}
    seen: set[str] = set()
    for element in root.iter():
        tag = str(element.tag).split("}")[-1].lower()
        if tag not in {"placement", "fiducial"}:
            continue
        attributes = {str(key).lower(): str(value) for key, value in element.attrib.items()}
        refdes = (
            attributes.get("designator")
            or attributes.get("ref")
            or attributes.get("refdes")
            or attributes.get("id")
            or ""
        ).strip()
        if not refdes:
            continue
        part_id = (
            attributes.get("part-id")
            or attributes.get("partid")
            or attributes.get("part")
            or ""
        ).strip()
        try:
            x_mm = parse_number(attributes.get("x", "0"))
            y_mm = parse_number(attributes.get("y", "0"))
            rotation = parse_number(attributes.get("rotation", attributes.get("angle", "0")))
        except ValueError:
            continue
        side = _side_from_text(attributes.get("side", "Top"))
        diameter = parse_number(attributes.get("diameter", "0"))
        if tag == "fiducial":
            result.fiducials.append(
                Fiducial(
                    name=refdes,
                    x_mm=x_mm,
                    y_mm=y_mm,
                    radius_mm=diameter / 2 if diameter > 0 else 1.0,
                )
            )
            continue
        result.total_rows += 1
        enabled = attributes.get("enabled", "true").lower() not in {"false", "0", "no"}
        x_mm, y_mm, rotation = options.transform(x_mm, y_mm, rotation, side)
        package = part_id
        component = _component_for(part_id, package, "OpenPnP 板文件")
        components[component.id] = component
        if refdes in seen:
            result.warnings.append(f"位号 {refdes} 重复，已保留最后一处")
        seen.add(refdes)
        result.placements.append(
            Placement(
                refdes=refdes,
                component_id=component.id,
                x_mm=x_mm,
                y_mm=y_mm,
                rotation_deg=rotation,
                side=side,
                skip=not enabled,
            )
        )
    result.components = sorted(components.values(), key=lambda item: item.name)
    if not result.placements:
        raise PositionImportError("OpenPnP 板文件中没有 placement 元素")
    return result


# ---------------------------------------------------------------- 辅助


def _side_from_text(value: str) -> Side:
    lowered = (value or "").strip().lower()
    if lowered in {"b", "bottom", "back", "b.cu", "bottomlayer", "底", "反面", "背面", "下"}:
        return Side.BOTTOM
    if "bottom" in lowered or "b.cu" in lowered or "bot" in lowered:
        return Side.BOTTOM
    return Side.TOP


def _component_for(name: str, package: str, source: str) -> Component:
    cleaned_name = (name or package or "未命名元件").strip()
    cleaned_package = (package or "UNKNOWN").strip()
    token = re.sub(r"[^A-Za-z0-9]+", "-", f"{cleaned_name}-{cleaned_package}".strip("-")).strip("-").upper()
    component = Component(
        id=f"CMP-{token[:44] or 'IMPORTED'}",
        name=cleaned_name,
        package=cleaned_package,
        notes=f"由{source}自动创建",
        color="#8a939c",
        value=cleaned_name,
    )
    return component


def _post_check(result: ImportResult) -> None:
    if not result.placements:
        raise PositionImportError("没有解析到有效贴装点")
    if any(placement.x_mm < 0 or placement.y_mm < 0 for placement in result.placements):
        result.warnings.append("存在负坐标，请确认板原点与镜像设置")
    if len(result.placements) > 5000:
        result.warnings.append(f"贴装点较多（{len(result.placements)}），请确认文件是否正确")


def export_template_csv() -> str:
    """导入向导里的示例坐标表。"""
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(["Designator", "Comment", "Footprint", "Mid X (mm)", "Mid Y (mm)", "Rotation", "Layer"])
    writer.writerow(["R1", "10k", "0603", "12.700", "8.400", "0.0", "Top"])
    writer.writerow(["C1", "100nF", "0402", "18.200", "8.400", "90.0", "Top"])
    writer.writerow(["U1", "STM32G030", "LQFP-48", "30.000", "20.000", "0.0", "Top"])
    return output.getvalue()
