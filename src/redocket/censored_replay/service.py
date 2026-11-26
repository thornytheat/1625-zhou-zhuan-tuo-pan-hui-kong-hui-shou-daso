from collections import defaultdict
from dataclasses import replace

from ..pallet_custody.service import known_labels
from ..return_survival.horizon import observed_not_returned
from ..return_survival.service import horizon as horizon_estimate, score
from ..settings import METRIC_LABEL, TARGET
from .contracts import Assessment, Folds, HorizonPair, Paired, ScoreCard
from .evaluation import (
    apply_calibration,
    calibrate,
    evaluate,
    evaluate_horizon,
    percentile,
)


def split(as_of):
    return Folds(as_of - 63, as_of - 34, as_of - 11, as_of)


def horizon_paired(signals, intake, after, before, reference_day, model):
    """按固定时距仍未归还构造回放对，只取能判明历史结局的单据。"""
    labels = known_labels(intake, reference_day)
    pairs = []
    for item in signals:
        if not (after <= item.record.day < before):
            continue
        if item.record.arrived > reference_day:
            continue
        label = labels.get(item.record.case_id)
        if label is None:
            continue
        if item.record.reported.get("age") is None:
            continue
        actual = observed_not_returned(label.value, label.occurred)
        if actual is None:
            continue
        estimate = horizon_estimate(model, item)
        if not estimate.available:
            continue
        pairs.append(
            HorizonPair(
                item.record.case_id,
                item.record.group,
                int(actual),
                float(estimate.probability),
                estimate.source,
            )
        )
    return pairs


def backcheck_horizon(signals, intake, bounds, model):
    calibration = horizon_paired(
        signals,
        intake,
        bounds.train_before,
        bounds.calibrate_before,
        bounds.calibrate_before - 1,
        model,
    )
    holdout = horizon_paired(
        signals,
        intake,
        bounds.calibrate_before,
        bounds.validate_before,
        bounds.snapshot - 1,
        model,
    )
    overall = evaluate_horizon(holdout)
    grouped = defaultdict(list)
    for row in holdout:
        grouped[row.group].append(row)
    support_ok = len(calibration) >= 16 and overall["support"] >= 16
    loss, benchmark = overall["brier"], overall["reference_brier"]
    passed = (
        loss is not None
        and benchmark is not None
        and loss <= 1.25 * benchmark + 0.05
    )
    report = {
        "horizon_days": model.horizon["horizon"] if model.horizon else None,
        "calibration_cases": len(calibration),
        "holdout_cases": len(holdout),
        "overall": overall,
        "groups": {k: evaluate_horizon(rows) for k, rows in sorted(grouped.items())},
        "passed": passed and support_ok,
        "decision_threshold": 0.5,
    }
    return support_ok and passed, report


def paired(signals, intake, after, before, reference_day, model):
    labels = known_labels(intake, reference_day)
    return [
        Paired(
            item.record.case_id,
            item.record.group,
            labels[item.record.case_id].value,
            score(model, item),
            score(model, item, baseline=True),
            labels[item.record.case_id].occurred,
        )
        for item in signals
        if after <= item.record.day < before
        and item.record.arrived <= reference_day
        and item.record.case_id in labels
    ]


def backcheck(signals, intake, bounds, model):
    calibration = paired(
        signals,
        intake,
        bounds.train_before,
        bounds.calibrate_before,
        bounds.calibrate_before - 1,
        model,
    )
    holdout = paired(
        signals,
        intake,
        bounds.calibrate_before,
        bounds.validate_before,
        bounds.snapshot - 1,
        model,
    )
    steps = calibrate(calibration, model.incumbent)
    evidence = [
        replace(row, predicted=apply_calibration(row.predicted, steps))
        for row in holdout
    ]
    radius = (
        None
        if TARGET in {"binary", "anomaly"} or len(calibration) < 16
        else percentile(
            [abs(row.actual - row.predicted) for row in calibration if row.occurred],
            0.80,
        )
    )
    overall = evaluate(evidence, radius)
    loss, benchmark = overall["loss"], overall["reference_loss"]
    if TARGET == "anomaly":
        rank = overall["auc"]
        passed = rank is not None and rank >= 0.48
    else:
        passed = (
            loss is not None
            and benchmark is not None
            and loss <= 1.25 * benchmark + 0.05
        )
    grouped = defaultdict(list)
    for row in evidence:
        grouped[row.group].append(row)
    report = {
        "metric": METRIC_LABEL,
        "overall": overall,
        "groups": {k: evaluate(rows, radius) for k, rows in sorted(grouped.items())},
        "calibration_cases": len(calibration),
        "holdout_cases": len(holdout),
        "holdout_days": [bounds.calibrate_before, bounds.validate_before - 1],
        "label_cutoffs": [
            bounds.train_before - 1,
            bounds.calibrate_before - 1,
            bounds.snapshot - 1,
        ],
        "fold_start": [
            bounds.train_before,
            bounds.calibrate_before,
            bounds.validate_before,
        ],
        "calibration_points": len(steps),
        "interval_radius": radius,
    }
    gate = (
        passed
        and model.state is not None
        and len(calibration) >= 16
        and overall["observed_support"] >= 16
    )
    horizon_gate, horizon_report = backcheck_horizon(signals, intake, bounds, model)
    report["horizon"] = horizon_report
    return Assessment(steps, radius, gate, report, horizon_gate)


def score_card(model, assessment, signal):
    estimate = apply_calibration(score(model, signal), assessment.calibration)
    prior = score(model, signal, baseline=True)
    lower = (
        max(0.0, estimate - assessment.radius)
        if assessment.radius is not None
        else None
    )
    upper = estimate + assessment.radius if assessment.radius is not None else None
    return ScoreCard(
        signal,
        estimate,
        prior,
        lower,
        upper,
        horizon_estimate(model, signal),
        assessment.horizon_passed,
    )
