from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from betflow.betfair.client import BetfairClient
from betflow.filter_config import StrategyConfig, load_filter_config


# -----------------------------
# Verbose printing
# -----------------------------

def vprint(verbose: bool, msg: str) -> None:
    if verbose:
        print(msg)


# -----------------------------
# Tick ladder (approx)
# -----------------------------

def ticks_between(a: float, b: float) -> Optional[int]:
    if a <= 1.0 or b <= 1.0:
        return None
    lo, hi = (a, b) if a <= b else (b, a)

    bands = [
        (1.01, 2.0, 0.01),
        (2.0, 3.0, 0.02),
        (3.0, 4.0, 0.05),
        (4.0, 6.0, 0.1),
        (6.0, 10.0, 0.2),
        (10.0, 20.0, 0.5),
        (20.0, 30.0, 1.0),
        (30.0, 50.0, 2.0),
        (50.0, 100.0, 5.0),
        (100.0, 1000.0, 10.0),
    ]

    ticks = 0
    p = lo
    while p < hi - 1e-9:
        step = None
        for x0, x1, inc in bands:
            if x0 <= p < x1:
                step = inc
                break
        if step is None:
            return None
        p = round(p + step, 10)
        ticks += 1
        if ticks > 5000:
            return None
    return ticks


# -----------------------------
# Price helpers
# -----------------------------

def best_price(side: str, ex: Dict[str, Any]) -> Optional[float]:
    key = "availableToBack" if side == "back" else "availableToLay"
    offers = ex.get(key) or []
    if not offers:
        return None
    p = offers[0].get("price")
    return float(p) if p else None


def runner_prices(runner_book: Dict[str, Any]) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    ex = runner_book.get("ex") or {}
    back = best_price("back", ex)
    lay = best_price("lay", ex)
    lpt = runner_book.get("lastPriceTraded")
    lpt = float(lpt) if lpt else None
    return back, lay, lpt


def implied_prob(price: float) -> float:
    return 1.0 / price


def uniform_probability(runner_count: int) -> float:
    return 1.0 / runner_count if runner_count > 0 else 0.0


# -----------------------------
# Market helpers
# -----------------------------

def count_under_odds(runners: List[Dict[str, Any]], threshold: float) -> int:
    """
    Compression check: how many runners have lastPriceTraded < threshold.
    """
    count = 0
    for r in runners:
        lpt = r.get("lastPriceTraded")
        if lpt and float(lpt) < float(threshold):
            count += 1
    return count


@dataclass
class MarketDecision:
    ok: bool
    reasons_ok: List[str]
    reasons_no: List[str]

    def add_ok(self, s: str) -> None:
        self.reasons_ok.append(s)

    def add_no(self, s: str) -> None:
        self.ok = False
        self.reasons_no.append(s)


def evaluate_market(
    cfg: StrategyConfig,
    market_cat: Dict[str, Any],
    market_book: Dict[str, Any],
) -> MarketDecision:
    d = MarketDecision(ok=True, reasons_ok=[], reasons_no=[])

    event = market_cat.get("event") or {}
    country = event.get("countryCode")
    runners_cat = market_cat.get("runners") or []
    runner_count = len(runners_cat)

    # Scope
    if not cfg.is_market_in_scope(country):
        d.add_no(f"Scope: OUT (country {country})")
    else:
        region = cfg.scope.region_for_country(country)
        d.add_ok(f"Scope: IN ({country} → {region.name if region else 'region?'})")

    # Field size
    ok_field, msg_field = cfg.field_size_ok(runner_count)
    if ok_field:
        d.add_ok(f"Field size: OK ({runner_count})")
    else:
        d.add_no(f"Field size: REJECT ({runner_count}) {msg_field}")

    # Liquidity
    total_matched = float(market_book.get("totalMatched") or 0.0)
    liq_min = cfg.market_liquidity_min(country)
    if liq_min is None:
        d.add_no("Liquidity: REJECT (no region liquidity_min rule)")
    elif total_matched < float(liq_min):
        d.add_no(f"Liquidity: REJECT ({total_matched:.0f} < {float(liq_min):.0f})")
    else:
        d.add_ok(f"Liquidity: OK ({total_matched:.0f} >= {float(liq_min):.0f})")

    # Compression
    comp = cfg.market.compression
    under_count = count_under_odds(market_book.get("runners") or [], comp.under_odds)
    if under_count > comp.max_count:
        d.add_no(f"Compression: REJECT ({under_count} runners < {comp.under_odds}, max {comp.max_count})")
    else:
        d.add_ok(f"Compression: OK ({under_count} runners < {comp.under_odds}, max {comp.max_count})")

    return d


# -----------------------------
# Ladder / candidate selection
# -----------------------------

@dataclass
class Candidate:
    selection_id: int
    cloth: int
    name: str
    back: Optional[float]
    lay: Optional[float]
    spread_ticks: Optional[int]
    rank: int
    score: float


def build_ladder(
    cfg: StrategyConfig,
    market_catalogue: Dict[str, Any],
    market_book: Dict[str, Any],
    verbose: bool,
) -> Tuple[List[Candidate], List[str]]:

    notes: List[str] = []

    runners_cat = market_catalogue.get("runners") or []
    runners_book = market_book.get("runners") or []

    if not runners_book:
        notes.append("No runners in marketBook")
        return [], notes

    # Map selectionId -> (name, cloth number)
    info: Dict[int, Tuple[str, Optional[int]]] = {}
    for r in runners_cat:
        sid = r.get("selectionId")
        if sid is None:
            continue
        name = r.get("runnerName", str(sid))
        cloth = r.get("sortPriority")  # Betfair "running number"
        info[int(sid)] = (name, int(cloth) if cloth is not None else None)

    # Rank runners by shortest price (favourite = 1)
    ranked: List[Tuple[int, float]] = []
    for rb in runners_book:
        sid = rb.get("selectionId")
        back, lay, lpt = runner_prices(rb)
        p = lpt or back or lay
        if sid and p:
            ranked.append((int(sid), float(p)))

    ranked.sort(key=lambda x: x[1])
    rank_by_id = {sid: idx + 1 for idx, (sid, _) in enumerate(ranked)}

    # Probability top cluster shape
    tc = cfg.probability.top_cluster
    if len(ranked) >= tc.count:
        top_prices = [p for _, p in ranked[:tc.count]]
        s = sum(implied_prob(p) for p in top_prices)
        if tc.min_total_implied <= s <= tc.max_total_implied:
            notes.append(f"Top cluster OK (sum={s:.3f} in {tc.min_total_implied}–{tc.max_total_implied})")
        else:
            notes.append(f"Top cluster REJECT (sum={s:.3f} not in {tc.min_total_implied}–{tc.max_total_implied})")
    else:
        notes.append(f"Top cluster insufficient data (need {tc.count}, have {len(ranked)})")

    # Candidates
    candidates: List[Candidate] = []
    pref = cfg.runner.preferred_odds
    lo_rank = cfg.runner.rank_buffer.min_rank
    hi_rank = cfg.runner.rank_buffer.max_rank

    for rb in runners_book:
        sid_raw = rb.get("selectionId")
        if sid_raw is None:
            continue
        sid = int(sid_raw)

        name, cloth = info.get(sid, (str(sid), None))
        back, lay, lpt = runner_prices(rb)

        # Candidate price preference
        price = back or lpt or lay
        if not price:
            vprint(verbose, f"  [RUNNER] -- {name}: skip (no price)")
            continue

        rank = rank_by_id.get(sid, 999)
        spread = ticks_between(back, lay) if back and lay else None
        cloth_str = f"{cloth:02d}" if cloth else "--"

        if verbose:
            print(f"  [RUNNER] {cloth_str} {name} | rank {rank} | back={back} lay={lay} lpt={lpt} cand={price}")

        # Odds band
        ok_band, msg_band = cfg.odds_band_ok(price)
        if not ok_band:
            vprint(verbose, f"    ✗ {msg_band}")
            continue
        vprint(verbose, f"    ✓ {msg_band}")

        # Spread
        if spread is None:
            vprint(verbose, "    ✗ Spread unknown (missing back/lay)")
            continue
        ok_spread, msg_spread = cfg.spread_ok(spread)
        if not ok_spread:
            vprint(verbose, f"    ✗ {msg_spread}")
            continue
        vprint(verbose, f"    ✓ {msg_spread}")

        # Rank buffer
        if rank < lo_rank or rank > hi_rank:
            vprint(verbose, f"    ✗ Rank {rank} outside buffer [{lo_rank}–{hi_rank}]")
            continue
        vprint(verbose, f"    ✓ Rank {rank} within buffer [{lo_rank}–{hi_rank}]")

        # Uniform probability check
        uni = uniform_probability(len(runners_book))
        cand_imp = implied_prob(price)
        max_allowed = uni * cfg.probability.uniform_check.multiplier
        if cand_imp > max_allowed:
            vprint(verbose, f"    ✗ Uniform check: implied={cand_imp:.4f} > max={max_allowed:.4f} (uniform={uni:.4f})")
            continue
        vprint(verbose, f"    ✓ Uniform check: implied={cand_imp:.4f} <= max={max_allowed:.4f} (uniform={uni:.4f})")

        score = abs(price - pref)
        candidates.append(
            Candidate(
                selection_id=sid,
                cloth=cloth or 0,
                name=name,
                back=back,
                lay=lay,
                spread_ticks=spread,
                rank=rank,
                score=score,
            )
        )
        vprint(verbose, "    → CANDIDATE ACCEPTED")

    return candidates, notes


def pick_best(candidates: List[Candidate]) -> Optional[Candidate]:
    if not candidates:
        return None
    # closest to preferred odds, then tightest spread
    candidates.sort(key=lambda c: (c.score, c.spread_ticks if c.spread_ticks is not None else 9999))
    return candidates[0]


# -----------------------------
# Main
# -----------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="Market selection + ladder for eligible markets")
    ap.add_argument("--filters", default="config/filters.yaml", help="Path to filters.yaml")
    ap.add_argument("--verbose", action="store_true", help="Verbose output")
    ap.add_argument("--max", type=int, default=50, help="Max markets to fetch (default 50)")
    args = ap.parse_args()

    verbose = args.verbose

    print("=== Betflow: Market Selection + Ladder ===")
    cfg = load_filter_config(args.filters, verbose=verbose)

    client = BetfairClient.from_env()
    vprint(verbose, "\n[BETFAIR LOGIN]")
    client.login()
    vprint(verbose, "  ✓ Login successful")

    markets = client.list_market_catalogue(max_results=args.max)
    print(f"\nFetched {len(markets)} market(s).")

    eligible_count = 0
    rejected_count = 0

    for m in markets:
        mid = m.get("marketId")
        mname = m.get("marketName")
        start_time = m.get("marketStartTime")
        event = m.get("event") or {}
        country = event.get("countryCode")
        runner_count = len(m.get("runners") or [])

        # Pull book once (used for market gating + ladder)
        book = client.list_market_book([mid])[0]

        print("\n==================================================")
        print(f"{mid} | {mname}")
        print(f"Start: {start_time} | Country: {country} | Runners: {runner_count}")

        # 1) Market selection decision
        decision = evaluate_market(cfg, m, book)

        if verbose:
            for s in decision.reasons_ok:
                print(f"  ✓ {s}")
            for s in decision.reasons_no:
                print(f"  ✗ {s}")
        else:
            # In non-verbose mode, still show the “why” if rejected (brief)
            if not decision.ok:
                why = decision.reasons_no[0] if decision.reasons_no else "Rejected"
                print(f"  → OUT: {why}")

        if not decision.ok:
            print("  → MARKET OUT")
            rejected_count += 1
            continue

        print("  → MARKET IN")
        eligible_count += 1

        # 2) Ladder for eligible market
        print("\n  --- LADDER / CANDIDATES ---")
        candidates, notes = build_ladder(cfg, m, book, verbose)

        for n in notes:
            print(f"  NOTE: {n}")

        if not candidates:
            print("  → No candidates")
            continue

        best = pick_best(candidates)

        # Summary block (human useful)
        print("\n  --- SUMMARY ---")
        print(f"  Candidates: {len(candidates)}")
        for c in candidates:
            cloth_str = f"{c.cloth:02d}" if c.cloth else "--"
            print(
                f"    {cloth_str} {c.name} | rank {c.rank:>2} | "
                f"back={c.back} lay={c.lay} | spread={c.spread_ticks} ticks"
            )

        if best:
            cloth_str = f"{best.cloth:02d}" if best.cloth else "--"
            print(
                f"\n  → SELECTED: {cloth_str} {best.name} "
                f"(rank {best.rank}) | back={best.back} lay={best.lay} | spread={best.spread_ticks} ticks"
            )

    print("\n==============================")
    print(f"Markets IN:  {eligible_count}")
    print(f"Markets OUT: {rejected_count}")
    print("==============================")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
