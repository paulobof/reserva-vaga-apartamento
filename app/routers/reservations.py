import asyncio
import logging
from datetime import date

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models import Reservation, Resource
from app.services.scheduler import (
    compute_trigger_date,
    is_within_window,
    run_reservation,
)

logger = logging.getLogger("icond.router")

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
async def index(request: Request, db: AsyncSession = Depends(get_db)):
    resources = (await db.execute(select(Resource))).scalars().all()
    reservations = (
        (
            await db.execute(
                select(Reservation)
                .options(selectinload(Reservation.resource))
                .order_by(Reservation.created_at.desc())
            )
        )
        .scalars()
        .all()
    )

    return templates.TemplateResponse(
        "index.html",
        {"request": request, "resources": resources, "reservations": reservations},
    )


@router.post("/reservations")
async def create_reservation(
    resource_id: int = Form(...),
    target_date: date = Form(...),
    db: AsyncSession = Depends(get_db),
):
    trigger = compute_trigger_date(target_date)
    within_window = is_within_window(target_date)

    reservation = Reservation(
        resource_id=resource_id,
        target_date=target_date,
        trigger_date=trigger,
        status="scheduled" if not within_window else "pending",
    )
    db.add(reservation)
    await db.commit()
    await db.refresh(reservation)

    logger.info(
        "Created reservation #%d: resource=%d, target=%s, trigger=%s, within_window=%s",
        reservation.id,
        resource_id,
        target_date,
        trigger,
        within_window,
    )

    if within_window:
        reservation.status = "pending"
        await db.commit()
        asyncio.create_task(run_reservation(reservation.id))
        logger.info("Reservation #%d executing immediately (within window)", reservation.id)

    return RedirectResponse(url="/", status_code=303)


@router.get("/reservations/{reservation_id}", response_class=HTMLResponse)
async def detail(
    request: Request,
    reservation_id: int,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Reservation)
        .options(selectinload(Reservation.resource), selectinload(Reservation.attempt_logs))
        .where(Reservation.id == reservation_id)
    )
    reservation = result.scalar_one_or_none()
    if not reservation:
        return RedirectResponse(url="/")

    return templates.TemplateResponse(
        "detail.html",
        {"request": request, "reservation": reservation},
    )


@router.post("/reservations/{reservation_id}/cancel")
async def cancel_reservation(
    reservation_id: int,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Reservation).where(Reservation.id == reservation_id))
    reservation = result.scalar_one_or_none()
    if reservation and reservation.status in ("pending", "scheduled"):
        reservation.status = "cancelled"
        await db.commit()
        logger.info("Cancelled reservation #%d", reservation_id)

    return RedirectResponse(url="/", status_code=303)


@router.post("/reservations/{reservation_id}/execute")
async def execute_now(
    reservation_id: int,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Reservation).where(Reservation.id == reservation_id))
    reservation = result.scalar_one_or_none()
    if reservation and reservation.status in ("pending", "scheduled"):
        asyncio.create_task(run_reservation(reservation.id))
        logger.info("Manual execution triggered for reservation #%d", reservation_id)

    return RedirectResponse(url=f"/reservations/{reservation_id}", status_code=303)
