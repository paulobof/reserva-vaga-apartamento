from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Resource(Base):
    __tablename__ = "resources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    recurso_id: Mapped[int] = mapped_column(Integer, nullable=False)
    periodo_id: Mapped[int] = mapped_column(Integer, nullable=False)
    hash: Mapped[str | None] = mapped_column(String(64), nullable=True, default=None)

    reservations: Mapped[list["Reservation"]] = relationship(back_populates="resource")


class Reservation(Base):
    __tablename__ = "reservations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    resource_id: Mapped[int] = mapped_column(ForeignKey("resources.id"), nullable=False)
    target_date: Mapped[date] = mapped_column(Date, nullable=False)
    trigger_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    result_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    resource: Mapped["Resource"] = relationship(back_populates="reservations")
    attempt_logs: Mapped[list["AttemptLog"]] = relationship(
        back_populates="reservation", order_by="AttemptLog.attempt_number"
    )


class AttemptLog(Base):
    __tablename__ = "attempt_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    reservation_id: Mapped[int] = mapped_column(ForeignKey("reservations.id"), nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    step: Mapped[str] = mapped_column(String(20), nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    response_snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    reservation: Mapped["Reservation"] = relationship(back_populates="attempt_logs")


SEED_RESOURCES = [
    Resource(id=1, name="Salão de Festas Adulto", recurso_id=2564, periodo_id=9894),
    Resource(id=2, name="Churrasqueira com Forno de Pizza", recurso_id=2563, periodo_id=9894),
    Resource(id=3, name="Salão de Festas Infantil", recurso_id=2565, periodo_id=9894),
    Resource(id=4, name="Home Cinema", recurso_id=2625, periodo_id=9894),
    Resource(id=5, name="Garage Band", recurso_id=2626, periodo_id=9894),
    Resource(id=6, name="Spa - Hidromassagem", recurso_id=5, periodo_id=9894),
    Resource(id=7, name="Pet Care - Ducha 1", recurso_id=3851, periodo_id=9894),
    Resource(id=8, name="Pet Care - Ducha 2", recurso_id=3883, periodo_id=9894),
    Resource(id=9, name="Pet Care - Ducha 3", recurso_id=3989, periodo_id=9894),
    Resource(
        id=10, name="Espaço Beauty - Cadeira Cabeleireiro 2", recurso_id=3885, periodo_id=9894
    ),
    Resource(id=11, name="Espaço Beauty - Manicure", recurso_id=3886, periodo_id=9894),
]
