from __future__ import annotations

import unittest

from midpnp.core.demo import build_demo_components, build_demo_feeders, build_demo_product
from midpnp.core.models import MachineLimits
from midpnp.core.planner import build_job, validate_job


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


if __name__ == "__main__":
    unittest.main()
