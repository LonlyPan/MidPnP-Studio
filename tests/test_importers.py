from __future__ import annotations

import unittest

from midpnp.core.demo import build_demo_components, build_demo_product
from midpnp.core.importers import ImportError_, export_centroid_csv, parse_centroid_csv


class ImporterTests(unittest.TestCase):
    def test_english_headers(self) -> None:
        csv_text = (
            "Designator,Comment,Footprint,Mid X (mm),Mid Y (mm),Rotation,Layer\n"
            "R1,10k,0603,12.5,22.0,90,Top\n"
            "C1,100nF,0603,14.0,22.0,0,Bottom\n"
        )
        result = parse_centroid_csv(csv_text)
        self.assertEqual(len(result.placements), 2)
        self.assertEqual(result.placements[0].refdes, "R1")
        self.assertAlmostEqual(result.placements[0].x_mm, 12.5)
        self.assertEqual(result.placements[1].side.value, "Bottom")
        self.assertEqual(len(result.components), 2)

    def test_chinese_headers_and_mil(self) -> None:
        csv_text = (
            "位号,元件,封装,坐标X,坐标Y,角度,层\n"
            "U1,MCU,QFN-24,1000,2000,45,顶\n"
        )
        # 中文表头默认单位 mm；此处验证中文映射，不验证 mil
        result = parse_centroid_csv(csv_text)
        self.assertEqual(result.placements[0].refdes, "U1")
        self.assertAlmostEqual(result.placements[0].x_mm, 1000)

    def test_mil_header_converts(self) -> None:
        csv_text = (
            "Ref,Value,Package,Mid X (mil),Mid Y (mil),Rot\n"
            "R1,1k,0402,100,200,0\n"
        )
        result = parse_centroid_csv(csv_text)
        self.assertAlmostEqual(result.placements[0].x_mm, 2.54, places=3)
        self.assertAlmostEqual(result.placements[0].y_mm, 5.08, places=3)

    def test_export_round_trip(self) -> None:
        product = build_demo_product()
        components = build_demo_components()
        text = export_centroid_csv(product, components)
        result = parse_centroid_csv(text)
        self.assertEqual(len(result.placements), len(product.placements))
        self.assertEqual(result.placements[0].refdes, product.placements[0].refdes)

    def test_missing_required_columns(self) -> None:
        with self.assertRaises(ImportError_):
            parse_centroid_csv("Name,Value\nR1,1k\n")

    def test_empty_file(self) -> None:
        with self.assertRaises(ImportError_):
            parse_centroid_csv("")


if __name__ == "__main__":
    unittest.main()
