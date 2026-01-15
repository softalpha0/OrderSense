import json
import os
import random
from pathlib import Path
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

from dotenv import load_dotenv

from app.config import settings
from app.state import store
from app.weex_client import WeexClient, WeexCredentials
from app.ai_log_queue import AiLogQueue
from app.execution.policy import choose_execution
from app.execution.types import MarketSnapshot


load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))

store.state.symbol = settings.symbol

creds = WeexCredentials(
    api_key=settings.weex_api_key,
    secret_key=settings.weex_secret_key,
    passphrase=settings.weex_passphrase,
)
weex = WeexClient(creds, settings.weex_base_url)
aiq = AiLogQueue(weex, db_path="ai_logs.sqlite", flush_interval_s=2.0)

_stop = threading.Event()
_bot_thread = None

def log_ai(stage, input_obj, output_obj, explanation, order_id=None):
    aiq.enqueue({
        "stage": stage,
        "model": settings.model_name,
        "input": input_obj,
        "output": output_obj,
        "explanation": (explanation or "")[:1000],
        "orderId": order_id,
    })

def real_market_snapshot(symbol: str) -> MarketSnapshot:
    d = weex.get_depth(symbol=symbol, limit=15)
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

    vol_1m = 0.002  
    return MarketSnapshot(mid=mid, spread=spread, vol_1m=vol_1m, liquidity_score=liq)

def fallback_snapshot() -> MarketSnapshot:
    mid = 60000 + random.uniform(-200, 200)
    spread = random.uniform(2, 15)
    vol_1m = random.uniform(0.0005, 0.006)
    liquidity_score = random.uniform(0.2, 0.9)
    return MarketSnapshot(mid=mid, spread=spread, vol_1m=vol_1m, liquidity_score=liquidity_score)

def bot_loop():
    while not _stop.is_set():
        try:
            snap = real_market_snapshot(store.state.symbol)
            src = "weex"
        except Exception as e:
            store.add_event({"type": "error", "msg": f"depth_failed: {e}"})
            snap = fallback_snapshot()
            src = "fallback"

        side = "buy" if int(time.time()) % 2 == 0 else "sell"
        target_size = 0.5
        decision = choose_execution(snap, side, target_size)

        store.add_event({
            "type": "decision",
            "symbol": store.state.symbol,
            "side": side,
            "style": decision.style,
            "price": decision.price,
            "size": decision.size,
            "reason": decision.reason,
            "snapshot": {"mid": snap.mid, "spread": snap.spread, "liq": snap.liquidity_score, "source": src},
        })
        with store.lock:
            store.state.metrics["decisions"] += 1

        log_ai(
            "Decision Making",
            {"symbol": store.state.symbol, "side": side, "target_size": target_size, "snapshot": snap.__dict__, "source": src},
            {"execution": decision.__dict__},
            decision.reason,
        )

        order_id = None
        client_oid = f"os_{int(time.time()*1000)}"

        try:
            if not settings.dry_run and src == "weex":
                
                if decision.style == "post_only_limit":
                    order_type = "1"  
                elif decision.style == "aggressive_limit":
                    order_type = "3"  
                else:
                    order_type = "0"

                type_ = "1" if side == "buy" else "2"  
                match_price = "0"  
                price = f"{decision.price:.2f}"

                resp = weex.place_order(
                    symbol=store.state.symbol,
                    client_oid=client_oid,
                    size=settings.order_size,
                    type_=type_,
                    order_type=order_type,
                    match_price=match_price,
                    price=price,
                )
                data = resp.get("data", resp)
                order_id = data.get("order_id") or data.get("orderId")
                store.add_event({"type": "order", "orderId": order_id, "status": "placed(real)", "client_oid": client_oid})
            else:
                order_id = int(time.time() * 1000) % 10_000_000
                store.add_event({"type": "order", "orderId": order_id, "status": "placed(simulated)", "client_oid": client_oid, "note": "DRY_RUN or fallback market data"})

            with store.lock:
                store.state.metrics["orders"] += 1

            oid_int = None
            if isinstance(order_id, int):
                oid_int = order_id
            elif isinstance(order_id, str) and order_id.isdigit():
                oid_int = int(order_id)

            log_ai(
                "Order Placement",
                {"requested": decision.__dict__, "client_oid": client_oid, "dry_run": settings.dry_run, "source": src},
                {"orderId": order_id, "status": "placed"},
                "Order placement executed.",
                order_id=oid_int,
            )

        except Exception as e:
            store.add_event({"type": "error", "msg": f"order_failed: {e}", "client_oid": client_oid})

        time.sleep(3)

def _read_frontend_file(name: str) -> bytes:
    p = Path(__file__).resolve().parent.parent / "frontend" / name
    try:
        return p.read_bytes()
    except Exception:
        return b"OrderSense backend is running."

class Handler(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
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
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == "/health":
            return self._send(200, {"ok": True})
        if path == "/api/status":
            with store.lock:
                return self._send(200, {"running": store.state.running, "symbol": store.state.symbol, "started_at": store.state.started_at, "dry_run": settings.dry_run})
        if path == "/api/metrics":
            with store.lock:
                return self._send(200, store.state.metrics)
        if path == "/api/events":
            with store.lock:
                return self._send(200, store.state.events[:50])
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        global _bot_thread
        path = urlparse(self.path).path

        if path == "/api/start":
            with store.lock:
                if store.state.running:
                    return self._send(200, {"running": True})
                store.state.running = True
                store.state.started_at = time.time()

            _stop.clear()
            _bot_thread = threading.Thread(target=bot_loop, daemon=True)
            _bot_thread.start()
            store.add_event({"type": "system", "msg": "Bot started"})
            return self._send(200, {"running": True})

        if path == "/api/stop":
            with store.lock:
                store.state.running = False
            _stop.set()
            store.add_event({"type": "system", "msg": "Bot stopped"})
            return self._send(200, {"running": False})

        return self._send(404, {"error": "not found"})

def main():
    port = int(os.getenv("PORT", "8000"))
    httpd = HTTPServer(("0.0.0.0", port), Handler)
    print(f"OrderSense backend running on http://localhost:{port}")
    httpd.serve_forever()

if __name__ == "__main__":
    main()
