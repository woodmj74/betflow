from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from betflow.betfair.client import BetfairClient
from betflow.services.ticks import ticks_between
from betflow.services.filter_config import RunnerTargeting
from betflow.services.filter_config import SanityChecks


@dataclass(frozen=True)
class RunnerLadder:
    selection_id: int
    number: Optional[int]
    name: Optional[str]
    best_back: Optional[float]
    best_lay: Optional[float]
    spread_ticks: Optional[int]
    rank: int

@dataclass(frozen=True)
class MarketSanity:
    ok: bool
    reasons: List[str]
    runners_under_10: int
    runners_under_cluster: int



def build_runner_ladder(client: BetfairClient, market: dict) -> List[RunnerLadder]:
    market_id = market["marketId"]

    # Map selectionId -> metadata from catalogue
    runner_meta = {}
    for r in market.get("runners", []):
        runner_meta[int(r["selectionId"])] = {
            "name": r.get("runnerName"),
            "number": r.get("sortPriority"),
        }

    books = client.list_market_book(
        market_ids=[market_id],
        price_projection={
            "priceData": ["EX_BEST_OFFERS"],
            "exBestOffersOverrides": {"bestPricesDepth": 1},
        },
    )

    if not books:
        return []

    b = books[0]
    runners = b.get("runners") or []

    ladder: List[RunnerLadder] = []

    for r in runners:
        if r.get("status") != "ACTIVE":
            continue

        sel_id = int(r["selectionId"])
        meta = runner_meta.get(sel_id, {})

        ex = r.get("ex") or {}
        atb = ex.get("availableToBack") or []
        atl = ex.get("availableToLay") or []

        best_back = float(atb[0]["price"]) if atb else None
        best_lay = float(atl[0]["price"]) if atl else None

        spread_ticks = None
        if best_back is not None and best_lay is not None:
            spread_ticks = ticks_between(best_back, best_lay)

        ladder.append(
            RunnerLadder(
                selection_id=sel_id,
                number=meta.get("number"),
                name=meta.get("name"),
                best_back=best_back,
                best_lay=best_lay,
                spread_ticks=spread_ticks,
                rank=0,
            )
        )

    # Sort by best_back (shortest first)
    ladder.sort(key=lambda rr: rr.best_back if rr.best_back is not None else 9999.0)

    # Assign rank
    ranked: List[RunnerLadder] = []
    for i, rr in enumerate(ladder, start=1):
        ranked.append(
            RunnerLadder(
                selection_id=rr.selection_id,
                number=rr.number,
                name=rr.name,
                best_back=rr.best_back,
                best_lay=rr.best_lay,
                spread_ticks=rr.spread_ticks,
                rank=i,
            )
        )

    return ranked


def select_target_runner(
    ladder: List[RunnerLadder],
    cfg: RunnerTargeting,
) -> Tuple[Optional[RunnerLadder], List[str]]:

    reasons: List[str] = []

    field_size = len(ladder)
    if field_size == 0:
        return None, ["no active runners"]

    target_rank = cfg.large_field_rank if field_size >= cfg.field_threshold else cfg.smaller_field_rank

    if field_size < target_rank:
        return None, [f"field_size {field_size} too small for rank {target_rank}"]

    candidate = ladder[target_rank - 1]

    if candidate.best_back is None:
        reasons.append("no back price")

    if candidate.best_back and candidate.best_back > cfg.max_odds:
        reasons.append(f"odds {candidate.best_back} > max {cfg.max_odds}")

    if candidate.best_back and not (
        cfg.target_odds_min <= candidate.best_back <= cfg.target_odds_max
    ):
        reasons.append(
            f"odds {candidate.best_back} not in ideal band [{cfg.target_odds_min},{cfg.target_odds_max}]"
        )

    if candidate.spread_ticks is None:
        reasons.append("no spread")
    elif candidate.spread_ticks > cfg.max_back_lay_spread_ticks:
        reasons.append(
            f"spread {candidate.spread_ticks} > {cfg.max_back_lay_spread_ticks}"
        )

    return (candidate if not reasons else None), reasons

def check_market_sanity(ladder: List[RunnerLadder], cfg: SanityChecks) -> MarketSanity:
    reasons: List[str] = []

    # Count runners with a back price under 10
    runners_under_10 = sum(1 for r in ladder if r.best_back is not None and r.best_back < 10)

    if runners_under_10 > cfg.max_runners_under_10:
        reasons.append(f"{runners_under_10} runners under 10 (max {cfg.max_runners_under_10})")

    # “Cluster around 5s” signal (not a fail)
    runners_under_cluster = sum(
        1 for r in ladder if r.best_back is not None and r.best_back <= cfg.prefer_cluster_under
    )

    ok = len(reasons) == 0
    return MarketSanity(ok=ok, reasons=reasons, runners_under_10=runners_under_10, runners_under_cluster=runners_under_cluster)