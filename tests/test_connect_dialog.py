from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from midpnp.config import load_settings  # noqa: E402
from midpnp.core.machine.service import MachineService  # noqa: E402
from midpnp.core.storage import Storage  # noqa: E402
from midpnp.paths import AppPaths  # noqa: E402
from midpnp.ui.connect_dialog import ConnectDialog  # noqa: E402
from midpnp.ui.context import AppContext  # noqa: E402


class ConnectDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        paths = AppPaths.create(Path(self.tempdir.name))
        self.storage = Storage(paths.database)
        self.storage.seed_demo()
        settings = load_settings(paths.settings)
        settings.auto_connect = False
        self.machine = MachineService()
        self.ctx = AppContext(paths, self.storage, settings, self.machine)

    def tearDown(self) -> None:
        self.machine.shutdown()
        self.storage.close()
        self.tempdir.cleanup()

    def _pump(self, dialog: ConnectDialog, seconds: float) -> None:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.02)
            if dialog.result() != 0:
                return

    def test_dialog_runs_all_steps_and_connects(self) -> None:
        dialog = ConnectDialog(self.ctx)
        dialog.show()
        self._pump(dialog, 8.0)
        self.assertEqual(dialog.result(), ConnectDialog.DialogCode.Accepted)
        self.assertTrue(self.machine.connected)
        self.assertEqual(dialog.rows["camera"].state.text() != "等待", True)
        self.assertEqual(dialog.rows["host"].state.text(), "已连接")
        self.assertEqual(dialog.rows["home"].state.text(), "已回零")
        self.assertEqual(dialog.rows["calibrate"].state.text(), "已完成")
        dialog.deleteLater()

    def test_cancel_stops_sequence(self) -> None:
        dialog = ConnectDialog(self.ctx)
        dialog.show()
        self.app.processEvents()
        dialog._cancel()
        self.assertEqual(dialog.result(), ConnectDialog.DialogCode.Rejected)
        dialog.deleteLater()


if __name__ == "__main__":
    unittest.main()
