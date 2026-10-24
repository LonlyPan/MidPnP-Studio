from __future__ import annotations

import unittest

from midpnp.core.imports import (
    ColumnMapping,
    ImportOptions,
    PositionImportError,
    detect_format,
    detect_columns,
    export_template_csv,
    parse_positions,
    preview_positions,
)


ALTIUM = """Designator,Comment,Layer,Footprint,Mid X (mm),Mid Y (mm),Rotation
R1,10k,Top,0603,12.7,8.4,0
C1,100nF,Top,0402,18.2,8.4,90
U1,STM32,Top,LQFP-48,30.0,20.0,0
"""

KICAD = """### Module positions - created on 2024-01-01 ###
## Unit = mm, Angle = deg.
## Side : top
# Ref     Val     Package     PosX    PosY    Rot  Side
R1        10k     R_0603      10.0    20.0    0.0  top
C1        100nF   C_0402      15.0    25.0    90.0 top
D1        LED     LED_0805    5.0     5.0     45.0 bottom
"""

OPENPNP = """<?xml version="1.0" encoding="UTF-8"?>
<openpnp-board version="1.0">
  <placements>
    <placement side="Top" designator="R1" part-id="R-0603-10K" x="10.0" y="20.0" rotation="90.0" enabled="true"/>
    <placement side="Bottom" designator="C2" part-id="C-0402-100N" x="30.0" y="40.0" rotation="0.0" enabled="false"/>
  </placements>
  <fiducials>
    <fiducial designator="FID1" x="2.0" y="2.0" diameter="1.0"/>
  </fiducials>
</openpnp-board>
"""


class ColumnMappingTests(unittest.TestCase):
    def test_detect_altium_headers(self) -> None:
        mapping, missing = detect_columns(
            ["Designator", "Comment", "Layer", "Footprint", "Mid X (mm)", "Mid Y (mm)", "Rotation"]
        )
        self.assertEqual(missing, [])
        self.assertEqual(mapping.refdes, "Designator")
        self.assertEqual(mapping.x, "Mid X (mm)")
        self.assertEqual(mapping.component, "Comment")
        self.assertEqual(mapping.package, "Footprint")

    def test_chinese_headers(self) -> None:
        mapping, missing = detect_columns(["位号", "元件", "封装", "坐标X", "坐标Y", "角度"])
        self.assertEqual(missing, [])

    def test_missing_columns(self) -> None:
        _mapping, missing = detect_columns(["Name", "Value"])
        self.assertEqual(set(missing), {"refdes", "x", "y"})


class PositionImportTests(unittest.TestCase):
    def test_generic_csv(self) -> None:
        result = parse_positions(ALTIUM, "altium.csv")
        self.assertEqual(result.format, "csv")
        self.assertEqual(len(result.placements), 3)
        self.assertEqual(result.placements[0].refdes, "R1")
        self.assertAlmostEqual(result.placements[0].x_mm, 12.7)
        self.assertEqual(result.placements[0].side.value, "Top")
        self.assertEqual(len(result.components), 3)

    def test_kicad_pos_bottom_flip(self) -> None:
        result = parse_positions(KICAD, "board.pos")
        self.assertEqual(result.format, "kicad-pos")
        bottom = result.placements[2]
        self.assertEqual(bottom.refdes, "D1")
        self.assertEqual(bottom.side.value, "Bottom")
        # OpenPnP 约定：底面 X 取反、角度 180-rot
        self.assertAlmostEqual(bottom.x_mm, -5.0)
        self.assertAlmostEqual(bottom.rotation_deg, 135.0)

    def test_openpnp_board_xml(self) -> None:
        result = parse_positions(OPENPNP, "board.board.xml")
        self.assertEqual(result.format, "openpnp-board")
        self.assertEqual(len(result.placements), 2)
        self.assertTrue(result.placements[1].skip)
        self.assertEqual(result.placements[0].rotation_deg, 90.0)
        self.assertEqual(len(result.fiducials), 1)
        self.assertAlmostEqual(result.fiducials[0].radius_mm, 0.5)

    def test_mil_conversion(self) -> None:
        text = "Designator,Mid X (mil),Mid Y (mil),Footprint\nR9,500,250,0603\n"
        result = parse_positions(text, "mil.csv")
        self.assertAlmostEqual(result.placements[0].x_mm, 12.7, places=3)
        self.assertAlmostEqual(result.placements[0].y_mm, 6.35, places=3)
        self.assertEqual(result.unit, "mil")

    def test_transform_options(self) -> None:
        options = ImportOptions(mirror_y=True, rotation_offset_deg=90.0, offset_x_mm=5.0)
        result = parse_positions(ALTIUM, "a.csv", options=options)
        placement = result.placements[0]
        self.assertAlmostEqual(placement.x_mm, 17.7)
        self.assertAlmostEqual(placement.y_mm, -8.4)
        self.assertAlmostEqual(placement.rotation_deg, 90.0)

    def test_swap_and_offset(self) -> None:
        options = ImportOptions(swap_xy=True, offset_x_mm=1.0, offset_y_mm=2.0)
        result = parse_positions(ALTIUM, "a.csv", options=options)
        placement = result.placements[0]
        self.assertAlmostEqual(placement.x_mm, 9.4)
        self.assertAlmostEqual(placement.y_mm, 14.7)

    def test_preview(self) -> None:
        result, rows = preview_positions(ALTIUM, "a.csv", limit=2)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["refdes"], "R1")
        self.assertEqual(result.mapping.refdes, "Designator")

    def test_missing_columns_raises(self) -> None:
        with self.assertRaises(PositionImportError):
            parse_positions("Name,Value\nR1,1k\n")

    def test_empty_raises(self) -> None:
        with self.assertRaises(PositionImportError):
            parse_positions("   ", "empty.csv")

    def test_explicit_mapping_overrides(self) -> None:
        text = "Ref,PosX,PosY\nR1,1.0,2.0\n"
        mapping = ColumnMapping(refdes="Ref", x="PosX", y="PosY")
        result = parse_positions(text, "weird.csv", mapping=mapping)
        self.assertAlmostEqual(result.placements[0].x_mm, 1.0)

    def test_template_round_trip(self) -> None:
        result = parse_positions(export_template_csv(), "template.csv")
        self.assertEqual(len(result.placements), 3)
        self.assertEqual(result.placements[2].refdes, "U1")

    def test_detect_format(self) -> None:
        self.assertEqual(detect_format(OPENPNP, "x.xml"), "openpnp-board")
        self.assertEqual(detect_format(KICAD, "board.pos"), "kicad-pos")
        self.assertEqual(detect_format(ALTIUM, "a.csv"), "csv")


if __name__ == "__main__":
    unittest.main()
