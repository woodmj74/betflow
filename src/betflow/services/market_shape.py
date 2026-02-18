from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from betflow.betfair.client import BetfairClient


@dataclass(frozen=True)
class MarketShape:
    market_id: str
    field_size: int
    total_matched: float
    fav_price: Optional[float]
    fav_selection_id: Optional[int]


def get_market_shape(client: BetfairClient, market_id: str) -> MarketShape:
    """
    Minimal 'shape' snapshot of a market:
      - field_size: count of ACTIVE runners
      - total_matched: market total matched (£)
      - fav_price: best available back price for shortest-priced ACTIVE runner
    """

    books = client.list_market_book(
        market_ids=[market_id],
        price_projection={
            "priceData": ["EX_BEST_OFFERS"],
            "exBestOffersOverrides": {"bestPricesDepth": 1},
            "virtualise": False,
            "rolloverStakes": False,
        },
    )

    if not books:
        raise RuntimeError(f"No market book returned for {market_id}")

    b = books[0]
    total_matched = float(b.get("totalMatched") or 0.0)

    runners = b.get("runners") or []
    active_runners = [r for r in runners if r.get("status") == "ACTIVE"]
    field_size = len(active_runners)

    fav_price: Optional[float] = None
    fav_selection_id: Optional[int] = None

    for r in active_runners:
        ex = r.get("ex") or {}
        atb = ex.get("availableToBack") or []
        if not atb:
            continue
        price = atb[0].get("price")
        if price is None:
            continue

        price_f = float(price)
        if fav_price is None or price_f < fav_price:
            fav_price = price_f
            fav_selection_id = r.get("selectionId")

    return MarketShape(
        market_id=market_id,
        field_size=field_size,
        total_matched=total_matched,
        fav_price=fav_price,
        fav_selection_id=fav_selection_id,
    )

@dataclass(frozen=True)
class ShapeFilter:
    min_runners: int = 8
    max_runners: int = 14
    min_total_matched: float = 2000.0
    fav_min: float = 2.0
    fav_max: float = 8.0


def passes_shape_filters(shape: MarketShape, f: ShapeFilter) -> tuple[bool, list[str]]:
    reasons: list[str] = []

    if shape.field_size < f.min_runners or shape.field_size > f.max_runners:
        reasons.append(f"field_size {shape.field_size} not in [{f.min_runners},{f.max_runners}]")

    if shape.total_matched < f.min_total_matched:
        reasons.append(f"total_matched {shape.total_matched:.2f} < {f.min_total_matched:.2f}")

    if shape.fav_price is None:
        reasons.append("fav_price missing")
    else:
        if shape.fav_price < f.fav_min or shape.fav_price > f.fav_max:
            reasons.append(f"fav_price {shape.fav_price} not in [{f.fav_min},{f.fav_max}]")

    return (len(reasons) == 0), reasons
