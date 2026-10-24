from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from midpnp.core.demo import build_demo_components, build_demo_feeders, build_demo_product
from midpnp.core.models import Component, MachineLimits
from midpnp.core.packages import PackageLibrary
from midpnp.core.planner import build_job, nozzle_for_component, validate_job
from midpnp.core.profiles import ProfileLibrary
from midpnp.core.vision import Affine, BoardAlignment


class PlannerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.product = build_demo_product()
        self.components = build_demo_components()
        self.feeders = build_demo_feeders()
        self.limits = MachineLimits()

    def test_demo_product_is_valid(self) -> None:
        issues = validate_job(self.product, self.components, self.feeders, self.limits)
        self.assertEqual([i for i in issues if i.is_error], [])
        self.assertTrue(any(i.code == "FEEDER_LOW" for i in issues))

    def test_build_job_contains_every_active_placement(self) -> None:
        plan, issues = build_job(self.product, self.components, self.feeders, self.limits)
        self.assertFalse([i for i in issues if i.is_error])
        self.assertEqual(plan.total, 35)
        self.assertEqual(len({step.refdes for step in plan.steps}), 35)
        self.assertEqual([step.index for step in plan.steps], list(range(1, 36)))
        self.assertGreater(plan.estimated_cycle_s, 0)
        for step in plan.steps:
            self.assertTrue(0 <= step.place.x <= self.limits.travel_x_mm)
            self.assertTrue(0 <= step.place.y <= self.limits.travel_y_mm)

    def test_missing_component_is_an_error(self) -> None:
        self.product.placements[0].component_id = "DOES-NOT-EXIST"
        issues = validate_job(self.product, self.components, self.feeders, self.limits)
        self.assertTrue(any(i.code == "MISSING_COMPONENT" for i in issues))

    def test_out_of_travel_is_an_error(self) -> None:
        self.product.board_origin_x_mm = 400
        issues = validate_job(self.product, self.components, self.feeders, self.limits)
        self.assertTrue(any(i.code == "OUT_OF_TRAVEL" for i in issues))

    def test_empty_feeder_blocks_job(self) -> None:
        self.feeders[0].remaining = 0
        plan, issues = build_job(self.product, self.components, self.feeders, self.limits)
        self.assertEqual(plan.total, 0)
        self.assertTrue(any(i.code == "FEEDER_EMPTY" for i in issues))

    def test_optimization_changes_order(self) -> None:
        original = [p.refdes for p in self.product.placements]
        plan, _ = build_job(self.product, self.components, self.feeders, self.limits, optimize=True)
        self.assertNotEqual(original, [step.refdes for step in plan.steps])

    def test_board_alignment_shifts_placements(self) -> None:
        base_plan, _ = build_job(self.product, self.components, self.feeders, self.limits)
        alignment = BoardAlignment(
            transform=Affine(
                e=self.product.board_origin_x_mm + 0.5,
                f=self.product.board_origin_y_mm - 0.25,
            )
        )
        shifted_plan, issues = build_job(
            self.product, self.components, self.feeders, self.limits, alignment=alignment
        )
        self.assertFalse([i for i in issues if i.is_error])
        base = {step.refdes: step for step in base_plan.steps}
        for step in shifted_plan.steps:
            self.assertAlmostEqual(step.place.x - base[step.refdes].place.x, 0.5, places=6)
            self.assertAlmostEqual(step.place.y - base[step.refdes].place.y, -0.25, places=6)

    def test_nozzle_selection_from_profile(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            profile = ProfileLibrary(Path(directory)).get("sim-desktop")
            packages = PackageLibrary.load(Path(__file__).resolve().parents[1] / "midpnp" / "data" / "packages.json")
            component = Component(
                id="CMP-IC",
                name="SOIC8 芯片",
                package="SOIC-8",
                package_id="PKG-SOIC-8",
                length_mm=4.9,
                width_mm=3.9,
                height_mm=1.5,
                nozzle="N1",
            )
            nozzle = nozzle_for_component(
                component, profile, {package.id: package for package in packages.list()}
            )
            self.assertEqual(nozzle, "N3")

    def test_limits_min_bound_is_honoured(self) -> None:
        limits = MachineLimits(travel_x_mm=420, travel_y_mm=360, min_x_mm=100, min_y_mm=100)
        issues = validate_job(self.product, self.components, self.feeders, limits)
        # 演示板原点 120,125，仍在 [100, 420] 内
        self.assertFalse([i for i in issues if i.code == "OUT_OF_TRAVEL"])
        self.product.board_origin_x_mm = 10
        issues = validate_job(self.product, self.components, self.feeders, limits)
        self.assertTrue(any(i.code == "OUT_OF_TRAVEL" for i in issues))


if __name__ == "__main__":
    unittest.main()
