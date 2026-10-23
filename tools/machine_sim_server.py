"""独立 TCP 机器模拟器，用于联调真实 TCP 适配器与第三方控制器。

用法：
    python tools/machine_sim_server.py --host 127.0.0.1 --port 5025

协议：UTF-8 JSON Lines，详见 docs/MACHINE_PROTOCOL.md。
"""

from __future__ import annotations

import argparse
import json
import socketserver
import sys
import threading
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from midpnp.core.demo import build_demo_feeders  # noqa: E402
from midpnp.core.machine.simulator import SimulatorBackend  # noqa: E402
from midpnp.core.models import MachineLimits  # noqa: E402
from midpnp.core.protocol import LineFramer, MachineError, ProtocolError, encode_message  # noqa: E402


class SimulatorHandler(socketserver.BaseRequestHandler):
    def setup(self) -> None:
        self.framer = LineFramer()
        self.send_lock = threading.Lock()
        self.backend = SimulatorBackend(
            feeders=build_demo_feeders(),
            limits=MachineLimits(),
            speed_factor=self.server.speed_factor,  # type: ignore[attr-defined]
            on_event=self._emit_event,
        )
        self.backend.connect()

    def _emit_event(self, event: str, data: dict[str, Any]) -> None:
        self._send({"event": event, "data": data})

    def _send(self, message: dict[str, Any]) -> None:
        with self.send_lock:
            self.request.sendall(encode_message(message))

    def handle(self) -> None:
        peer = f"{self.client_address[0]}:{self.client_address[1]}"
        print(f"[server] client connected {peer}", flush=True)
        try:
            while True:
                data = self.request.recv(65536)
                if not data:
                    break
                for message in self.framer.feed(data):
                    self._dispatch(message)
        except (ConnectionResetError, BrokenPipeError, ProtocolError) as exc:
            print(f"[server] client error {peer}: {exc}", flush=True)
        finally:
            try:
                self.backend.disconnect()
            except Exception:
                pass
            print(f"[server] client disconnected {peer}", flush=True)

    def _dispatch(self, message: dict[str, Any]) -> None:
        request_id = message.get("id")
        command = str(message.get("cmd", ""))
        args = message.get("args") if isinstance(message.get("args"), dict) else {}
        if request_id is None:
            return
        try:
            if command == "disconnect":
                self._send({"id": request_id, "ok": True, "result": {}})
                return
            result = self.backend.command(command, **args)
            self._send({"id": request_id, "ok": True, "result": result})
        except (MachineError, TypeError, ValueError) as exc:
            self._send({"id": request_id, "ok": False, "error": str(exc)})
        except Exception as exc:  # noqa: BLE001
            self._send({"id": request_id, "ok": False, "error": f"server exception: {exc}"})


class ThreadedServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main() -> int:
    parser = argparse.ArgumentParser(description="MidPnP TCP machine simulator")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5025)
    parser.add_argument("--speed", type=float, default=5.0, help="simulation speed factor")
    args = parser.parse_args()
    server = ThreadedServer((args.host, args.port), SimulatorHandler)
    server.speed_factor = max(1.0, args.speed)  # type: ignore[attr-defined]
    print(f"[server] MidPnP simulator listening on {args.host}:{args.port}", flush=True)
    print(json.dumps({"protocol": "jsonl", "commands": ["home", "move", "jog", "pick", "place", "feed", "status"]}), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[server] stopped", flush=True)
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
