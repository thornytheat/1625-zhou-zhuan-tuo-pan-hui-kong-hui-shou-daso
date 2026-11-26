from math import ceil

from ..settings import ACTION_LABEL, FIELD_BOUNDS
from .contracts import Request


def project_request(card, gate, calendar_day=None) -> Request:
    record = card.signal.record
    values = {
        key: record.reported[key]
        if record.reported.get(key) is not None
        else (lo + hi) / 2
        for key, (lo, hi) in FIELD_BOUNDS.items()
    }
    age = values["age"]
    distance = values["distance"]
    collectors = values["collectors"]
    pallets = values["pallets"]
    deposit = values["deposit"]
    disputed = values["disputed"]
    score = card.estimate if gate.allowed else card.prior
    blocked = disputed >= 1 or collectors < 1
    priority = max(0, age + 2 - score) * (0.35 + deposit / 75) * (1 + pallets / 45)
    units = 1 + int(pallets > 8) + int(distance > 95)
    status = "candidate"
    reason = "RULE_ELIGIBLE"
    details = ()
    if blocked and all(
        record.reported.get(k) is not None for k in ("collectors", "disputed")
    ):
        status, reason, details = "held", "BUSINESS_LOCK", ("押金争议锁或无提货班组",)
    elif not gate.allowed:
        status, reason, details = "manual", "TRUST_REVIEW", gate.reasons
    elif priority <= 0:
        status, reason, details = "monitor", "BELOW_ACTION", ("预计收益未达到处置阈值",)

    return Request(
        record.case_id,
        record.group,
        record.day if calendar_day is None else calendar_day,
        record.clock,
        record.group,
        units,
        round(score, 7),
        card.lower if gate.allowed else None,
        card.upper if gate.allowed else None,
        round(priority, 7),
        gate.source,
        status,
        reason,
        details,
        ACTION_LABEL,
    )


def resource_limit(day_budget: int) -> int:
    return max(1, day_budget * 2 // 3)
