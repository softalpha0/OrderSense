from __future__ import annotations
import os, threading, time, random
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from .config import settings
from .weex_client import WeexClient, WeexCredentials
from .ai_log_queue import AiLogQueue
from .state import store
from .execution.policy import choose_execution
from .execution.types import MarketSnapshot

load_dotenv()

app = FastAPI(title="OrderSense Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

creds = WeexCredentials(
    api_key=settings.weex_api_key,
    secret_key=settings.weex_secret_key,
    passphrase=settings.weex_passphrase,
)
weex = WeexClient(creds, settings.weex_base_url)
aiq = AiLogQueue(weex, db_path="ai_logs.sqlite", flush_interval_s=2.0)

_bot_thread: threading.Thread | None = None
_stop_flag = threading.Event()

def log_ai(stage: str, input_obj: dict, output_obj: dict, explanation: str, order_id: int | None = None):
    payload = {
        "stage": stage,
        "model": settings.model_name,
        "input": input_obj,
        "output": output_obj,
        "explanation": explanation[:1000],
        "orderId": order_id,
    }
    aiq.enqueue(payload)

def demo_market_snapshot() -> MarketSnapshot:
    mid = 60000 + random.uniform(-150, 150)
    spread = random.uniform(2, 15)
    vol_1m = random.uniform(0.0005, 0.006)
    liquidity_score = random.uniform(0.2, 0.9)
    return MarketSnapshot(mid=mid, spread=spread, vol_1m=vol_1m, liquidity_score=liquidity_score)

def bot_loop():

    while not _stop_flag.is_set():
        snap = demo_market_snapshot()

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
            "snapshot": {"mid": snap.mid, "spread": snap.spread, "vol_1m": snap.vol_1m, "liq": snap.liquidity_score},
        })
        with store.lock:
            store.state.metrics["decisions"] += 1

        log_ai(
            stage="Decision Making",
            input_obj={"symbol": store.state.symbol, "side": side, "target_size": target_size, "snapshot": snap.__dict__},
            output_obj={"execution": decision.__dict__},
            explanation=decision.reason,
        )

        fake_order_id = int(time.time() * 1000) % 10_000_000
        store.add_event({
            "type": "order",
            "orderId": fake_order_id,
            "symbol": store.state.symbol,
            "side": side,
            "style": decision.style,
            "price": decision.price,
            "size": decision.size,
            "status": "placed(simulated)",
        })
        with store.lock:
            store.state.metrics["orders"] += 1

        log_ai(
            stage="Order Placement",
            input_obj={"requested": decision.__dict__},
            output_obj={"orderId": fake_order_id, "status": "placed(simulated)"},
            explanation="Order placed (simulated in MVP). Replace with WEEX place order call.",
            order_id=fake_order_id,
        )

        time.sleep(3)

@app.get("/health")
def health():
    return {"ok": True}

@app.get("/api/status")
def status():
    with store.lock:
        return {"running": store.state.running, "started_at": store.state.started_at, "symbol": store.state.symbol}

@app.get("/api/metrics")
def metrics():
    with store.lock:
        return store.state.metrics

@app.get("/api/events")
def events():
    with store.lock:
        return store.state.events[:50]

@app.post("/api/start")
def start():
    global _bot_thread
    with store.lock:
        if store.state.running:
            return {"running": True}
        store.state.running = True
        store.state.started_at = time.time()
    _stop_flag.clear()
    _bot_thread = threading.Thread(target=bot_loop, daemon=True)
    _bot_thread.start()
    store.add_event({"type": "system", "msg": "Bot started"})
    return {"running": True}

@app.post("/api/stop")
def stop():
    with store.lock:
        store.state.running = False
    _stop_flag.set()
    store.add_event({"type": "system", "msg": "Bot stopped"})
    return {"running": False}

@app.websocket("/ws")
async def ws(websocket: WebSocket):
    await websocket.accept()
    last_sent = 0
    try:
        while True:
            await asyncio_sleep(0.5)
            with store.lock:
                
                payload = {"metrics": store.state.metrics, "events": store.state.events[:25]}
            await websocket.send_json(payload)
            last_sent += 1
    except Exception:
        pass

async def asyncio_sleep(sec: float):
    import asyncio
    await asyncio.sleep(sec)