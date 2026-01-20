import os, time, math
from types import SimpleNamespace
from dotenv import load_dotenv
from app.weex_client import WeexClient

def build_client():
    load_dotenv(".env")
    base_url = os.getenv("WEEX_BASE_URL", "https://api-contract.weex.com")
    creds = SimpleNamespace(
        api_key=os.getenv("WEEX_API_KEY"),
        secret_key=os.getenv("WEEX_SECRET_KEY"),
        passphrase=os.getenv("WEEX_PASSPHRASE"),
    )
    if not (creds.api_key and creds.secret_key and creds.passphrase):
        raise SystemExit("Missing WEEX_API_KEY / WEEX_SECRET_KEY / WEEX_PASSPHRASE")
    return WeexClient(creds, base_url)

def place_market_order(weex):
    symbol = os.getenv("SYMBOL", "cmt_btcusdt")
    depth_limit = int(os.getenv("DEPTH_LIMIT", "15"))
    notional_usdt = float(os.getenv("TEST_NOTIONAL_USDT", "10"))

    depth = weex.request("GET", "/capi/v2/market/depth", params={"symbol": symbol, "limit": depth_limit})
    data = depth.get("data", depth)
    asks = data.get("asks", [])
    bids = data.get("bids", [])
    if not asks or not bids:
        raise SystemExit(f"Depth empty/unexpected: {depth}")

    best_ask = float(asks[0][0])
    best_bid = float(bids[0][0])
    mid = (best_ask + best_bid) / 2.0

    # Step size for cmt_btcusdt is 0.0001, so round DOWN to 4 decimals.
    size = notional_usdt / mid
    size = math.floor(size / 0.0001) * 0.0001
    size = max(size, 0.0001)

    client_oid = f"os_test_{int(time.time()*1000)}"

    print("symbol:", symbol)
    print("limit:", depth_limit)
    print("best_bid:", best_bid, "best_ask:", best_ask, "mid:", mid)
    print("target notional:", notional_usdt, "USDT")
    print("computed size:", f"{size:.4f}")

    resp = weex.place_order(
        symbol=symbol,
        client_oid=client_oid,
        size=f"{size:.4f}",
        type_="1",          # open long
        order_type="0",     # normal
        match_price="1",    # market
        price="0",
    )
    return resp

def fetch_order_detail(weex, order_id: str):
    return weex.request("GET", "/capi/v2/order/detail", params={"orderId": order_id})

def main():
    weex = build_client()

    order_id = os.getenv("ORDER_ID", "").strip()
    if not order_id:
        placed = place_market_order(weex)
        order_id = str(placed.get("order_id") or placed.get("orderId") or placed.get("data", {}).get("order_id") or "")
        print("\nplace_order response:\n", placed)
        if not order_id:
            print("\nCould not parse order_id from response. Set ORDER_ID manually and rerun.")
            return

    print("\nChecking order:", order_id)

    # Poll a few times because fills can take a moment
    for i in range(6):
        detail = fetch_order_detail(weex, order_id)
        print(f"\norder detail attempt {i+1}:\n", detail)
        time.sleep(2)

if __name__ == "__main__":
    main()
