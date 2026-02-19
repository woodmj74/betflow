from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple
import json
import time

import requests
import structlog

from betflow.settings import settings


log = structlog.get_logger(__name__)


class BetfairError(RuntimeError):
    """Base error for Betfair client issues."""


class BetfairAuthError(BetfairError):
    """Login/authentication problems."""


class BetfairRpcError(BetfairError):
    """JSON-RPC returned an error response."""


@dataclass(frozen=True)
class RpcErrorInfo:
    code: Optional[str]
    message: str
    request_uuid: Optional[str]


class BetfairClient:
    """
    Thin Betfair gateway:
      - cert login (session token)
      - JSON-RPC calls with minimal ergonomics
      - one-shot retry on INVALID_SESSION_INFORMATION
    """

    def __init__(self) -> None:
        self._session_token: Optional[str] = None
        self._session_token_set_at: Optional[float] = None

        self._app_key = settings.betfair_app_key
        self._username = settings.betfair_username
        self._password = settings.betfair_password
        self._cert_crt = str(settings.betfair_cert_crt)
        self._cert_key = str(settings.betfair_cert_key)

        self._login_url = "https://identitysso-cert.betfair.com/api/certlogin"
        self._rpc_url = "https://api.betfair.com/exchange/betting/json-rpc/v1"

        self._http = requests.Session()

    @property
    def session_token(self) -> Optional[str]:
        return self._session_token

    @session_token.setter
    def session_token(self, value: Optional[str]) -> None:
        self._session_token = value
        self._session_token_set_at = time.time() if value else None

    def login(self) -> str:
        """
        Perform Betfair cert login and store session token.
        Betfair cert login may return JSON (preferred) or key=value text.
        """
        log.info(
            "betfair.login.start",
            app_key_len=len(self._app_key or ""),
            cert_crt=self._cert_crt,
            cert_key=self._cert_key,
        )

        headers = {"X-Application": self._app_key, "Content-Type": "application/x-www-form-urlencoded"}
        data = {"username": self._username, "password": self._password}

        try:
            resp = self._http.post(
                self._login_url,
                data=data,
                headers=headers,
                cert=(self._cert_crt, self._cert_key),
                timeout=15,
            )
        except requests.RequestException as e:
            raise BetfairAuthError(f"Cert login request failed: {e}") from e

        if resp.status_code != 200:
            raise BetfairAuthError(f"Cert login HTTP {resp.status_code}: {resp.text[:300]}")

        token, status, raw = self._parse_cert_login_response(resp)
        if status != "SUCCESS" or not token:
            raise BetfairAuthError(f"Cert login failed: status={status} body={raw[:300]}")

        self.session_token = token
        log.info("betfair.login.ok")
        return token

    def rpc(self, method: str, params: Dict[str, Any]) -> Any:
        """
        JSON-RPC call with retry-once behaviour if session is invalid/expired.
        """
        if not self.session_token:
            self.login()

        # 1st attempt
        result, err = self._rpc_once(method, params)
        if err is None:
            return result

        if err.code == "INVALID_SESSION_INFORMATION":
            log.warning("betfair.rpc.invalid_session.retrying", method=method, request_uuid=err.request_uuid)
            self.login()  # re-auth once
            # 2nd attempt
            result2, err2 = self._rpc_once(method, params)
            if err2 is None:
                log.info("betfair.rpc.retry.success", method=method)
                return result2

            raise BetfairRpcError(
                f"JSON-RPC failed after retry: code={err2.code} message={err2.message} uuid={err2.request_uuid}"
            )

        raise BetfairRpcError(f"JSON-RPC failed: code={err.code} message={err.message} uuid={err.request_uuid}")

    # -------------------------
    # Internals
    # -------------------------

    def _rpc_once(self, method: str, params: Dict[str, Any]) -> Tuple[Any, Optional[RpcErrorInfo]]:
        headers = {
            "X-Application": self._app_key,
            "X-Authentication": self.session_token or "",
            "Content-Type": "application/json",
        }

        payload = {
            "jsonrpc": "2.0",
            "method": f"SportsAPING/v1.0/{method}",
            "params": params,
            "id": 1,
        }

        log.debug("betfair.rpc.call", method=method)

        try:
            resp = self._http.post(self._rpc_url, headers=headers, json=payload, timeout=20)
        except requests.RequestException as e:
            return None, RpcErrorInfo(code="HTTP_REQUEST_FAILED", message=str(e), request_uuid=None)

        if resp.status_code != 200:
            return None, RpcErrorInfo(
                code=f"HTTP_{resp.status_code}",
                message=resp.text[:300],
                request_uuid=None,
            )

        try:
            data = resp.json()
        except json.JSONDecodeError:
            return None, RpcErrorInfo(code="BAD_JSON", message=resp.text[:300], request_uuid=None)

        if isinstance(data, dict) and "error" in data:
            err = self._extract_rpc_error(data.get("error"))
            return None, err

        if isinstance(data, dict) and "result" in data:
            return data["result"], None

        return None, RpcErrorInfo(code="UNKNOWN_RESPONSE", message=str(data)[:300], request_uuid=None)

    def _extract_rpc_error(self, err_obj: Any) -> RpcErrorInfo:
        code = None
        message = "Unknown error"
        request_uuid = None

        try:
            if isinstance(err_obj, dict):
                message = str(err_obj.get("message") or message)

                data = err_obj.get("data") if isinstance(err_obj.get("data"), dict) else {}
                aping = data.get("APINGException") if isinstance(data.get("APINGException"), dict) else {}

                code = aping.get("errorCode") or data.get("errorCode") or None
                request_uuid = aping.get("requestUUID") or data.get("requestUUID") or None

        except Exception:
            pass

        return RpcErrorInfo(code=code, message=message, request_uuid=request_uuid)

    def _parse_cert_login_response(self, resp: requests.Response) -> Tuple[Optional[str], str, str]:
        raw = resp.text or ""

        try:
            j = resp.json()
            if isinstance(j, dict):
                status = str(j.get("loginStatus", "UNKNOWN"))
                token = j.get("sessionToken")
                return token, status, raw
        except Exception:
            pass

        status = "UNKNOWN"
        token = None
        for line in raw.splitlines():
            if "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip()
            if k == "loginStatus":
                status = v
            if k == "sessionToken":
                token = v

        return token, status, raw
