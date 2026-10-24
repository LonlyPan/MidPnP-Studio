from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from midpnp.core.machine.gcode import GcodeBackend
from midpnp.core.profiles import ProfileLibrary


class RecordingBackend(GcodeBackend):
    """把 G-code 记录下来，不真正发到网络/串口。"""

    def __init__(self, profile) -> None:
        super().__init__(profile)
        self.sent: list[str] = []

    def _send(self, line: str) -> str:  # type: ignore[override]
        self.sent.append(line)
        return "ok"


class GcodeBackendTests(unittest.TestCase):
    def setUp(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            library = ProfileLibrary(Path(directory))
            self.profile = library.get("gcode-3axis")
        self.backend = RecordingBackend(self.profile)

    def test_move_renders_axis_and_feedrate(self) -> None:
        self.backend.command("move", x=12.345, y=6.5, z=3.25, speed=100)
        self.assertEqual(self.backend.sent, ["G1 X12.345 Y6.500 Z3.250 F6000"])

    def test_pick_renders_slot_and_dwell(self) -> None:
        self.backend.command("pick", slot=7, nozzle="N1")
        self.assertEqual(len(self.backend.sent), 2)
        self.assertEqual(self.backend.sent[0], "M42 P7 S1")
        self.assertTrue(self.backend.sent[1].startswith("G4 P0."))

    def test_place_dwell_then_blow(self) -> None:
        self.backend.command("place", x=1.0, y=2.0, rotation=90.0, slot=7)
        self.assertEqual(len(self.backend.sent), 2)
        self.assertTrue(self.backend.sent[0].startswith("G4 P0."))
        self.assertEqual(self.backend.sent[1], "M42 P7 S0")

    def test_nozzle_index_mapping(self) -> None:
        self.backend.command("nozzle", nozzle="N2")
        self.assertEqual(self.backend.sent, ["T1"])

    def test_vacuum_state(self) -> None:
        self.backend.command("vacuum", on=True)
        self.assertEqual(self.backend.sent, ["M42 P0 S1"])
        self.backend.command("vacuum", on=False)
        self.assertEqual(self.backend.sent[-1], "M42 P0 S0")

    def test_estop_and_clear_fault(self) -> None:
        self.backend.command("estop")
        self.backend.command("clear_fault")
        self.assertEqual(self.backend.sent, ["M112", "M999"])

    def test_unknown_command_is_skipped(self) -> None:
        result = self.backend.command("not_a_real_command")
        self.assertTrue(result.get("skipped"))

    def test_null_variable_removes_segment(self) -> None:
        self.backend.commands["feed"] = "G4 P{unknown_variable}"
        self.backend.command("feed")
        self.assertEqual(self.backend.sent, ["G4 P"])

    def test_position_tracking(self) -> None:
        self.backend.command("move", x=10.0, y=20.0, z=5.0)
        self.assertEqual(self.backend._position, (10.0, 20.0, 5.0))


if __name__ == "__main__":
    unittest.main()
