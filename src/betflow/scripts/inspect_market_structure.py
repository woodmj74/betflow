from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from betflow.betfair.client import BetfairClient
from betflow.filter_config import load_filter_config, FilterConfig
from betflow.markets.market_rules import evaluate_market_rules
from betflow.markets.structure_metrics import build_runner_ladders, compute_market_structure_metrics


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
    print("  No  Runner                           Back     Lay   Sprd(t)")
    print("  ----------------------------------------------------------")

    for idx, r in enumerate(ladders, start=1):
        # Prefer cloth number if available; otherwise fall back to row index.
        if getattr(r, "runner_number", None) is not None:
            num = f"{int(r.runner_number):02d}"
        else:
            num = f"{idx:02d}"

        back = f"{r.best_back:>6.2f}" if r.best_back else "   -  "
        lay = f"{r.best_lay:>6.2f}" if r.best_lay else "   -  "
        sprd = f"{r.spread_ticks:>6d}" if r.spread_ticks is not None else "   -  "

        name = (getattr(r, "name", "") or "")[:30]
        print(f"  {num}  {name:<30} {back}  {lay}  {sprd}")


def inspect_one_market(client: BetfairClient, market_id: str, filters_path: Optional[str]) -> None:
    cfg: FilterConfig = load_filter_config(filters_path)

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

    print("")
    print("[MARKET]")
    print(f"  id: {market_id} - {market_name}")
    print(f"  Start: {start_time}")
    print(f"  Country: {country or '?'}")
    print("")

    # --- Build ladders + metrics (always)
    ladders = build_runner_ladders(market_catalogue, market_book)
    metrics = compute_market_structure_metrics(ladders)

    # --- Market-level gating (config-driven)
    accepted, region_code, rule_results = evaluate_market_rules(
        market_catalogue=market_catalogue,
        market_book=market_book,
        metrics=metrics,
        cfg=cfg,
    )

    print("[VALIDATION]")
    if region_code and region_code in cfg.regions:
        print(f"  Region: {region_code} ({cfg.regions[region_code].name})")
    else:
        print("  Region: -")
    _print_rule_results(rule_results)

    # --- Ladder (always)
    _print_ladder(ladders)

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
