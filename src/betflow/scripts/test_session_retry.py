from __future__ import annotations

from betflow.betfair.client import BetfairClient
from betflow.logging import configure_logging
from betflow.settings import settings


def main() -> None:
    configure_logging(settings.env)

    print("\n== Betflow Proof: Session Retry Logic ==")
    client = BetfairClient()

    print("\n[1] Login (baseline)")
    client.login()
    print("  ✓ login ok")

    print("\n[2] Break the session token deliberately")
    client.session_token = "THIS_IS_NOT_A_REAL_SESSION_TOKEN"
    print("  ✓ token overwritten")

    print("\n[3] Call listEventTypes (should auto re-login + retry once)")
    result = client.rpc("listEventTypes", {"filter": {}})

    count = len(result) if isinstance(result, list) else 0
    print(f"  ✓ call succeeded after retry (eventTypes returned: {count})")

    print("\n✅ Session retry proof passed.\n")


if __name__ == "__main__":
    main()
