"""
Structured logging configuration for GBADS.

Provides:
- correlation_id_var: ContextVar for propagating request/workflow IDs
- CorrelationIDFilter: injects correlation_id into every LogRecord
- configure_logging(): call once at startup to enable correlation-ID logging
"""
import contextvars
import logging
import sys

# Module-level ContextVar — set this at the start of each request / workflow node
correlation_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "correlation_id", default="-"
)


class CorrelationIDFilter(logging.Filter):
    """Injects ``correlation_id`` attribute into every LogRecord."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = correlation_id_var.get("-")
        return True


def configure_logging(level: int = logging.INFO, stream=None) -> None:
    """Configure root logger with correlation-ID format.

    Format: ``2024-01-01 12:00:00,000 [INFO] [cid=<id>] module.name: message``

    Call this once at application startup (FastAPI lifespan or CLI entry point).
    Calling it multiple times is safe — existing handlers are cleared first.
    """
    fmt = "%(asctime)s [%(levelname)s] [cid=%(correlation_id)s] %(name)s: %(message)s"
    handler = logging.StreamHandler(stream or sys.stderr)
    handler.addFilter(CorrelationIDFilter())
    handler.setFormatter(logging.Formatter(fmt, datefmt="%Y-%m-%d %H:%M:%S"))

    root = logging.getLogger()
    root.setLevel(level)
    # Clear any handlers configured before us (e.g. from uvicorn)
    root.handlers.clear()
    root.addHandler(handler)
