"""Utility helpers for structured logging and fault-tolerant retry logic."""

import functools
import logging
from pathlib import Path
import sys
import time
from typing import Any, Callable, Tuple, Type, TypeVar

from config.settings import settings

F = TypeVar("F", bound=Callable[..., Any])

_LOGGER_INITIALIZED = False


def setup_logger(name: str = "olist_dw", log_file: Path = settings.LOGS_DIR / "pipeline.log") -> logging.Logger:
    """Configures and returns a thread-safe logger writing to both console and log file.

    Args:
        name: Logger name.
        log_file: Path to the log file.

    Returns:
        logging.Logger: Configured logger instance.
    """
    global _LOGGER_INITIALIZED
    logger = logging.getLogger(name)

    # Convert string level to logging level
    level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    logger.setLevel(level)

    # Avoid adding duplicate handlers if already configured
    if not logger.handlers:
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] [%(name)s:%(filename)s:%(lineno)d]: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        # Console Handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        # File Handler
        try:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(log_file, encoding="utf-8")
            file_handler.setLevel(level)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        except Exception as exc:
            console_handler.setLevel(level)
            logger.warning("Could not initialize file logger at %s: %s", log_file, exc)

        logger.propagate = False

    return logger


logger = setup_logger()


def retry_operation(
    max_attempts: int = 3,
    delay: float = 2.0,
    backoff: float = 2.0,
    exceptions: Tuple[Type[BaseException], ...] = (Exception,),
) -> Callable[[F], F]:
    """Decorator that retries a function call using exponential backoff upon specified exceptions.

    Args:
        max_attempts: Maximum number of execution attempts before re-raising.
        delay: Initial sleep duration in seconds between retries.
        backoff: Multiplier applied to delay after each retry attempt.
        exceptions: Tuple of exception classes that trigger a retry.

    Returns:
        Decorated callable with retry logic.
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            current_delay = delay
            last_exception: Optional[BaseException] = None

            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as exc:
                    last_exception = exc
                    if attempt == max_attempts:
                        logger.error(
                            "Operation %s failed permanently after %d attempts. Error: %s",
                            func.__name__,
                            attempt,
                            exc,
                        )
                        raise
                    logger.warning(
                        "Operation %s failed attempt %d/%d with error: %s. Retrying in %.1f seconds...",
                        func.__name__,
                        attempt,
                        max_attempts,
                        exc,
                        current_delay,
                    )
                    time.sleep(current_delay)
                    current_delay *= backoff

            if last_exception:
                raise last_exception

        return wrapper  # type: ignore

    return decorator
