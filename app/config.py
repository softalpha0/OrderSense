from dataclasses import dataclass
import os

@dataclass
class Settings:
    weex_api_key: str = os.getenv("WEEX_API_KEY", "")
    weex_secret_key: str = os.getenv("WEEX_SECRET_KEY", "")
    weex_passphrase: str = os.getenv("WEEX_PASSPHRASE", "")
    weex_base_url: str = os.getenv("WEEX_BASE_URL", "https://api-contract.weex.com")
    model_name: str = os.getenv("MODEL_NAME", "ordersense-v1")

settings = Settings()
