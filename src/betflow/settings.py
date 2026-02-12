from pydantic import BaseModel, Field
from dotenv import load_dotenv
import os


class Settings(BaseModel):
    env: str = Field(default="dev", description="Environment name, e.g. dev/prod")
    log_level: str = Field(default="INFO", description="Log level")

    # Later (Phase 0/1): DB + Betfair creds go here
    # db_dsn: str = Field(default="postgresql://...")
    # betfair_username: str | None = None


def load_settings() -> Settings:
    # Load .env into process env (no-op if missing)
    load_dotenv()

    return Settings(
        env=os.getenv("BETFLOW_ENV", "dev"),
        log_level=os.getenv("BETFLOW_LOG_LEVEL", "INFO"),
    )
