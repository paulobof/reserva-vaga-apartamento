import asyncio
import logging
from datetime import date, datetime, timedelta

import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database import async_session
from app.models import Reservation
from app.services.icondominio import ICondominioClient
from app.services.notifier import send_whatsapp

logger = logging.getLogger("icond.scheduler")

SP_TZ = pytz.timezone("America/Sao_Paulo")

scheduler = AsyncIOScheduler(timezone=SP_TZ)


async def nightly_check():
    """Called daily at 23:55 SP time. Finds scheduled reservations to trigger."""
    today = date.today()
    logger.info("Nightly check for trigger_date <= %s", today)

    async with async_session() as db:
        result = await db.execute(
            select(Reservation)
            .options(selectinload(Reservation.resource))
            .where(Reservation.trigger_date <= today, Reservation.status == "scheduled")
        )
        reservations = result.scalars().all()

        if not reservations:
            logger.info("No reservations to trigger today")
            return

        for reservation in reservations:
            logger.info(
                "Triggering reservation #%d for %s on %s",
                reservation.id,
                reservation.resource.name,
                reservation.target_date,
            )
            asyncio.create_task(
                _run_reservation_at_midnight(reservation.id, reservation.resource_id)
            )


async def _run_reservation_at_midnight(reservation_id: int, resource_id: int):
    """Wait until 23:59:30, then start the reservation attempt loop."""
    now = datetime.now(SP_TZ)
    target_time = now.replace(hour=23, minute=59, second=30, microsecond=0)
    wait_seconds = (target_time - now).total_seconds()
    if wait_seconds > 0:
        logger.info("Waiting %.0f seconds until 23:59:30", wait_seconds)
        await asyncio.sleep(wait_seconds)

    await run_reservation(reservation_id)


async def run_reservation(reservation_id: int):
    """Execute a reservation (can be called directly for immediate execution)."""
    client = ICondominioClient()
    try:
        async with async_session() as db:
            result = await db.execute(
                select(Reservation)
                .options(selectinload(Reservation.resource))
                .where(Reservation.id == reservation_id)
            )
            reservation = result.scalar_one_or_none()
            if not reservation:
                logger.error("Reservation #%d not found", reservation_id)
                return

            resource = reservation.resource
            logger.info(
                "Executing reservation #%d: %s on %s",
                reservation.id,
                resource.name,
                reservation.target_date,
            )

            success = await client.execute_reservation(db, reservation, resource)

            status_emoji = "✅" if success else "❌"
            msg = (
                f"{status_emoji} Reserva #{reservation.id}\n"
                f"Recurso: {resource.name}\n"
                f"Data: {reservation.target_date.strftime('%d/%m/%Y')}\n"
                f"Status: {reservation.status}\n"
                f"Tentativas: {reservation.attempt_count}"
            )
            if reservation.result_message:
                msg += f"\nMensagem: {reservation.result_message}"

            await send_whatsapp(msg)
    finally:
        await client.close()


def compute_trigger_date(target_date: date) -> date:
    """trigger_date = target_date - 91 days."""
    return target_date - timedelta(days=91)


def is_within_window(target_date: date) -> bool:
    """Check if target_date is already available (< 90 days, window already open)."""
    today = date.today()
    delta = (target_date - today).days
    return 0 < delta < 90


def opens_tonight(target_date: date) -> bool:
    """Check if target_date window opens tonight at midnight (exactly 90 days)."""
    today = date.today()
    delta = (target_date - today).days
    return delta == 90


def start_scheduler():
    scheduler.add_job(
        nightly_check,
        "cron",
        hour=23,
        minute=55,
        id="nightly_check",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Scheduler started - nightly check at 23:55 SP")


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")
