from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from midpnp.core.models import Component, Feeder, RunRecord, now_iso
from midpnp.core.storage import Storage


class StorageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db = Path(self.tempdir.name) / "test.db"
        self.storage = Storage(self.db)
        self.storage.seed_demo()

    def tearDown(self) -> None:
        self.storage.close()
        self.tempdir.cleanup()

    def test_demo_seed(self) -> None:
        self.assertEqual(len(self.storage.list_components()), 7)
        self.assertEqual(len(self.storage.list_feeders()), 7)
        self.assertEqual(len(self.storage.list_products()), 1)
        self.assertEqual(len(self.storage.recent_runs()), 2)
        self.assertTrue(self.storage.has_demo_data())

    def test_component_round_trip(self) -> None:
        component = Component(id="CMP-TEST", name="测试电阻", package="0402", length_mm=1.0)
        self.storage.save_component(component)
        loaded = self.storage.get_component("CMP-TEST")
        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual(loaded.name, "测试电阻")
        self.assertEqual(loaded.package, "0402")

    def test_duplicate_slot_is_rejected(self) -> None:
        feeders = self.storage.list_feeders()
        duplicate = Feeder(id="FDR-X", slot=feeders[0].slot, component_id=feeders[0].component_id)
        with self.assertRaises(ValueError):
            self.storage.save_feeder(duplicate)

    def test_product_duplicate(self) -> None:
        source = self.storage.list_products()[0]
        clone = self.storage.duplicate_product(source.id, "克隆产品")
        self.assertNotEqual(source.id, clone.id)
        self.assertEqual(clone.name, "克隆产品")
        self.assertEqual(len(clone.placements), len(source.placements))

    def test_run_and_summary(self) -> None:
        run = RunRecord(
            id="RUN-TEST",
            product_id="demo-mxled8",
            product_name="演示",
            started_at=now_iso(),
            finished_at=now_iso(),
            total=10,
            placed=9,
            failed=1,
            skipped=0,
            status="Completed",
            duration_s=60,
        )
        self.storage.save_run(run)
        summary = self.storage.today_summary()
        self.assertGreaterEqual(summary["placed"], 9)
        self.assertGreater(summary["yield"], 0)

    def test_logs(self) -> None:
        entry = self.storage.add_log("INFO", "TEST", "测试消息")
        logs = self.storage.list_logs(10, "INFO", "测试")
        self.assertTrue(any(item.id == entry.id for item in logs))
        self.storage.clear_logs()
        self.assertEqual(self.storage.list_logs(10), [])

    def test_meta(self) -> None:
        self.storage.set_meta("foo", "bar")
        self.assertEqual(self.storage.get_meta("foo"), "bar")
        self.assertEqual(self.storage.get_meta("missing", "default"), "default")


if __name__ == "__main__":
    unittest.main()
