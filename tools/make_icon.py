"""生成 Windows 图标 assets/midpnp.ico。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication  # noqa: E402

from midpnp.ui.icons import app_icon  # noqa: E402


def main() -> int:
    app = QApplication([])
    app.processEvents()
    target = ROOT / "assets" / "midpnp.ico"
    target.parent.mkdir(parents=True, exist_ok=True)
    icon = app_icon(256)
    pixmap = icon.pixmap(256, 256)
    if not pixmap.save(str(target), "ICO"):
        png = target.with_suffix(".png")
        pixmap.save(str(png), "PNG")
        print(f"ICO save unsupported; wrote {png}")
        return 1
    print(f"wrote {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
