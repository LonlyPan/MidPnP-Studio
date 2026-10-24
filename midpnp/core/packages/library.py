"""封装库：封装定义、名称规范化与自动匹配。

对应 OpenPnP 的 Part / Package 拆分：OpenPnP 里 `Part` 描述物料（型号、参数），
`Package` 描述焊盘几何与定位特征。本项目把「封装」独立成库，元件只引用
封装 ID，这样坐标导入时可以先按封装名匹配、再补齐尺寸/吸嘴/视觉策略。

匹配策略（三级）：
1. 归一化后精确相等 —— 例如 `R-0603_1608Metric` → `0603`；
2. 同义名 / 别名命中 —— 例如 `SOIC8`、`SO-8`、`SOP-8` 都归到 `SOIC-8`；
3. 名称相似度 + 本体尺寸约束 —— 用于 `QFN32_5x5`、`SOT23-5` 这类带后缀的写法。

尺寸表默认采用「英制 4 位码」口径（0603 = 1.6×0.8 mm），同时接受公制码
（1608 → 0603、1005 → 0402）。两种口径在 0603 上存在重名冲突，本项目
按行业习惯把裸 `0603` 解释为英制，公制请写 `1608` 或 `0603Metric`。
"""

from __future__ import annotations

import difflib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

# 英制 4 位码 → 本体尺寸 (长, 宽) mm
CHIP_SIZES_MM: dict[str, tuple[float, float]] = {
    "0201": (0.6, 0.3),
    "0402": (1.0, 0.5),
    "0603": (1.6, 0.8),
    "0805": (2.0, 1.25),
    "1206": (3.2, 1.6),
    "1210": (3.2, 2.5),
    "1812": (4.5, 3.2),
    "2010": (5.0, 2.5),
    "2512": (6.3, 3.2),
}

# 公制尺寸码 → 英制码（仅收录与英制码不冲突的写法）
METRIC_TO_IMPERIAL: dict[str, str] = {
    "1005": "0402",
    "1608": "0603",
    "2012": "0805",
    "3216": "1206",
    "3225": "1210",
    "4532": "1812",
    "5025": "2010",
    "6332": "2512",
}

# 常见封装的同义名分组；组内第一个是规范名
ALIAS_GROUPS: list[tuple[str, ...]] = [
    ("SOT-23", "SOT23", "SOT-23-3", "SOT23-3", "SOT-346"),
    ("SOT-23-5", "SOT23-5", "SOT-23-5L", "SOT25"),
    ("SOT-23-6", "SOT23-6", "SOT-26"),
    ("SOT-89", "SOT89", "SOT-89-3"),
    ("SOT-223", "SOT223", "SOT-223-4"),
    ("SOD-123", "SOD123"),
    ("SOD-323", "SOD323"),
    ("SOIC-8", "SOIC8", "SO-8", "SO8", "SOP-8", "SOP8", "SOIC-8N"),
    ("SOIC-14", "SOIC14", "SO-14", "SOP-14"),
    ("SOIC-16", "SOIC16", "SO-16", "SOP-16"),
    ("TSSOP-8", "TSSOP8", "TSSOP-8P"),
    ("TSSOP-16", "TSSOP16"),
    ("TSSOP-20", "TSSOP20"),
    ("MSOP-8", "MSOP8", "MSOP-8P"),
    ("QFN-16", "QFN16", "VQFN-16", "DFN-16"),
    ("QFN-24", "QFN24", "VQFN-24"),
    ("QFN-32", "QFN32", "VQFN-32"),
    ("QFN-48", "QFN48", "VQFN-48"),
    ("LQFP-32", "LQFP32", "TQFP-32", "TQFP32", "QFP-32"),
    ("LQFP-44", "LQFP44", "TQFP-44", "TQFP44", "QFP-44"),
    ("LQFP-48", "LQFP48", "TQFP-48", "TQFP48", "QFP-48"),
    ("LQFP-64", "LQFP64", "TQFP-64", "TQFP64", "QFP-64"),
    ("LQFP-100", "LQFP100", "TQFP-100", "TQFP100", "QFP-100"),
    ("USB-C-16P", "USB-C", "TYPE-C-16P", "USB-TYPE-C", "USB-C-16PIN"),
    ("USB-MICRO-B", "MICRO-USB", "USB-MICRO", "MICROUSB"),
    ("HDR-1X2.54", "HDR1X2.54", "PIN-1X2.54", "HEADER-2.54-1X"),
    ("HDR-2X2.54", "HDR2X2.54", "PIN-2X2.54", "HEADER-2.54-2X"),
    ("LED-0603", "LED0603", "LED-1608"),
    ("LED-0805", "LED0805", "LED-2012"),
    ("LED-3528", "LED3528", "PLCC-2"),
    ("LED-5050", "LED5050", "PLCC-6", "RGB-5050"),
    ("XTAL-3225", "CRYSTAL-3225", "3225-XTAL", "SMD-3225"),
    ("XTAL-HC49", "HC-49S", "HC49", "HC-49/US"),
    ("IND-4X4", "IND4X4", "POWER-INDUCTOR-4X4", "CD54"),
    ("IND-6X6", "IND6X6", "POWER-INDUCTOR-6X6", "CD75"),
    ("DIP-8", "DIP8", "DIP-8N", "PDIP-8"),
    ("TO-220", "TO220", "TO-220-3"),
    ("TP-1.5", "TESTPOINT-1.5", "TP1.5"),
    ("FID-1.0", "FIDUCIAL-1.0", "FID1.0"),
    ("FID-2.0", "FIDUCIAL-2.0", "FID2.0"),
    ("JST-PH-2", "JSTPH2", "PH-2P", "JST-2P"),
    ("FUSE-1206", "FUSE1206", "PTC-1206"),
    ("SW-TACT-3X4", "TACT-3X4", "SW-3X4", "TACT-SWITCH-3X4"),
    ("FFC-0.5-10P", "FFC10P", "FPC-0.5-10P", "FFC-10PIN"),
]

_PREFIX_WORDS = (
    "R", "C", "L", "D", "Q", "U", "Y", "X", "LED", "CAP", "RES", "IND", "CON",
    "CONN", "IC", "PKG", "PACKAGE", "FOOTPRINT", "SMD", "SMT",
)


def normalize_footprint(name: str) -> str:
    """把 EDA 里的封装写法归一成 `0603` / `SOIC-8` / `USB-C-16P` 形式。"""
    text = (name or "").strip().upper()
    if not text:
        return ""
    text = text.replace("µ", "U").replace("μ", "U").replace("Ω", "OHM")
    # 去掉括号注释、单位后缀
    text = re.sub(r"[\(\[].*?[\)\]]", " ", text)
    text = re.sub(r"[-_ ]?(METRIC|IMPERIAL)$", "", text)
    # EDA 常见前缀：R_0603 / C0603 / LED_0805
    text = re.sub(r"[^A-Z0-9]+", "-", text).strip("-")
    for word in _PREFIX_WORDS:
        if text == word:
            break
        if text.startswith(word + "-"):
            text = text[len(word) + 1 :]
            break
    # R0603 / C0805 这类无分隔前缀
    match = re.fullmatch(r"(R|C|L|D|Q|U|Y)(\d{3,4})", text)
    if match:
        text = match.group(2)
    # Capacitor-0805 / Resistor-0603：词前缀 + 纯尺寸码
    match = re.fullmatch(r"[A-Z]{3,}[-_](\d{3,4})", text)
    if match and (match.group(1) in CHIP_SIZES_MM or match.group(1) in METRIC_TO_IMPERIAL):
        text = match.group(1)
    text = re.sub(r"^(\d{3,4})-(\d{3,4})$", r"\1", text)  # 0603-1608
    # 去掉尺寸后缀：QFN32_5X5 → QFN32
    text = re.sub(r"[-_](\d+(?:\.\d+)?X\d+(?:\.\d+)?)$", "", text)
    return text.strip("-")


def compact_key(name: str) -> str:
    """仅保留字母数字的紧凑键，用于 SOIC8 / SOIC-8 互认。"""
    return re.sub(r"[^A-Z0-9]+", "", normalize_footprint(name).upper())


def canonical_footprint(name: str) -> str:
    """同义名归一：`SOP8` → `SOIC-8`，`1608` → `0603`。"""
    base = normalize_footprint(name)
    if not base:
        return ""
    if base in CHIP_SIZES_MM:
        return base
    if base in METRIC_TO_IMPERIAL:
        return METRIC_TO_IMPERIAL[base]
    key = compact_key(base)
    for group in ALIAS_GROUPS:
        canonical = group[0]
        if key == compact_key(canonical) or any(key == compact_key(alias) for alias in group[1:]):
            return canonical
    return base


@dataclass
class PadDef:
    """单个焊盘（板内坐标，封装中心为原点，mm）。"""

    name: str = "1"
    x_mm: float = 0.0
    y_mm: float = 0.0
    width_mm: float = 0.8
    height_mm: float = 0.8
    rotation_deg: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "x_mm": round(self.x_mm, 3),
            "y_mm": round(self.y_mm, 3),
            "width_mm": round(self.width_mm, 3),
            "height_mm": round(self.height_mm, 3),
            "rotation_deg": round(self.rotation_deg, 2),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PadDef":
        return cls(
            name=str(data.get("name", "1")),
            x_mm=float(data.get("x_mm", 0.0)),
            y_mm=float(data.get("y_mm", 0.0)),
            width_mm=float(data.get("width_mm", 0.8)),
            height_mm=float(data.get("height_mm", 0.8)),
            rotation_deg=float(data.get("rotation_deg", 0.0)),
        )


@dataclass
class PackageDef:
    """封装定义。

    `pad_rows` 描述焊盘排布，用于在没有显式 `pads` 时推导几何：
    1 = 两端各一个（片式元件）；2 = 两侧双列（SOIC/TSSOP）；
    4 = 四边（QFP/QFN）；0 = 自定义，必须提供 `pads`。
    """

    id: str
    name: str
    aliases: list[str] = field(default_factory=list)
    category: str = "other"
    length_mm: float = 1.6
    width_mm: float = 0.8
    height_mm: float = 0.8
    pin_count: int = 2
    pad_rows: int = 1
    pad_pitch_mm: float = 0.0
    pad_width_mm: float = 0.0
    pad_height_mm: float = 0.0
    pads: list[PadDef] = field(default_factory=list)
    nozzle: str = "N1"
    vision_mode: str = "None"
    tags: list[str] = field(default_factory=list)
    notes: str = ""
    builtin: bool = False

    # ---------------- 关键字 ----------------

    @property
    def compact_name(self) -> str:
        return compact_key(self.name)

    def all_names(self) -> list[str]:
        return [self.name, *self.aliases]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "aliases": list(self.aliases),
            "category": self.category,
            "length_mm": round(self.length_mm, 3),
            "width_mm": round(self.width_mm, 3),
            "height_mm": round(self.height_mm, 3),
            "pin_count": self.pin_count,
            "pad_rows": self.pad_rows,
            "pad_pitch_mm": round(self.pad_pitch_mm, 3),
            "pad_width_mm": round(self.pad_width_mm, 3),
            "pad_height_mm": round(self.pad_height_mm, 3),
            "pads": [pad.to_dict() for pad in self.pads],
            "nozzle": self.nozzle,
            "vision_mode": self.vision_mode,
            "tags": list(self.tags),
            "notes": self.notes,
            "builtin": self.builtin,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PackageDef":
        return cls(
            id=str(data.get("id") or "PKG-" + compact_key(str(data.get("name", "")))),
            name=str(data.get("name", "UNKNOWN")),
            aliases=[str(item) for item in data.get("aliases", [])],
            category=str(data.get("category", "other")),
            length_mm=float(data.get("length_mm", 1.6)),
            width_mm=float(data.get("width_mm", 0.8)),
            height_mm=float(data.get("height_mm", 0.8)),
            pin_count=int(data.get("pin_count", 2)),
            pad_rows=int(data.get("pad_rows", 1)),
            pad_pitch_mm=float(data.get("pad_pitch_mm", 0.0)),
            pad_width_mm=float(data.get("pad_width_mm", 0.0)),
            pad_height_mm=float(data.get("pad_height_mm", 0.0)),
            pads=[PadDef.from_dict(item) for item in data.get("pads", [])],
            nozzle=str(data.get("nozzle", "N1")),
            vision_mode=str(data.get("vision_mode", "None")),
            tags=[str(item) for item in data.get("tags", [])],
            notes=str(data.get("notes", "")),
            builtin=bool(data.get("builtin", False)),
        )

    # ---------------- 焊盘几何 ----------------

    def derived_pads(self) -> list[PadDef]:
        """返回显式焊盘；为空时按 `pad_rows` 推导近似焊盘（用于绘图与演示）。"""
        if self.pads:
            return list(self.pads)
        rows = self.pad_rows
        if rows == 1 and self.pin_count > 2:
            # 单排多脚（排针 / TO-220 / DIP 的一侧）
            pitch = self.pad_pitch_mm or max(1.0, self.length_mm / max(1, self.pin_count - 1))
            pad_w = self.pad_width_mm or max(0.8, pitch * 0.7)
            pad_h = self.pad_height_mm or max(0.8, self.width_mm * 0.8)
            pads = []
            for index in range(self.pin_count):
                x = (index - (self.pin_count - 1) / 2.0) * pitch
                pads.append(PadDef(str(index + 1), x, 0.0, pad_w, pad_h))
            return pads
        if rows == 1 or self.pin_count <= 2:
            pad_w = self.pad_width_mm or max(0.2, self.length_mm * 0.30)
            pad_h = self.pad_height_mm or max(0.2, self.width_mm * 0.92)
            offset = self.length_mm / 2 + pad_w / 2 - min(0.15, pad_w * 0.2)
            return [
                PadDef("1", -offset, 0.0, pad_w, pad_h),
                PadDef("2", offset, 0.0, pad_w, pad_h),
            ]
        if rows == 2:
            first_row = (self.pin_count + 1) // 2
            second_row = max(0, self.pin_count - first_row)
            pitch = self.pad_pitch_mm or (
                self.length_mm / max(1, first_row - 1) if first_row > 1 else 1.0
            )
            pad_w = self.pad_width_mm or max(0.15, pitch * 0.55)
            pad_h = self.pad_height_mm or max(0.4, self.width_mm * 0.28)
            y = self.width_mm / 2 + pad_h / 2 - min(0.1, pad_h * 0.15)
            pads: list[PadDef] = []
            for index in range(first_row):
                x = (index - (first_row - 1) / 2) * pitch
                pads.append(PadDef(str(index + 1), x, -y, pad_w, pad_h))
            for index in range(second_row):
                x = ((second_row - 1) / 2 - index) * pitch
                pads.append(PadDef(str(first_row + index + 1), x, y, pad_w, pad_h))
            return pads
        if rows == 4:
            per_side = max(1, self.pin_count // 4)
            pitch = self.pad_pitch_mm or (self.length_mm / max(1, per_side))
            pad_w = self.pad_width_mm or max(0.15, pitch * 0.5)
            pad_h = self.pad_height_mm or max(0.3, pad_w * 2.2)
            pads = []
            number = 1
            half_x = self.length_mm / 2 + pad_h / 2 - min(0.1, pad_h * 0.1)
            half_y = self.width_mm / 2 + pad_h / 2 - min(0.1, pad_h * 0.1)
            for index in range(per_side):
                y = ((per_side - 1) / 2 - index) * pitch
                pads.append(PadDef(str(number), -half_x, y, pad_h, pad_w))
                number += 1
            for index in range(per_side):
                x = ((per_side - 1) / 2 - index) * -pitch
                pads.append(PadDef(str(number), x, -half_y, pad_w, pad_h, 90.0))
                number += 1
            for index in range(per_side):
                y = ((per_side - 1) / 2 - index) * -pitch
                pads.append(PadDef(str(number), half_x, y, pad_h, pad_w))
                number += 1
            for index in range(per_side):
                x = ((per_side - 1) / 2 - index) * pitch
                pads.append(PadDef(str(number), x, half_y, pad_w, pad_h, 90.0))
                number += 1
            return pads
        return []

    @property
    def is_chip(self) -> bool:
        return self.category in {"chip", "led", "inductor"} and self.pin_count <= 2

    @property
    def footprint_dims(self) -> tuple[float, float]:
        return (self.length_mm, self.width_mm)


@dataclass
class MatchResult:
    package: PackageDef | None
    score: float
    reason: str
    status: str  # matched / likely / unknown

    def to_dict(self) -> dict[str, Any]:
        return {
            "package_id": self.package.id if self.package else "",
            "package_name": self.package.name if self.package else "",
            "score": round(self.score, 3),
            "reason": self.reason,
            "status": self.status,
        }


@dataclass
class MatchRow:
    footprint: str
    usage: int
    result: MatchResult
    candidates: list[MatchResult] = field(default_factory=list)


@dataclass
class MatchReport:
    rows: list[MatchRow] = field(default_factory=list)

    @property
    def matched(self) -> list[MatchRow]:
        return [row for row in self.rows if row.result.status == "matched"]

    @property
    def likely(self) -> list[MatchRow]:
        return [row for row in self.rows if row.result.status == "likely"]

    @property
    def unknown(self) -> list[MatchRow]:
        return [row for row in self.rows if row.result.status == "unknown"]

    @property
    def auto_assignable(self) -> list[MatchRow]:
        return [row for row in self.rows if row.result.status in {"matched", "likely"}]

    def summary(self) -> str:
        return (
            f"确认 {len(self.matched)} · 疑似 {len(self.likely)} · 未知 {len(self.unknown)}"
        )


def _ratio(left: str, right: str) -> float:
    return difflib.SequenceMatcher(None, left, right).ratio()


class PackageLibrary:
    """封装库：内置封装 + 用户覆盖（data 目录的 packages.json）。"""

    def __init__(self, packages: Iterable[PackageDef] | None = None) -> None:
        self._packages: dict[str, PackageDef] = {}
        self._index: dict[str, str] = {}
        for package in packages or []:
            self.add(package)

    # ---------------- 集合操作 ----------------

    def add(self, package: PackageDef, replace: bool = True) -> None:
        if package.id in self._packages and not replace:
            return
        self._packages[package.id] = package
        self._rebuild_keys(package)

    def _rebuild_keys(self, package: PackageDef) -> None:
        for name in package.all_names():
            key = compact_key(name)
            if key:
                self._index.setdefault(key, package.id)

    def get(self, package_id: str) -> PackageDef | None:
        return self._packages.get(package_id)

    def find(self, name: str) -> PackageDef | None:
        key = compact_key(name)
        package_id = self._index.get(key)
        return self._packages.get(package_id) if package_id else None

    def remove(self, package_id: str) -> None:
        package = self._packages.pop(package_id, None)
        if package is None:
            return
        self._index = {}
        for item in self._packages.values():
            self._rebuild_keys(item)

    def list(self) -> list[PackageDef]:
        return sorted(self._packages.values(), key=lambda pkg: (pkg.category, pkg.name))

    def by_category(self) -> dict[str, list[PackageDef]]:
        result: dict[str, list[PackageDef]] = {}
        for package in self.list():
            result.setdefault(package.category, []).append(package)
        return result

    def __len__(self) -> int:
        return len(self._packages)

    # ---------------- 匹配 ----------------

    def match(
        self,
        footprint: str,
        body_hint: tuple[float, float] | None = None,
        threshold: float = 0.92,
    ) -> MatchResult:
        candidates = self.suggest(footprint, body_hint, limit=1)
        if not candidates:
            return MatchResult(None, 0.0, "封装库为空", "unknown")
        best = candidates[0]
        if best.score >= threshold:
            best.status = "matched"
        elif best.score >= 0.72:
            best.status = "likely"
        else:
            best.status = "unknown"
        return best

    def suggest(
        self,
        footprint: str,
        body_hint: tuple[float, float] | None = None,
        limit: int = 3,
    ) -> list[MatchResult]:
        raw = (footprint or "").strip()
        if not raw or not self._packages:
            return []
        normalized = normalize_footprint(raw)
        canonical = canonical_footprint(raw)
        key = compact_key(raw)
        canonical_key = compact_key(canonical)
        results: list[MatchResult] = []
        for package in self._packages.values():
            score, reason = self._score(package, raw, normalized, canonical, key, canonical_key, body_hint)
            if score <= 0.25:
                continue
            results.append(MatchResult(package, score, reason, "unknown"))
        results.sort(key=lambda item: (-item.score, item.package.name if item.package else ""))
        return results[:limit]

    def _score(
        self,
        package: PackageDef,
        raw: str,
        normalized: str,
        canonical: str,
        key: str,
        canonical_key: str,
        body_hint: tuple[float, float] | None,
    ) -> tuple[float, str]:
        score = 0.0
        reason = ""
        for alias in package.all_names():
            alias_norm = normalize_footprint(alias)
            alias_key = compact_key(alias)
            if not alias_key:
                continue
            if alias_key == key:
                score = 1.0
                reason = f"别名精确命中 {alias}"
                break
            if alias_norm == normalized:
                score = max(score, 0.99)
                reason = f"归一化命中 {alias}"
            if compact_key(canonical_footprint(alias)) == canonical_key and canonical_key:
                score = max(score, 0.96)
                reason = f"同义名 {alias} ↔ {canonical}"
        if score < 0.9 and normalized:
            ratio = _ratio(compact_key(normalized), package.compact_name)
            if ratio >= 0.72:
                if score < ratio * 0.82:
                    score = ratio * 0.82
                    reason = f"名称相似 {ratio:.0%}"
        if body_hint is not None and score < 0.9:
            dim_error = _dimension_error(package, body_hint)
            if dim_error is not None:
                dim_score = max(0.0, 1.0 - dim_error / 0.35)
                if score == 0.0 and dim_score > 0.55:
                    score = dim_score * 0.72
                    reason = f"尺寸吻合（偏差 {dim_error:.0%}）"
                elif score > 0:
                    score = min(1.0, score * 0.85 + dim_score * 0.15)
        return min(score, 1.0), reason or "无匹配"

    def match_report(
        self,
        footprints: dict[str, int] | Iterable[tuple[str, int]],
        threshold: float = 0.92,
    ) -> MatchReport:
        items = footprints.items() if isinstance(footprints, dict) else footprints
        report = MatchReport()
        for footprint, usage in items:
            best = self.match(footprint, threshold=threshold)
            candidates = self.suggest(footprint, limit=3) if best.package is None or best.score < threshold else []
            report.rows.append(
                MatchRow(footprint=footprint, usage=int(usage), result=best, candidates=candidates)
            )
        report.rows.sort(key=lambda row: (-row.usage, row.footprint))
        return report

    # ---------------- 持久化 ----------------

    def to_list(self) -> list[dict[str, Any]]:
        return [package.to_dict() for package in self.list()]

    def save_user_file(self, path: str | Path) -> Path:
        """把非内置封装写入用户封装文件（data 目录）。"""
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = [package.to_dict() for package in self.list() if not package.builtin]
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return target

    @classmethod
    def load(cls, builtin_path: str | Path | None = None, user_path: str | Path | None = None) -> "PackageLibrary":
        library = cls()
        for path, is_builtin in ((builtin_path, True), (user_path, False)):
            if not path:
                continue
            file_path = Path(path)
            if not file_path.exists():
                continue
            try:
                data = json.loads(file_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            for item in data if isinstance(data, list) else []:
                try:
                    package = PackageDef.from_dict(item)
                except (TypeError, ValueError):
                    continue
                package.builtin = is_builtin
                library.add(package)
        return library


def _dimension_error(package: PackageDef, hint: tuple[float, float]) -> float | None:
    """比较本体长宽（忽略长短边朝向），返回平均相对偏差。"""
    if hint[0] <= 0 or hint[1] <= 0:
        return None
    left = sorted((package.length_mm, package.width_mm))
    right = sorted((float(hint[0]), float(hint[1])))
    errors = [abs(a - b) / max(b, 1e-6) for a, b in zip(left, right)]
    return sum(errors) / len(errors)


def default_package_paths(data_root: str | Path) -> tuple[Path, Path]:
    """(内置封装文件, 用户封装文件)。"""
    here = Path(__file__).resolve().parents[2]
    return here / "data" / "packages.json", Path(data_root) / "packages.json"
