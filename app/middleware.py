"""Middleware de observabilidade: request logging, correlation ID, timing."""

import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.logging_config import correlation_id_var, generate_correlation_id

logger = logging.getLogger("icond.http")


class ObservabilityMiddleware(BaseHTTPMiddleware):
    """Middleware que adiciona correlation ID, mede duração e loga cada request.

    Logs gerados:
        - INFO: request recebido (method, path)
        - INFO: response enviado (method, path, status, duração)
        - WARNING: responses 4xx
        - ERROR: responses 5xx
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        correlation_id = request.headers.get("X-Correlation-ID", generate_correlation_id())
        correlation_id_var.set(correlation_id)

        start_time = time.perf_counter()
        method = request.method
        path = request.url.path

        # Não logar health check para não poluir
        is_health = path == "/health"

        if not is_health:
            logger.info(
                "%s %s",
                method,
                path,
                extra={"method": method, "path": path},
            )

        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.exception(
                "%s %s 500 %.0fms (unhandled exception)",
                method,
                path,
                duration_ms,
                extra={
                    "method": method,
                    "path": path,
                    "status_code": 500,
                    "duration_ms": duration_ms,
                },
            )
            raise

        duration_ms = (time.perf_counter() - start_time) * 1000

        response.headers["X-Correlation-ID"] = correlation_id
        response.headers["X-Response-Time"] = f"{duration_ms:.0f}ms"

        if not is_health:
            status_code = response.status_code
            log_extra = {
                "method": method,
                "path": path,
                "status_code": status_code,
                "duration_ms": duration_ms,
            }

            if status_code >= 500:
                logger.error(
                    "%s %s %d %.0fms",
                    method,
                    path,
                    status_code,
                    duration_ms,
                    extra=log_extra,
                )
            elif status_code >= 400:
                logger.warning(
                    "%s %s %d %.0fms",
                    method,
                    path,
                    status_code,
                    duration_ms,
                    extra=log_extra,
                )
            else:
                logger.info(
                    "%s %s %d %.0fms",
                    method,
                    path,
                    status_code,
                    duration_ms,
                    extra=log_extra,
                )

        return response
