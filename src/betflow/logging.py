import logging
import structlog


_LEVELS = {
    "CRITICAL": logging.CRITICAL,
    "ERROR": logging.ERROR,
    "WARNING": logging.WARNING,
    "INFO": logging.INFO,
    "DEBUG": logging.DEBUG,
}


def configure_logging(level: str = "INFO") -> None:
    # Make stdlib logging behave (useful when libraries log)
    logging.basicConfig(level=_LEVELS.get(level.upper(), logging.INFO))

    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            _LEVELS.get(level.upper(), logging.INFO)
        ),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = "betflow"):
    return structlog.get_logger(name)
