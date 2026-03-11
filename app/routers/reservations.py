import asyncio
import json
import logging
from collections import Counter
from datetime import date

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models import Period, Reservation, Resource
from app.services.scheduler import (
    compute_trigger_date,
    is_within_window,
    opens_tonight,
    run_reservation,
)

logger = logging.getLogger("icond.router")

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

STATUS_LABELS = {
    "pending": "Pendente",
    "scheduled": "Agendado",
    "executing": "Executando",
    "success": "Concluido",
    "failed": "Falhou",
    "cancelled": "Cancelado",
}
templates.env.globals["sl"] = lambda s: STATUS_LABELS.get(s, s)

FLASH_MESSAGES = {
    "created": ("Reserva agendada com sucesso!", "success"),
    "cancelled": ("Reserva cancelada.", "success"),
    "executing": ("Execucao iniciada.", "success"),
    "invalid_date": ("Data invalida. Selecione uma data futura.", "error"),
    "missing_period": ("Selecione um horario para este recurso.", "error"),
}


@router.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
    msg: str = Query(None),
    db: AsyncSession = Depends(get_db),
):
    resources = (
        (await db.execute(select(Resource).options(selectinload(Resource.periods)))).scalars().all()
    )
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

    flash_message, flash_type = FLASH_MESSAGES.get(msg, (None, None))

    # JSON com períodos por recurso para o JS do frontend
    resource_periods = {
        r.id: [{"periodo_id": p.periodo_id, "label": p.label} for p in r.periods] for r in resources
    }

    # Mapa periodo_id -> label para exibição na lista
    period_labels = {}
    for r in resources:
        for p in r.periods:
            period_labels[p.periodo_id] = p.label

    today = date.today()
    status_counts = Counter(r.status for r in reservations)
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "resources": resources,
            "reservations": reservations,
            "today": today.isoformat(),
            "today_date": today,
            "flash_message": flash_message,
            "flash_type": flash_type,
            "status_counts": status_counts,
            "total_count": len(reservations),
            "resource_periods_json": json.dumps(resource_periods),
            "period_labels": period_labels,
        },
    )


@router.post("/reservations")
async def create_reservation(
    resource_id: int = Form(...),
    target_date: date = Form(...),
    reason: str = Form(""),
    periodo_id: int = Form(None),
    db: AsyncSession = Depends(get_db),
):
    if target_date <= date.today():
        return RedirectResponse(url="/?msg=invalid_date", status_code=303)

    # Buscar períodos do recurso para validação
    periods = (
        (await db.execute(select(Period).where(Period.resource_id == resource_id))).scalars().all()
    )

    if len(periods) == 1:
        # Recurso INTEGRAL: auto-preencher
        periodo_id = periods[0].periodo_id
    elif len(periods) > 1 and not periodo_id:
        return RedirectResponse(url="/?msg=missing_period", status_code=303)

    trigger = compute_trigger_date(target_date)

    if is_within_window(target_date):
        status = "pending"
    elif opens_tonight(target_date):
        status = "scheduled"
    else:
        status = "scheduled"

    reservation = Reservation(
        resource_id=resource_id,
        target_date=target_date,
        trigger_date=trigger,
        status=status,
        reason=reason.strip() or None,
        periodo_id=periodo_id,
    )
    db.add(reservation)
    await db.commit()
    await db.refresh(reservation)

    logger.info(
        "Created reservation #%d: resource=%d, target=%s, trigger=%s, status=%s, periodo=%s",
        reservation.id,
        resource_id,
        target_date,
        trigger,
        status,
        periodo_id,
    )

    if status == "pending":
        asyncio.create_task(run_reservation(reservation.id))
        logger.info("Reservation #%d executing immediately (within window)", reservation.id)

    return RedirectResponse(url="/?msg=created", status_code=303)


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

    # Buscar label do período
    periodo_label = None
    if reservation.periodo_id:
        period = (
            await db.execute(
                select(Period).where(
                    Period.resource_id == reservation.resource_id,
                    Period.periodo_id == reservation.periodo_id,
                )
            )
        ).scalar_one_or_none()
        if period:
            periodo_label = period.label

    return templates.TemplateResponse(
        "detail.html",
        {"request": request, "reservation": reservation, "periodo_label": periodo_label},
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

    return RedirectResponse(url="/?msg=cancelled", status_code=303)


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
