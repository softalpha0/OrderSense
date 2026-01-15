from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List
import threading, time

@dataclass
class BotState:
    running: bool = False
    started_at: float | None = None
    symbol: str = "BTCUSDT"
    events: List[Dict[str, Any]] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=lambda: {
        "decisions": 0,
        "orders": 0,
        "maker_rate": 0.0,
        "avg_slippage_bps": 0.0,
    })

class StateStore:
    def __init__(self):
        self.state = BotState()
        self.lock = threading.Lock()

    def add_event(self, evt: Dict[str, Any]):
        with self.lock:
            evt["ts"] = evt.get("ts") or time.time()
            self.state.events.insert(0, evt)
            self.state.events = self.state.events[:200] 

store = StateStore()