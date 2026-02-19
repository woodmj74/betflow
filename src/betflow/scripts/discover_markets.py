from __future__ import annotations

from datetime import timezone

from betflow.betfair.client import BetfairClient
from betflow.filter_config import load_filter_config
from betflow.logging import configure_logging
from betflow.settings import settings
from betflow.services.market_discovery import discover_next_markets


def main() -> int:
    configure_logging(settings.env)

    cfg = load_filter_config()

    print("\n== Betflow: Market Discovery (Phase 1) ==")
    print(f"Config: take={cfg.global_cfg.take} horizon_hours={cfg.global_cfg.horizon_hours}")
    print(f"Countries: {', '.join(cfg.all_market_countries())}\n")

    client = BetfairClient()

    eligible, rejected = discover_next_markets(client, cfg)

    def fmt_dt(dt):
        # Print in UTC for now (consistent with Betfair), can later add local formatting
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%MZ")

    print("---- Markets (next by time) ----\n")

    # We show both eligible + rejected, but grouped
    for bucket_name, items in [("ELIGIBLE", eligible), ("REJECTED", rejected)]:
        print(f"[{bucket_name}] {len(items)}\n")
        for d in items:
            m = d.market
            print(f"[MARKET] {m.market_id} — {fmt_dt(m.start_time)} — {m.market_name} ({m.country_code})")
            for line in d.reasons[:-1]:
                print(f"  {line}")
            print(f"  {d.reasons[-1]}\n")

    print("==============================")
    print(f"Eligible: {len(eligible)}")
    print(f"Rejected: {len(rejected)}")
    print("==============================\n")

    print("Proof: ✅ markets discovered + validated (runner count + liquidity)\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
