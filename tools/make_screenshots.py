"""生成文档用界面截图（离屏渲染）。"""

from __future__ import annotations

import os
import shutil
import sys
import time
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
from midpnp.ui.connect_dialog import ConnectDialog  # noqa: E402
from midpnp.ui.main_window import MainWindow  # noqa: E402
from midpnp.ui.machine_gallery import MachineGalleryDialog  # noqa: E402
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
    settings.auto_connect = False
    service = MachineService()
    ctx = AppContext(paths, storage, settings, service)
    window = MainWindow(ctx)
    window.resize(1680, 1000)
    window.show()
    QTest.qWait(1600)

    # 首次启动的设备画廊
    gallery = MachineGalleryDialog(ctx, first_run=True, parent=window)
    gallery.show()
    QTest.qWait(500)
    gallery.grab().save(str(out_dir / "13-machine-gallery.png"))
    print("saved 13-machine-gallery")
    gallery.reject()

    # 连接流程弹窗：截取“正在进行”的状态，然后等它自动完成
    connect = ConnectDialog(ctx, parent=window)
    connect.show()
    QTest.qWait(1300)
    connect.grab().save(str(out_dir / "14-connect.png"))
    print("saved 14-connect")
    deadline = time.monotonic() + 8.0
    while connect.result() == 0 and time.monotonic() < deadline:
        QTest.qWait(150)
    QTest.qWait(500)
    window.toast.hide()

    pages = [
        ("home", "01-home"),
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
    window.vision.simulate_error.setChecked(True)
    window.vision._capture()
    window.vision._align()
    QTest.qWait(1200)
    window.grab().save(str(out_dir / "07-vision.png"))
    print("saved 07-vision")
    window.toast.hide()

    for key, name in (("logs", "08-logs"), ("settings", "09-settings")):
        window.navigate(key)
        QTest.qWait(400)
        window.grab().save(str(out_dir / f"{name}.png"))
        print(f"saved {name}")

    window.navigate("packages")
    window.packages.match_input.setText("QFN32_5x5")
    window.packages._run_match()
    QTest.qWait(400)
    window.grab().save(str(out_dir / "12-packages.png"))
    print("saved 12-packages")

    window.navigate("production")
    QTest.qWait(300)
    window.production._start()
    QTest.qWait(1700)
    window.grab().save(str(out_dir / "10-production-running.png"))
    print("saved production-running")
    deadline = time.monotonic() + 25.0
    while service.run_active and time.monotonic() < deadline:
        QTest.qWait(250)
    QTest.qWait(400)
    window.grab().save(str(out_dir / "11-production-complete.png"))
    print("saved production-complete")
    service.stop()
    QTest.qWait(250)

    window.close()
    service.shutdown()
    storage.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
