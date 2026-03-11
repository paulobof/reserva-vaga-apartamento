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
    periods: Mapped[list["Period"]] = relationship(back_populates="resource", order_by="Period.id")


class Period(Base):
    __tablename__ = "periods"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    resource_id: Mapped[int] = mapped_column(ForeignKey("resources.id"), nullable=False)
    periodo_id: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str] = mapped_column(String(50), nullable=False)

    resource: Mapped["Resource"] = relationship(back_populates="periods")


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
    periodo_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
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

# Períodos por recurso (extraídos da API iCondomínio em 2026-03-11)
SEED_PERIODS = [
    # Salão de Festas Adulto - INTEGRAL
    Period(resource_id=1, periodo_id=9894, label="INTEGRAL"),
    # Churrasqueira com Forno de Pizza - INTEGRAL
    Period(resource_id=2, periodo_id=9894, label="INTEGRAL"),
    # Salão de Festas Infantil - INTEGRAL
    Period(resource_id=3, periodo_id=9894, label="INTEGRAL"),
    # Home Cinema - slots de 2h
    Period(resource_id=4, periodo_id=10072, label="08:00 às 10:00"),
    Period(resource_id=4, periodo_id=10073, label="10:00 às 12:00"),
    Period(resource_id=4, periodo_id=11634, label="12:00 às 14:00"),
    Period(resource_id=4, periodo_id=171101, label="14:00 às 16:00"),
    Period(resource_id=4, periodo_id=171102, label="16:00 às 18:00"),
    Period(resource_id=4, periodo_id=171002, label="18:00 às 20:00"),
    Period(resource_id=4, periodo_id=171003, label="20:00 às 22:00"),
    Period(resource_id=4, periodo_id=171004, label="22:00 às 00:00"),
    # Garage Band - slots de 3h
    Period(resource_id=5, periodo_id=10068, label="09:00 às 12:00"),
    Period(resource_id=5, periodo_id=10069, label="12:00 às 15:00"),
    Period(resource_id=5, periodo_id=10070, label="15:00 às 18:00"),
    Period(resource_id=5, periodo_id=10071, label="18:00 às 21:00"),
    # Spa - Hidromassagem - 2 turnos
    Period(resource_id=6, periodo_id=12653, label="10:00 às 13:00"),
    Period(resource_id=6, periodo_id=12654, label="16:00 às 22:00"),
    # Pet Care - Ducha 1 - slots de 1h
    Period(resource_id=7, periodo_id=54945, label="08:00 às 09:00"),
    Period(resource_id=7, periodo_id=54946, label="09:00 às 10:00"),
    Period(resource_id=7, periodo_id=54947, label="10:00 às 11:00"),
    Period(resource_id=7, periodo_id=54949, label="11:00 às 12:00"),
    Period(resource_id=7, periodo_id=54950, label="12:00 às 13:00"),
    Period(resource_id=7, periodo_id=54951, label="13:00 às 14:00"),
    Period(resource_id=7, periodo_id=54952, label="14:00 às 15:00"),
    Period(resource_id=7, periodo_id=54953, label="15:00 às 16:00"),
    Period(resource_id=7, periodo_id=54954, label="16:00 às 17:00"),
    Period(resource_id=7, periodo_id=54955, label="17:00 às 18:00"),
    Period(resource_id=7, periodo_id=54956, label="18:00 às 19:00"),
    Period(resource_id=7, periodo_id=54957, label="19:00 às 20:00"),
    Period(resource_id=7, periodo_id=54958, label="20:00 às 21:00"),
    Period(resource_id=7, periodo_id=54959, label="21:00 às 22:00"),
    # Pet Care - Ducha 2 - mesmos slots
    Period(resource_id=8, periodo_id=54945, label="08:00 às 09:00"),
    Period(resource_id=8, periodo_id=54946, label="09:00 às 10:00"),
    Period(resource_id=8, periodo_id=54947, label="10:00 às 11:00"),
    Period(resource_id=8, periodo_id=54949, label="11:00 às 12:00"),
    Period(resource_id=8, periodo_id=54950, label="12:00 às 13:00"),
    Period(resource_id=8, periodo_id=54951, label="13:00 às 14:00"),
    Period(resource_id=8, periodo_id=54952, label="14:00 às 15:00"),
    Period(resource_id=8, periodo_id=54953, label="15:00 às 16:00"),
    Period(resource_id=8, periodo_id=54954, label="16:00 às 17:00"),
    Period(resource_id=8, periodo_id=54955, label="17:00 às 18:00"),
    Period(resource_id=8, periodo_id=54956, label="18:00 às 19:00"),
    Period(resource_id=8, periodo_id=54957, label="19:00 às 20:00"),
    Period(resource_id=8, periodo_id=54958, label="20:00 às 21:00"),
    Period(resource_id=8, periodo_id=54959, label="21:00 às 22:00"),
    # Pet Care - Ducha 3 - mesmos slots
    Period(resource_id=9, periodo_id=54945, label="08:00 às 09:00"),
    Period(resource_id=9, periodo_id=54946, label="09:00 às 10:00"),
    Period(resource_id=9, periodo_id=54947, label="10:00 às 11:00"),
    Period(resource_id=9, periodo_id=54949, label="11:00 às 12:00"),
    Period(resource_id=9, periodo_id=54950, label="12:00 às 13:00"),
    Period(resource_id=9, periodo_id=54951, label="13:00 às 14:00"),
    Period(resource_id=9, periodo_id=54952, label="14:00 às 15:00"),
    Period(resource_id=9, periodo_id=54953, label="15:00 às 16:00"),
    Period(resource_id=9, periodo_id=54954, label="16:00 às 17:00"),
    Period(resource_id=9, periodo_id=54955, label="17:00 às 18:00"),
    Period(resource_id=9, periodo_id=54956, label="18:00 às 19:00"),
    Period(resource_id=9, periodo_id=54957, label="19:00 às 20:00"),
    Period(resource_id=9, periodo_id=54958, label="20:00 às 21:00"),
    Period(resource_id=9, periodo_id=54959, label="21:00 às 22:00"),
    # Espaço Beauty - Cadeira Cabeleireiro 2 - slots de 1h
    Period(resource_id=10, periodo_id=141904, label="08:00 às 09:00"),
    Period(resource_id=10, periodo_id=13364, label="09:00 às 10:00"),
    Period(resource_id=10, periodo_id=13366, label="10:00 às 11:00"),
    Period(resource_id=10, periodo_id=13367, label="11:00 às 12:00"),
    Period(resource_id=10, periodo_id=13368, label="12:00 às 13:00"),
    Period(resource_id=10, periodo_id=13369, label="13:00 às 14:00"),
    Period(resource_id=10, periodo_id=13370, label="14:00 às 15:00"),
    Period(resource_id=10, periodo_id=13371, label="15:00 às 16:00"),
    Period(resource_id=10, periodo_id=13372, label="16:00 às 17:00"),
    Period(resource_id=10, periodo_id=13373, label="17:00 às 18:00"),
    Period(resource_id=10, periodo_id=13374, label="18:00 às 19:00"),
    Period(resource_id=10, periodo_id=13375, label="19:00 às 20:00"),
    Period(resource_id=10, periodo_id=13376, label="20:00 às 21:00"),
    Period(resource_id=10, periodo_id=13377, label="21:00 às 22:00"),
    # Espaço Beauty - Manicure - mesmos slots
    Period(resource_id=11, periodo_id=141904, label="08:00 às 09:00"),
    Period(resource_id=11, periodo_id=13364, label="09:00 às 10:00"),
    Period(resource_id=11, periodo_id=13366, label="10:00 às 11:00"),
    Period(resource_id=11, periodo_id=13367, label="11:00 às 12:00"),
    Period(resource_id=11, periodo_id=13368, label="12:00 às 13:00"),
    Period(resource_id=11, periodo_id=13369, label="13:00 às 14:00"),
    Period(resource_id=11, periodo_id=13370, label="14:00 às 15:00"),
    Period(resource_id=11, periodo_id=13371, label="15:00 às 16:00"),
    Period(resource_id=11, periodo_id=13372, label="16:00 às 17:00"),
    Period(resource_id=11, periodo_id=13373, label="17:00 às 18:00"),
    Period(resource_id=11, periodo_id=13374, label="18:00 às 19:00"),
    Period(resource_id=11, periodo_id=13375, label="19:00 às 20:00"),
    Period(resource_id=11, periodo_id=13376, label="20:00 às 21:00"),
    Period(resource_id=11, periodo_id=13377, label="21:00 às 22:00"),
]
