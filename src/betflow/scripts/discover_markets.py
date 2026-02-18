from __future__ import annotations

import argparse
from typing import Any, Dict, List

from betflow.betfair.client import BetfairClient
from betflow.filter_config import load_filter_config


# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------

def vprint(verbose: bool, msg: str) -> None:
    if verbose:
        print(msg)


def count_under_odds(runners: List[Dict[str, Any]], threshold: float) -> int:
    count = 0
    for r in runners:
        lpt = r.get("lastPriceTraded")
        if lpt and lpt < threshold:
            count += 1
    return count


# ---------------------------------------------------------
# Main
# ---------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Discover eligible markets")
    parser.add_argument(
        "--filters",
        default="config/filters.yaml",
        help="Path to filters.yaml",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Verbose decision output",
    )

    args = parser.parse_args()
    verbose = args.verbose

    print("=== Betflow Market Discovery ===")

    cfg = load_filter_config(args.filters, verbose=verbose)

    # -------------------------
    # Betfair Login
    # -------------------------
    client = BetfairClient.from_env()

    vprint(verbose, "\n[BETFAIR LOGIN]")
    client.login()
    vprint(verbose, "  ✓ Login successful")

    # -------------------------
    # Fetch markets
    # -------------------------
    markets = client.list_market_catalogue(max_results=50)

    print(f"\nFetched {len(markets)} markets from Betfair.")

    eligible = []
    rejected = []

    for m in markets:
        market_id = m.get("marketId")
        market_name = m.get("marketName")
        event = m.get("event", {})
        country = event.get("countryCode")
        runners = m.get("runners", [])
        runner_count = len(runners)

        print(f"\n[MARKET] {market_id} - {market_name}")

        ok = True

        # -------------------------
        # Scope check
        # -------------------------
        if not cfg.is_market_in_scope(country):
            print(f"  ✗ Country {country} not in scope.")
            ok = False
        else:
            region = cfg.scope.region_for_country(country)
            print(f"  ✓ Country {country} in region {region.name if region else 'Unknown'}")

        # -------------------------
        # Field size gate
        # -------------------------
        field_ok, msg = cfg.field_size_ok(runner_count)
        if field_ok:
            print(f"  ✓ {msg}")
        else:
            print(f"  ✗ {msg}")
            ok = False

        # -------------------------
        # Liquidity check (requires marketBook)
        # -------------------------
        book = client.list_market_book([market_id])[0]
        total_matched = book.get("totalMatched", 0.0)

        liquidity_min = cfg.market_liquidity_min(country)

        if liquidity_min is None:
            print("  ✗ No liquidity rule for region.")
            ok = False
        elif total_matched < liquidity_min:
            print(f"  ✗ Liquidity {total_matched:.0f} < {liquidity_min:.0f}")
            ok = False
        else:
            print(f"  ✓ Liquidity {total_matched:.0f} >= {liquidity_min:.0f}")

        # -------------------------
        # Compression check
        # -------------------------
        under_count = count_under_odds(
            book.get("runners", []),
            cfg.market.compression.under_odds,
        )

        if under_count > cfg.market.compression.max_count:
            print(
                f"  ✗ Compression: {under_count} runners < "
                f"{cfg.market.compression.under_odds}"
            )
            ok = False
        else:
            print(
                f"  ✓ Compression: {under_count} runners < "
                f"{cfg.market.compression.under_odds}"
            )

        # -------------------------
        # Final
        # -------------------------
        if ok:
            print("  → MARKET ELIGIBLE")
            eligible.append(m)
        else:
            print("  → MARKET REJECTED")
            rejected.append(m)

    print("\n==============================")
    print(f"Eligible: {len(eligible)}")
    print(f"Rejected: {len(rejected)}")
    print("==============================")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
