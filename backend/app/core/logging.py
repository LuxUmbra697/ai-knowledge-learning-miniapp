"""One stdout pipeline; container rotation owns retention, not application files."""
import logging
import sys

import structlog


def configure_logging(level: str) -> None:
    numeric_level = logging.getLevelNamesMapping()[level]
    logging.basicConfig(level=numeric_level, format='%(message)s', stream=sys.stdout)
    logging.getLogger().setLevel(numeric_level)
    for name in ('uvicorn.error', 'httpx', 'httpcore', 'openai'):
        logging.getLogger(name).setLevel(numeric_level)
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt='iso', utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=False,
    )
