from .types import MarketSnapshot, ExecDecision, Side

def choose_execution(snapshot: MarketSnapshot, side: Side, target_size: float) -> ExecDecision:
    tight_spread = snapshot.spread / max(snapshot.mid, 1e-9) < 0.0005
    calm = snapshot.vol_1m < 0.002
    big = target_size > 1.0 and snapshot.liquidity_score < 0.5

    if big:
        return ExecDecision(style="slice", price=None, size=target_size, reason="Large size vs liquidity: slicing to reduce impact")
    if tight_spread and calm:
        
        px = snapshot.mid - snapshot.spread * 0.25 if side == "buy" else snapshot.mid + snapshot.spread * 0.25
        return ExecDecision(style="post_only_limit", price=px, size=target_size, reason="Tight spread + calm: post-only to capture maker")

    px = snapshot.mid + snapshot.spread * 0.49 if side == "buy" else snapshot.mid - snapshot.spread * 0.49
    return ExecDecision(style="aggressive_limit", price=px, size=target_size, reason="Volatile or wide spread: prioritize fill with aggressive limit")