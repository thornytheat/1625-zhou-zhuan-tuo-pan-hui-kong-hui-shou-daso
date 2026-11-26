from dataclasses import dataclass


@dataclass(frozen=True)
class Request:
    case_id: str
    cohort: str
    calendar_day: int
    tick: int
    resource: str
    units: int
    estimate: float
    low: float | None
    high: float | None
    priority: float
    source: str
    status: str
    reason: str
    details: tuple[str, ...]
    next_step: str
    horizon: float | None = None
    horizon_exact: str | None = None
    horizon_source: str | None = None
    horizon_eligible: bool | None = None


@dataclass(frozen=True)
class Allocation:
    capacity: int
    used: int
    resource_use: dict[str, int]
    decisions: tuple[Request, ...]
    returned: tuple[str, ...] = ()
