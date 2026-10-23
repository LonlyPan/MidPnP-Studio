"""SQLite 持久化层。

单文件数据库便于备份；所有写入通过进程内可重入锁串行化，
连接允许跨线程使用（生产线程只通过主线程信号落库）。
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import date, datetime
from pathlib import Path
from typing import Any

from .demo import build_demo_components, build_demo_feeders, build_demo_product, build_demo_runs
from .models import Component, Feeder, LogEntry, Product, RunRecord, new_id, now_iso


class Storage:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._closed = False
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._migrate()

    def _migrate(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS components (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                package TEXT NOT NULL DEFAULT '',
                payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS feeders (
                id TEXT PRIMARY KEY,
                slot INTEGER NOT NULL UNIQUE,
                component_id TEXT NOT NULL,
                payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS products (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                revision TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL,
                payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY,
                product_id TEXT NOT NULL,
                product_name TEXT NOT NULL,
                started_at TEXT NOT NULL,
                finished_at TEXT NOT NULL,
                status TEXT NOT NULL,
                total INTEGER NOT NULL DEFAULT 0,
                placed INTEGER NOT NULL DEFAULT 0,
                failed INTEGER NOT NULL DEFAULT 0,
                duration_s REAL NOT NULL DEFAULT 0,
                payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                level TEXT NOT NULL,
                source TEXT NOT NULL,
                message TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_logs_ts ON logs(timestamp DESC);
            CREATE INDEX IF NOT EXISTS idx_runs_started ON runs(started_at DESC);
            """
        )
        self._conn.commit()

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._conn.close()

    # ---------------- meta / demo ----------------

    def count_products(self) -> int:
        with self._lock:
            row = self._conn.execute("SELECT COUNT(*) AS n FROM products").fetchone()
        return int(row["n"])

    def has_demo_data(self) -> bool:
        return self.get_meta("demo_seeded") == "1"

    def seed_demo(self, force: bool = False) -> None:
        with self._lock:
            if not force and self.count_products() > 0:
                return
            if force:
                self._conn.execute("DELETE FROM runs")
                self._conn.execute("DELETE FROM feeders")
                self._conn.execute("DELETE FROM products")
                self._conn.execute("DELETE FROM components")
            for component in build_demo_components():
                self.save_component(component)
            for feeder in build_demo_feeders():
                self.save_feeder(feeder)
            self.save_product(build_demo_product())
            for run in build_demo_runs():
                self.save_run(run)
            self.set_meta("demo_seeded", "1")
            self._conn.commit()

    def get_meta(self, key: str, default: str = "") -> str:
        with self._lock:
            row = self._conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return str(row["value"]) if row else default

    def set_meta(self, key: str, value: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO meta(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
            self._conn.commit()

    # ---------------- components ----------------

    def list_components(self) -> list[Component]:
        with self._lock:
            rows = self._conn.execute("SELECT payload FROM components ORDER BY name COLLATE NOCASE").fetchall()
        return [Component.from_dict(json.loads(row["payload"])) for row in rows]

    def get_component(self, component_id: str) -> Component | None:
        with self._lock:
            row = self._conn.execute("SELECT payload FROM components WHERE id = ?", (component_id,)).fetchone()
        return Component.from_dict(json.loads(row["payload"])) if row else None

    def save_component(self, component: Component) -> None:
        payload = json.dumps(component.to_dict(), ensure_ascii=False)
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO components(id, name, package, payload) VALUES(?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET name=excluded.name, package=excluded.package, payload=excluded.payload
                """,
                (component.id, component.name, component.package, payload),
            )
            self._conn.commit()

    def delete_component(self, component_id: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM components WHERE id = ?", (component_id,))
            self._conn.commit()

    def component_usage(self, component_id: str) -> tuple[int, int]:
        """返回 (供料器数量, 产品贴装点数量)。"""
        with self._lock:
            feeders = self._conn.execute(
                "SELECT COUNT(*) AS n FROM feeders WHERE component_id = ?", (component_id,)
            ).fetchone()["n"]
            products = self._conn.execute("SELECT payload FROM products").fetchall()
        placements = 0
        for row in products:
            data = json.loads(row["payload"])
            placements += sum(1 for p in data.get("placements", []) if p.get("component_id") == component_id)
        return int(feeders), placements

    # ---------------- feeders ----------------

    def list_feeders(self) -> list[Feeder]:
        with self._lock:
            rows = self._conn.execute("SELECT payload FROM feeders ORDER BY slot").fetchall()
        return [Feeder.from_dict(json.loads(row["payload"])) for row in rows]

    def get_feeder(self, feeder_id: str) -> Feeder | None:
        with self._lock:
            row = self._conn.execute("SELECT payload FROM feeders WHERE id = ?", (feeder_id,)).fetchone()
        return Feeder.from_dict(json.loads(row["payload"])) if row else None

    def save_feeder(self, feeder: Feeder) -> None:
        payload = json.dumps(feeder.to_dict(), ensure_ascii=False)
        with self._lock:
            try:
                self._conn.execute(
                    """
                    INSERT INTO feeders(id, slot, component_id, payload) VALUES(?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET slot=excluded.slot, component_id=excluded.component_id, payload=excluded.payload
                    """,
                    (feeder.id, feeder.slot, feeder.component_id, payload),
                )
                self._conn.commit()
            except sqlite3.IntegrityError as exc:
                self._conn.rollback()
                raise ValueError(f"槽位 {feeder.slot:02d} 已被其他供料器占用") from exc

    def delete_feeder(self, feeder_id: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM feeders WHERE id = ?", (feeder_id,))
            self._conn.commit()

    # ---------------- products ----------------

    def list_products(self) -> list[Product]:
        with self._lock:
            rows = self._conn.execute("SELECT payload FROM products ORDER BY updated_at DESC").fetchall()
        return [Product.from_dict(json.loads(row["payload"])) for row in rows]

    def get_product(self, product_id: str) -> Product | None:
        with self._lock:
            row = self._conn.execute("SELECT payload FROM products WHERE id = ?", (product_id,)).fetchone()
        return Product.from_dict(json.loads(row["payload"])) if row else None

    def save_product(self, product: Product) -> None:
        product.updated_at = now_iso()
        payload = json.dumps(product.to_dict(), ensure_ascii=False)
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO products(id, name, revision, updated_at, payload) VALUES(?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name, revision=excluded.revision,
                    updated_at=excluded.updated_at, payload=excluded.payload
                """,
                (product.id, product.name, product.revision, product.updated_at, payload),
            )
            self._conn.commit()

    def delete_product(self, product_id: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM products WHERE id = ?", (product_id,))
            self._conn.commit()

    def duplicate_product(self, product_id: str, new_name: str | None = None) -> Product:
        source = self.get_product(product_id)
        if source is None:
            raise ValueError("产品不存在")
        clone = Product.from_dict(source.to_dict())
        clone.id = new_id("PRD-")
        clone.name = new_name or f"{source.name} 副本"
        clone.updated_at = now_iso()
        self.save_product(clone)
        return clone

    # ---------------- runs ----------------

    def save_run(self, run: RunRecord) -> None:
        payload = json.dumps(run.to_dict(), ensure_ascii=False)
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO runs(id, product_id, product_name, started_at, finished_at, status, total, placed, failed, duration_s, payload)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    finished_at=excluded.finished_at, status=excluded.status,
                    total=excluded.total, placed=excluded.placed, failed=excluded.failed,
                    duration_s=excluded.duration_s, payload=excluded.payload
                """,
                (
                    run.id,
                    run.product_id,
                    run.product_name,
                    run.started_at,
                    run.finished_at,
                    run.status,
                    run.total,
                    run.placed,
                    run.failed,
                    run.duration_s,
                    payload,
                ),
            )
            self._conn.commit()

    def recent_runs(self, limit: int = 20) -> list[RunRecord]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT payload FROM runs ORDER BY started_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [RunRecord.from_dict(json.loads(row["payload"])) for row in rows]

    def today_summary(self) -> dict[str, float]:
        today = date.today().isoformat()
        with self._lock:
            rows = self._conn.execute(
                "SELECT payload FROM runs WHERE started_at LIKE ?", (f"{today}%",)
            ).fetchall()
        runs = [RunRecord.from_dict(json.loads(row["payload"])) for row in rows]
        placed = sum(r.placed for r in runs)
        failed = sum(r.failed for r in runs)
        duration = sum(r.duration_s for r in runs)
        total_attempts = placed + failed
        return {
            "runs": float(len(runs)),
            "placed": float(placed),
            "failed": float(failed),
            "yield": (placed / total_attempts * 100) if total_attempts else 0.0,
            "duration_s": duration,
            "cph": (placed / (duration / 3600)) if duration > 0 else 0.0,
        }

    # ---------------- logs ----------------

    def add_log(self, level: str, source: str, message: str) -> LogEntry:
        timestamp = datetime.now().isoformat(timespec="seconds")
        with self._lock:
            cursor = self._conn.execute(
                "INSERT INTO logs(timestamp, level, source, message) VALUES(?, ?, ?, ?)",
                (timestamp, level.upper(), source, message),
            )
            log_id = int(cursor.lastrowid)
            count = self._conn.execute("SELECT COUNT(*) AS n FROM logs").fetchone()["n"]
            if count > 5000:
                self._conn.execute(
                    "DELETE FROM logs WHERE id <= (SELECT id FROM logs ORDER BY id DESC LIMIT 1 OFFSET 4500)"
                )
            self._conn.commit()
        return LogEntry(log_id, timestamp, level.upper(), source, message)

    def list_logs(self, limit: int = 500, level: str = "", search: str = "") -> list[LogEntry]:
        clauses: list[str] = []
        params: list[Any] = []
        if level and level.upper() != "全部":
            clauses.append("level = ?")
            params.append(level.upper())
        if search:
            clauses.append("(message LIKE ? OR source LIKE ?)")
            params.extend([f"%{search}%", f"%{search}%"])
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        params.append(limit)
        with self._lock:
            rows = self._conn.execute(
                f"SELECT id, timestamp, level, source, message FROM logs {where} ORDER BY id DESC LIMIT ?",
                params,
            ).fetchall()
        return [
            LogEntry(int(r["id"]), str(r["timestamp"]), str(r["level"]), str(r["source"]), str(r["message"]))
            for r in rows
        ]

    def clear_logs(self) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM logs")
            self._conn.commit()

    def backup_to(self, destination: str | Path) -> Path:
        target = Path(destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            backup = sqlite3.connect(str(target))
            try:
                self._conn.backup(backup)
            finally:
                backup.close()
        return target
