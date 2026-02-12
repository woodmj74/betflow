import os
from betflow.settings import load_settings
from betflow.logging import configure_logging, get_logger


def main() -> None:
    settings = load_settings()
    configure_logging(settings.log_level)

    log = get_logger("betflow")
    log.info("betflow_start", env=settings.env, cwd=os.getcwd())


if __name__ == "__main__":
    main()
