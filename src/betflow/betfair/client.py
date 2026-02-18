from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

import requests

from betflow.logging import get_logger
from betflow.settings import Settings


IDENTITY_CERT_LOGIN_URL = "https://identitysso-cert.betfair.com/api/certlogin"
API_JSONRPC_URL = "https://api.betfair.com/exchange/betting/json-rpc/v1"


@dataclass
class BetfairSession:
    session_token: str
    issued_at_epoch: float


class BetfairClient:
    """
    Thin Betfair API gateway:
      - cert login
      - JSON-RPC calls
      - minimal session caching
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self.log = get_logger("betfair.client")
        self._session: Optional[BetfairSession] = None
        self._http = requests.Session()
        self._http.headers.update({"X-Application": self.settings.betfair_app_key})

    def _parse_login_response(self, text: str) -> Dict[str, str]:
        """
        Betfair certlogin historically returned key=value lines, but can also return JSON.
        We support both.
        """
        raw = text.strip()

        # Try JSON first
        if raw.startswith("{") and raw.endswith("}"):
            try:
                obj = json.loads(raw)
                # Ensure string keys/values (sessionToken/loginStatus)
                return {str(k): "" if v is None else str(v) for k, v in obj.items()}
            except json.JSONDecodeError:
                pass  # fall through to key=value parsing

        # Fallback: key=value per line
        data: Dict[str, str] = {}
        for line in raw.splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                data[k.strip()] = v.strip()
        return data

    def login(self) -> str:
        """Certificate login; stores session token in memory."""
        self.log.info(
            "login.start",
            username=self.settings.betfair_username,
            cert_crt=str(self.settings.betfair_cert_crt),
            cert_key=str(self.settings.betfair_cert_key),
            app_key_len=len(self.settings.betfair_app_key),
        )

        payload = {
            "username": self.settings.betfair_username,
            "password": self.settings.betfair_password,
        }

        try:
            r = self._http.post(
                IDENTITY_CERT_LOGIN_URL,
                data=payload,
                cert=(str(self.settings.betfair_cert_crt), str(self.settings.betfair_cert_key)),
                timeout=self.settings.http_timeout_seconds,
            )
        except requests.RequestException as e:
            self.log.error("login.http_error", error=str(e))
            raise

        if r.status_code != 200:
            self.log.error("login.http_status", status=r.status_code, body=r.text[:500])
            raise RuntimeError(f"Betfair login failed HTTP {r.status_code}")

        body = r.text.strip()
        data = self._parse_login_response(body)

        status = data.get("loginStatus")
        if status != "SUCCESS":
            self.log.error("login.failed", loginStatus=status, raw=body[:500])
            raise RuntimeError(f"Betfair login failed: {status}")

        token = data.get("sessionToken")
        if not token:
            self.log.error("login.missing_token", raw=body[:500])
            raise RuntimeError("Betfair login succeeded but no sessionToken returned")

        self._session = BetfairSession(session_token=token, issued_at_epoch=time.time())
        self._http.headers.update({"X-Authentication": token})

        self.log.info("login.success")
        return token

    def ensure_session(self) -> str:
        """Simple 'make sure we have a token' gate."""
        if self._session and self._session.session_token:
            return self._session.session_token
        return self.login()

    def jsonrpc(self, method: str, params: Dict[str, Any]) -> Any:
        """
        JSON-RPC call. Returns the 'result' payload or raises on error.
        """
        self.ensure_session()

        payload = {
            "jsonrpc": "2.0",
            "method": f"SportsAPING/v1.0/{method}",
            "params": params,
            "id": 1,
        }

        self.log.info("rpc.call", method=method)

        try:
            r = self._http.post(
                API_JSONRPC_URL,
                json=payload,
                timeout=self.settings.http_timeout_seconds,
            )
        except requests.RequestException as e:
            self.log.error("rpc.http_error", method=method, error=str(e))
            raise

        if r.status_code != 200:
            self.log.error("rpc.http_status", method=method, status=r.status_code, body=r.text[:500])
            raise RuntimeError(f"Betfair RPC failed HTTP {r.status_code}")

        data = r.json()
        if "error" in data and data["error"]:
            self.log.error("rpc.error", method=method, error=data["error"])
            raise RuntimeError(f"Betfair RPC error: {data['error']}")

        return data.get("result")

    # Convenience
    def list_event_types(self) -> Any:
        return self.jsonrpc("listEventTypes", {"filter": {}})
