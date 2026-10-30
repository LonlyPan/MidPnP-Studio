from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from midpnp.config import AppSettings
from midpnp.core.profiles import (
    AxisConfig,
    MachineProfile,
    ProfileError,
    ProfileLibrary,
    profile_summary,
)


class ProfileTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.library = ProfileLibrary(self.root)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_builtin_profiles_present_and_valid(self) -> None:
        ids = set(self.library.ids())
        self.assertIn("sim-desktop", ids)
        self.assertIn("gcode-3axis", ids)
        self.assertIn("bench-single", ids)
        for profile in self.library.list():
            errors = [issue for issue in profile.validate() if issue.is_error]
            self.assertEqual(errors, [], msg=f"{profile.id}: {[issue.message for issue in errors]}")

    def test_sim_desktop_limits(self) -> None:
        profile = self.library.get("sim-desktop")
        limits = profile.limits()
        self.assertAlmostEqual(limits.travel_x_mm, 420.0)
        self.assertAlmostEqual(limits.travel_y_mm, 360.0)
        self.assertAlmostEqual(limits.safe_z_mm, 12.0)
        self.assertEqual(limits.nozzle_count, 2)
        self.assertEqual(len(profile.nozzle_ids()), 2)

    def test_settings_projection(self) -> None:
        profile = self.library.get("gcode-3axis")
        values = profile.settings_values()
        self.assertEqual(values["connection_mode"], "tcp")
        self.assertEqual(values["machine_name"], profile.name)
        self.assertEqual(values["travel_x_mm"], 600.0)

    def test_from_settings_legacy(self) -> None:
        settings = AppSettings(machine_name="旧机器", travel_x_mm=500, nozzle_count=2)
        profile = MachineProfile.from_settings(settings)
        self.assertEqual(profile.name, "旧机器")
        self.assertAlmostEqual(profile.limits().travel_x_mm, 500.0)
        self.assertEqual(len(profile.nozzle_ids()), 2)
        self.assertEqual(profile.driver.type, "simulator")

    def test_save_duplicate_delete(self) -> None:
        clone = self.library.duplicate("sim-desktop", "my-machine", "我的机器")
        self.assertEqual(clone.id, "my-machine")
        self.assertFalse(clone.builtin)
        self.assertTrue((self.root / "profiles" / "my-machine.json").exists())
        # 重新加载后仍存在
        reloaded = ProfileLibrary(self.root)
        self.assertIsNotNone(reloaded.get("my-machine"))
        # 内置模板不允许直接覆盖
        with self.assertRaises(ProfileError):
            self.library.save(self.library.get("sim-desktop"))
        self.assertTrue(self.library.delete("my-machine"))
        self.assertIsNone(self.library.get("my-machine"))

    def test_import_export(self) -> None:
        target = self.root / "exported.json"
        profile = self.library.get("bench-single")
        self.library.export(profile, target)
        imported = self.library.import_file(target)
        self.assertEqual(imported.id, "bench-single")
        self.assertFalse(imported.builtin)

    def test_validation_catches_errors(self) -> None:
        profile = self.library.get("sim-desktop")
        profile.axes["x"] = AxisConfig("x", min=400, max=100)
        profile.heads = []
        issues = profile.validate()
        fields = {issue.field for issue in issues if issue.is_error}
        self.assertIn("axes.x", fields)
        self.assertIn("heads", fields)

    def test_round_trip_json(self) -> None:
        profile = self.library.get("dual-head-demo")
        data = json.loads(json.dumps(profile.to_dict()))
        clone = MachineProfile.from_dict(data)
        self.assertEqual(clone.id, profile.id)
        self.assertEqual(len(clone.heads), 2)
        self.assertEqual(len(clone.nozzle_ids()), 4)
        self.assertEqual(clone.to_dict()["axes"]["x"]["max"], 450.0)

    def test_summary(self) -> None:
        summary = profile_summary(self.library.get("sim-desktop"))
        self.assertEqual(summary["nozzles"], 2)
        self.assertEqual(summary["feeders"], 50)
        self.assertEqual(summary["driver"], "simulator")


if __name__ == "__main__":
    unittest.main()
