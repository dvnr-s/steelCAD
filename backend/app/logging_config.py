"""
Logging configuration for the SteelCAD API.

Stdlib logging only — no extra dependencies. Emits a single-line, level-prefixed
format that is readable in `docker compose logs` and easy to grep. Log level is
controlled by the LOG_LEVEL environment variable (default: INFO).
"""
import logging
import os
import sys

_CONFIGURED = False


def configure_logging() -> None:
    """Configure root logging once. Safe to call multiple times (idempotent)."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    level = os.getenv("LOG_LEVEL", "INFO").upper()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    # Tame uvicorn's duplicate access logging — we do our own request logging.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Return a module-scoped logger (configures logging on first use)."""
    configure_logging()
    return logging.getLogger(name)
