"""资源文件路径（兼容源码运行与 PyInstaller 打包）。"""

from __future__ import annotations

import sys
from pathlib import Path


def assets_root() -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return base / "assets"


def asset_path(relative: str) -> Path:
    """返回 assets 下的路径；`relative` 用正斜杠，例如 machines/m1.png。"""
    return assets_root() / relative
