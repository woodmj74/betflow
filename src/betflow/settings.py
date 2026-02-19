from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


def _repo_root() -> Path:
    # /opt/betflow/src/betflow/settings.py -> /opt/betflow
    return Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    # General
    env: str

    # Betfair
    betfair_app_key: str
    betfair_username: str
    betfair_password: str
    betfair_cert_crt: Path
    betfair_cert_key: Path

    # HTTP / behaviour
    http_timeout_seconds: float = 15.0

    @staticmethod
    def load() -> "Settings":
        # Load .env from repo root by default
        root = _repo_root()
        load_dotenv(dotenv_path=root / ".env", override=False)

        env = os.getenv("BETFLOW_ENV", "dev").strip()

        app_key = (os.getenv("BETFAIR_APP_KEY") or "").strip()
        username = (os.getenv("BETFAIR_USERNAME") or "").strip()
        password = (os.getenv("BETFAIR_PASSWORD") or "").strip()

        # Sensible defaults if you keep certs in /opt/betflow/secrets
        cert_crt = os.getenv("BETFAIR_CERT_CRT", str(root / "secrets" / "client-2048.crt"))
        cert_key = os.getenv("BETFAIR_CERT_KEY", str(root / "secrets" / "client-2048.key"))

        missing = []
        if not app_key:
            missing.append("BETFAIR_APP_KEY")
        if not username:
            missing.append("BETFAIR_USERNAME")
        if not password:
            missing.append("BETFAIR_PASSWORD")

        if missing:
            raise RuntimeError(
                "Missing required environment variables: "
                + ", ".join(missing)
                + " (check your .env)"
            )

        cert_crt_path = Path(cert_crt).expanduser().resolve()
        cert_key_path = Path(cert_key).expanduser().resolve()

        if not cert_crt_path.exists():
            raise RuntimeError(f"Betfair cert not found: {cert_crt_path}")
        if not cert_key_path.exists():
            raise RuntimeError(f"Betfair key not found: {cert_key_path}")

        return Settings(
            env=env,
            betfair_app_key=app_key,
            betfair_username=username,
            betfair_password=password,
            betfair_cert_crt=cert_crt_path,
            betfair_cert_key=cert_key_path,
        )


# Singleton-style settings instance (loaded once on import)
settings = Settings.load()
