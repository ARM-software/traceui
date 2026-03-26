import logging
import os
from datetime import datetime

LOG_LEVEL_ENV = "TRACEUI_LOG_LEVEL"
DEFAULT_CONSOLE_LEVEL = "INFO"
DEFAULT_FILE_LEVEL = "DEBUG"
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGS_DIR = os.path.join(REPO_ROOT, "logs")
LOG_TIMESTAMP = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
LOG_PATH = os.path.join(LOGS_DIR, f"traceui_{LOG_TIMESTAMP}.log")


def _parse_level(value: str, fallback: int) -> int:
    try:
        return getattr(logging, value.upper())
    except AttributeError as e:
        logging.warning(f"Failed to parse log level: {e}")
        return fallback


def setup_logger(name: str = "traceui") -> logging.Logger:
    """
    Create a logger with console and file handlers. Levels can be overridden via
    TRACEUI_LOG_LEVEL
    """
    logger = logging.getLogger(name)

    if logger.hasHandlers():
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)
            handler.close()

    console_level = _parse_level(os.getenv(LOG_LEVEL_ENV, DEFAULT_CONSOLE_LEVEL), logging.INFO)
    file_level = _parse_level(os.getenv(LOG_LEVEL_ENV, DEFAULT_FILE_LEVEL), logging.DEBUG)

    logger.setLevel(min(console_level, file_level))

    formatter = logging.Formatter(
        '%(asctime)s | %(levelname)s | %(name)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    console_handler = logging.StreamHandler()
    console_handler.setLevel(console_level)
    console_handler.setFormatter(formatter)

    os.makedirs(LOGS_DIR, exist_ok=True)

    file_handler = logging.FileHandler(LOG_PATH)
    file_handler.setLevel(file_level)
    file_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    logger.propagate = False

    return logger
