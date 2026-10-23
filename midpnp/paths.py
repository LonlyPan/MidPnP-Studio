"""应用数据目录与路径管理。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


APP_DIR_NAME = "MidPnP Studio"


def default_data_root() -> Path:
    override = os.environ.get("MIDPNP_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    local = os.environ.get("LOCALAPPDATA")
    if local:
        return Path(local) / APP_DIR_NAME
    return Path.home() / ".midpnp-studio"


@dataclass(frozen=True)
class AppPaths:
    root: Path
    database: Path
    settings: Path
    logs: Path
    exports: Path
    screenshots: Path

    @classmethod
    def create(cls, root: Path | None = None) -> "AppPaths":
        base = (root or default_data_root()).expanduser().resolve()
        paths = cls(
            root=base,
            database=base / "midpnp.db",
            settings=base / "settings.json",
            logs=base / "logs",
            exports=base / "exports",
            screenshots=base / "screenshots",
        )
        for directory in (base, paths.logs, paths.exports, paths.screenshots):
            directory.mkdir(parents=True, exist_ok=True)
        return paths
