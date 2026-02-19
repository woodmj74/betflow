from __future__ import annotations

from betflow.betfair.client import BetfairClient
from betflow.logging import configure_logging
from betflow.settings import settings


def main() -> int:
    configure_logging(settings.env)

    print("\n== Betflow Proof: Connection Smoke Test ==")

    client = BetfairClient()

    print("\n[1] Login")
    client.login()
    print("  ✓ login ok")

    print("\n[2] JSON-RPC: listEventTypes")
    result = client.rpc("listEventTypes", {"filter": {}})

    if not isinstance(result, list):
        print(f"  ✗ unexpected result type: {type(result)}")
        return 1

    print(f"  ✓ returned {len(result)} event types (showing first 10)\n")
    for row in result[:10]:
        # row shape: {"eventType":{"id":"7","name":"Horse Racing"},"marketCount":123}
        et = (row or {}).get("eventType", {}) if isinstance(row, dict) else {}
        et_id = et.get("id", "?")
        et_name = et.get("name", "?")
        mc = (row or {}).get("marketCount", "?") if isinstance(row, dict) else "?"
        print(f"  - {et_id:>2}  {et_name:<20} (markets: {mc})")

    print("\n✅ Connection looks good.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
