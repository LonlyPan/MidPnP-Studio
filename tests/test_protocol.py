from __future__ import annotations

import unittest

from midpnp.core.protocol import (
    LineFramer,
    MachineError,
    ProtocolError,
    RequestTracker,
    encode_message,
)


class ProtocolTests(unittest.TestCase):
    def test_encode_is_newline_delimited_json(self) -> None:
        payload = encode_message({"id": 1, "cmd": "status", "args": {}})
        self.assertTrue(payload.endswith(b"\n"))
        self.assertIn(b'"cmd":"status"', payload)

    def test_framer_handles_partial_and_multiple_frames(self) -> None:
        framer = LineFramer()
        data = encode_message({"id": 1, "ok": True}) + encode_message({"event": "state", "data": {"state": "ready"}})
        self.assertEqual(framer.feed(data[:7]), [])
        messages = framer.feed(data[7:])
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]["id"], 1)
        self.assertEqual(messages[1]["event"], "state")

    def test_framer_ignores_blank_lines(self) -> None:
        framer = LineFramer()
        self.assertEqual(framer.feed(b"\n\n"), [])
        self.assertEqual(framer.feed(b'{"id":1}\n'), [{"id": 1}])

    def test_invalid_json_raises(self) -> None:
        framer = LineFramer()
        with self.assertRaises(ProtocolError):
            framer.feed(b"{not json}\n")

    def test_response_error_raises_machine_error(self) -> None:
        with self.assertRaises(MachineError):
            RequestTracker.validate_response({"id": 2, "ok": False, "error": "vacuum lost"}, 2)

    def test_response_id_mismatch(self) -> None:
        with self.assertRaises(ProtocolError):
            RequestTracker.validate_response({"id": 3, "ok": True}, 2)

    def test_events_are_dispatched(self) -> None:
        seen = []
        tracker = RequestTracker(lambda event, data: seen.append((event, data)))
        self.assertTrue(tracker.consume({"event": "position", "data": {"x": 1}}))
        self.assertFalse(tracker.consume({"id": 1, "ok": True}))
        self.assertEqual(seen, [("position", {"x": 1})])


if __name__ == "__main__":
    unittest.main()
