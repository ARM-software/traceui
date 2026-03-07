import logging
import os

LOG_LEVEL_ENV = "TRACEUI_LOG_LEVEL"
DEFAULT_CONSOLE_LEVEL = "INFO"
DEFAULT_FILE_LEVEL = "DEBUG"


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
        logger.handlers.clear()

    console_level = _parse_level(os.getenv(LOG_LEVEL_ENV, DEFAULT_CONSOLE_LEVEL), logging.INFO)
    file_level = _parse_level(os.getenv(LOG_LEVEL_ENV, DEFAULT_FILE_LEVEL), logging.DEBUG)

    logger.setLevel(min(console_level, file_level))

    formatter = logging.Formatter('%(levelname)s | %(name)s | %(message)s')

    console_handler = logging.StreamHandler()
    console_handler.setLevel(console_level)
    console_handler.setFormatter(formatter)

    file_handler = logging.FileHandler('traceui.log')
    file_handler.setLevel(file_level)
    file_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger
