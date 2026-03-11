import asyncio
import logging
import re
from datetime import date, datetime

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import AttemptLog, Reservation, Resource

logger = logging.getLogger("icond.client")

LOGIN_URL = "https://servicoacesso.webware.com.br/Aplicativo/Login/Usuario"
REDIRECT_URL = "https://servicoacesso.webware.com.br/Aplicativo/Redireciona"
BASE_URL = "https://www.icondominio.com.br"


class ICondominioClient:
    def __init__(self):
        self.client: httpx.AsyncClient | None = None

    async def _ensure_client(self):
        if self.client is None or self.client.is_closed:
            self.client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0),
                follow_redirects=False,
            )
        return self.client

    async def close(self):
        if self.client and not self.client.is_closed:
            await self.client.aclose()

    async def login(self) -> tuple[str, str]:
        """Step 1: POST login, returns (NIU, Token)."""
        client = await self._ensure_client()
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
        niu = data.get("NIU")
        token = data.get("Token")
        if not niu or not token:
            raise RuntimeError(f"Login failed: {data}")
        niu = str(niu)
        logger.info("Login OK - NIU=%s", niu[:12])
        return niu, token

    async def redirect(self, niu: str, token: str) -> str:
        """Step 2: POST Redireciona, returns auth URL."""
        client = await self._ensure_client()
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
        if not auth_url:
            raise RuntimeError(f"Redirect failed: {data}")
        logger.info("Redirect OK - URL obtained")
        return auth_url

    async def authenticate(self, auth_url: str) -> httpx.Cookies:
        """Step 3: Follow redirect chain manually, collecting cookies."""
        client = await self._ensure_client()
        cookies = httpx.Cookies()
        url = auth_url
        for hop in range(20):
            resp = await client.get(url, cookies=cookies, follow_redirects=False)
            for cookie_name, cookie_value in resp.cookies.items():
                cookies.set(cookie_name, cookie_value)
            if resp.status_code in (301, 302, 303, 307, 308):
                location = resp.headers.get("location", "")
                if location.startswith("/"):
                    from urllib.parse import urlparse

                    parsed = urlparse(url)
                    location = f"{parsed.scheme}://{parsed.netloc}{location}"
                url = location
                logger.debug("Hop %d -> %s", hop, url[:80])
            else:
                break
        logger.info("Auth OK - %d cookies captured", len(cookies.jar))
        return cookies

    async def warmup(self, cookies: httpx.Cookies, recurso_id: int):
        """Step 4: Hit Index + RecursoData to warm up session."""
        client = await self._ensure_client()
        await client.get(
            f"{BASE_URL}/Reservas/Index", cookies=cookies, follow_redirects=True
        )
        await client.get(
            f"{BASE_URL}/Reservas/RecursoData/{recurso_id}",
            cookies=cookies,
            follow_redirects=True,
        )
        logger.info("Warmup OK for recurso %d", recurso_id)

    async def get_condicao(
        self,
        cookies: httpx.Cookies,
        target_date: date,
        recurso_id: int,
        periodo_id: int,
    ) -> tuple[bool, dict[str, str]]:
        """Step 5: GET Condicao, parse hidden fields. Returns (available, fields)."""
        client = await self._ensure_client()
        date_str = target_date.strftime("%d-%m-%Y")
        url = (
            f"{BASE_URL}/Reservas/Condicao"
            f"?data={date_str}&recurso={recurso_id}&periodo={periodo_id}&unidade="
        )
        resp = await client.get(url, cookies=cookies, follow_redirects=True)
        html = resp.text

        if "ReservaCancelada" in str(resp.url) or "não está disponível" in html.lower():
            logger.warning("Date %s not available", date_str)
            return False, {}

        fields = {}
        for match in re.finditer(
            r'<input[^>]+type=["\']hidden["\'][^>]*name=["\']([^"\']+)["\'][^>]*value=["\']([^"\']*)["\']',
            html,
            re.IGNORECASE,
        ):
            fields[match.group(1)] = match.group(2)

        # Also try reversed order (value before name)
        for match in re.finditer(
            r'<input[^>]+type=["\']hidden["\'][^>]*value=["\']([^"\']*)["\'][^>]*name=["\']([^"\']+)["\']',
            html,
            re.IGNORECASE,
        ):
            if match.group(2) not in fields:
                fields[match.group(2)] = match.group(1)

        if not fields:
            logger.warning("No hidden fields found in Condicao response")
            return False, {}

        logger.info("Condicao OK - %d hidden fields parsed", len(fields))
        return True, fields

    async def submit(
        self, cookies: httpx.Cookies, fields: dict[str, str]
    ) -> tuple[bool, str]:
        """Step 6: POST Conclusao with hidden fields."""
        client = await self._ensure_client()
        resp = await client.post(
            f"{BASE_URL}/Reservas/Conclusao?Length=8",
            data=fields,
            cookies=cookies,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            follow_redirects=True,
        )
        html = resp.text
        success = (
            "reserva agendada com sucesso" in html.lower() or "sucesso" in html.lower()
        )
        snippet = html[:500]
        logger.info("Submit result: success=%s", success)
        return success, snippet

    async def execute_reservation(
        self, db: AsyncSession, reservation: Reservation, resource: Resource
    ) -> bool:
        """Orchestrate full reservation flow with retry loop."""
        reservation.status = "executing"
        reservation.updated_at = datetime.now()
        await db.commit()

        try:
            niu, token = await self.login()
            await self._log_attempt(db, reservation, 0, "login", True, "Login OK")

            auth_url = await self.redirect(niu, token)
            cookies = await self.authenticate(auth_url)
            await self._log_attempt(db, reservation, 0, "auth", True, "Auth OK")

            await self.warmup(cookies, resource.recurso_id)
        except Exception as e:
            await self._log_attempt(db, reservation, 0, "auth", False, error=str(e))
            reservation.status = "failed"
            reservation.result_message = f"Auth failed: {e}"
            reservation.updated_at = datetime.now()
            await db.commit()
            return False

        max_attempts = 60
        for attempt in range(1, max_attempts + 1):
            reservation.attempt_count = attempt
            reservation.updated_at = datetime.now()
            await db.commit()

            try:
                available, fields = await self.get_condicao(
                    cookies,
                    reservation.target_date,
                    resource.recurso_id,
                    resource.periodo_id,
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
                    if attempt < max_attempts:
                        await asyncio.sleep(1)
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
                    reservation.status = "success"
                    reservation.result_message = "Reserva agendada com sucesso!"
                    reservation.updated_at = datetime.now()
                    await db.commit()
                    return True
                else:
                    if attempt < max_attempts:
                        await asyncio.sleep(1)

            except Exception as e:
                await self._log_attempt(
                    db, reservation, attempt, "error", False, error=str(e)
                )
                if attempt < max_attempts:
                    await asyncio.sleep(1)

        reservation.status = "failed"
        reservation.result_message = f"Falhou após {max_attempts} tentativas"
        reservation.updated_at = datetime.now()
        await db.commit()
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
    ):
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
