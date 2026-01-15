from dataclasses import dataclass
import os

def _bool_env(name: str, default: bool = False) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "y", "on")

@dataclass
class Settings:
    weex_api_key: str = os.getenv("WEEX_API_KEY", "")
    weex_secret_key: str = os.getenv("WEEX_SECRET_KEY", "")
    weex_passphrase: str = os.getenv("WEEX_PASSPHRASE", "")
    weex_base_url: str = os.getenv("WEEX_BASE_URL", "https://api-contract.weex.com")
    model_name: str = os.getenv("MODEL_NAME", "ordersense-v1")

    dry_run: bool = _bool_env("DRY_RUN", True)
    symbol: str = os.getenv("SYMBOL", "cmt_btcusdt")
    order_size: str = os.getenv("ORDER_SIZE", "0.001")

settings = Settings()
