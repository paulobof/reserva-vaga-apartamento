import logging

import httpx

from app.config import settings

logger = logging.getLogger("icond.notifier")

EVOLUTION_URL = (
    "https://evolutionbotparticular.paulobof.com.br/message/sendText/BotParticular"
)


async def send_whatsapp(message: str):
    """Send a WhatsApp message via Evolution API."""
    if not settings.evolution_api_key:
        logger.warning("Evolution API key not configured, skipping notification")
        return

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                EVOLUTION_URL,
                json={"number": settings.whatsapp_number, "text": message},
                headers={"apikey": settings.evolution_api_key},
            )
            resp.raise_for_status()
            logger.info("WhatsApp sent: %s", message[:50])
    except Exception as e:
        logger.error("Failed to send WhatsApp: %s", e)
