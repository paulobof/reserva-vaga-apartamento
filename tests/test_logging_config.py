"""Testes para logging_config.py - Formatters, LogContext, setup."""

import json
import logging
from unittest.mock import patch

import pytest

from app.logging_config import (
    JsonFormatter,
    LogContext,
    TextFormatter,
    correlation_id_var,
    generate_correlation_id,
    setup_logging,
)


def test_generate_correlation_id_is_unique():
    id1 = generate_correlation_id()
    id2 = generate_correlation_id()
    assert id1 != id2
    assert len(id1) == 32  # uuid4 hex


def test_generate_correlation_id_is_hex():
    cid = generate_correlation_id()
    int(cid, 16)  # Nao deve levantar ValueError


class TestJsonFormatter:
    def _make_record(self, msg="test", **kwargs):
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg=msg,
            args=(),
            exc_info=None,
        )
        for k, v in kwargs.items():
            setattr(record, k, v)
        return record

    def test_basic_format(self):
        formatter = JsonFormatter()
        record = self._make_record("Hello")
        output = formatter.format(record)
        data = json.loads(output)
        assert data["message"] == "Hello"
        assert data["level"] == "INFO"
        assert data["logger"] == "test.logger"
        assert "timestamp" in data
        assert "correlation_id" in data

    def test_includes_duration_ms(self):
        formatter = JsonFormatter()
        record = self._make_record(duration_ms=123.45)
        data = json.loads(formatter.format(record))
        assert data["duration_ms"] == 123.45

    def test_includes_reservation_id(self):
        formatter = JsonFormatter()
        record = self._make_record(reservation_id=42)
        data = json.loads(formatter.format(record))
        assert data["reservation_id"] == 42

    def test_includes_resource_id(self):
        formatter = JsonFormatter()
        record = self._make_record(resource_id=5)
        data = json.loads(formatter.format(record))
        assert data["resource_id"] == 5

    def test_includes_step(self):
        formatter = JsonFormatter()
        record = self._make_record(step="auth")
        data = json.loads(formatter.format(record))
        assert data["step"] == "auth"

    def test_includes_attempt(self):
        formatter = JsonFormatter()
        record = self._make_record(attempt=3)
        data = json.loads(formatter.format(record))
        assert data["attempt"] == 3

    def test_includes_http_fields(self):
        formatter = JsonFormatter()
        record = self._make_record(status_code=200, method="GET", path="/health")
        data = json.loads(formatter.format(record))
        assert data["status_code"] == 200
        assert data["method"] == "GET"
        assert data["path"] == "/health"

    def test_includes_exception(self):
        formatter = JsonFormatter()
        try:
            raise ValueError("test error")
        except ValueError:
            import sys

            record = logging.LogRecord(
                name="test",
                level=logging.ERROR,
                pathname="test.py",
                lineno=1,
                msg="Error occurred",
                args=(),
                exc_info=sys.exc_info(),
            )
        data = json.loads(formatter.format(record))
        assert "exception" in data
        assert "ValueError" in data["exception"]

    def test_correlation_id_from_context(self):
        formatter = JsonFormatter()
        token = correlation_id_var.set("abc12345")
        try:
            record = self._make_record()
            data = json.loads(formatter.format(record))
            assert data["correlation_id"] == "abc12345"
        finally:
            correlation_id_var.reset(token)


class TestTextFormatter:
    def _make_record(self, msg="test", **kwargs):
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg=msg,
            args=(),
            exc_info=None,
        )
        for k, v in kwargs.items():
            setattr(record, k, v)
        return record

    def test_basic_format(self):
        formatter = TextFormatter(datefmt="%Y-%m-%d %H:%M:%S")
        record = self._make_record("Hello world")
        output = formatter.format(record)
        assert "test.logger" in output
        assert "INFO" in output
        assert "Hello world" in output

    def test_includes_correlation_id(self):
        formatter = TextFormatter()
        token = correlation_id_var.set("deadbeef12345678")
        try:
            record = self._make_record()
            output = formatter.format(record)
            assert "cid=deadbeef" in output
        finally:
            correlation_id_var.reset(token)

    def test_includes_duration(self):
        formatter = TextFormatter()
        record = self._make_record(duration_ms=42.5)
        output = formatter.format(record)
        assert "duration=42ms" in output

    def test_includes_reservation_id(self):
        formatter = TextFormatter()
        record = self._make_record(reservation_id=7)
        output = formatter.format(record)
        assert "res_id=7" in output

    def test_includes_attempt(self):
        formatter = TextFormatter()
        record = self._make_record(attempt=5)
        output = formatter.format(record)
        assert "attempt=5" in output

    def test_no_extras_when_default_cid(self):
        formatter = TextFormatter()
        token = correlation_id_var.set("-")
        try:
            record = self._make_record()
            output = formatter.format(record)
            assert "cid=" not in output
        finally:
            correlation_id_var.reset(token)

    def test_includes_exception(self):
        formatter = TextFormatter()
        try:
            raise RuntimeError("boom")
        except RuntimeError:
            import sys

            record = logging.LogRecord(
                name="test",
                level=logging.ERROR,
                pathname="test.py",
                lineno=1,
                msg="Error",
                args=(),
                exc_info=sys.exc_info(),
            )
        output = formatter.format(record)
        assert "RuntimeError" in output


class TestSetupLogging:
    def test_configures_root_logger(self):
        with patch("app.logging_config.settings") as mock_settings:
            mock_settings.log_level = "DEBUG"
            mock_settings.log_format = "text"
            setup_logging()
            root = logging.getLogger()
            assert root.level == logging.DEBUG
            assert len(root.handlers) >= 1

    def test_json_format(self):
        with patch("app.logging_config.settings") as mock_settings:
            mock_settings.log_level = "INFO"
            mock_settings.log_format = "json"
            setup_logging()
            root = logging.getLogger()
            assert any(isinstance(h.formatter, JsonFormatter) for h in root.handlers)

    def test_text_format(self):
        with patch("app.logging_config.settings") as mock_settings:
            mock_settings.log_level = "INFO"
            mock_settings.log_format = "text"
            setup_logging()
            root = logging.getLogger()
            assert any(isinstance(h.formatter, TextFormatter) for h in root.handlers)

    def test_silences_noisy_loggers(self):
        with patch("app.logging_config.settings") as mock_settings:
            mock_settings.log_level = "DEBUG"
            mock_settings.log_format = "text"
            setup_logging()
            assert logging.getLogger("httpx").level == logging.WARNING
            assert logging.getLogger("sqlalchemy.engine").level == logging.WARNING


class TestLogContext:
    async def test_measures_duration(self):
        logger = logging.getLogger("test.context")
        async with LogContext(logger, "test_op"):
            pass  # Operacao instantanea
        # Nao deve levantar excecao

    async def test_logs_success(self):
        logger = logging.getLogger("test.context")
        with patch.object(logger, "info") as mock_info:
            async with LogContext(logger, "my_op", reservation_id=1):
                pass
            # Deve ter logado "started" e "completed"
            assert mock_info.call_count == 2
            assert "started" in mock_info.call_args_list[0][0][0]
            assert "completed" in mock_info.call_args_list[1][0][0]

    async def test_logs_error_on_exception(self):
        logger = logging.getLogger("test.context")
        with patch.object(logger, "info"), patch.object(logger, "error") as mock_error:
            with pytest.raises(ValueError, match="boom"):
                async with LogContext(logger, "fail_op"):
                    raise ValueError("boom")
            mock_error.assert_called_once()
            assert "failed" in mock_error.call_args[0][0]
