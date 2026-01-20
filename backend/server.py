import json
import os
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

from dotenv import load_dotenv

from app.weex_client import WeexClient
from app.order_status import poll_until_filled, to_fill_event

load_dotenv(".env")


@dataclass
class StateStore:
    events: List[Dict[str, Any]] = field(default_factory=list)
    last_fill: Dict[str, Any] = field(default_factory=dict)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def add_event(self, e: Dict[str, Any]) -> None:
        with self.lock:
            self.events.insert(0, e)
            self.events = self.events[:500]

    def get_events(self) -> List[Dict[str, Any]]:
        with self.lock:
            return list(self.events)

    def set_last_fill(self, e: Dict[str, Any]) -> None:
        with self.lock:
            self.last_fill = dict(e)

    def get_last_fill(self) -> Dict[str, Any]:
        with self.lock:
            return dict(self.last_fill)


store = StateStore()

WEEX_BASE_URL = os.getenv("WEEX_BASE_URL", "https://api-contract.weex.com")
SYMBOL = os.getenv("SYMBOL", "cmt_btcusdt")
DRY_RUN = os.getenv("DRY_RUN", "1").strip() in ("1", "true", "True", "yes", "YES")
ORDER_SIZE = os.getenv("ORDER_SIZE", "0.0001").strip()  # contracts size for WEEX contract
DEPTH_LIMIT = int(os.getenv("DEPTH_LIMIT", "15"))

# creds object must have attributes
class Creds:
    def __init__(self, api_key: str, secret_key: str, passphrase: str):
        self.api_key = api_key
        self.secret_key = secret_key
        self.passphrase = passphrase

creds = Creds(
    os.getenv("WEEX_API_KEY", ""),
    os.getenv("WEEX_SECRET_KEY", ""),
    os.getenv("WEEX_PASSPHRASE", ""),
)

weex = WeexClient(creds, WEEX_BASE_URL)

_running = False
_thread: Optional[threading.Thread] = None


def _read_frontend_file(name: str) -> bytes:
    p = Path(__file__).resolve().parent.parent / "frontend" / name
    try:
        return p.read_bytes()
    except Exception:
        return b"OrderSense backend is running."


def real_market_snapshot(symbol: str) -> Dict[str, Any]:
    d = weex.request("GET", "/capi/v2/market/depth", params={"symbol": symbol, "limit": DEPTH_LIMIT})
    data = d.get("data", d)
    asks = data.get("asks", [])
    bids = data.get("bids", [])
    if not asks or not bids:
        raise RuntimeError(f"Depth empty for {symbol}: {d}")
    best_ask = float(asks[0][0])
    best_bid = float(bids[0][0])
    mid = (best_ask + best_bid) / 2.0
    spread = max(0.0, best_ask - best_bid)
    topn = 5
    ask_qty = sum(float(x[1]) for x in asks[:topn])
    bid_qty = sum(float(x[1]) for x in bids[:topn])
    liq = max(0.0, min(1.0, (ask_qty + bid_qty) / 100000.0))
    return {"mid": mid, "spread": spread, "liq": liq, "source": "weex"}


def bot_loop() -> None:
    global _running
    store.add_event({"type": "system", "msg": "Bot started", "ts": time.time()})

    while _running:
        symbol = SYMBOL

        # snapshot
        try:
            snap = real_market_snapshot(symbol)
        except Exception as e:
            store.add_event({"type": "error", "msg": f"depth_failed: {e}", "ts": time.time()})
            snap = {"mid": 60000.0, "spread": 10.0, "liq": 0.5, "source": "fallback"}

        # toy decision
        side = "buy" if int(time.time()) % 2 == 0 else "sell"
        style = "aggressive_limit"
        price = round(snap["mid"] + (0.05 if side == "buy" else -0.05), 3)

        store.add_event({
            "type": "decision",
            "symbol": symbol,
            "side": side,
            "style": style,
            "price": price,
            "size": float(ORDER_SIZE),
            "reason": "Live microstructure snapshot",
            "snapshot": snap,
            "ts": time.time()
        })

        # place order
        client_oid = f"os_{int(time.time()*1000)}"
        if DRY_RUN or not (creds.api_key and creds.secret_key and creds.passphrase):
            store.add_event({
                "type": "order",
                "orderId": int(time.time() * 1000) % 10_000_000,
                "status": "placed(simulated)",
                "client_oid": client_oid,
                "note": "DRY_RUN=1 or missing API keys",
                "ts": time.time(),
            })
            time.sleep(3)
            continue

        try:
            type_ = "1" if side == "buy" else "2"   # open long / open short
            resp = weex.place_order(
                symbol=symbol,
                client_oid=client_oid,
                size=str(ORDER_SIZE),
                type_=type_,
                order_type="3",     # IOC
                match_price="1",    # market
                price="0",
            )

            order_id = None
            if isinstance(resp, dict):
                order_id = resp.get("order_id") or resp.get("orderId")
            if not order_id:
                store.add_event({"type": "error", "msg": f"order_failed: unexpected response {resp}", "ts": time.time()})
                time.sleep(3)
                continue

            store.add_event({
                "type": "order",
                "orderId": order_id,
                "status": "placed",
                "client_oid": client_oid,
                "note": "LIVE order sent to WEEX",
                "ts": time.time(),
            })

            # poll fill + store last fill
            try:
                detail = poll_until_filled(weex, str(order_id), timeout_s=20.0, interval_s=1.0)
                if detail:
                    fill_event = to_fill_event(detail)
                    store.set_last_fill(fill_event)
                    store.add_event(fill_event)
            except Exception as e:
                store.add_event({"type": "error", "msg": f"fill_poll_failed: {e}", "ts": time.time()})

        except Exception as e:
            store.add_event({"type": "error", "msg": f"order_failed: {e}", "client_oid": client_oid, "ts": time.time()})

        time.sleep(3)


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, obj: Any) -> None:
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        path = urlparse(self.path).path

        if path == "/":
            body = _read_frontend_file("index.html")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == "/demo":
            body = _read_frontend_file("demo.html")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == "/vision":
            body = _read_frontend_file("vision.html")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == "/api/status":
            self._send(200, {"running": _running, "symbol": SYMBOL, "dry_run": DRY_RUN})
            return

        if path == "/api/metrics":
            # lightweight metrics placeholder
            self._send(200, {"symbol": SYMBOL, "spread": None, "liq": None, "updated_at": time.time()})
            return

        if path == "/api/events":
            self._send(200, store.get_events())
            return

        if path == "/api/last_fill":
            self._send(200, store.get_last_fill())
            return

        self.send_response(404)
        self.end_headers()

    def do_POST(self) -> None:
        global _running, _thread
        path = urlparse(self.path).path

        if path == "/api/start":
            if not _running:
                _running = True
                _thread = threading.Thread(target=bot_loop, daemon=True)
                _thread.start()
            self._send(200, {"running": True})
            return

        if path == "/api/stop":
            _running = False
            self._send(200, {"running": False})
            return

        self.send_response(404)
        self.end_headers()


def main() -> None:
    port = int(os.getenv("PORT", "8000"))
    httpd = HTTPServer(("0.0.0.0", port), Handler)
    print(f"OrderSense backend running on http://localhost:{port}")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
