from __future__ import annotations
import base64, hashlib, hmac, json, time
from dataclasses import dataclass
from typing import Any, Dict, Optional
from urllib.parse import urlencode
import requests

def _ms() -> int:
    return int(time.time() * 1000)

def _json(obj: Any) -> str:
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)

def _b64_hmac_sha256(secret: str, message: str) -> str:
    digest = hmac.new(secret.encode(), message.encode(), hashlib.sha256).digest()
    return base64.b64encode(digest).decode()

@dataclass(frozen=True)
class WeexCredentials:
    api_key: str
    secret_key: str
    passphrase: str

class WeexClient:
    def __init__(self, creds: WeexCredentials, base_url: str):
        self.creds = creds
        self.base_url = base_url.rstrip("/")
        self.s = requests.Session()

    def _sign(self, timestamp: str, method: str, path: str, query: str, body: str) -> str:
        # timestamp + METHOD + requestPath + (?query) + body
        msg = f"{timestamp}{method}{path}{query}{body}"
        return _b64_hmac_sha256(self.creds.secret_key, msg)

    def request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Dict[str, Any]] = None,
        timeout: float = 10.0,
    ) -> Dict[str, Any]:
        method = method.upper()
        query = ""
        if params:
            query = "?" + urlencode(params, doseq=True)

        body = ""
        data = None
        if method == "POST":
            json_body = json_body or {}
            body = _json(json_body)
            data = body

        ts = str(_ms())
        sign = self._sign(ts, method, path, query, body)

        headers = {
            "ACCESS-KEY": self.creds.api_key,
            "ACCESS-SIGN": sign,
            "ACCESS-PASSPHRASE": self.creds.passphrase,
            "ACCESS-TIMESTAMP": ts,
            "Content-Type": "application/json",
            "locale": "en-US",
        }

        url = f"{self.base_url}{path}{query}"
        resp = self.s.get(url, headers=headers, timeout=timeout) if method == "GET" else self.s.post(url, headers=headers, data=data, timeout=timeout)

        try:
            payload = resp.json()
        except Exception:
            raise RuntimeError(f"Non-JSON response (status={resp.status_code}): {resp.text[:500]}")

        if resp.status_code >= 400:
            raise RuntimeError(f"WEEX HTTP {resp.status_code}: {payload}")

        return payload

    def upload_ai_log(
        self,
        *,
        stage: str,
        model: str,
        input_obj: Dict[str, Any],
        output_obj: Dict[str, Any],
        explanation: str,
        order_id: Optional[int] = None,
        timeout: float = 10.0,
    ) -> Dict[str, Any]:
        explanation = (explanation or "")[:1000]
        body: Dict[str, Any] = {
            "orderId": order_id,
            "stage": stage,
            "model": model,
            "input": input_obj,
            "output": output_obj,
            "explanation": explanation,
        }
        return self.request("POST", "/capi/v2/order/uploadAiLog", json_body=body, timeout=timeout)

    def get_depth(self, symbol: str, limit: int = 15) -> Dict[str, Any]:
        # GET /capi/v2/market/depth
        return self.request("GET", "/capi/v2/market/depth", params={"symbol": symbol, "limit": limit}, timeout=3.0)

    def place_order(
        self,
        *,
        symbol: str,
        client_oid: str,
        size: str,
        type_: str,         # 1 open long, 2 open short, 3 close long, 4 close short
        order_type: str,    # 0 normal, 1 post-only, 2 FOK, 3 IOC
        match_price: str,   # 0 limit, 1 market
        price: str,
        presetTakeProfitPrice: str | None = None,
        presetStopLossPrice: str | None = None,
        marginMode: int | None = None,
    ) -> Dict[str, Any]:
        body: Dict[str, Any] = {
            "symbol": symbol,
            "client_oid": client_oid[:40],
            "size": size,
            "type": type_,
            "order_type": order_type,
            "match_price": match_price,
            "price": price,
        }
        if presetTakeProfitPrice is not None:
            body["presetTakeProfitPrice"] = presetTakeProfitPrice
        if presetStopLossPrice is not None:
            body["presetStopLossPrice"] = presetStopLossPrice
        if marginMode is not None:
            body["marginMode"] = marginMode

        return self.request("POST", "/capi/v2/order/placeOrder", json_body=body)
