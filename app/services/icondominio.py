"""Client para comunicação com a API do iCondomínio.

Responsável por todo o fluxo de autenticação e reserva:
login → redirect → authenticate → warmup → condicao → conclusao.
"""

import asyncio
import html as html_mod
import logging
import re
import time
from datetime import date, datetime
from urllib.parse import urlparse

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.logging_config import LogContext
from app.models import AttemptLog, Reservation, Resource

logger = logging.getLogger("icond.client")

LOGIN_URL = "https://servicoacesso.webware.com.br/Aplicativo/Login/Usuario"
REDIRECT_URL = "https://servicoacesso.webware.com.br/Aplicativo/Redireciona"
BASE_URL = "https://www.icondominio.com.br"

MAX_ATTEMPTS = 60
RETRY_INTERVAL_SECONDS = 1
MAX_AUTH_HOPS = 20

_ATTR_RE = re.compile(r"""(\w+)\s*=\s*["']([^"']*)["']""")


def _extract_attr(attrs_str: str, attr_name: str) -> str | None:
    """Extract an HTML attribute value from an attribute string."""
    for m in _ATTR_RE.finditer(attrs_str):
        if m.group(1).lower() == attr_name.lower():
            return m.group(2)
    return None


class ICondominioClient:
    """Client HTTP para o portal iCondomínio.

    Gerencia o ciclo de vida do httpx.AsyncClient e executa
    o fluxo completo de reserva com retry loop.
    """

    def __init__(self) -> None:
        self.client: httpx.AsyncClient | None = None

    async def _ensure_client(self) -> httpx.AsyncClient:
        """Garante que o client HTTP está aberto e pronto para uso."""
        if self.client is None or self.client.is_closed:
            self.client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0),
                follow_redirects=False,
            )
        return self.client

    async def close(self) -> None:
        """Fecha o client HTTP liberando recursos."""
        if self.client and not self.client.is_closed:
            await self.client.aclose()

    async def login(self) -> tuple[str, str]:
        """Autentica no serviço de acesso e retorna credenciais de sessão.

        Returns:
            Tupla (NIU, Token) para uso nas próximas chamadas.

        Raises:
            RuntimeError: Se o login falhar (sem NIU/Token na resposta).
        """
        client = await self._ensure_client()
        start = time.perf_counter()

        resp = await client.post(
            LOGIN_URL,
            json={
                "APP": 34,
                "Login": settings.icond_login,
                "Senha": settings.icond_senha,
            },
            headers={"Content-Type": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()

        duration_ms = (time.perf_counter() - start) * 1000
        niu = data.get("NIU")
        token = data.get("Token")

        if not niu or not token:
            logger.error(
                "Login failed: missing NIU/Token in response",
                extra={"step": "login", "duration_ms": duration_ms},
            )
            raise RuntimeError(f"Login failed: {data}")

        niu = str(niu)
        logger.info(
            "Login OK in %.0fms",
            duration_ms,
            extra={"step": "login", "duration_ms": duration_ms},
        )
        return niu, token

    async def redirect(self, niu: str, token: str) -> str:
        """Obtém a URL de autenticação via endpoint de redirecionamento.

        Args:
            niu: Identificador do usuário retornado pelo login.
            token: Token de sessão retornado pelo login.

        Returns:
            URL de autenticação para o iCondomínio.

        Raises:
            RuntimeError: Se a resposta não contiver URL.
        """
        client = await self._ensure_client()
        start = time.perf_counter()

        resp = await client.post(
            REDIRECT_URL,
            json={"Id": 19, "VersaoAPP": "3.0"},
            headers={
                "Content-Type": "application/json",
                "NIU": niu,
                "Token": token,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        auth_url = data.get("URL") or data.get("Url")

        duration_ms = (time.perf_counter() - start) * 1000

        if not auth_url:
            logger.error(
                "Redirect failed: no URL in response",
                extra={"step": "redirect", "duration_ms": duration_ms},
            )
            raise RuntimeError(f"Redirect failed: {data}")

        logger.info(
            "Redirect OK in %.0fms",
            duration_ms,
            extra={"step": "redirect", "duration_ms": duration_ms},
        )
        return auth_url

    async def authenticate(self, auth_url: str) -> httpx.Cookies:
        """Segue a cadeia de redirects coletando cookies de sessão.

        Args:
            auth_url: URL de autenticação obtida do redirect.

        Returns:
            Cookie jar com todos os cookies de sessão coletados.
        """
        client = await self._ensure_client()
        cookies = httpx.Cookies()
        url = auth_url
        start = time.perf_counter()
        hop_count = 0

        for hop in range(MAX_AUTH_HOPS):
            resp = await client.get(url, cookies=cookies, follow_redirects=False)
            for cookie_name, cookie_value in resp.cookies.items():
                cookies.set(cookie_name, cookie_value)
            if resp.status_code in (301, 302, 303, 307, 308):
                location = resp.headers.get("location", "")
                if location.startswith("/"):
                    parsed = urlparse(url)
                    location = f"{parsed.scheme}://{parsed.netloc}{location}"
                url = location
                hop_count = hop + 1
                logger.debug("Auth hop %d -> %s", hop, url[:80])
            else:
                hop_count = hop + 1
                break

        duration_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "Auth OK: %d cookies in %d hops (%.0fms)",
            len(cookies.jar),
            hop_count,
            duration_ms,
            extra={"step": "auth", "duration_ms": duration_ms},
        )
        return cookies

    async def warmup(self, cookies: httpx.Cookies, recurso_id: int) -> None:
        """Aquece a sessão acessando páginas necessárias antes da reserva.

        Args:
            cookies: Cookies de sessão autenticados.
            recurso_id: ID do recurso a ser reservado.
        """
        client = await self._ensure_client()
        start = time.perf_counter()

        await client.get(f"{BASE_URL}/Reservas/Index", cookies=cookies, follow_redirects=True)
        await client.get(
            f"{BASE_URL}/Reservas/RecursoData/{recurso_id}",
            cookies=cookies,
            follow_redirects=True,
        )

        duration_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "Warmup OK for recurso %d (%.0fms)",
            recurso_id,
            duration_ms,
            extra={
                "step": "warmup",
                "resource_id": recurso_id,
                "duration_ms": duration_ms,
            },
        )

    async def get_condicao(
        self,
        cookies: httpx.Cookies,
        target_date: date,
        recurso_id: int,
        periodo_id: int,
    ) -> tuple[bool, dict[str, str]]:
        """Verifica disponibilidade e coleta hidden fields do formulário.

        Args:
            cookies: Cookies de sessão autenticados.
            target_date: Data alvo da reserva.
            recurso_id: ID do recurso.
            periodo_id: ID do período.

        Returns:
            Tupla (disponível, campos_hidden). Se indisponível, campos vazio.
        """
        client = await self._ensure_client()
        date_str = target_date.strftime("%d-%m-%Y")
        url = (
            f"{BASE_URL}/Reservas/Condicao"
            f"?data={date_str}&recurso={recurso_id}&periodo={periodo_id}&unidade="
        )
        start = time.perf_counter()
        resp = await client.get(url, cookies=cookies, follow_redirects=True)
        html = resp.text
        duration_ms = (time.perf_counter() - start) * 1000

        if "ReservaCancelada" in str(resp.url) or "não está disponível" in html.lower():
            logger.warning(
                "Date %s not available (%.0fms)",
                date_str,
                duration_ms,
                extra={"step": "condicao", "duration_ms": duration_ms},
            )
            return False, {}

        fields = {}
        # Parse ALL <input> elements and extract attributes robustly
        for input_match in re.finditer(r"<input\b([^>]*)>", html, re.IGNORECASE):
            attrs_str = input_match.group(1)
            attr_name = _extract_attr(attrs_str, "name")
            attr_type = (_extract_attr(attrs_str, "type") or "").lower()
            attr_value = _extract_attr(attrs_str, "value")

            if not attr_name:
                continue

            if attr_type == "hidden":
                fields[attr_name] = html_mod.unescape(attr_value) if attr_value else ""
            elif attr_type == "checkbox":
                # Check all checkboxes (simulate clicking "Concordo")
                fields[attr_name] = "on"

        if not fields:
            logger.warning(
                "No hidden fields found in Condicao response (%.0fms)",
                duration_ms,
                extra={"step": "condicao", "duration_ms": duration_ms},
            )
            return False, {}

        logger.info(
            "Condicao OK: %d fields parsed (%.0fms) - keys: %s",
            len(fields),
            duration_ms,
            ", ".join(fields.keys()),
            extra={"step": "condicao", "duration_ms": duration_ms},
        )
        return True, fields

    async def submit(self, cookies: httpx.Cookies, fields: dict[str, str]) -> tuple[bool, str]:
        """Submete o formulário de conclusão da reserva.

        Args:
            cookies: Cookies de sessão autenticados.
            fields: Hidden fields coletados do Condicao.

        Returns:
            Tupla (sucesso, snippet_html) com resultado da submissão.
        """
        client = await self._ensure_client()
        start = time.perf_counter()

        resp = await client.post(
            f"{BASE_URL}/Reservas/Conclusao?Length=8",
            data=fields,
            cookies=cookies,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            follow_redirects=True,
        )
        html = resp.text
        success = "reserva agendada com sucesso" in html.lower() or "sucesso" in html.lower()
        snippet = html[:500]
        duration_ms = (time.perf_counter() - start) * 1000

        log_fn = logger.info if success else logger.warning
        log_fn(
            "Submit %s (HTTP %d, %.0fms)",
            "OK" if success else "FAILED",
            resp.status_code,
            duration_ms,
            extra={"step": "conclusao", "duration_ms": duration_ms},
        )
        return success, snippet

    async def execute_reservation(
        self, db: AsyncSession, reservation: Reservation, resource: Resource
    ) -> bool:
        """Orquestra o fluxo completo de reserva com retry loop.

        Args:
            db: Sessão do banco de dados.
            reservation: Reserva a ser executada.
            resource: Recurso associado à reserva.

        Returns:
            True se a reserva foi confirmada com sucesso.
        """
        reservation.status = "executing"
        reservation.updated_at = datetime.now()
        await db.commit()

        total_start = time.perf_counter()
        res_extra = {
            "reservation_id": reservation.id,
            "resource_id": resource.recurso_id,
        }

        logger.info(
            "Starting reservation #%d: %s on %s",
            reservation.id,
            resource.name,
            reservation.target_date,
            extra=res_extra,
        )

        # Fase 1: Autenticação
        try:
            async with LogContext(logger, "auth_flow", **res_extra):
                niu, token = await self.login()
                auth_url = await self.redirect(niu, token)
                cookies = await self.authenticate(auth_url)
                await self.warmup(cookies, resource.recurso_id)

            await self._log_attempt(db, reservation, 0, "auth", True, "Auth OK")
        except Exception as e:
            await self._log_attempt(db, reservation, 0, "auth", False, error=str(e))
            reservation.status = "failed"
            reservation.result_message = f"Auth failed: {e}"
            reservation.updated_at = datetime.now()
            await db.commit()
            logger.error(
                "Reservation #%d auth failed: %s",
                reservation.id,
                e,
                extra=res_extra,
            )
            return False

        # Fase 2: Retry loop
        for attempt in range(1, MAX_ATTEMPTS + 1):
            reservation.attempt_count = attempt
            reservation.updated_at = datetime.now()
            await db.commit()

            attempt_extra = {**res_extra, "attempt": attempt}

            try:
                periodo_id = reservation.periodo_id or resource.periodo_id
                available, fields = await self.get_condicao(
                    cookies,
                    reservation.target_date,
                    resource.recurso_id,
                    periodo_id,
                )
                if not available:
                    await self._log_attempt(
                        db,
                        reservation,
                        attempt,
                        "condicao",
                        False,
                        error="Data não disponível ainda",
                    )
                    logger.debug(
                        "Attempt %d/%d: date not available yet",
                        attempt,
                        MAX_ATTEMPTS,
                        extra=attempt_extra,
                    )
                    if attempt < MAX_ATTEMPTS:
                        await asyncio.sleep(RETRY_INTERVAL_SECONDS)
                    continue

                await self._log_attempt(
                    db,
                    reservation,
                    attempt,
                    "condicao",
                    True,
                    snippet=f"{len(fields)} fields parsed",
                )

                success, snippet = await self.submit(cookies, fields)
                await self._log_attempt(
                    db, reservation, attempt, "conclusao", success, snippet=snippet
                )

                if success:
                    total_duration_ms = (time.perf_counter() - total_start) * 1000
                    reservation.status = "success"
                    reservation.result_message = "Reserva agendada com sucesso!"
                    reservation.updated_at = datetime.now()
                    await db.commit()
                    logger.info(
                        "Reservation #%d confirmed on attempt %d (total: %.0fms)",
                        reservation.id,
                        attempt,
                        total_duration_ms,
                        extra={**attempt_extra, "duration_ms": total_duration_ms},
                    )
                    return True

                if attempt < MAX_ATTEMPTS:
                    await asyncio.sleep(RETRY_INTERVAL_SECONDS)

            except Exception as e:
                await self._log_attempt(db, reservation, attempt, "error", False, error=str(e))
                logger.warning(
                    "Attempt %d/%d error: %s",
                    attempt,
                    MAX_ATTEMPTS,
                    e,
                    extra=attempt_extra,
                )
                if attempt < MAX_ATTEMPTS:
                    await asyncio.sleep(RETRY_INTERVAL_SECONDS)

        total_duration_ms = (time.perf_counter() - total_start) * 1000
        reservation.status = "failed"
        reservation.result_message = f"Falhou após {MAX_ATTEMPTS} tentativas"
        reservation.updated_at = datetime.now()
        await db.commit()
        logger.error(
            "Reservation #%d failed after %d attempts (total: %.0fms)",
            reservation.id,
            MAX_ATTEMPTS,
            total_duration_ms,
            extra={**res_extra, "duration_ms": total_duration_ms},
        )
        return False

    async def _log_attempt(
        self,
        db: AsyncSession,
        reservation: Reservation,
        attempt: int,
        step: str,
        success: bool,
        snippet: str | None = None,
        error: str | None = None,
    ) -> None:
        """Persiste uma tentativa no banco de dados.

        Args:
            db: Sessão do banco de dados.
            reservation: Reserva associada.
            attempt: Número da tentativa.
            step: Etapa do fluxo (login, auth, condicao, conclusao).
            success: Se a etapa foi bem-sucedida.
            snippet: Trecho da resposta HTML (opcional).
            error: Mensagem de erro (opcional).
        """
        log = AttemptLog(
            reservation_id=reservation.id,
            attempt_number=attempt,
            timestamp=datetime.now(),
            step=step,
            success=success,
            response_snippet=snippet[:500] if snippet else None,
            error_message=error,
        )
        db.add(log)
        await db.commit()
