from __future__ import annotations

import unittest

from midpnp.core.demo import build_demo_feeders
from midpnp.core.machine.simulator import SimulatorBackend
from midpnp.core.models import MachineLimits
from midpnp.core.protocol import MachineError


class SimulatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.feeders = build_demo_feeders()
        self.events = []
        self.sim = SimulatorBackend(
            feeders=self.feeders,
            limits=MachineLimits(),
            speed_factor=30.0,
            on_event=lambda event, data: self.events.append((event, data)),
        )

    def test_connect_and_status(self) -> None:
        status = self.sim.connect()
        self.assertEqual(status["state"], "ready")
        self.assertTrue(self.sim.connected)
        self.sim.disconnect()
        self.assertFalse(self.sim.connected)

    def test_home_and_jog(self) -> None:
        self.sim.connect()
        self.sim.command("jog", dx=10, dy=20, dz=0, speed=300)
        status = self.sim.command("status")
        self.assertAlmostEqual(status["x"], 10, places=2)
        self.assertAlmostEqual(status["y"], 20, places=2)
        self.sim.command("home")
        status = self.sim.command("status")
        self.assertAlmostEqual(status["x"], 0)
        self.assertAlmostEqual(status["y"], 0)

    def test_pick_feed_place(self) -> None:
        self.sim.connect()
        feeder = self.feeders[0]
        before = feeder.remaining
        self.sim.command("move", x=feeder.pick_x_mm, y=feeder.pick_y_mm, z=0)
        result = self.sim.command("pick", slot=feeder.slot, nozzle="N1")
        self.assertTrue(result["picked"])
        self.sim.command("feed", slot=feeder.slot)
        self.assertEqual(feeder.remaining, before - 1)
        self.sim.command("move", x=150, y=180, z=10)
        placed = self.sim.command("place", x=150, y=180, rotation=90)
        self.assertTrue(placed["placed"])
        self.assertEqual(self.sim.command("status")["placed"], 1)

    def test_out_of_travel_rejected(self) -> None:
        self.sim.connect()
        with self.assertRaises(MachineError):
            self.sim.command("move", x=9999, y=0, z=0)

    def test_estop_blocks_motion_until_reset(self) -> None:
        self.sim.connect()
        self.sim.command("estop")
        with self.assertRaises(MachineError):
            self.sim.command("jog", dx=1)
        self.sim.command("clear_fault")
        self.sim.command("jog", dx=1)
        self.assertEqual(self.sim.command("status")["state"], "ready")

    def test_not_connected(self) -> None:
        with self.assertRaises(MachineError):
            self.sim.command("status")


if __name__ == "__main__":
    unittest.main()
