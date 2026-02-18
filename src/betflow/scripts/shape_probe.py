from __future__ import annotations

from betflow.betfair.client import BetfairClient
from betflow.services.market_shape import get_market_shape


def main() -> None:
    client = BetfairClient.from_env()
    client.login()

    markets = client.list_market_catalogue(max_results=1)
    if not markets:
        raise RuntimeError("No markets returned from list_market_catalogue")

    market_id = markets[0]["marketId"]
    print(f"Using next marketId from catalogue: {market_id}")


    shape = get_market_shape(client, market_id)

    print("Market shape probe")
    print(f"  market_id     : {shape.market_id}")
    print(f"  field_size    : {shape.field_size}")
    print(f"  total_matched : {shape.total_matched:.2f}")
    print(f"  fav_price     : {shape.fav_price} (selectionId={shape.fav_selection_id})")



if __name__ == "__main__":
    main()