from datetime import date, datetime

from pydantic import BaseModel


class PeriodOut(BaseModel):
    id: int
    resource_id: int
    periodo_id: int
    label: str

    model_config = {"from_attributes": True}


class ResourceOut(BaseModel):
    id: int
    name: str
    recurso_id: int
    periodo_id: int
    hash: str | None = None
    periods: list[PeriodOut] = []

    model_config = {"from_attributes": True}


class ReservationCreate(BaseModel):
    resource_id: int
    target_date: date
    reason: str = ""
    periodo_id: int | None = None


class AttemptLogOut(BaseModel):
    id: int
    attempt_number: int
    timestamp: datetime
    step: str
    success: bool
    response_snippet: str | None
    error_message: str | None

    model_config = {"from_attributes": True}


class ReservationOut(BaseModel):
    id: int
    resource_id: int
    target_date: date
    trigger_date: date
    status: str
    created_at: datetime
    updated_at: datetime
    attempt_count: int
    reason: str | None = None
    periodo_id: int | None = None
    result_message: str | None = None
    resource: ResourceOut | None = None
    attempt_logs: list[AttemptLogOut] = []

    model_config = {"from_attributes": True}
