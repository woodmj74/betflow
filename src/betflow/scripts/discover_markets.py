from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional

from betflow.filter_config import load_filter_config  # you added this
from betflow.betfair.client import BetfairClient      # assumed existing
from betflow.util.time import utc_now_iso             # optional; see fallback below


# -----------------------------
# Utilities
# -----------------------------

def env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def fmt_money(n: float | int) -> str:
    try:
        return f"£{float(n):,.0f}"
    except Exception:
        return str(n)


def ticks_between(price_a: float, price_b: float) -> Optional[int]:
    """
    Rough tick distance using Betfair tick ladder bands.
    Good enough for spread gating; exact mapping can be swapped later.
    """
    if price_a <= 1.0 or price_b <= 1.0:
        return None
    lo, hi = sorted([price_a, price_b])

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
    # step in ticks until reaching hi
    while p < hi - 1e-9:
        step = None
        for a, b, inc in bands:
            if a <= p < b:
                step = inc
                break
        if step is None:
            return None
        p = round(p + step, 10)
        ticks += 1
        if ticks > 5000:
            # safety guard
            return None
    return ticks


def vprint(verbose: bool, msg: str) -> None:
    if verbose:
        print(msg)


# -----------------------------
# Eligibility result types
# -----------------------------

@dataclass
class Decision:
    ok: bool
    reasons_ok: list[str]
    reasons_no: list[str]

    def add_ok(self, s: str) -> None:
        self.reasons_ok.append(s)

    def add_no(self, s: str) -> None:
        self.reasons_no.append(s)
        self.ok = False


# -----------------------------
# Market checks
# -----------------------------

def evaluate_market(
    *,
    market: dict[str, Any],
    cfg: Any,
    verbose: bool,
) -> Decision:
    """
    Market: marketCatalogue-like dict.
    cfg: output from load_filter_config().
    """
    d = Decision(ok=True, reasons_ok=[], reasons_no=[])

    market_id = market.get("marketId", "?")
    market_name = market.get("marketName", "?")
    runners = market.get("runners") or []
    n_runners = len(runners)

    vprint(verbose, f"\n[MARKET CHECK] {market_id} - {market_name}")

    # runner count gate
    min_r = cfg.market.runners_min
    max_r = cfg.market.runners_max
    if n_runners < min_r or n_runners > max_r:
        d.add_no(f"Runners: {n_runners} (REJECT: outside {min_r}–{max_r})")
    else:
        d.add_ok(f"Runners: {n_runners} (OK: within {min_r}–{max_r})")

    # venue / country gate (if present in config)
    # We assume your cfg already filters eventType + country in the API call.
    # This is just additional belt-and-braces if you store e.g. market['event']['countryCode'].
    country = (market.get("event") or {}).get("countryCode")
    allowed_countries = getattr(cfg.market, "allowed_countries", None)
    if allowed_countries and country:
        if country not in allowed_countries:
            d.add_no(f"Country: {country} (REJECT: not in {allowed_countries})")
        else:
            d.add_ok(f"Country: {country} (OK)")

    # liquidity gate (catalogue doesn't always include matched; we often need marketBook)
    # We’ll mark as "unknown" here and let the caller optionally enrich via marketBook.
    d.add_ok("Liquidity: pending (requires marketBook)")

    # compressed market check is usually based on prices; needs marketBook too
    d.add_ok("Compression: pending (requires marketBook)")

    # print decision snapshot
    if verbose:
        for s in d.reasons_ok:
            print(f"  - {s}")
        for s in d.reasons_no:
            print(f"  - {s}")
        print(f"  → {'MARKET ELIGIBLE' if d.ok else 'MARKET REJECTED (so far)'}")

    return d


def enrich_with_market_book_checks(
    *,
    market_id: str,
    market_book: dict[str, Any],
    cfg: Any,
    decision: Decision,
    verbose: bool,
) -> None:
    """
    Add liquidity + compression checks using marketBook.
    """
    # Liquidity
    total_matched = market_book.get("totalMatched")
    if total_matched is None:
        decision.add_no("Liquidity: unknown (REJECT: marketBook missing totalMatched)")
    else:
        min_liq = cfg.market.min_total_matched
        if float(total_matched) < float(min_liq):
            decision.add_no(f"Total Matched: {fmt_money(total_matched)} (REJECT: < {fmt_money(min_liq)})")
        else:
            decision.add_ok(f"Total Matched: {fmt_money(total_matched)} (OK: >= {fmt_money(min_liq)})")

    # Compression / overly-compressed market
    # Simple version: count runners trading below a threshold (e.g. odds < 10)
    # and reject if too many are clustered.
    compression = getattr(cfg.market, "compression", None)
    if not compression:
        decision.add_ok("Compression: skipped (no config)")
        return

    max_under = compression.max_runners_under_price
    under_price = compression.under_price

    rc = market_book.get("runners") or []
    count_under = 0
    for r in rc:
        # lastPriceTraded is a decent proxy; can be replaced with bestAvailableToBack[0].price etc
        lpt = r.get("lastPriceTraded")
        if lpt is not None and float(lpt) < float(under_price):
            count_under += 1

    if count_under > max_under:
        decision.add_no(
            f"Compression: {count_under} runners < {under_price} "
            f"(REJECT: > max {max_under})"
        )
    else:
        decision.add_ok(
            f"Compression: {count_under} runners < {under_price} "
            f"(OK: <= max {max_under})"
        )

    if verbose:
        # print just the new info (caller prints full summary later)
        pass


# -----------------------------
# Main: discover markets
# -----------------------------

def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Discover eligible GB/IE horse racing WIN markets")
    p.add_argument("--hours", type=int, default=int(os.getenv("BETFLOW_LOOKAHEAD_HOURS", "24")),
                   help="Lookahead window in hours (default: env BETFLOW_LOOKAHEAD_HOURS or 24)")
    p.add_argument("--max", type=int, default=50, help="Max markets to fetch (default 50)")
    p.add_argument("--verbose", action="store_true", help="Verbose decision output")
    p.add_argument("--filters", type=str, default=os.getenv("BETFLOW_FILTERS_PATH", "config/filters.yaml"),
                   help="Path to filters.yaml (default: config/filters.yaml or env BETFLOW_FILTERS_PATH)")
    return p


def main() -> int:
    args = build_arg_parser().parse_args()

    # Verbosity: CLI overrides env default
    verbose = args.verbose or env_bool("BETFLOW_VERBOSE", False)

    cfg = load_filter_config(args.filters)

    start = now_utc()
    end = start + timedelta(hours=args.hours)

    # Fallback if you don’t have utc_now_iso util
    time_range = {
        "from": start.isoformat().replace("+00:00", "Z"),
        "to": end.isoformat().replace("+00:00", "Z"),
    }

    print("=== Betflow: Market Discovery ===")
    print(f"Time window: {time_range['from']}  →  {time_range['to']}")
    print(f"Filters: {args.filters}")
    print(f"Verbose: {'ON' if verbose else 'off'}")

    # ---- Betfair query setup ----
    # You may already do this elsewhere; this is deliberately explicit.
    # eventTypeId 7 = Horse Racing (commonly), but you may already have this abstracted.
    client = BetfairClient.from_env()  # assumed existing pattern in your repo

    # Build a filter; adjust to your actual API wrapper signature.
    # We focus GB/IE WIN markets next N hours.
    market_filter = {
        "eventTypeIds": [cfg.market.event_type_id],           # e.g. 7
        "marketCountries": cfg.market.countries,             # e.g. ["GB", "IE"]
        "marketTypeCodes": [cfg.market.market_type_code],    # e.g. "WIN"
        "marketStartTime": {"from": time_range["from"], "to": time_range["to"]},
    }

    vprint(verbose, "\n[QUERY]")
    vprint(verbose, f"  marketFilter={market_filter}")

    # Catalogue gives us runners + basic details
    catalogues: list[dict[str, Any]] = client.list_market_catalogue(
        market_filter=market_filter,
        max_results=args.max,
        market_projection=["EVENT", "MARKET_START_TIME", "RUNNER_DESCRIPTION"],
        sort="FIRST_TO_START",
    )

    print(f"\nFetched {len(catalogues)} market(s) from catalogue.")

    eligible: list[tuple[dict[str, Any], Decision]] = []
    rejected: list[tuple[dict[str, Any], Decision]] = []

    # First pass: market-level checks that don't require prices/liquidity
    for m in catalogues:
        dec = evaluate_market(market=m, cfg=cfg, verbose=verbose)
        (eligible if dec.ok else rejected).append((m, dec))

    print(f"\nAfter runner-count gates: eligible={len(eligible)} rejected={len(rejected)}")

    # Second pass: enrich eligibility with marketBook (liquidity + compression)
    # Only if we still have any eligible candidates.
    if eligible:
        market_ids = [m["marketId"] for m, _ in eligible if m.get("marketId")]
        books_by_id: dict[str, dict[str, Any]] = client.list_market_book_by_id(
            market_ids=market_ids,
            price_projection={"priceData": ["EX_BEST_OFFERS"]},
        )

        eligible2: list[tuple[dict[str, Any], Decision]] = []
        rejected2: list[tuple[dict[str, Any], Decision]] = []

        for m, dec in eligible:
            mid = m.get("marketId", "")
            book = books_by_id.get(mid)
            if not book:
                dec.add_no("marketBook missing (REJECT)")
            else:
                enrich_with_market_book_checks(
                    market_id=mid,
                    market_book=book,
                    cfg=cfg,
                    decision=dec,
                    verbose=verbose,
                )

            # Print full decision summary in verbose mode
            if verbose:
                print(f"\n[MARKET DECISION] {mid} - {m.get('marketName','?')}")
                for s in dec.reasons_ok:
                    print(f"  ✓ {s}")
                for s in dec.reasons_no:
                    print(f"  ✗ {s}")
                print(f"  → {'ELIGIBLE' if dec.ok else 'REJECTED'}")

            (eligible2 if dec.ok else rejected2).append((m, dec))

        eligible = eligible2
        rejected.extend(rejected2)

    # Final summary (always printed)
    print("\n=== Eligible Markets ===")
    if not eligible:
        print("None found (within current filters).")
        return 0

    for m, dec in eligible:
        event = m.get("event") or {}
        start_time = m.get("marketStartTime", "?")
        print(f"- {m.get('marketId','?')} | {event.get('name','?')} | {m.get('marketName','?')} | {start_time}")

    print(f"\nDone. eligible={len(eligible)} rejected={len(rejected)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
