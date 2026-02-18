from __future__ import annotations

import json
import os
from pathlib import Path

import requests
from dotenv import load_dotenv

IDENTITY_URL = "https://identitysso-cert.betfair.com/api/certlogin"
BETTING_JSONRPC_URL = "https://api.betfair.com/exchange/betting/json-rpc/v1"

ENV_PATH = "/opt/betflow/.env"
CERT_CRT = "/opt/betflow/secrets/client-2048.crt"
CERT_KEY = "/opt/betflow/secrets/client-2048.key"


def load_env() -> None:
    if not Path(ENV_PATH).exists():
        raise SystemExit(f"Missing {ENV_PATH}")
    load_dotenv(ENV_PATH, override=True)


def req(name: str) -> str:
    v = (os.getenv(name) or "").strip()
    if not v:
        raise SystemExit(f"Missing env var: {name}")
    return v


def login(app_key: str, username: str, password: str) -> str:
    r = requests.post(
        IDENTITY_URL,
        headers={
            "X-Application": app_key,
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
        data={"username": username, "password": password},
        cert=(CERT_CRT, CERT_KEY),
        timeout=20,
    )
    r.raise_for_status()
    j = r.json()
    if j.get("loginStatus") != "SUCCESS":
        raise RuntimeError(f"Login failed: {j}")
    return j["sessionToken"]


def list_event_types(app_key: str, token: str) -> dict:
    payload = [{
        "jsonrpc": "2.0",
        "method": "SportsAPING/v1.0/listEventTypes",
        "params": {"filter": {}},
        "id": 1,
    }]
    r = requests.post(
        BETTING_JSONRPC_URL,
        headers={
            "X-Application": app_key,
            "X-Authentication": token,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        data=json.dumps(payload),
        timeout=20,
    )
    r.raise_for_status()
    data = r.json()
    return data[0] if isinstance(data, list) and data else {"unexpected": data}


def main() -> None:
    load_env()
    app_key = req("BETFAIR_APP_KEY")
    user = req("BETFAIR_USERNAME")
    pwd = req("BETFAIR_PASSWORD")

    print("Logging in...")
    token = login(app_key, user, pwd)
    print("Login SUCCESS")
    print("Session Token:", token)  # diagnostic only

    print("Calling listEventTypes...")
    resp = list_event_types(app_key, token)
    print("\nRaw response:")
    print(resp)

    if resp.get("error"):
        print("\nBetfair error:", resp["error"])
        raise SystemExit(1)

    print("\nEvent Types:")
    for item in (resp.get("result") or [])[:30]:
        et = item.get("eventType", {})
        print(f"- {et.get('id')}: {et.get('name')}")


if __name__ == "__main__":
    main()
