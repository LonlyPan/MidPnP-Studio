"""端到端冒烟测试：连接模拟器、执行完整生产、落库并核对余料。"""

from __future__ import annotations

import os
import shutil
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from midpnp import APP_NAME  # noqa: E402
from midpnp.config import load_settings  # noqa: E402
from midpnp.core.machine.service import MachineService  # noqa: E402
from midpnp.core.planner import build_job  # noqa: E402
from midpnp.core.storage import Storage  # noqa: E402
from midpnp.paths import AppPaths  # noqa: E402
from midpnp.ui.context import AppContext  # noqa: E402
from midpnp.ui.main_window import MainWindow  # noqa: E402
from midpnp.ui.theme import STYLESHEET  # noqa: E402


def main() -> int:
    data_dir = ROOT / ".smoke-data"
    if data_dir.exists():
        shutil.rmtree(data_dir)
    app = QApplication(sys.argv[:1])
    app.setApplicationName(APP_NAME)
    app.setStyle("Fusion")
    app.setStyleSheet(STYLESHEET)
    paths = AppPaths.create(data_dir)
    storage = Storage(paths.database)
    storage.seed_demo()
    settings = load_settings(paths.settings)
    settings.simulation_speed = 30.0
    settings.auto_connect = True
    service = MachineService()
    ctx = AppContext(paths, storage, settings, service)
    window = MainWindow(ctx)
    window.show()
    QTest.qWait(1400)
    assert ctx.connected, "simulator did not connect"
    product = ctx.current_product
    assert product is not None
    plan, issues = build_job(product, ctx.components(), ctx.feeders(), settings.limits)
    errors = [issue for issue in issues if issue.is_error]
    assert not errors, errors

    before = {f.id: f.remaining for f in ctx.feeders()}
    window.navigate("production")
    QTest.qWait(200)
    window.production._start()
    deadline = time.monotonic() + 25
    started = False
    while time.monotonic() < deadline:
        app.processEvents()
        if service.run_active:
            started = True
        if started and not service.run_active:
            break
        time.sleep(0.02)
    else:
        print("FAIL: production did not finish")
        return 1
    QTest.qWait(800)
    records = storage.recent_runs(1)
    record = records[0]
    print(
        f"run status={record.status} placed={record.placed}/{record.total} "
        f"duration={record.duration_s:.1f}s state={service.state.value}"
    )
    assert record.placed == 35, f"expected 35 placed, got {record.placed}"
    after = {f.id: f.remaining for f in ctx.feeders()}
    for feeder_id, count in plan.feeder_usage.items():
        assert before[feeder_id] - after[feeder_id] == count, (feeder_id, count)
    print("feeder stock decremented correctly")
    window.grab().save(str(ROOT / "docs" / "screenshots" / "11-production-complete.png"))
    window.close()
    service.shutdown()
    storage.close()
    print("E2E OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
