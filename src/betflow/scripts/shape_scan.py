from __future__ import annotations

from betflow.betfair.client import BetfairClient
from betflow.services.market_shape import ShapeFilter, get_market_shape, passes_shape_filters


def main() -> None:
    client = BetfairClient.from_env()
    client.login()

    markets = client.list_market_catalogue(max_results=30)

    f = ShapeFilter(
        min_runners=7,
        max_runners=16,
        min_total_matched=2000.0,
        fav_min=1.8,
        fav_max=8.0,
    )

    print(f"Scanning {len(markets)} markets with filters: {f}")

    passes = 0
    for m in markets:
        market_id = m["marketId"]
        shape = get_market_shape(client, market_id)
        ok, reasons = passes_shape_filters(shape, f)

        if ok:
            passes += 1
            print(f"PASS {market_id} runners={shape.field_size} matched={shape.total_matched:.0f} fav={shape.fav_price}")
        else:
            print(f"FAIL {market_id} runners={shape.field_size} matched={shape.total_matched:.0f} fav={shape.fav_price} | {', '.join(reasons)}")

    print(f"\nPassed: {passes}/{len(markets)}")


if __name__ == "__main__":
    main()
