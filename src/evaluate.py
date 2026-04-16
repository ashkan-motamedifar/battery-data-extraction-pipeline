"""Level 1 evaluation: score extraction results against a gold dataset.

Computes field-level precision, recall, F1, and a hallucination rate for
one or more prompting strategies, then prints a Markdown comparison table.

Usage (from the project root):

    # Score zero-shot results already in out/zero-shot/
    .venv/bin/python -m src.evaluate \\
        --gold data/gold.json \\
        --predictions out/zero-shot/extractions.json \\
        --label zero-shot

    # Compare zero-shot vs few-shot side-by-side
    .venv/bin/python -m src.evaluate \\
        --gold data/gold.json \\
        --predictions out/zero-shot/extractions.json out/few-shot/extractions.json \\
        --labels zero-shot few-shot

Definitions
-----------
A predicted field value is **correct** if it matches the gold value within
tolerance (numeric: ≤1 % relative error; string/enum: exact match).

- **Precision**  = correct_predictions / total_non-null_predictions
  (of what the model claimed, how much was right)
- **Recall**     = correct_predictions / total_non-null_gold_fields
  (of what was in the datasheet, how much did we find)
- **F1**         = 2 * P * R / (P + R)
- **Hallucination rate** = wrong_non-null_predictions / total_non-null_predictions
  (of what the model claimed, how much was fabricated or wrong)

`project.pdf` is excluded from all metrics: it is a negative control
(non-datasheet), not a battery spec to be evaluated.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

NUMERIC_TOLERANCE = 0.01  # 1 % relative error allowed for floats

# Leaf fields of BatterySpec that we score.  Nested objects (Capacity,
# TemperatureRange) are flattened one level down.  `raw` sub-fields are
# excluded from scoring — they are provenance strings, not extracted facts.
_NESTED_FIELDS = {
    "capacity": ["nominal_mah", "minimum_mah", "c_rate_condition", "test_temperature_celsius"],
    "operating_temperature": ["min_celsius", "max_celsius"],
    "charge_temperature": ["min_celsius", "max_celsius"],
    "storage_temperature": ["min_celsius", "max_celsius"],
}

_SCALAR_FIELDS = [
    "manufacturer",
    "model",
    "chemistry",
    "form_factor",
    "nominal_voltage_v",
    "charge_cutoff_voltage_v",
    "discharge_cutoff_voltage_v",
    "max_continuous_discharge_current_a",
    "internal_resistance_mohm",
    "cycle_life",
    "weight_g",
]


def _flatten(record: dict) -> dict[str, Any]:
    """Return a flat dict of scoreable leaf values from a BatterySpec dict."""
    flat: dict[str, Any] = {}
    for f in _SCALAR_FIELDS:
        flat[f] = record.get(f)
    for parent, children in _NESTED_FIELDS.items():
        sub = record.get(parent) or {}
        for child in children:
            key = f"{parent}.{child}"
            flat[key] = sub.get(child) if sub else None
    return flat


def _values_match(pred: Any, gold: Any) -> bool:
    """Return True if pred is considered correct given gold."""
    if gold is None:
        # If gold is null the field is unknown — we don't penalise either way.
        return False  # treat as n/a (excluded from scoring)
    if pred is None:
        return False  # missed
    if isinstance(gold, float) or isinstance(pred, float):
        try:
            gf, pf = float(gold), float(pred)
        except (TypeError, ValueError):
            return str(pred).strip().lower() == str(gold).strip().lower()
        if gf == 0.0:
            return math.isclose(pf, gf, abs_tol=0.001)
        return abs(pf - gf) / abs(gf) <= NUMERIC_TOLERANCE
    # String / int comparison
    return str(pred).strip().lower() == str(gold).strip().lower()


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

class FieldStats:
    def __init__(self) -> None:
        self.tp = 0   # correct non-null prediction
        self.fp = 0   # wrong non-null prediction (hallucinated or off)
        self.fn = 0   # gold is non-null but prediction is null (missed)

    def precision(self) -> float:
        denom = self.tp + self.fp
        return self.tp / denom if denom else float("nan")

    def recall(self) -> float:
        denom = self.tp + self.fn
        return self.tp / denom if denom else float("nan")

    def f1(self) -> float:
        p, r = self.precision(), self.recall()
        if math.isnan(p) or math.isnan(r) or (p + r) == 0:
            return float("nan")
        return 2 * p * r / (p + r)

    def hallucination_rate(self) -> float:
        denom = self.tp + self.fp
        return self.fp / denom if denom else float("nan")


def score_predictions(
    gold_records: list[dict],
    pred_records: list[dict],
) -> tuple[FieldStats, dict[str, FieldStats]]:
    """Score pred_records against gold_records.

    Returns (overall_stats, per_field_stats).
    """
    # Index gold by source_file for O(1) lookup
    gold_index = {r["source_file"]: r for r in gold_records}

    overall = FieldStats()
    per_field: dict[str, FieldStats] = {}

    for pred in pred_records:
        src = pred.get("source_file", "")
        if src not in gold_index:
            # No gold entry → skip (includes project.pdf)
            continue
        gold = gold_index[src]

        pred_flat = _flatten(pred)
        gold_flat = _flatten(gold)

        for field, gold_val in gold_flat.items():
            if gold_val is None:
                continue  # unknown gold — don't count either way
            pred_val = pred_flat.get(field)
            fs = per_field.setdefault(field, FieldStats())
            if _values_match(pred_val, gold_val):
                fs.tp += 1
                overall.tp += 1
            elif pred_val is not None:
                # Predicted something but it's wrong → hallucination / error
                fs.fp += 1
                overall.fp += 1
            else:
                # Missed
                fs.fn += 1
                overall.fn += 1

    return overall, per_field


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def _pct(v: float) -> str:
    return f"{v * 100:.1f}%" if not math.isnan(v) else "—"


def print_summary_table(labels: list[str], results: list[tuple[FieldStats, dict]]) -> None:
    print("\n## Overall metrics\n")
    header = f"{'Strategy':<15} {'Precision':>10} {'Recall':>8} {'F1':>8} {'Halluc. rate':>14}"
    print(header)
    print("-" * len(header))
    for label, (overall, _) in zip(labels, results):
        print(
            f"{label:<15} "
            f"{_pct(overall.precision()):>10} "
            f"{_pct(overall.recall()):>8} "
            f"{_pct(overall.f1()):>8} "
            f"{_pct(overall.hallucination_rate()):>14}"
        )

    if len(results) < 2:
        return

    print("\n## Per-field F1 comparison\n")
    all_fields = sorted(
        set().union(*[set(pf.keys()) for _, pf in results])
    )
    col_w = 10
    header2 = f"{'Field':<42}" + "".join(f"{lbl:>{col_w}}" for lbl in labels)
    print(header2)
    print("-" * len(header2))
    for field in all_fields:
        row = f"{field:<42}"
        for _, per_field in results:
            fs = per_field.get(field)
            row += f"{_pct(fs.f1()) if fs else '—':>{col_w}}"
        print(row)


def print_detailed_errors(
    label: str,
    gold_records: list[dict],
    pred_records: list[dict],
) -> None:
    gold_index = {r["source_file"]: r for r in gold_records}
    print(f"\n## Errors — {label}\n")
    found_any = False
    for pred in pred_records:
        src = pred.get("source_file", "")
        if src not in gold_index:
            continue
        gold = gold_index[src]
        pred_flat = _flatten(pred)
        gold_flat = _flatten(gold)
        for field, gold_val in gold_flat.items():
            if gold_val is None:
                continue
            pred_val = pred_flat.get(field)
            if pred_val is not None and not _values_match(pred_val, gold_val):
                print(f"  [{src}] {field}: predicted={pred_val!r}, gold={gold_val!r}  ← WRONG")
                found_any = True
            elif pred_val is None:
                print(f"  [{src}] {field}: predicted=null, gold={gold_val!r}  ← MISSED")
                found_any = True
    if not found_any:
        print("  (no errors)")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--gold",
        type=Path,
        default=Path("data/gold.json"),
        help="Path to gold.json (default: data/gold.json).",
    )
    parser.add_argument(
        "--predictions",
        type=Path,
        nargs="+",
        required=True,
        help="One or more extractions.json files to evaluate.",
    )
    parser.add_argument(
        "--labels",
        nargs="*",
        help="Display labels for each predictions file (defaults to filenames).",
    )
    parser.add_argument(
        "--errors",
        action="store_true",
        default=False,
        help="Print detailed field-level errors after the summary table.",
    )
    args = parser.parse_args()

    if not args.gold.is_file():
        print(f"ERROR: gold file not found: {args.gold}", file=sys.stderr)
        return 1

    gold_records: list[dict] = json.loads(args.gold.read_text())

    labels = args.labels or [str(p) for p in args.predictions]
    if len(labels) != len(args.predictions):
        print("ERROR: --labels count must match --predictions count", file=sys.stderr)
        return 1

    all_results: list[tuple[FieldStats, dict]] = []
    all_preds: list[list[dict]] = []

    for pred_path in args.predictions:
        if not pred_path.is_file():
            print(f"ERROR: predictions file not found: {pred_path}", file=sys.stderr)
            return 1
        pred_records: list[dict] = json.loads(pred_path.read_text())
        overall, per_field = score_predictions(gold_records, pred_records)
        all_results.append((overall, per_field))
        all_preds.append(pred_records)

    print_summary_table(labels, all_results)

    if args.errors:
        for label, pred_records in zip(labels, all_preds):
            print_detailed_errors(label, gold_records, pred_records)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
