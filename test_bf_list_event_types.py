from __future__ import annotations

import json
import os
from typing import Any

import requests
from dotenv import load_dotenv

CERT_CRT = "/opt/betflow/secrets/client-2048.crt"
CERT_KEY = "/opt/betflow/secrets/client-2048.key"

SSO_CERTLOGIN_URL = "https://identitysso-cert.betfair.com/api/certlogin"
EXCHANGE_JSONRPC_URL = "https://api.betfair.com/exchange/betting/json-rpc/v1"

SYSTEM_CA_BUNDLE = "/etc/ssl/certs/ca-certificates.crt"


def _get_env(name: str) -> str:
    """Read an env var and strip whitespace. Return empty string if missing."""
    return (os.getenv(name) or "").strip()


def _mask(s: str, show_last: int = 8) -> str:
    if not s:
        return "<missing>"
    if len(s) <= show_last:
        return "****" + s
    return "****" + s[-show_last:]


def login(app_key: str, username: str, password: str) -> str:
    headers = {
        "X-Application": app_key,
        "Content-Type": "application/x-www-form-urlencoded",
    }
    data = {"username": username, "password": password}

    r = requests.post(
        SSO_CERTLOGIN_URL,
        headers=headers,
        data=data,
        cert=(CERT_CRT, CERT_KEY),
        # If your container ever has CA path weirdness, uncomment:
        # verify=SYSTEM_CA_BUNDLE,
        timeout=20,
    )
    r.raise_for_status()

    j = r.json()
    if j.get("loginStatus") != "SUCCESS":
        raise RuntimeError(f"Login failed: {j}")

    token = j.get("sessionToken", "")
    if not token:
        raise RuntimeError(f"Login response missing sessionToken: {j}")

    return token


def call_list_event_types(app_key: str, session_token: str) -> dict[str, Any]:
    headers = {
        "X-Application": app_key,
        "X-Authentication": session_token,
        "Content-Type": "application/json",
    }

    payload = {
        "jsonrpc": "2.0",
        "method": "SportsAPING/v1.0/listEventTypes",
        "params": {"filter": {}},
        "id": 1,
    }

    r = requests.post(
        EXCHANGE_JSONRPC_URL,
        headers=headers,
        data=json.dumps(payload),
        # If your container ever has CA path weirdness, uncomment:
        # verify=SYSTEM_CA_BUNDLE,
        timeout=20,
    )
    r.raise_for_status()
    return r.json()


def main() -> None:
    load_dotenv("/opt/betflow/.env")

    # Accept either name, but always strip (kills hidden whitespace)
    app_key = _get_env("BETFLOW_API_KEY") or _get_env("BETFAIR_APP_KEY")
    username = _get_env("BETFAIR_USERNAME")
    password = _get_env("BETFAIR_PASSWORD")

    print("Config check:")
    print("  App key:", _mask(app_key))
    print("  Username:", username or "<missing>")
    print("  Password:", "<set>" if password else "<missing>")
    print("  Cert CRT exists:", os.path.exists(CERT_CRT))
    print("  Cert KEY exists:", os.path.exists(CERT_KEY))

    if not app_key:
        raise SystemExit("Missing app key env var (BETFLOW_API_KEY or BETFAIR_APP_KEY).")
    if not username or not password:
        raise SystemExit("Missing BETFAIR_USERNAME and/or BETFAIR_PASSWORD in /opt/betflow/.env")
    if not (os.path.exists(CERT_CRT) and os.path.exists(CERT_KEY)):
        raise SystemExit("Missing cert files in /opt/betflow/secrets/")

    print("\nLogging in...")
    token = login(app_key, username, password)
    print("Login SUCCESS. Session token:", _mask(token, show_last=10))

    print("\nCalling listEventTypes...")
    response = call_list_event_types(app_key, token)

    # Handle JSON-RPC success vs error cleanly
    if "error" in response:
        print("\nJSON-RPC ERROR response:")
        print(json.dumps(response, indent=2))
        raise SystemExit(1)

    result = response.get("result")
    if not isinstance(result, list):
        print("\nUnexpected response shape:")
        print(json.dumps(response, indent=2))
        raise SystemExit(1)

    print("\nEvent Types Returned:")
    for item in result:
        et = item.get("eventType", {})
        name = et.get("name")
        eid = et.get("id")
        if name and eid is not None:
            print(f"- {name} (id: {eid})")


if __name__ == "__main__":
    main()
