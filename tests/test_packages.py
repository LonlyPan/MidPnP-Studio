from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from midpnp.core.packages import PackageDef, PackageLibrary, normalize_footprint


BUILTIN = Path(__file__).resolve().parents[1] / "midpnp" / "data" / "packages.json"


class PackageLibraryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.library = PackageLibrary.load(BUILTIN)

    def test_builtin_library_loaded(self) -> None:
        self.assertGreaterEqual(len(self.library), 40)
        self.assertIsNotNone(self.library.get("PKG-0603"))

    def test_chip_footprint_variants(self) -> None:
        for name in ("R-0603_1608Metric", "C0603", "0603", "1608", "0603Metric"):
            result = self.library.match(name)
            self.assertEqual(result.package.name, "0603", msg=name)
            self.assertGreaterEqual(result.score, 0.95)

    def test_ic_alias_matching(self) -> None:
        self.assertEqual(self.library.match("SOP8").package.name, "SOIC-8")
        self.assertEqual(self.library.match("SOIC8").package.name, "SOIC-8")
        self.assertEqual(self.library.match("QFN32_5x5").package.name, "QFN-32")
        self.assertEqual(self.library.match("SOT23-5").package.name, "SOT-23-5")

    def test_unknown_footprint(self) -> None:
        result = self.library.match("BGA-9999X")
        self.assertEqual(result.status, "unknown")
        self.assertIsNone(result.package)

    def test_dimension_hint(self) -> None:
        result = self.library.match("GENERIC-CHIP-2P", body_hint=(1.6, 0.8))
        self.assertIsNotNone(result.package)
        self.assertEqual(result.package.name, "0603")

    def test_derived_pads(self) -> None:
        soic = self.library.get("PKG-SOIC-8")
        pads = soic.derived_pads()
        self.assertEqual(len(pads), 8)
        chip = self.library.get("PKG-0603")
        chip_pads = chip.derived_pads()
        self.assertEqual(len(chip_pads), 2)
        self.assertLess(chip_pads[0].x_mm, 0)
        self.assertGreater(chip_pads[1].x_mm, 0)

    def test_normalize_footprint(self) -> None:
        self.assertEqual(normalize_footprint("R_0603"), "0603")
        self.assertEqual(normalize_footprint("Capacitor-0805"), "0805")
        self.assertEqual(normalize_footprint(""), "")

    def test_round_trip(self) -> None:
        package = self.library.get("PKG-SOIC-8")
        clone = PackageDef.from_dict(package.to_dict())
        self.assertEqual(clone.id, package.id)
        self.assertEqual(len(clone.derived_pads()), 8)

    def test_match_report(self) -> None:
        report = self.library.match_report({"0603": 5, "SOP8": 2, "MYSTERY": 1})
        self.assertEqual(len(report.rows), 3)
        self.assertEqual(report.rows[0].footprint, "0603")
        self.assertEqual(len(report.matched), 2)
        self.assertEqual(len(report.unknown), 1)

    def test_user_file_override(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            user_file = Path(directory) / "packages.json"
            user_file.write_text(
                json.dumps(
                    [
                        {
                            "id": "PKG-CUSTOM",
                            "name": "CUSTOM-1",
                            "length_mm": 1.0,
                            "width_mm": 1.0,
                        }
                    ]
                ),
                encoding="utf-8",
            )
            library = PackageLibrary.load(BUILTIN, user_file)
            self.assertIsNotNone(library.get("PKG-CUSTOM"))
            self.assertEqual(library.match("CUSTOM-1").package.name, "CUSTOM-1")


if __name__ == "__main__":
    unittest.main()
