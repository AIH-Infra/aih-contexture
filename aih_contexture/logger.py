import logging
import warnings

from aih_contexture.runtime.console_text import sanitize_console_text
from aih_contexture.settings import settings


class ConsoleFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return sanitize_console_text(super().format(record))


def configure_logging():
    # Setup marker logger
    logger = get_logger()

    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = ConsoleFormatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    logger.setLevel(settings.LOGLEVEL)

    # Ignore future warnings
    warnings.simplefilter(action="ignore", category=FutureWarning)

    # Set component loglevels
    logging.getLogger("PIL").setLevel(logging.ERROR)
    logging.getLogger("fontTools.subset").setLevel(logging.ERROR)
    logging.getLogger("fontTools.ttLib.ttFont").setLevel(logging.ERROR)
    logging.getLogger("weasyprint").setLevel(logging.CRITICAL)


def get_logger():
    return logging.getLogger("marker")
