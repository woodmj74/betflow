# src/betflow/analysis/structure_metrics.py

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass(frozen=True)
class RunnerLadder:
    selection_id: int
    runner_name: str
    sort_priority: int
    best_back: Optional[float]
    best_lay: Optional[float]


@dataclass(frozen=True)
class MarketStructureMetrics:
    runner_count: int
    priced_runners: int
    runners_under_10: int
    top_cluster_total_implied: Optional[float]
    best_back_prices_sorted: List[float]


def _best_price(price_size_list: Optional[List[Dict]], side: str) -> Optional[float]:
    """
    Betfair MarketBook runner.ex.availableToBack / availableToLay list elements are dict-like:
      {"price": 12.0, "size": 3.45}
    """
    if not price_size_list:
        return None
    # They are already best-first, but be defensive
    prices = [ps.get("price") for ps in price_size_list if isinstance(ps, dict) and ps.get("price")]
    if not prices:
        return None
    return float(min(prices) if side == "LAY" else max(prices)) if False else float(prices[0])


def build_runner_ladders(
    market_catalogue: Dict,
    market_book: Dict,
) -> List[RunnerLadder]:
    """
    Produces per-runner best back/lay using MarketBook, and runner name/sortPriority using MarketCatalogue.
    Expects dicts shaped like Betfair JSON-RPC results.
    """
    # Catalogue runners by selectionId
    cat_runners = {}
    for r in market_catalogue.get("runners", []) or []:
        sid = r.get("selectionId")
        if sid is None:
            continue
        cat_runners[int(sid)] = {
            "runner_name": r.get("runnerName") or f"sel:{sid}",
            "sort_priority": int(r.get("sortPriority") or 0),
        }

    ladders: List[RunnerLadder] = []
    for r in market_book.get("runners", []) or []:
        sid = r.get("selectionId")
        if sid is None:
            continue
        sid_i = int(sid)
        ex = r.get("ex", {}) or {}
        best_back = _best_price(ex.get("availableToBack"), "BACK")
        best_lay = _best_price(ex.get("availableToLay"), "LAY")

        meta = cat_runners.get(sid_i, {"runner_name": f"sel:{sid_i}", "sort_priority": 0})
        ladders.append(
            RunnerLadder(
                selection_id=sid_i,
                runner_name=str(meta["runner_name"]),
                sort_priority=int(meta["sort_priority"]),
                best_back=best_back,
                best_lay=best_lay,
            )
        )

    ladders.sort(key=lambda x: x.sort_priority)
    return ladders


def compute_market_structure_metrics(
    ladders: List[RunnerLadder],
    *,
    under_odds_threshold: float = 10.0,
    top_cluster_count: int = 4,
) -> MarketStructureMetrics:
    """
    Computes market-level metrics from runner ladders:
      - runners_under_10: count of runners with best_back < under_odds_threshold
      - top_cluster_total_implied: sum(1/price) for lowest-priced N runners (using best_back)
    """
    runner_count = len(ladders)

    priced = [r for r in ladders if r.best_back and r.best_back > 1.0]
    priced_runners = len(priced)

    best_backs = sorted([float(r.best_back) for r in priced if r.best_back is not None])
    runners_under_10 = sum(1 for p in best_backs if p < float(under_odds_threshold))

    top_cluster_total_implied: Optional[float] = None
    if len(best_backs) >= max(1, top_cluster_count):
        top_prices = best_backs[:top_cluster_count]
        # implied probability approximation from best back
        top_cluster_total_implied = sum(1.0 / p for p in top_prices if p and p > 0)

    return MarketStructureMetrics(
        runner_count=runner_count,
        priced_runners=priced_runners,
        runners_under_10=runners_under_10,
        top_cluster_total_implied=top_cluster_total_implied,
        best_back_prices_sorted=best_backs,
    )
