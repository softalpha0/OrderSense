from dataclasses import dataclass
from typing import Optional, Literal

Side = Literal["buy", "sell"]
ExecStyle = Literal["post_only_limit", "aggressive_limit", "slice"]

@dataclass
class MarketSnapshot:
    mid: float
    spread: float
    vol_1m: float
    liquidity_score: float

@dataclass
class ExecDecision:
    style: ExecStyle
    price: Optional[float]
    size: float
    reason: str
