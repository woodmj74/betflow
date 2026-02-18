from __future__ import annotations

def tick_size(price: float) -> float:
    # Betfair tick ladder
    if price < 2: return 0.01
    if price < 3: return 0.02
    if price < 4: return 0.05
    if price < 6: return 0.1
    if price < 10: return 0.2
    if price < 20: return 0.5
    if price < 30: return 1.0
    if price < 50: return 2.0
    if price < 100: return 5.0
    return 10.0

def ticks_between(back: float, lay: float) -> int:
    """
    Approx ticks between best back and best lay.
    Uses tick size at the back price (good enough for gating spreads).
    """
    if back <= 0 or lay <= 0 or lay < back:
        return 0
    ts = tick_size(back)
    return int(round((lay - back) / ts))
