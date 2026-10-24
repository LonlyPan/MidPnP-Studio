"""应用配置（JSON 文件）。"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any

from .core.models import MachineLimits


@dataclass
class AppSettings:
    machine_name: str = "MidPnP M1"
    operator: str = "操作员"
    connection_mode: str = "simulator"  # simulator / tcp / serial
    host: str = "192.168.1.50"
    port: int = 5025
    serial_port: str = "COM3"
    baud_rate: int = 115200
    auto_connect: bool = True
    simulation_speed: float = 8.0
    travel_x_mm: float = 420.0
    travel_y_mm: float = 360.0
    travel_z_mm: float = 30.0
    safe_z_mm: float = 12.0
    max_speed_mm_s: float = 320.0
    nozzle_count: int = 4
    optimize_route: bool = True
    confirm_before_start: bool = False
    stop_on_low_feeder: bool = False
    camera_source: str = "simulation"
    camera_index: int = 0
    log_level: str = "INFO"
    last_product_id: str = ""
    machine_profile_id: str = ""

    @property
    def limits(self) -> MachineLimits:
        return MachineLimits(
            travel_x_mm=self.travel_x_mm,
            travel_y_mm=self.travel_y_mm,
            travel_z_mm=self.travel_z_mm,
            safe_z_mm=self.safe_z_mm,
            max_speed_mm_s=self.max_speed_mm_s,
            nozzle_count=self.nozzle_count,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AppSettings":
        known = {f.name for f in fields(cls)}
        clean = {k: v for k, v in (data or {}).items() if k in known}
        settings = cls(**clean)
        if settings.connection_mode not in {"simulator", "tcp", "serial"}:
            settings.connection_mode = "simulator"
        settings.simulation_speed = max(1.0, min(30.0, float(settings.simulation_speed)))
        settings.port = max(1, min(65535, int(settings.port)))
        settings.baud_rate = max(1200, int(settings.baud_rate))
        return settings


def load_settings(path: str | Path) -> AppSettings:
    settings_path = Path(path)
    if not settings_path.exists():
        return AppSettings()
    try:
        data = json.loads(settings_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return AppSettings()
    return AppSettings.from_dict(data if isinstance(data, dict) else {})


def save_settings(settings: AppSettings, path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    data = json.dumps(settings.to_dict(), ensure_ascii=False, indent=2)
    temporary.write_text(data, encoding="utf-8")
    os.replace(temporary, target)
