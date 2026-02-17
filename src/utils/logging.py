"""
Structured logging configuration using Loguru
"""
import sys
from pathlib import Path
from loguru import logger

from src.config.settings import settings


def setup_logging(
    log_level: str = None,
    log_file: str = None,
    rotation: str = None,
    retention: str = None,
) -> None:
    """
    Configure loguru logging for the application

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
        log_file: Path to log file
        rotation: Log rotation size/interval (e.g. "10 MB", "1 day")
        retention: Log retention period (e.g. "30 days")
    """
    level = log_level or settings.log_level
    file_path = log_file or settings.log_file
    rot = rotation or settings.log_rotation
    ret = retention or settings.log_retention

    # Remove default handler
    logger.remove()

    # Console handler with colour
    logger.add(
        sys.stderr,
        level=level,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>"
        ),
        colorize=True,
    )

    # File handler
    log_path = Path(file_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logger.add(
        file_path,
        level=level,
        format=(
            "{time:YYYY-MM-DD HH:mm:ss} | "
            "{level: <8} | "
            "{name}:{function}:{line} | "
            "{message}"
        ),
        rotation=rot,
        retention=ret,
        compression="gz",
    )

    logger.info(f"Logging configured: level={level}, file={file_path}")


def get_logger(name: str):
    """Return a bound logger with a component name tag"""
    return logger.bind(component=name)
