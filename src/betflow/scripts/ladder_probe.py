from __future__ import annotations

from betflow.betfair.client import BetfairClient
from betflow.services.filter_config import load_filter_config
from betflow.services.market_ladder import (
    build_runner_ladder,
    select_target_runner,
    check_market_sanity,
)


def section(title: str) -> None:
    line = "-" * 60
    print(f"\n{line}")
    print(title)
    print(line)


def main() -> None:
    client = BetfairClient.from_env()
    client.login()

    # Load config once, early
    cfg = load_filter_config()

    markets = client.list_market_catalogue(max_results=1)
    if not markets:
        raise RuntimeError("No markets returned from list_market_catalogue")

    m = markets[0]

    # Build ladder using catalogue market object
    ladder = build_runner_ladder(client, m)

    # Run market sanity checks
    sanity = check_market_sanity(ladder, cfg.sanity_checks)

    # Only evaluate target runner if sanity passes
    if sanity.ok:
        candidate, reasons = select_target_runner(ladder, cfg.runner_targeting)
    else:
        candidate, reasons = None, ["market failed sanity checks"]

    # =====================
    # OUTPUT
    # =====================

    section("MARKET")
    print(f"Name      : {m.get('marketName')}")
    print(f"Market ID : {m.get('marketId')}")
    print(f"Country   : {(m.get('event') or {}).get('countryCode')}")
    print(f"Start     : {m.get('marketStartTime')}")

    section("MARKET SANITY")
    print(f"Runners < 10           : {sanity.runners_under_10}")
    print(
        f"Cluster <= {cfg.sanity_checks.prefer_cluster_under} : {sanity.runners_under_cluster}"
    )

    if sanity.ok:
        print("SANITY: OK")
    else:
        print("SANITY: FAIL")
        for r in sanity.reasons:
            print(f"  - {r}")

    section("RUNNER LADDER")

    if not ladder:
        print("No active runners.")
    else:
        for r in ladder:
            name_short = (
                (r.name[:10] + "...") if r.name and len(r.name) > 13 else r.name
            )

            print(
                f"{r.rank:>2} | "
                f"No {str(r.number):>2} | "
                f"{str(name_short):<15} | "
                f"Back {str(r.best_back):>6} | "
                f"Lay {str(r.best_lay):>6} | "
                f"Spr {str(r.spread_ticks):>3}"
            )

    section("TARGET EVALUATION")

    if candidate:
        print(
            f"TARGET → Rank {candidate.rank} | "
            f"{candidate.name} | "
            f"Back {candidate.best_back} | "
            f"Spr {candidate.spread_ticks}"
        )
    else:
        print("NO TARGET RUNNER")
        for r in reasons:
            print(f"  - {r}")

    print("-" * 60)


if __name__ == "__main__":
    main()
