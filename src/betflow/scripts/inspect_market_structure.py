from __future__ import annotations

from datetime import datetime, timezone

from betflow.betfair.client import BetfairClient
from betflow.filter_config import load_filter_config
from betflow.markets.market_rules import evaluate_market_rules
from betflow.markets.structure_metrics import (
    build_runner_ladders,
    compute_market_structure_metrics,
    select_candidate_runner,
)


def _fmt_dt(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%MZ")
    except Exception:
        return iso


def _print_rule_results(rule_results) -> None:
    for r in rule_results:
        mark = "✓" if r.ok else "✗"
        print(f"  {mark} {r.label}: {r.detail}")


def _print_ladder(ladders) -> None:
    print("")
    print("[LADDER]  (best back/lay)")
    print("  No  Runner                             Back       Lay    Sprd(t)")
    print("  ----------------------------------------------------------------")

    for idx, r in enumerate(ladders, start=1):
        # Prefer cloth number if available; otherwise fall back to row index.
        if getattr(r, "runner_number", None) is not None:
            num = f"{int(r.runner_number):02d}"
        else:
            num = f"{idx:02d}"

        back = f"{r.best_back:>8.2f}" if r.best_back else "   -  "
        lay = f"{r.best_lay:>8.2f}" if r.best_lay else "   -  "
        sprd = f"{r.spread_ticks:>8d}" if r.spread_ticks is not None else "   -  "

        name = (getattr(r, "name", "") or "")[:30]
        print(f"  {num}  {name:<30} {back}  {lay}  {sprd}")

def _print_selection_debug(cfg, metrics, debug_rows, selected) -> None:
    sel = cfg.selection
    hard = sel.hard_band
    primary = sel.primary_band
    secondary = sel.secondary_band
    rank_excl = sel.rank_exclusion

    top_n = cfg.structure_gates.anchor.top_n
    top_n_implied = getattr(metrics, "top_n_implied_sum", None)

    anchored_ok = False
    if top_n_implied is not None:
        anchored_ok = top_n_implied >= secondary.requires_top_n_implied_at_least

    print("  Config:")
    print(f"    hard_band:      {hard.min:.1f}–{hard.max:.1f}")
    print(f"    primary_band:   {primary.min:.1f}–{primary.max:.1f}")
    if top_n_implied is None:
        print(
            f"    secondary_band: {secondary.min:.1f}–{secondary.max:.1f} "
            f"(allowed if top{top_n} >= {secondary.requires_top_n_implied_at_least:.2f}; top{top_n}=? )"
        )
    else:
        print(
            f"    secondary_band: {secondary.min:.1f}–{secondary.max:.1f} "
            f"(allowed: {'YES' if anchored_ok else 'NO'}; top{top_n}={top_n_implied:.2f} >= {secondary.requires_top_n_implied_at_least:.2f})"
        )
    print(f"    max_spread:     {sel.max_spread_ticks} ticks")
    print(f"    rank_excl:      top {rank_excl.top_n}, bottom {rank_excl.bottom_n}")
    print("")

    # Header (your requested columns)
    print("  No  Runner                             Back       Lay  Sprd  Dist  Band       Status     Reason")
    print("  ----------------------------------------------------------------------------------------------------")

    rows = sorted(debug_rows, key=lambda x: x.price_rank)

    def _num_for(runner, fallback_rank: int) -> str:
        n = getattr(runner, "runner_number", None)
        if n is None:
            return f"{fallback_rank:02d}"
        try:
            return f"{int(n):02d}"
        except Exception:
            return f"{fallback_rank:02d}"

    eligible_count = 0
    for row in rows:
        r = row.runner
        num = _num_for(r, row.price_rank)

        name = (getattr(r, "name", "") or "")[:30]

        back = f"{r.best_back:>8.2f}" if getattr(r, "best_back", None) else "  -   "
        lay = f"{r.best_lay:>8.2f}" if getattr(r, "best_lay", None) else "  -   "

        sprd = f"{row.spread_ticks:>4d}" if row.spread_ticks is not None else "  - "
        dist = f"{row.distance_ticks:>4d}" if row.distance_ticks is not None else "  - "

        band = f"{row.band:<9}"

        is_eligible = row.score > -9000  # compatibility: eligible rows use 0.0, rejected -9999.0
        status = "ELIGIBLE" if is_eligible else "REJECTED"
        if is_eligible:
            eligible_count += 1

        reason = (row.reason or "")[:45]

        print(f"  {num}  {name:<30} {back:>6}  {lay:>6}  {sprd:>4}  {dist:>4}  {band}  {status:<9}  {reason}")

    print("")
    print(f"  Eligible runners: {eligible_count}")

    if selected is None:
        print("  → Selected: NONE")
    else:
        n = getattr(selected, "runner_number", None)
        num = f"{int(n):02d}" if n is not None else "--"
        nm = getattr(selected, "name", "") or ""
        bb = getattr(selected, "best_back", None)
        bl = getattr(selected, "best_lay", None)
        if bb is not None and bl is not None:
            print(f"  → Selected: {num} {nm}  ({bb:.2f}/{bl:.2f})")
        else:
            print(f"  → Selected: {num} {nm}")


def inspect_one_market(client: BetfairClient, market_id: str, filters_path: str) -> None:
    cfg = load_filter_config(filters_path)

    # --- MarketCatalogue
    cat = client.rpc(
        "listMarketCatalogue",
        {
            "filter": {"marketIds": [market_id]},
            "maxResults": "1",
            "marketProjection": ["RUNNER_DESCRIPTION", "RUNNER_METADATA", "EVENT", "MARKET_START_TIME"],
        },
    )
    if not cat:
        print(f"[MARKET] {market_id} - not found in catalogue")
        return
    market_catalogue = cat[0]

    # --- MarketBook
    book = client.rpc(
        "listMarketBook",
        {
            "marketIds": [market_id],
            "priceProjection": {
                "priceData": ["EX_BEST_OFFERS"],
                "virtualise": False,
                "exBestOffersOverrides": {"bestPricesDepth": 1},
            },
        },
    )
    if not book:
        print(f"[MARKET] {market_id} - no market book returned")
        return
    market_book = book[0]

    market_name = market_catalogue.get("marketName", "")
    start_time = _fmt_dt(market_catalogue.get("marketStartTime", ""))
    country = (market_catalogue.get("event", {}) or {}).get("countryCode")
    venue = (market_catalogue.get("event", {}) or {}).get("venue")

    print("")
    print("[MARKET]")
    print(f"  id: {market_id} - {market_name}")
    print(f"  Start: {start_time}")
    if venue:
        print(f"  Venue: {venue}")
    print(f"  Country: {country or '?'}")

    # --- Build ladders + metrics (always)
    ladders = build_runner_ladders(market_catalogue, market_book)
    metrics = compute_market_structure_metrics(
        ladders,
        anchor_top_n=cfg.structure_gates.anchor.top_n,
        soup_top_k=cfg.structure_gates.soup.top_k,
        tier_top_region=cfg.structure_gates.tier.top_region,
    )

    # --- Market-level gating (config-driven)
    accepted, region_code, rule_results = evaluate_market_rules(
        market_catalogue=market_catalogue,
        market_book=market_book,
        metrics=metrics,
        cfg=cfg,
    )

    if region_code and region_code in cfg.regions:
        print(f"  Region: {region_code} ({cfg.regions[region_code].name})")
    else:
        print("  Region: -")
    print("")

    print("[VALIDATION]")

    _print_rule_results(rule_results)

    # --- Ladder (always)
    _print_ladder(ladders)

    # --- Selection (only if market accepted)
    print("")
    print("")
    print("[SELECTION]")

    if accepted:
        selected, debug_rows = select_candidate_runner(
            ladders=ladders,
            metrics=metrics,
            cfg=cfg,
        )

        _print_selection_debug(cfg=cfg, metrics=metrics, debug_rows=debug_rows, selected=selected)

    else:
        print("  → Market rejected — no runner considered")

    print("")
    print("[DECISION]")
    print(f"  → MARKET {'ACCEPTED' if accepted else 'REJECTED'}")


def main() -> None:
    """
    Usage:
      python -m betflow.scripts.inspect_market_structure --market-id 1.254186197
      python -m betflow.scripts.inspect_market_structure 1.254186197
    """
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("market_id_pos", nargs="?", help="MarketId as positional arg (optional)")
    p.add_argument("--market-id", help="Betfair marketId (e.g. 1.254186197)")
    p.add_argument("--filters", default="config/filters.yaml", help="Path to filters yaml")
    args = p.parse_args()

    market_id = args.market_id or args.market_id_pos
    if not market_id:
        raise SystemExit("Provide a market id: either positional or --market-id")

    client = BetfairClient()
    inspect_one_market(client, market_id, args.filters)


if __name__ == "__main__":
    main()
