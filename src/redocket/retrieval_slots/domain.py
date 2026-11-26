from ..settings import ACTION_LABEL, FIELD_BOUNDS
from ..return_survival.horizon import MANUAL, evidence as horizon_evidence
from .contracts import Request


def _horizon_fields(card) -> dict:
    value = card.horizon
    if value is None:
        return {
            "horizon": None,
            "horizon_exact": None,
            "horizon_source": MANUAL,
            "horizon_eligible": False,
        }
    row = horizon_evidence(value)
    return {
        "horizon": row["probability"],
        "horizon_exact": row["probability_exact"],
        "horizon_source": row["source"],
        "horizon_eligible": row["eligible"],
    }


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
    horizon = _horizon_fields(card)
    status = "candidate"
    reason = "RULE_ELIGIBLE"
    details = ()
    if blocked and all(
        record.reported.get(k) is not None for k in ("collectors", "disputed")
    ):
        status, reason, details = "held", "BUSINESS_LOCK", ("押金争议锁或无提货班组",)
    elif not gate.allowed:
        status, reason, details = "manual", "TRUST_REVIEW", gate.reasons
    elif card.horizon is None or not card.horizon.available:
        # 本线路与全场都凑不够可判明样本，转人工且不占车位。
        status, reason, details = "manual", "HORIZON_UNSUPPORTED", (
            "本线路与全场可判明样本均不足二十笔",
        )
    elif not card.horizon_passed:
        status, reason, details = "manual", "HORIZON_BACKTEST", (
            "固定时距回放未达门限",
        )
    elif not horizon["horizon_eligible"]:
        # 概率未过半：预计两天内归还，只观察不派单。
        status, reason, details = "monitor", "WITHIN_HORIZON", (
            "预计两天内已归还，不派发车位",
        )
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
        horizon["horizon"],
        horizon["horizon_exact"],
        horizon["horizon_source"],
        horizon["horizon_eligible"],
    )


def resource_limit(day_budget: int) -> int:
    return max(1, day_budget * 2 // 3)
