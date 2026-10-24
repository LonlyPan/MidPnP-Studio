from __future__ import annotations

import math
import tempfile
import unittest
from pathlib import Path

from midpnp.core.models import Component, Fiducial, Product
from midpnp.core.profiles import ProfileLibrary
from midpnp.core.vision import (
    Affine,
    AlignmentError,
    BoardAlignment,
    Point2,
    SimulatedCamera,
    align_board,
    align_part,
    build_pipeline,
    check_alignment,
    derive_affine,
    measure_fiducials_by_capture,
)


def make_product() -> Product:
    return Product(
        id="PRD-TEST",
        name="测试板",
        board_width_mm=160.0,
        board_height_mm=100.0,
        board_origin_x_mm=120.0,
        board_origin_y_mm=125.0,
        fiducials=[
            Fiducial("FID1", 6.0, 6.0, 1.2),
            Fiducial("FID2", 154.0, 6.0, 1.2),
            Fiducial("FID3", 80.0, 94.0, 1.2),
        ],
    )


class AffineTests(unittest.TestCase):
    def test_derive_affine_from_three_points(self) -> None:
        expected = [Point2(0, 0), Point2(100, 0), Point2(0, 50)]
        transform = Affine(a=0.999, b=-0.01, c=0.01, d=1.001, e=10.0, f=20.0)
        measured = [transform.apply_point(point) for point in expected]
        solved, residuals = derive_affine(expected, measured)
        self.assertAlmostEqual(solved.e, 10.0, places=4)
        self.assertAlmostEqual(solved.f, 20.0, places=4)
        self.assertLess(max(residuals), 1e-6)

    def test_two_points_gives_similarity(self) -> None:
        expected = [Point2(0, 0), Point2(100, 0)]
        measured = [Point2(10, 20), Point2(10, 120)]  # 逆时针 90°
        solved, _ = derive_affine(expected, measured)
        self.assertAlmostEqual(solved.rotation_deg, 90.0, places=6)
        self.assertAlmostEqual(solved.a, 0.0, places=6)
        self.assertAlmostEqual(solved.apply(10, 0).y, 30.0, places=6)

    def test_inverse(self) -> None:
        transform = Affine(a=1.2, b=0.1, c=-0.05, d=0.9, e=3.0, f=-4.0)
        point = Point2(12.0, 8.0)
        restored = transform.inverse().apply_point(transform.apply_point(point))
        self.assertAlmostEqual(restored.x, point.x, places=6)
        self.assertAlmostEqual(restored.y, point.y, places=6)

    def test_degenerate_points_raise(self) -> None:
        with self.assertRaises(AlignmentError):
            derive_affine([Point2(0, 0), Point2(0, 0)], [Point2(1, 1), Point2(2, 2)])

    def test_alignment_check_detects_bad_scale(self) -> None:
        transform = Affine(a=1.5, d=1.0, e=120.0, f=125.0)
        problems = check_alignment(transform, [0.0], expected_translation=Point2(120.0, 125.0))
        self.assertTrue(any("缩放" in problem for problem in problems))

    def test_alignment_check_uses_relative_translation(self) -> None:
        transform = Affine(e=120.4, f=124.8)
        problems = check_alignment(transform, [0.0], expected_translation=Point2(120.0, 125.0))
        self.assertEqual(problems, [])


class SimulatedCameraTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tempdir = tempfile.TemporaryDirectory()
        cls.library = ProfileLibrary(Path(cls.tempdir.name))
        cls.profile = cls.library.get("sim-desktop")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tempdir.cleanup()

    def test_capture_shape(self) -> None:
        camera = SimulatedCamera(self.profile.camera("CAM-TOP"))
        # 对准第一个基准点，画面里应出现高亮圆形标靶
        frame = camera.capture_board(Point2(126, 131), product=make_product())
        self.assertEqual(frame.image.shape, (720, 1280))
        self.assertGreater(frame.image.max(), 0.5)
        self.assertLessEqual(frame.image.max(), 1.0)

    def test_fiducial_alignment_recovers_transform(self) -> None:
        camera = SimulatedCamera(self.profile.camera("CAM-TOP"))
        product = make_product()
        angle = math.radians(0.6)
        true_transform = Affine(
            a=math.cos(angle),
            b=-math.sin(angle),
            c=math.sin(angle),
            d=math.cos(angle),
            e=120.4,
            f=124.75,
        )
        true_alignment = BoardAlignment(transform=true_transform)

        def capture(center: Point2):
            return camera.capture_board(center, product=product, alignment=true_alignment)

        measurements = measure_fiducials_by_capture(
            product, capture, build_pipeline("fiducial-simple"), search_radius_mm=10.0
        )
        self.assertTrue(all(item.found for item in measurements))
        result = align_board(measurements)
        self.assertTrue(result.ok, msg="; ".join(result.problems))
        solved = result.alignment.transform
        self.assertAlmostEqual(solved.rotation_deg, 0.6, places=2)
        self.assertAlmostEqual(solved.e, 120.4, places=1)
        self.assertAlmostEqual(solved.f, 124.75, places=1)
        corner = solved.apply(160.0, 100.0)
        expected = true_transform.apply(160.0, 100.0)
        self.assertLess(math.hypot(corner.x - expected.x, corner.y - expected.y), 0.05)

    def test_bottom_vision_recovers_offsets(self) -> None:
        camera = SimulatedCamera(self.profile.camera("CAM-BOTTOM"))
        component = Component(
            id="CMP-1", name="R0603", package="0603", length_mm=1.6, width_mm=0.8, height_mm=0.8
        )
        frame = camera.capture_part(component, offset_mm=(0.12, -0.08), angle_deg=1.2)
        alignment = align_part(frame, build_pipeline("bottom-default"), component=component)
        self.assertTrue(alignment.passed, msg=alignment.message)
        self.assertAlmostEqual(alignment.dx_mm, 0.12, delta=0.03)
        self.assertAlmostEqual(alignment.dy_mm, -0.08, delta=0.03)
        self.assertAlmostEqual(alignment.theta_deg, 1.2, delta=0.35)

    def test_bottom_vision_rejects_missing_part(self) -> None:
        camera = SimulatedCamera(self.profile.camera("CAM-BOTTOM"))
        frame = camera.capture_part(None)
        alignment = align_part(frame, build_pipeline("bottom-default"))
        self.assertFalse(alignment.passed)
        self.assertIn("未识别", alignment.message)


class PipelineTests(unittest.TestCase):
    def test_serialization_round_trip(self) -> None:
        pipeline = build_pipeline("fiducial-default")
        data = pipeline.to_dict()
        clone = build_pipeline(data)
        self.assertEqual(len(clone), len(pipeline))
        self.assertEqual(clone.stages[0].NAME, "ConvertColor")

    def test_unknown_stage_raises(self) -> None:
        with self.assertRaises(ValueError):
            build_pipeline([{"name": "NoSuchStage"}])

    def test_unknown_pipeline_raises(self) -> None:
        with self.assertRaises(ValueError):
            build_pipeline("no-such-pipeline")


if __name__ == "__main__":
    unittest.main()
