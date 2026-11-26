from collections import defaultdict
from math import isfinite

REVIEW_NAME = "在途货值与回空场次"
IMPACT_NAME = "周转在途押金/元"
HEADROOM_NAME = "接驳班组余量"
OVERRIDE_NOTE = "合到长线回程班组前暂停单独提货"


def operational_check(readings, estimate):
    """押金争议保持冻结，长程多托订单单列班组余量。"""
    age = readings["age"]
    loops = readings["loops"]
    distance = readings["distance"]
    collectors = readings["collectors"]
    pallets = readings["pallets"]
    deposit = readings["deposit"]
    impact = max(0.0, age - estimate) * deposit * pallets / max(1.0, loops)
    headroom = collectors - (0.5 if distance > 115 else 0.0) - pallets / 12
    override = bool(pallets > 15 and collectors < 2 and distance > 85)
    if not isfinite(impact) or not isfinite(headroom):
        raise ValueError("业务复核的观测量超出计算范围")
    return {
        "name": REVIEW_NAME,
        "impact_label": IMPACT_NAME,
        "headroom_label": HEADROOM_NAME,
        "impact": round(impact, 6),
        "headroom": round(headroom, 6),
        "requires_operator": override,
        "reason": OVERRIDE_NOTE if override else "",
    }


def summarize_workload(actions, evidence):
    distribution = defaultdict(
        lambda: {
            "selected_impact": 0.0,
            "selected": 0,
            "tight_window": 0,
            "needs_operator": 0,
        }
    )
    for action in actions:
        branch = distribution[action.cohort]
        current = evidence[action.case_id]["operational_check"]
        if action.status == "allocated":
            branch["selected"] += 1
            branch["selected_impact"] += current["impact"]
            if current["headroom"] < 0:
                branch["tight_window"] += 1
        if current["requires_operator"]:
            branch["needs_operator"] += 1
    return {
        name: {**data, "selected_impact": round(data["selected_impact"], 4)}
        for name, data in sorted(distribution.items())
    }
