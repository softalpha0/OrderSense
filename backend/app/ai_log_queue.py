from __future__ import annotations
import json, queue, sqlite3, threading, time, uuid
from typing import Any, Dict, Optional

def _ms() -> int:
    return int(time.time() * 1000)

def _json(obj: Any) -> str:
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)

class AiLogQueue:
    def __init__(self, weex_client, db_path: str = "ai_logs.sqlite", flush_interval_s: float = 2.0, max_batch: int = 25):
        self.weex = weex_client
        self.db_path = db_path
        self.flush_interval_s = flush_interval_s
        self.max_batch = max_batch

        self._stop = threading.Event()
        self._poke = queue.Queue(maxsize=1)
        self._init_db()
        self._t = threading.Thread(target=self._run, daemon=True)
        self._t.start()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("""
            CREATE TABLE IF NOT EXISTS ai_log_events (
                id TEXT PRIMARY KEY,
                created_ms INTEGER NOT NULL,
                next_try_ms INTEGER NOT NULL,
                tries INTEGER NOT NULL,
                payload_json TEXT NOT NULL,
                last_error TEXT
            );""")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_next_try ON ai_log_events(next_try_ms);")
            conn.commit()
        finally:
            conn.close()

    def enqueue(self, payload: Dict[str, Any]) -> str:
        eid = str(uuid.uuid4())
        now = _ms()
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                "INSERT INTO ai_log_events (id, created_ms, next_try_ms, tries, payload_json, last_error) VALUES (?,?,?,?,?,?)",
                (eid, now, now, 0, _json(payload), None),
            )
            conn.commit()
        finally:
            conn.close()

        try:
            self._poke.put_nowait(1)
        except queue.Full:
            pass
        return eid

    def stop(self):
        self._stop.set()
        try:
            self._poke.put_nowait(1)
        except queue.Full:
            pass
        self._t.join(timeout=5)

    def _run(self):
        while not self._stop.is_set():
            self._flush_due()
            try:
                self._poke.get(timeout=self.flush_interval_s)
            except queue.Empty:
                pass

    def _flush_due(self):
        conn = sqlite3.connect(self.db_path)
        try:
            now = _ms()
            rows = conn.execute(
                "SELECT id, tries, payload_json FROM ai_log_events WHERE next_try_ms <= ? ORDER BY next_try_ms LIMIT ?",
                (now, self.max_batch),
            ).fetchall()

            for eid, tries, payload_json in rows:
                payload = json.loads(payload_json)
                try:
                    resp = self.weex.upload_ai_log(
                        stage=payload["stage"],
                        model=payload["model"],
                        input_obj=payload["input"],
                        output_obj=payload["output"],
                        explanation=payload["explanation"],
                        order_id=payload.get("orderId"),
                    )
                    code = str(resp.get("code", ""))  # accept empty too
                    if code and code != "00000":
                        raise RuntimeError(f"WEEX non-success: {resp}")
                    conn.execute("DELETE FROM ai_log_events WHERE id=?", (eid,))
                    conn.commit()
                except Exception as e:
                    new_tries = tries + 1
                    backoff_s = min(60, 2 ** min(new_tries, 6))
                    next_try = _ms() + int(backoff_s * 1000)
                    conn.execute(
                        "UPDATE ai_log_events SET tries=?, next_try_ms=?, last_error=? WHERE id=?",
                        (new_tries, next_try, str(e)[:500], eid),
                    )
                    conn.commit()
        finally:
            conn.close()