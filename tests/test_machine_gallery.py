from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from midpnp.config import load_settings  # noqa: E402
from midpnp.core.machine.service import MachineService  # noqa: E402
from midpnp.core.storage import Storage  # noqa: E402
from midpnp.paths import AppPaths  # noqa: E402
from midpnp.ui.context import AppContext  # noqa: E402
from midpnp.ui.machine_gallery import MachineGalleryDialog  # noqa: E402


class MachineGalleryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        paths = AppPaths.create(Path(self.tempdir.name))
        self.storage = Storage(paths.database)
        self.storage.seed_demo()
        self.settings = load_settings(paths.settings)
        self.machine = MachineService()
        self.ctx = AppContext(paths, self.storage, self.settings, self.machine)

    def tearDown(self) -> None:
        self.machine.shutdown()
        self.storage.close()
        self.tempdir.cleanup()

    def _dialog(self, first_run: bool = False) -> MachineGalleryDialog:
        dialog = MachineGalleryDialog(self.ctx, first_run=first_run)
        self.addCleanup(dialog.deleteLater)
        return dialog

    def test_one_card_per_profile(self) -> None:
        dialog = self._dialog()
        self.assertEqual(len(dialog._cards), len(self.ctx.profile_library.list()))
        self.assertGreaterEqual(len(dialog._cards), 4)

    def test_current_machine_preselected(self) -> None:
        dialog = self._dialog()
        self.assertEqual(dialog.selected_profile.id, self.ctx.profile.id)
        self.assertTrue(dialog._cards[self.ctx.profile.id].selected)

    def test_select_updates_detail_and_selection(self) -> None:
        dialog = self._dialog()
        target = self.ctx.profile_library.get("dual-head-demo")
        dialog._select(target)
        self.assertEqual(dialog.detail_name.text(), target.name)
        self.assertIn("2 头", dialog.specs["heads"].text())
        self.assertTrue(dialog._cards["dual-head-demo"].selected)
        self.assertFalse(dialog._cards[self.ctx.profile.id].selected)

    def test_custom_filter_starts_empty(self) -> None:
        dialog = self._dialog()
        dialog._set_filter("custom")
        self.assertEqual(len(dialog._cards), 0)
        dialog._set_filter("all")
        self.assertEqual(len(dialog._cards), len(self.ctx.profile_library.list()))

    def test_confirm_accepts_selected_profile(self) -> None:
        dialog = self._dialog(first_run=True)
        dialog._select(self.ctx.profile_library.get("bench-single"))
        dialog._confirm()
        self.assertEqual(dialog.result(), MachineGalleryDialog.DialogCode.Accepted)
        self.assertEqual(dialog.selected_profile.id, "bench-single")

    def test_builtin_cannot_be_deleted(self) -> None:
        dialog = self._dialog()
        dialog._select(self.ctx.profile_library.get("sim-desktop"))
        self.assertFalse(dialog.delete_button.isEnabled())

    def test_first_run_title(self) -> None:
        dialog = self._dialog(first_run=True)
        self.assertTrue(dialog.first_run)
        self.assertEqual(dialog.windowTitle(), "选择设备")


if __name__ == "__main__":
    unittest.main()
