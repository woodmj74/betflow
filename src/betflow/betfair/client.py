from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv


IDENTITY_CERTLOGIN_URL = "https://identitysso-cert.betfair.com/api/certlogin"
BETTING_JSONRPC_URL = "https://api.betfair.com/exchange/betting/json-rpc/v1"


def _load_env() -> None:
    """
    Load .env reliably even when running as a module.
    Avoids python-dotenv's find_dotenv() stack-frame quirks.
    """
    # This file is: src/betflow/betfair/client.py
    # Project root is: /opt/betflow
    project_root = Path(__file__).resolve().parents[3]
    env_path = project_root / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=str(env_path), override=True)


def _mask(s: str, head: int = 4, tail: int = 4) -> str:
    if not s:
        return "<missing>"
    if len(s) <= head + tail:
        return "<masked>"
    return f"{s[:head]}…{s[-tail:]}"


@dataclass(frozen=True)
class BetfairConfig:
    app_key: str
    session_token: str
    cert_crt: str
    cert_key: str


class BetfairApiError(RuntimeError):
    def __init__(self, message: str, request_uuid: Optional[str] = None):
        super().__init__(message)
        self.request_uuid = request_uuid


class BetfairClient:
    def __init__(self, config: BetfairConfig, timeout_s: int = 20):
        self._config = config
        self._timeout_s = timeout_s

    @staticmethod
    def from_env() -> "BetfairClient":
        _load_env()

        app_key = (os.getenv("BETFAIR_APP_KEY") or "").strip()
        if not app_key:
            raise SystemExit("Missing BETFAIR_APP_KEY in environment/.env")

        # Optional overrides; defaults match your current setup
        cert_crt = (os.getenv("BETFAIR_CERT_CRT") or "/opt/betflow/secrets/client-2048.crt").strip()
        cert_key = (os.getenv("BETFAIR_CERT_KEY") or "/opt/betflow/secrets/client-2048.key").strip()

        print(f"[betfair] app_key={_mask(app_key)} len={len(app_key)}")
        print(f"[betfair] cert_crt={cert_crt}")
        print(f"[betfair] cert_key={cert_key}")

        return BetfairClient(
            BetfairConfig(app_key=app_key, session_token="", cert_crt=cert_crt, cert_key=cert_key)
        )

    def login(self) -> None:
        """
        Cert login; stores the returned session token inside the client.
        Requires BETFAIR_USERNAME and BETFAIR_PASSWORD in .env.
        """
        username = (os.getenv("BETFAIR_USERNAME") or "").strip()
        password = (os.getenv("BETFAIR_PASSWORD") or "").strip()
        if not username or not password:
            raise SystemExit("Missing BETFAIR_USERNAME or BETFAIR_PASSWORD in environment/.env")

        headers = {
            "X-Application": self._config.app_key,
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        }

        r = requests.post(
            IDENTITY_CERTLOGIN_URL,
            headers=headers,
            data={"username": username, "password": password},
            cert=(self._config.cert_crt, self._config.cert_key),
            timeout=self._timeout_s,
        )
        r.raise_for_status()
        j = r.json()

        if j.get("loginStatus") != "SUCCESS":
            raise BetfairApiError(f"Login failed: {j}")

        token = j["sessionToken"]
        object.__setattr__(self._config, "session_token", token)
        print("[betfair] login successful")

    def _headers(self) -> Dict[str, str]:
        if not self._config.session_token:
            raise BetfairApiError("No session token set. Call client.login() first.")
        return {
            "X-Application": self._config.app_key,
            "X-Authentication": self._config.session_token,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def call_jsonrpc(self, method: str, params: Dict[str, Any], request_id: int = 1) -> Any:
        payload = [{
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": request_id,
        }]

        r = requests.post(
            BETTING_JSONRPC_URL,
            headers=self._headers(),
            data=json.dumps(payload),
            timeout=self._timeout_s,
        )

        if r.status_code != 200:
            raise BetfairApiError(f"HTTP {r.status_code}: {r.text}")

        data = r.json()

        # JSON-RPC responses are a list
        if not isinstance(data, list) or not data:
            raise BetfairApiError(f"Unexpected JSON-RPC response: {data!r}")

        item = data[0]
        if "error" in item and item["error"]:
            req_uuid = None
            try:
                req_uuid = item["error"]["data"]["APINGException"]["requestUUID"]
            except Exception:
                pass
            raise BetfairApiError(f"Betfair error: {item['error']}", request_uuid=req_uuid)

        return item.get("result")

    def list_event_types(self) -> List[Dict[str, Any]]:
        return self.call_jsonrpc("SportsAPING/v1.0/listEventTypes", {"filter": {}})

    def list_market_catalogue(self, max_results: int = 10) -> List[Dict[str, Any]]:
        """
        Pull upcoming GB/IE Horse Racing WIN markets in the next 24 hours.
        """
        now = datetime.now(timezone.utc)
        later = now + timedelta(hours=24)

        params = {
            "filter": {
                "eventTypeIds": ["7"],           # Horse Racing
                "marketTypeCodes": ["WIN"],      # only WIN markets
                "marketCountries": ["GB", "IE"], # UK/IRE
                "marketStartTime": {
                    "from": now.isoformat().replace("+00:00", "Z"),
                    "to": later.isoformat().replace("+00:00", "Z"),
                },
            },
            "sort": "FIRST_TO_START",
            "maxResults": str(max_results),
            "marketProjection": [
                "EVENT",
                "RUNNER_DESCRIPTION",
                "MARKET_START_TIME",
                "MARKET_DESCRIPTION",
            ],
        }

        return self.call_jsonrpc("SportsAPING/v1.0/listMarketCatalogue", params)

    def list_market_book(
        self,
        market_ids: List[str],
        price_projection: Optional[Dict[str, Any]] = None,
        order_projection: Optional[str] = None,
        match_projection: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Wrapper for SportsAPING/v1.0/listMarketBook.
        Pass price_projection to request best offers, traded prices, etc.
        """
        params: Dict[str, Any] = {
            "marketIds": market_ids,
        }
        if price_projection is not None:
            params["priceProjection"] = price_projection
        if order_projection is not None:
            params["orderProjection"] = order_projection
        if match_projection is not None:
            params["matchProjection"] = match_projection

        return self.call_jsonrpc("SportsAPING/v1.0/listMarketBook", params)


def main() -> None:
    client = BetfairClient.from_env()
    client.login()

    markets = client.list_market_catalogue(max_results=10)

    print("\nHorse Racing WIN Markets (GB/IE, next 24h):")
    for m in markets:
        print(f"\nMarket: {m.get('marketName')}")
        print(f"Market ID: {m.get('marketId')}")
        print(f"Start Time: {m.get('marketStartTime')}")

        desc = m.get("description", {})
        if desc:
            print(f"Type: {desc.get('marketType')}  Betting: {desc.get('bettingType')}")

        runners = m.get("runners", [])
        print(f"Runners ({len(runners)}):")
        for r in runners:
            print(f"  - {r.get('runnerName')}")


if __name__ == "__main__":
    main()
