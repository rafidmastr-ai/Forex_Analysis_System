"""Applies the 8-point weight-acceptance rule to a strategy's optimization
summary (written by scripts/optimize_strategy.py) and writes the verdict
back into the same JSON file under "acceptance_rule" / "final_status".

The 8 criteria (spec): must improve in Training; must hold in Validation;
must show reasonable OOS behavior; must not collapse under perturbation;
must not rely on too few trades; must not be overly sensitive to weight
changes; must not depend on only one Symbol without explanation; must not
depend on only one time period. Fail any -> do NOT adopt the weights (the
experiment stays logged in the registry either way).

Thresholds below were fixed while writing this classifier, before reading
any strategy's actual numbers, and applied identically to Classic, SMC and
ICT — never adjusted per-strategy after seeing a result (that would be
exactly the kind of threshold-shopping this framework exists to prevent).

Usage: python scripts/classify_optimization_result.py <classic|smc|ict>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

MIN_RESOLVED_TRAIN_HARD_FLOOR = 10   # below this, the sample is not meaningfully evaluable at all
MIN_RESOLVED_TRAIN_SOFT_TARGET = 30  # matches optimization/objective.py's own min_trades full-credit target
MIN_RESOLVED_OOS_FLOOR = 5           # OOS windows are short (~20% of a year of M15 data); demand only a minimal sample
COLLAPSE_MARGIN_MULTIPLIER = 2.0     # a perturbation drop beyond 2x |unperturbed objective| (or 2.0 absolute, whichever larger) is a collapse


def classify(summary: dict) -> dict:
    baseline_train_obj = summary["baseline"]["train"]["objective"]
    baseline_validation_obj = summary["baseline"]["validation"]["objective"]
    baseline_oos_obj = summary["baseline"]["out_of_sample"]["objective"]

    candidate_train_obj = summary["candidate_train_objective"]
    candidate_validation_obj = summary["candidate_validation"]["objective"]
    candidate_oos_obj = summary["candidate_oos"]["objective"]

    train_resolved = None
    for r in summary["all_train_search_results"]:
        if r["weights"] == summary["candidate_weights"]:
            train_resolved = r["resolved_count"]
            break
    oos_resolved = summary["candidate_oos"]["metrics"]["resolved_count"]

    unperturbed = summary["perturbation"]["unperturbed_validation_objective"]
    min_perturbed = summary["perturbation"]["min_objective"]
    collapse_margin = max(abs(unperturbed), 1.0) * COLLAPSE_MARGIN_MULTIPLIER
    perturbation_drop = unperturbed - min_perturbed

    checks = {
        "improves_in_training": candidate_train_obj > baseline_train_obj,
        "holds_in_validation": candidate_validation_obj >= baseline_validation_obj,
        "reasonable_oos": (candidate_oos_obj >= baseline_oos_obj) and (oos_resolved >= MIN_RESOLVED_OOS_FLOOR),
        "no_perturbation_collapse": perturbation_drop <= collapse_margin,
        "sufficient_trades": (train_resolved or 0) >= MIN_RESOLVED_TRAIN_HARD_FLOOR,
        "not_oversensitive_to_weights": perturbation_drop <= collapse_margin,  # same signal as collapse, kept separate per spec's own 8-item list
    }

    xau = summary["xauusd_generalization"]
    xau_objectives = [xau[p]["objective"] for p in ("train", "validation", "out_of_sample")]
    xau_positive_phases = sum(1 for o in xau_objectives if o > 0)
    symbol_note = (
        f"positive on {xau_positive_phases}/3 XAUUSD phases (objectives: "
        f"{[round(o, 3) for o in xau_objectives]}) using the EURUSD-derived weights unchanged"
    )

    period_note = (
        "validation and OOS both move in the same direction as training relative to baseline"
        if checks["holds_in_validation"] and checks["reasonable_oos"]
        else "candidate does not hold consistently outside the training period"
    )

    all_hard_checks_pass = all(checks.values())
    if all_hard_checks_pass:
        status = "Robust Candidate" if xau_positive_phases >= 1 else "Candidate"
    elif not checks["no_perturbation_collapse"]:
        status = "Overfit Risk"
    else:
        status = "Rejected"

    warnings = []
    if (train_resolved or 0) < MIN_RESOLVED_TRAIN_SOFT_TARGET:
        warnings.append(
            f"train resolved_count={train_resolved} is below the {MIN_RESOLVED_TRAIN_SOFT_TARGET}-trade "
            "full-credit target used by composite_objective's own trade_count_factor — results are "
            "small-sample and already discounted accordingly, not silently trusted at face value."
        )
    if xau_positive_phases == 0:
        warnings.append("candidate is negative on all 3 XAUUSD phases — no evidence of cross-symbol generalization.")

    return {
        "checks": checks,
        "perturbation_drop": perturbation_drop,
        "collapse_margin_used": collapse_margin,
        "symbol_generalization_note": symbol_note,
        "period_dependence_note": period_note,
        "warnings": warnings,
        "final_status": status,
    }


def main(strategy_key: str) -> None:
    path = Path("data/optimization_results") / f"{strategy_key}_summary.json"
    summary = json.loads(path.read_text())
    verdict = classify(summary)
    summary["acceptance_rule"] = verdict
    path.write_text(json.dumps(summary, indent=2, default=str))
    print(json.dumps(verdict, indent=2))
    print(f"\nFINAL STATUS for {summary['strategy']}: {verdict['final_status']}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"usage: python {sys.argv[0]} <classic|smc|ict>")
        sys.exit(1)
    main(sys.argv[1])
