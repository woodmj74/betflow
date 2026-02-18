from __future__ import annotations

from betflow.logging import configure_logging, get_logger
from betflow.settings import Settings
from betflow.betfair.client import BetfairClient


def main() -> int:
    settings = Settings.load()
    configure_logging(settings.env)

    log = get_logger("script.test_connection")

    # Don’t print secrets; just sanity
    log.info(
        "env.loaded",
        env=settings.env,
        app_key_len=len(settings.betfair_app_key),
        cert_crt=str(settings.betfair_cert_crt),
        cert_key=str(settings.betfair_cert_key),
        username=settings.betfair_username,
    )

    client = BetfairClient(settings)

    log.info("betfair.login.check")
    client.login()

    log.info("betfair.rpc.check", method="listEventTypes")
    result = client.list_event_types()

    # Human-friendly output
    count = len(result or [])
    log.info("betfair.rpc.ok", event_types=count)

    print("\nEvent Types (first 10):")
    for row in (result or [])[:10]:
        et = row.get("eventType", {})
        print(f"  - {et.get('id','?'):>3}  {et.get('name','?')}")

    print("\n✅ Connection looks good.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
