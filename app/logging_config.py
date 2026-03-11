"""Configuração centralizada de logging com suporte a JSON (produção) e texto (dev)."""

import json
import logging
import sys
import time
import uuid
from contextvars import ContextVar

from app.config import settings

# Context var para correlation ID (rastreia uma requisição entre camadas)
correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="-")


class JsonFormatter(logging.Formatter):
    """Formatter que emite logs em JSON estruturado para agregadores (Loki, ELK, etc.)."""

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": (
                self.formatTime(record, "%Y-%m-%dT%H:%M:%S.") + f"{int(record.msecs):03d}Z"
            ),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": correlation_id_var.get("-"),
        }

        if hasattr(record, "duration_ms"):
            log_data["duration_ms"] = record.duration_ms
        if hasattr(record, "reservation_id"):
            log_data["reservation_id"] = record.reservation_id
        if hasattr(record, "resource_id"):
            log_data["resource_id"] = record.resource_id
        if hasattr(record, "step"):
            log_data["step"] = record.step
        if hasattr(record, "attempt"):
            log_data["attempt"] = record.attempt
        if hasattr(record, "status_code"):
            log_data["status_code"] = record.status_code
        if hasattr(record, "method"):
            log_data["method"] = record.method
        if hasattr(record, "path"):
            log_data["path"] = record.path

        if record.exc_info and record.exc_info[1]:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data, ensure_ascii=False)


class TextFormatter(logging.Formatter):
    """Formatter legível para desenvolvimento local."""

    def format(self, record: logging.LogRecord) -> str:
        cid = correlation_id_var.get("-")
        ts = self.formatTime(record)
        base = f"{ts} [{record.name}] {record.levelname}: {record.getMessage()}"

        extras = []
        if cid != "-":
            extras.append(f"cid={cid[:8]}")
        if hasattr(record, "duration_ms"):
            extras.append(f"duration={record.duration_ms:.0f}ms")
        if hasattr(record, "reservation_id"):
            extras.append(f"res_id={record.reservation_id}")
        if hasattr(record, "attempt"):
            extras.append(f"attempt={record.attempt}")

        if extras:
            base += f" ({', '.join(extras)})"

        if record.exc_info and record.exc_info[1]:
            base += "\n" + self.formatException(record.exc_info)

        return base


def setup_logging() -> None:
    """Configura logging global baseado nas variáveis de ambiente."""
    root = logging.getLogger()
    root.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))

    # Remove handlers existentes
    root.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)

    if settings.log_format == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(TextFormatter(datefmt="%Y-%m-%d %H:%M:%S"))

    root.addHandler(handler)

    # Silenciar loggers verbosos de terceiros
    for noisy_logger in ("httpx", "httpcore", "sqlalchemy.engine", "apscheduler", "aiosqlite"):
        logging.getLogger(noisy_logger).setLevel(logging.WARNING)


def generate_correlation_id() -> str:
    """Gera um correlation ID único para rastrear uma operação."""
    return uuid.uuid4().hex


class LogContext:
    """Context manager para medir duração de operações e logar com extras.

    Args:
        logger: Logger a ser utilizado.
        operation: Nome da operação sendo medida.
        **extras: Campos extras adicionados ao log (reservation_id, step, etc.).

    Exemplo:
        async with LogContext(logger, "login", reservation_id=1):
            await do_login()
    """

    def __init__(self, logger: logging.Logger, operation: str, **extras: object):
        self.logger = logger
        self.operation = operation
        self.extras = extras
        self.start_time = 0.0

    async def __aenter__(self) -> "LogContext":
        self.start_time = time.perf_counter()
        self.logger.info(
            "%s started",
            self.operation,
            extra=self.extras,
        )
        return self

    async def __aexit__(
        self,
        exc_type: type | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        duration_ms = (time.perf_counter() - self.start_time) * 1000
        extras = {**self.extras, "duration_ms": duration_ms}

        if exc_type:
            self.logger.error(
                "%s failed after %.0fms: %s",
                self.operation,
                duration_ms,
                exc_val,
                extra=extras,
                exc_info=True,
            )
        else:
            self.logger.info(
                "%s completed in %.0fms",
                self.operation,
                duration_ms,
                extra=extras,
            )
