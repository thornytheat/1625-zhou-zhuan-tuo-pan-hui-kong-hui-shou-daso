from collections import defaultdict


FOLLOW_UP = 25.0
MIN_LANE = 18


def survival_ladder(records):
    at_risk = len(records)
    probability = 1.0
    counts = defaultdict(lambda: [0, 0])
    for duration, event in records:
        counts[min(duration, FOLLOW_UP)][int(event and duration <= FOLLOW_UP)] += 1
    rungs = []
    for day, (censored, returned) in sorted(counts.items()):
        # 当天已归还与同日失访都在当日开头的在险集合里。
        probability *= 1 - returned / max(1, at_risk)
        rungs.append((day, at_risk, returned, censored, probability))
        at_risk -= returned + censored
    return tuple(rungs)


def _typical_return(ladder):
    medians = [day for day, _, _, _, left in ladder if left <= 0.5]
    if medians:
        return medians[0]
    # 观测范围内中位数不可识别时给受限均值，并在模型卡保留该信息。
    area, prior, left = 0.0, 0.0, 1.0
    for day, _, _, _, after in ladder:
        area += (day - prior) * left
        prior, left = day, after
    return area + (FOLLOW_UP - prior) * left


def _lane(signal):
    return signal.record.group, signal.vector[2] >= 0.52


def train(rows):
    cohorts = defaultdict(list)
    records = []
    for row in rows:
        outcome = (row.y, row.outcome.occurred)
        cohorts[_lane(row.signal)].append(outcome)
        records.append(outcome)
    if not any(event for _, event in records):
        return None
    ladders = {
        key: survival_ladder(events)
        for key, events in cohorts.items()
        if len(events) >= MIN_LANE
    }
    return {
        "overall": survival_ladder(records),
        "lanes": ladders,
        "censored": sum(not observed for _, observed in records),
        "support": len(records),
    }


def infer(state, signal):
    ladder = state["lanes"].get(_lane(signal), state["overall"])
    return _typical_return(ladder)


def explain(state):
    lanes = {
        f"{key[0]} · {'长程' if key[1] else '短程'}": _typical_return(ladder)
        for key, ladder in state["lanes"].items()
    }
    return {
        "censored_rows": state["censored"],
        "mature_rows": state["support"],
        "lanes": lanes,
        "right_limit": FOLLOW_UP,
        "tail_reaches_median": state["overall"][-1][-1] <= 0.5,
    }
