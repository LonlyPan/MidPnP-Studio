"""首次启动时写入的演示数据。

演示数据只用于在没有机器/产品的情况下体验完整流程，可在设置页一键重置。
"""

from __future__ import annotations

from datetime import datetime, timedelta

from .models import (
    Component,
    Feeder,
    Fiducial,
    Placement,
    Product,
    RunRecord,
    Side,
    VisionMode,
    now_iso,
)


def _component(
    cid: str,
    name: str,
    package: str,
    length: float,
    width: float,
    height: float,
    nozzle: str,
    color: str,
    vision: VisionMode = VisionMode.NONE,
    notes: str = "",
    value: str = "",
) -> Component:
    return Component(
        id=cid,
        name=name,
        package=package,
        length_mm=length,
        width_mm=width,
        height_mm=height,
        nozzle=nozzle,
        vision_mode=vision,
        color=color,
        notes=notes,
        value=value,
    )


def build_demo_components() -> list[Component]:
    return [
        _component("CMP-R0603", "电阻 0603", "0603", 1.6, 0.8, 0.5, "N1", "#d6b35b", value="10K"),
        _component("CMP-C0603", "电容 0603", "0603", 1.6, 0.8, 0.8, "N1", "#c48458", value="100nF"),
        _component("CMP-LED0805", "LED 0805", "0805", 2.0, 1.25, 0.8, "N2", "#e8f2c9", value="LED-RED"),
        _component("CMP-L0805", "功率电感 0805", "0805", 2.0, 1.25, 1.0, "N2", "#7b8794", value="2.2uH"),
        _component(
            "CMP-SOP8",
            "驱动 IC SOP-8",
            "SOP-8",
            4.9,
            3.9,
            1.5,
            "N2",
            "#2d343b",
            VisionMode.IC,
            "引脚间距 1.27 mm",
            value="DRV8833",
        ),
        _component(
            "CMP-QFN24",
            "MCU QFN-24",
            "QFN-24",
            5.0,
            5.0,
            0.9,
            "N2",
            "#242a31",
            VisionMode.IC,
            "底部散热焊盘",
            value="STM32G030",
        ),
        _component("CMP-HDR4", "排针 2.54", "HDR-1x4", 10.16, 2.54, 2.5, "N2", "#b08d57", value="4P"),
    ]


def build_demo_feeders() -> list[Feeder]:
    definitions = [
        (1, "CMP-R0603", 4000, 3120, 4.0, 18.0, 8),
        (2, "CMP-C0603", 4000, 2860, 4.0, 28.0, 8),
        (3, "CMP-LED0805", 3000, 1420, 4.0, 38.0, 12),
        (4, "CMP-SOP8", 1000, 640, 8.0, 48.0, 16),
        (5, "CMP-QFN24", 800, 520, 12.0, 58.0, 24),
        (6, "CMP-HDR4", 500, 40, 8.0, 68.0, 16),
        (7, "CMP-L0805", 2500, 1980, 4.0, 78.0, 12),
    ]
    return [
        Feeder(
            id=f"FDR-{slot:02d}",
            slot=slot,
            component_id=cid,
            label=f"{slot:02d} · {cid.replace('CMP-', '')}",
            capacity=capacity,
            remaining=remaining,
            pitch_mm=pitch,
            pick_x_mm=pick_x,
            pick_y_mm=28.0,
            pick_z_mm=0.0,
            enabled=True,
            low_threshold_pct=15,
            tape_width_mm=tape,
        )
        for slot, cid, capacity, remaining, pitch, pick_x, tape in definitions
    ]


def build_demo_placements() -> list[Placement]:
    placements: list[Placement] = []

    def add(ref: str, cid: str, x: float, y: float, rot: float = 0.0, side: Side = Side.TOP) -> None:
        placements.append(
            Placement(
                refdes=ref,
                component_id=cid,
                x_mm=x,
                y_mm=y,
                rotation_deg=rot,
                side=side,
            )
        )

    for i in range(8):
        add(f"LED{i + 1}", "CMP-LED0805", 20.0 + i * 20.0, 14.0)

    add("U1", "CMP-QFN24", 52.0, 55.0, 90.0)
    add("U2", "CMP-SOP8", 104.0, 55.0, 180.0)
    add("U3", "CMP-SOP8", 148.0, 55.0, 0.0)

    for i, (x, y) in enumerate(((43, 44), (61, 44), (43, 66), (61, 66)), start=1):
        add(f"C{i}", "CMP-C0603", float(x), float(y))

    for i, (x, y) in enumerate(((74, 38), (80, 38), (86, 38), (74, 44), (80, 44), (86, 44)), start=1):
        add(f"R{i}", "CMP-R0603", float(x), float(y))

    add("L1", "CMP-L0805", 74.0, 70.0, 90.0)
    add("L2", "CMP-L0805", 80.0, 70.0, 90.0)

    for i, (x, y) in enumerate(((92, 72), (98, 72), (116, 72), (122, 72)), start=5):
        add(f"C{i}", "CMP-C0603", float(x), float(y))

    for i, x in enumerate((30, 37, 44, 51, 58, 65), start=7):
        add(f"R{i}", "CMP-R0603", float(x), 90.0)

    add("J1", "CMP-HDR4", 16.0, 88.0, 90.0)
    add("J2", "CMP-HDR4", 164.0, 88.0, 90.0)

    return placements


def build_demo_product() -> Product:
    return Product(
        id="demo-mxled8",
        name="MX-LED8 灯控板",
        revision="A.2",
        board_width_mm=180.0,
        board_height_mm=110.0,
        board_thickness_mm=1.6,
        board_origin_x_mm=120.0,
        board_origin_y_mm=125.0,
        fiducials=[
            Fiducial("FID1", 8.0, 8.0, 1.2),
            Fiducial("FID2", 172.0, 8.0, 1.2),
            Fiducial("FID3", 90.0, 102.0, 1.2),
        ],
        placements=build_demo_placements(),
        notes="35 点 · 7 种元件 · 可生产",
        updated_at=now_iso(),
    )


def build_demo_runs() -> list[RunRecord]:
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    start1 = today + timedelta(hours=8, minutes=5)
    start2 = today + timedelta(hours=10, minutes=20)
    return [
        RunRecord(
            id="RUN-DEMO-001",
            product_id="demo-mxled8",
            product_name="MX-LED8 灯控板",
            started_at=start1.isoformat(timespec="seconds"),
            finished_at=(start1 + timedelta(seconds=2540)).isoformat(timespec="seconds"),
            total=1240,
            placed=1236,
            failed=4,
            skipped=0,
            status="Completed",
            duration_s=2540,
            notes="演示记录",
        ),
        RunRecord(
            id="RUN-DEMO-002",
            product_id="demo-mxled8",
            product_name="MX-LED8 灯控板",
            started_at=start2.isoformat(timespec="seconds"),
            finished_at=(start2 + timedelta(seconds=1735)).isoformat(timespec="seconds"),
            total=840,
            placed=838,
            failed=2,
            skipped=0,
            status="Completed",
            duration_s=1735,
            notes="演示记录",
        ),
    ]
