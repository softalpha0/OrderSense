import time
from typing import Any, Dict, Optional

def fetch_order_detail(weex, order_id: str) -> Dict[str, Any]:
    return weex.request("GET", "/capi/v2/order/detail", params={"orderId": str(order_id)})

def poll_until_filled(weex, order_id: str, *, timeout_s: float = 20.0, interval_s: float = 1.0) -> Optional[Dict[str, Any]]:
    deadline = time.time() + timeout_s
    last = None
    while time.time() < deadline:
        last = fetch_order_detail(weex, order_id)
        data = last.get("data", last) if isinstance(last, dict) else last
        if isinstance(data, dict):
            status = str(data.get("status", "")).lower()
            if status in ("filled", "full_fill", "complete"):
                return data
        time.sleep(interval_s)
    if isinstance(last, dict):
        data = last.get("data", last)
        return data if isinstance(data, dict) else None
    return None

def to_fill_event(detail: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "type": "fill",
        "order_id": detail.get("order_id") or detail.get("orderId"),
        "client_oid": detail.get("client_oid"),
        "symbol": detail.get("symbol"),
        "status": detail.get("status"),
        "side": detail.get("type"),  # open_long, open_short, close_long, close_short
        "filled_qty": detail.get("filled_qty"),
        "avg_price": detail.get("price_avg"),
        "fee": detail.get("fee"),
        "ts": time.time(),
    }
