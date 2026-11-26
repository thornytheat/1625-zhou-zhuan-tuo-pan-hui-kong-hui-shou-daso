"""未来固定时距仍未归还的概率。

回放和派单都以托盘当时已在途的天数为起点，估计再过一个固定窗口仍未归还的
条件概率 ``P(T > age + horizon | T > age)``。在途回执只说明观察结束时还没
归还，只有在满窗口时才能据此判定「窗口内没有归还」。

概率全部用有理数计算，派单资格在取整之前以严格大于二分之一判定，避免显示
舍入把临界单据推进或推出车位。
"""
from collections import Counter, defaultdict
from dataclasses import dataclass
from fractions import Fraction

from ..pallet_custody.contracts import Outcome
from ..route_age.contracts import Signal


HORIZON_DAYS = 2
MIN_HORIZON_SUPPORT = 20
DECISION_THRESHOLD = Fraction(1, 2)

LANE = "lane"
OVERALL = "overall"
MANUAL = "manual"


@dataclass(frozen=True)
class HorizonEstimate:
    probability: Fraction | None
    source: str
    horizon: int
    lane_support: int
    overall_support: int

    @property
    def available(self) -> bool:
        return self.probability is not None

    @property
    def eligible(self) -> bool:
        """概率严格过半才可派单；临界值不派。"""
        return self.probability is not None and self.probability > DECISION_THRESHOLD


def _as_day(value) -> Fraction:
    # 浮点读数按其精确二进制值转成有理数，保证边界判定可复现。
    return Fraction(value)


def horizon_ladder(records):
    """按总在途天数建立 Kaplan–Meier 阶梯。

    ``records`` 为 ``(total_day, returned)`` 序列；``total_day`` 是入账时已在途
    天数加上回执给出的时长，右删失样本在观察结束处退出在险集合。
    """
    ordered = sorted(records, key=lambda item: item[0])
    at_risk = len(ordered)
    survival = Fraction(1)
    rungs = []
    index = 0
    while index < len(ordered):
        day = ordered[index][0]
        returned = censored = 0
        cursor = index
        while cursor < len(ordered) and ordered[cursor][0] == day:
            if ordered[cursor][1]:
                returned += 1
            else:
                censored += 1
            cursor += 1
        if returned:
            survival *= Fraction(at_risk - returned, at_risk)
        rungs.append((day, at_risk, returned, censored, survival))
        at_risk -= returned + censored
        index = cursor
    return tuple(rungs)


def survival_at(ladder, day: Fraction) -> Fraction:
    value = Fraction(1)
    for edge, _, _, _, after in ladder:
        if edge <= day:
            value = after
        else:
            break
    return value


def probability(ladder, age, horizon: int = HORIZON_DAYS) -> Fraction:
    """从当前在途天数起算，未来 ``horizon`` 天内仍未归还的概率。"""
    start = _as_day(age)
    left = survival_at(ladder, start)
    if left == 0:
        return Fraction(0)
    return survival_at(ladder, start + horizon) / left


def observed_not_returned(value, occurred: bool, horizon: int = HORIZON_DAYS):
    """历史单在窗口内是否确实没归还。

    观察到的回执只证明观察结束前没归还：已结案时能区分窗口内外；删失回执只有
    在观察时长已覆盖整个窗口时才能判明。返回 ``None`` 表示无法判明。
    """
    duration = _as_day(value)
    limit = Fraction(horizon)
    if occurred:
        return duration > limit
    return True if duration >= limit else None


def build(rows):
    """从训练行构建分层阶梯与可判明样本数。"""
    lanes = defaultdict(list)
    records = []
    lane_support = Counter()
    overall_support = 0
    for row in rows:
        age = row.signal.record.reported.get("age")
        if age is None:
            continue
        outcome: Outcome = row.outcome
        total = _as_day(age) + _as_day(outcome.value)
        lanes[row.signal.record.group].append((total, outcome.occurred))
        records.append((total, outcome.occurred))
        if observed_not_returned(outcome.value, outcome.occurred) is not None:
            lane_support[row.signal.record.group] += 1
            overall_support += 1
    if not any(returned for _, returned in records):
        return None
    return {
        "horizon": HORIZON_DAYS,
        "minimum_support": MIN_HORIZON_SUPPORT,
        "lanes": {group: horizon_ladder(items) for group, items in lanes.items()},
        "overall": horizon_ladder(records),
        "lane_support": dict(lane_support),
        "overall_support": overall_support,
    }


def estimate(state, signal: Signal) -> HorizonEstimate:
    age = signal.record.reported.get("age")
    group = signal.record.group
    if state is None or age is None:
        # 没有在途天数就找不回起点，只能转人工。
        return HorizonEstimate(None, MANUAL, HORIZON_DAYS, 0, 0)
    lane_support = state["lane_support"].get(group, 0)
    overall_support = state["overall_support"]
    if lane_support >= MIN_HORIZON_SUPPORT and group in state["lanes"]:
        return HorizonEstimate(
            probability(state["lanes"][group], age),
            LANE,
            HORIZON_DAYS,
            lane_support,
            overall_support,
        )
    # 本线路可判明样本不足时借全场记录；全场也不足只能转人工。
    if overall_support >= MIN_HORIZON_SUPPORT:
        return HorizonEstimate(
            probability(state["overall"], age),
            OVERALL,
            HORIZON_DAYS,
            lane_support,
            overall_support,
        )
    return HorizonEstimate(
        None, MANUAL, HORIZON_DAYS, lane_support, overall_support
    )


def card(state) -> dict:
    """写入模型卡的可序列化摘要。"""
    if state is None:
        return {
            "horizon": HORIZON_DAYS,
            "minimum_support": MIN_HORIZON_SUPPORT,
            "decision_threshold": float(DECISION_THRESHOLD),
            "overall_support": 0,
            "lane_support": {},
            "available": False,
        }
    return {
        "horizon": state["horizon"],
        "minimum_support": state["minimum_support"],
        "decision_threshold": float(DECISION_THRESHOLD),
        "overall_support": state["overall_support"],
        "lane_support": dict(sorted(state["lane_support"].items())),
        "available": True,
    }


def evidence(value: HorizonEstimate) -> dict:
    return {
        "horizon": value.horizon,
        "probability": None
        if value.probability is None
        else float(value.probability),
        "probability_exact": None
        if value.probability is None
        else f"{value.probability.numerator}/{value.probability.denominator}",
        "source": value.source,
        "lane_support": value.lane_support,
        "overall_support": value.overall_support,
        "minimum_support": MIN_HORIZON_SUPPORT,
        "threshold": float(DECISION_THRESHOLD),
        "eligible": value.eligible,
    }
