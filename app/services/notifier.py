"""Serviço de notificação via WhatsApp (Evolution API)."""

import logging
import time

import httpx

from app.config import settings

logger = logging.getLogger("icond.notifier")

EVOLUTION_URL = "https://evolutionbotparticular.paulobof.com.br/message/sendText/BotParticular"


async def send_whatsapp(message: str) -> None:
    """Envia mensagem via WhatsApp usando a Evolution API.

    Args:
        message: Texto da mensagem a ser enviada.
    """
    if not settings.evolution_api_key:
        logger.warning("Evolution API key not configured, skipping notification")
        return

    start = time.perf_counter()

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                EVOLUTION_URL,
                json={"number": settings.whatsapp_number, "text": message},
                headers={"apikey": settings.evolution_api_key},
            )
            resp.raise_for_status()

            duration_ms = (time.perf_counter() - start) * 1000
            logger.info(
                "WhatsApp sent in %.0fms: %s",
                duration_ms,
                message[:80],
                extra={"step": "notify", "duration_ms": duration_ms},
            )
    except httpx.TimeoutException:
        duration_ms = (time.perf_counter() - start) * 1000
        logger.error(
            "WhatsApp timeout after %.0fms",
            duration_ms,
            extra={"step": "notify", "duration_ms": duration_ms},
        )
    except Exception as e:
        duration_ms = (time.perf_counter() - start) * 1000
        logger.error(
            "WhatsApp failed after %.0fms: %s",
            duration_ms,
            e,
            extra={"step": "notify", "duration_ms": duration_ms},
        )
