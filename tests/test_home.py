from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from midpnp.config import load_settings  # noqa: E402
from midpnp.core.machine.service import MachineService  # noqa: E402
from midpnp.core.models import Component, Feeder  # noqa: E402
from midpnp.core.storage import Storage  # noqa: E402
from midpnp.paths import AppPaths  # noqa: E402
from midpnp.ui.context import AppContext  # noqa: E402
from midpnp.ui.pages.home import HomePage, MachineScene  # noqa: E402


class HomePageTests(unittest.TestCase):
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
        self.page = HomePage(self.ctx)

    def tearDown(self) -> None:
        self.page.deleteLater()
        self.machine.shutdown()
        self.storage.close()
        self.tempdir.cleanup()

    def test_bank_chip_reflects_profile(self) -> None:
        self.assertIn("上料 25", self.page.bank_chip.text())
        self.assertIn("下料 25", self.page.bank_chip.text())
        self.assertIn("已装", self.page.bank_chip.text())

    def test_feeders_are_counted_for_both_banks(self) -> None:
        bank = self.ctx.profile.feeders
        self.assertEqual(bank.top_count, 25)
        self.assertEqual(bank.bottom_count, 25)
        self.assertEqual(bank.bank_of(1), "top")
        self.assertEqual(bank.bank_of(25), "top")
        self.assertEqual(bank.bank_of(26), "bottom")
        self.assertEqual(bank.bank_of(50), "bottom")

    def test_feeder_texts_show_value_and_package(self) -> None:
        feeder = Feeder(id="F1", slot=3, component_id="C1", label="03 · 10K")
        component = Component(id="C1", name="10K", package="R0805", value="10K")
        value, package = MachineScene._feeder_texts(feeder, component)
        self.assertEqual(value, "10K")
        self.assertEqual(package, "R0805")

    def test_feeder_texts_fall_back_to_label(self) -> None:
        feeder = Feeder(id="F1", slot=4, component_id="C1", label="04 · SOP8")
        component = Component(id="C1", name="SOP8", package="SOP-8")
        value, package = MachineScene._feeder_texts(feeder, component)
        self.assertEqual(value, "SOP8")
        self.assertEqual(package, "SOP-8")

    def test_scene_paints(self) -> None:
        pixmap = self.page.scene.grab()
        self.assertFalse(pixmap.isNull())
        self.assertGreater(pixmap.width(), 300)

    def test_step_scale_values(self) -> None:
        self.assertEqual(self.page.step_scale.value(), 0.1)
        self.page.step_scale._set_index(0)
        self.assertEqual(self.page.step_scale.value(), 100.0)
        self.assertAlmostEqual(self.page._step, 100.0)

    def test_top_camera_hides_vacuum(self) -> None:
        self.page._set_target("camera")
        self.assertTrue(self.page.vacuum_button.isHidden())
        self.page._set_target("left")
        self.assertFalse(self.page.vacuum_button.isHidden())

    def test_nozzle_selection_maps_to_vacuum_target(self) -> None:
        self.page._set_target("right")
        self.assertEqual(self.page._active_nozzle(), self.page._nozzle_ids[1])

    def test_top_and_bottom_banks_are_aligned(self) -> None:
        self.page.scene.grab()
        top = self.page.scene._lane_rects[1]
        bottom = self.page.scene._lane_rects[26]
        self.assertAlmostEqual(top.left(), bottom.left(), delta=0.6)
        self.assertAlmostEqual(top.width(), bottom.width(), delta=0.6)

    def test_camera_modes_switch(self) -> None:
        self.page._set_camera("top")
        self.assertIsNotNone(self.page._camera_config("top"))
        self.page._tick_camera()
        self.assertEqual(self.page.camera_chip.text(), "CAM-TOP")
        self.page._set_camera("bottom")
        self.page._tick_camera()
        self.assertEqual(self.page.camera_chip.text(), "CAM-BOTTOM")

    def test_disconnected_banner_visible(self) -> None:
        self.assertFalse(self.page.banner.isHidden())
        self.assertFalse(self.page._jog_buttons[0].isEnabled())


if __name__ == "__main__":
    unittest.main()
