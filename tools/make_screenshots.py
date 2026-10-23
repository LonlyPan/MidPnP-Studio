"""生成文档用界面截图（离屏渲染）。"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from midpnp import APP_NAME  # noqa: E402
from midpnp.config import load_settings  # noqa: E402
from midpnp.core.machine.service import MachineService  # noqa: E402
from midpnp.core.storage import Storage  # noqa: E402
from midpnp.paths import AppPaths  # noqa: E402
from midpnp.ui.context import AppContext  # noqa: E402
from midpnp.ui.main_window import MainWindow  # noqa: E402
from midpnp.ui.theme import STYLESHEET  # noqa: E402


def main() -> int:
    data_dir = ROOT / ".preview-data"
    if data_dir.exists():
        shutil.rmtree(data_dir)
    out_dir = ROOT / "docs" / "screenshots"
    out_dir.mkdir(parents=True, exist_ok=True)

    app = QApplication(sys.argv[:1])
    app.setApplicationName(APP_NAME)
    app.setStyle("Fusion")
    app.setStyleSheet(STYLESHEET)

    paths = AppPaths.create(data_dir)
    storage = Storage(paths.database)
    storage.seed_demo()
    settings = load_settings(paths.settings)
    service = MachineService()
    ctx = AppContext(paths, storage, settings, service)
    window = MainWindow(ctx)
    window.resize(1680, 1000)
    window.show()
    QTest.qWait(1600)

    pages = [
        ("dashboard", "01-dashboard"),
        ("production", "02-production"),
        ("programming", "03-programming"),
        ("feeders", "04-feeders"),
        ("components", "05-components"),
    ]
    for key, name in pages:
        window.navigate(key)
        QTest.qWait(400)
        window.grab().save(str(out_dir / f"{name}.png"))
        print(f"saved {name}")

    window.navigate("manual")
    window.manual._jog("X+")
    window.manual._jog("Y+")
    QTest.qWait(650)
    window.grab().save(str(out_dir / "06-manual.png"))
    print("saved 06-manual")

    window.navigate("vision")
    window.vision._align()
    QTest.qWait(1200)
    window.grab().save(str(out_dir / "07-vision.png"))
    print("saved 07-vision")

    for key, name in (("logs", "08-logs"), ("settings", "09-settings")):
        window.navigate(key)
        QTest.qWait(400)
        window.grab().save(str(out_dir / f"{name}.png"))
        print(f"saved {name}")

    window.navigate("production")
    QTest.qWait(300)
    window.production._start()
    QTest.qWait(1700)
    window.grab().save(str(out_dir / "10-production-running.png"))
    print("saved production-running")
    service.stop()
    QTest.qWait(250)

    window.close()
    service.shutdown()
    storage.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
