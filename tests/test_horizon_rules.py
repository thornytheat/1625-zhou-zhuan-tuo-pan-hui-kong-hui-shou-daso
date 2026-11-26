from copy import deepcopy
from fractions import Fraction
from pathlib import Path

import pytest

from redocket.engine import plan
from redocket.pallet_custody.service import returned_by, sample, stage
from redocket.retrieval_slots.contracts import Allocation, Request
from redocket.retrieval_slots.domain import project_request
from redocket.retrieval_slots.service import allocate, allocate_requests
from redocket.return_survival.horizon import (
    HORIZON_DAYS,
    MIN_HORIZON_SUPPORT,
    HorizonEstimate,
    build,
    estimate,
    horizon_ladder,
    observed_not_returned,
    probability,
    survival_at,
)
from redocket.deposit_manifest.contracts import AccountingError
from redocket.censored_replay.service import split
from redocket.return_survival.contracts import LearningRow
from redocket.settings import DEFAULT_DAY


def test_return_within_horizon_lowers_survival_from_current_age():
    # 在途 2 天起算：要到第 4 天才算「两天内没回」。
    ladder = horizon_ladder([(4, True), (6, True), (10, False)])
    assert survival_at(ladder, Fraction(2)) == 1
    assert probability(ladder, 2) == Fraction(2, 3)
    assert probability(ladder, 4) == Fraction(1, 2)
    assert probability(ladder, 6) == Fraction(1, 1)
    assert probability(ladder, 2, horizon=6) == Fraction(1, 3)


def test_censor_only_proves_absence_when_window_is_covered():
    # 在途回执只证明观察结束时还没归还。
    assert observed_not_returned(5.0, False) is True
    assert observed_not_returned(HORIZON_DAYS, False) is True
    assert observed_not_returned(1.0, False) is None
    assert observed_not_returned(1.0, True) is False
    assert observed_not_returned(3.0, True) is True


def test_probability_over_half_uses_exact_arithmetic():
    near_half = Fraction(10**18 + 1, 2 * 10**18)
    assert float(near_half) == 0.5
    assert HorizonEstimate(near_half, "lane", 2, 99, 400).eligible is True
    assert HorizonEstimate(Fraction(1, 2), "lane", 2, 99, 400).eligible is False
    assert HorizonEstimate(Fraction(1, 2) + Fraction(1, 10**9), "lane", 2, 99, 400).eligible


def make_row(group, age, value, occurred, case_id="C"):
    from dataclasses import replace

    from redocket.route_age.contracts import Signal

    record = stage(
        {
            "observations": [
                {
                    "case_id": case_id,
                    "group": group,
                    "day": 1,
                    "arrived": 1,
                    "revision": 1,
                    "clock": 0,
                    "measurements": {"age": age},
                }
            ],
            "outcomes": [],
        },
        10,
    ).observations[0]
    from redocket.pallet_custody.contracts import Outcome

    return LearningRow(
        Signal(record, (age, 0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 0.0), (), "全域"),
        Outcome(case_id, 9, value, occurred),
    )


def test_thin_lane_borrows_overall_then_falls_back_to_manual():
    thin = [make_row("门店联配", 5.0, 4.0, True, f"S{i}") for i in range(5)]
    rich = [make_row("县域专线", 5.0, 1.0, True, f"R{i}") for i in range(MIN_HORIZON_SUPPORT)]
    state = build(thin + rich)
    assert state["lane_support"]["门店联配"] == 5
    assert state["overall_support"] == 25

    from redocket.route_age.contracts import Signal

    def signal(group):
        return Signal(
            stage(
                {
                    "observations": [
                        {
                            "case_id": "Q",
                            "group": group,
                            "day": 6,
                            "arrived": 6,
                            "revision": 1,
                            "clock": 0,
                            "measurements": {"age": 5.0},
                        }
                    ],
                    "outcomes": [],
                },
                10,
            ).observations[0],
            (5.0, 0.0, 0.0, 0.0),
            (0.0, 0.0, 0.0, 0.0),
            (),
            "全域",
        )

    borrowed = estimate(state, signal("门店联配"))
    assert borrowed.source == "overall" and borrowed.available
    solo = build(thin)
    manual = estimate(solo, signal("门店联配"))
    assert manual.source == "manual" and not manual.available


def request(case_id="A", **kwargs):
    base = dict(
        cohort="one",
        calendar_day=12,
        tick=37,
        resource="one",
        units=1,
        estimate=6.0,
        low=None,
        high=None,
        priority=8.0,
        source="trained",
        status="allocated",
        reason="OK",
        details=(),
        next_step="送检",
        horizon=0.8,
        horizon_exact="4/5",
        horizon_source="lane",
        horizon_eligible=True,
    )
    base.update(kwargs)
    return Request(case_id, **base)


def test_below_half_horizon_cannot_spend_or_register():
    blocked = Allocation(10, 1, {"one": 1}, (request(horizon=0.4, horizon_eligible=False),))
    from redocket.deposit_manifest.reconcile import verify

    with pytest.raises(AccountingError, match="时距"):
        verify(blocked)


def test_manual_horizon_candidate_does_not_take_a_slot():
    batch = allocate_requests(
        [request("M", status="manual", reason="HORIZON_UNSUPPORTED", horizon=None)], 10
    )
    assert batch.used == 0 and batch.decisions[0].status == "manual"


def test_withdrawn_case_leaves_queue_and_keeps_resources_for_others():
    from dataclasses import replace

    from redocket.censored_replay.contracts import ScoreCard
    from redocket.lane_population.contracts import Gate
    from redocket.route_age.contracts import Signal

    def card(case_id, age):
        record = stage(
            {
                "observations": [
                    {
                        "case_id": case_id,
                        "group": "县域专线",
                        "day": 20,
                        "arrived": 20,
                        "revision": 1,
                        "clock": 0,
                        "measurements": {
                            "age": age,
                            "distance": 50.0,
                            "pallets": 5.0,
                            "collectors": 3.0,
                        },
                    }
                ],
                "outcomes": [],
            },
            30,
        ).observations[0]
        signal = Signal(record, (age, 0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 0.0), (), "全域")
        return ScoreCard(
            signal,
            6.0,
            6.0,
            None,
            None,
            HorizonEstimate(Fraction(9, 10), "lane", 2, 40, 300),
            True,
        )

    allowed = Gate(True, (), "trained")
    pairs = [(card("A", 20.0), allowed), (card("B", 5.0), allowed)]
    without_withdrawal = allocate(pairs, 1, snapshot=20)
    status = {row.case_id: row.status for row in without_withdrawal.decisions}
    assert status == {"A": "allocated", "B": "deferred"}
    assert without_withdrawal.used == 1

    withdrawn = allocate(pairs, 1, snapshot=20, withdrawn=("A",))
    assert withdrawn.returned == ("A",)
    assert [row.case_id for row in withdrawn.decisions] == ["B"]
    assert withdrawn.decisions[0].status == "allocated"
    assert withdrawn.used == 1


def test_snapshot_return_withdraws_but_late_return_does_not(packet, report):
    target = next(row for row in report.body["decisions"] if row["status"] == "allocated")
    case = target["case_id"]
    visible = deepcopy(packet)
    visible["outcomes"].append(
        {"case_id": case, "available": DEFAULT_DAY - 1, "value": 3.0, "occurred": True}
    )
    result = plan(visible).body
    assert result["summary"]["withdrawn"] == 1
    assert result["returned"] == [case]
    assert all(row["case_id"] != case for row in result["decisions"])

    late = deepcopy(packet)
    late["outcomes"].append(
        {"case_id": case, "available": DEFAULT_DAY + 2, "value": 3.0, "occurred": True}
    )
    assert plan(late).body["decisions"] == report.body["decisions"]


def test_in_flight_receipt_does_not_withdraw(packet, report):
    target = report.body["decisions"][0]
    book = deepcopy(packet)
    book["outcomes"].append(
        {
            "case_id": target["case_id"],
            "available": DEFAULT_DAY,
            "value": 3.0,
            "occurred": False,
        }
    )
    result = plan(book).body
    assert result["summary"]["withdrawn"] == 0
    assert result["decisions"] == report.body["decisions"]


def test_returned_by_only_counts_confirmed_returns(observation):
    returned = deepcopy(observation)
    returned["case_id"] = "QA-RET"
    inflight = {**returned, "case_id": "QA-FLIGHT"}
    book = stage(
        {
            "observations": [returned, inflight],
            "outcomes": [
                {"case_id": "QA-RET", "available": 30, "value": 3.0, "occurred": True},
                {"case_id": "QA-FLIGHT", "available": 30, "value": 3.0, "occurred": False},
            ],
        },
        30,
    )
    assert returned_by(book, 30) == {"QA-RET"}
    assert returned_by(book, 29) == set()


def test_horizon_model_respects_training_freeze_and_lane_support(learning):
    _, fold, _, _, history, model = learning
    assert model.horizon["horizon"] == HORIZON_DAYS
    assert set(model.horizon["lane_support"]) == {
        signal.record.group for signal in history
    }
    assert model.horizon["overall_support"] <= model.support
    assert model.horizon["overall_support"] >= MIN_HORIZON_SUPPORT
    assert fold.train_before == split(fold.snapshot).train_before
