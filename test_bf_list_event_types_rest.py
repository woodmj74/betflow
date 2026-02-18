from __future__ import annotations

import json
import os
import requests
from dotenv import load_dotenv

CERT_CRT = "/opt/betflow/secrets/client-2048.crt"
CERT_KEY = "/opt/betflow/secrets/client-2048.key"

SSO_CERTLOGIN_URL = "https://identitysso-cert.betfair.com/api/certlogin"
REST_LIST_EVENT_TYPES_URL = "https://api.betfair.com/exchange/betting/rest/v1.0/listEventTypes/"

def env(name: str) -> str:
    return (os.getenv(name) or "").strip()

def mask(s: str, n: int = 8) -> str:
    return "****" + s[-n:] if s else "<missing>"

def login(app_key: str, username: str, password: str) -> str:
    r = requests.post(
        SSO_CERTLOGIN_URL,
        headers={"X-Application": app_key, "Content-Type": "application/x-www-form-urlencoded"},
        data={"username": username, "password": password},
        cert=(CERT_CRT, CERT_KEY),
        timeout=20,
    )
    r.raise_for_status()
    j = r.json()
    if j.get("loginStatus") != "SUCCESS":
        raise RuntimeError(f"Login failed: {j}")
    return j["sessionToken"]

def list_event_types_rest(app_key: str, session_token: str) -> dict:
    # REST expects a JSON body and these headers
    r = requests.post(
        REST_LIST_EVENT_TYPES_URL,
        headers={
            "X-Application": app_key,
            "X-Authentication": session_token,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        data=json.dumps({"filter": {}}),
        timeout=20,
    )
    if r.status_code != 200:
        print("HTTP:", r.status_code)
        print("Response headers:", dict(r.headers))
        print("Response text:", r.text[:1000])
        r.raise_for_status()
    return r.json()


def main() -> None:
    load_dotenv("/opt/betflow/.env")

    app_key = env("BETFLOW_API_KEY") or env("BETFAIR_APP_KEY")
    username = env("BETFAIR_USERNAME")
    password = env("BETFAIR_PASSWORD")

    print("Config:")
    print("  App key:", mask(app_key))
    print("  Username:", username or "<missing>")
    print("  Password:", "<set>" if password else "<missing>")

    print("\nLogging in...")
    token = login(app_key, username, password)
    print("Login OK. Token:", mask(token, 10))

    print("\nCalling REST listEventTypes...")
    resp = list_event_types_rest(app_key, token)

    print("\nEvent Types Returned:")
    for item in resp:
        et = item.get("eventType", {})
        print(f"- {et.get('name')} (id: {et.get('id')})")

if __name__ == "__main__":
    main()
