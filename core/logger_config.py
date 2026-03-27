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
ANSI_RESET = "\033[0m"
LEVEL_COLORS = {
    logging.DEBUG: "\033[36m",
    logging.INFO: "\033[32m",
    logging.WARNING: "\033[33m",
    logging.ERROR: "\033[31m",
    logging.CRITICAL: "\033[1;31m",
}


def _parse_level(value: str, fallback: int) -> int:
    try:
        return getattr(logging, value.upper())
    except AttributeError as e:
        logging.warning(f"Failed to parse log level: {e}")
        return fallback


class ColorFormatter(logging.Formatter):
    def __init__(self, fmt=None, datefmt=None, use_color=True):
        super().__init__(fmt=fmt, datefmt=datefmt)
        self.use_color = use_color

    def format(self, record):
        if not self.use_color:
            return super().format(record)

        color = LEVEL_COLORS.get(record.levelno, "")
        original_levelname = record.levelname
        original_name = record.name
        if color:
            record.levelname = f"{color}{record.levelname}{ANSI_RESET}"
            record.name = f"{color}{record.name}{ANSI_RESET}"
        try:
            return super().format(record)
        finally:
            record.levelname = original_levelname
            record.name = original_name


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
    use_color = hasattr(os.sys.stderr, "isatty") and os.sys.stderr.isatty() and "NO_COLOR" not in os.environ
    color_formatter = ColorFormatter(
        '%(asctime)s | %(levelname)s | %(name)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        use_color=use_color,
    )

    console_handler = logging.StreamHandler()
    console_handler.setLevel(console_level)
    console_handler.setFormatter(color_formatter)

    os.makedirs(LOGS_DIR, exist_ok=True)

    file_handler = logging.FileHandler(LOG_PATH)
    file_handler.setLevel(file_level)
    file_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    logger.propagate = False

    return logger
