"""Generate raw provenance strings for the gold dataset.

For every numeric value already validated in data/gold.json, locate the
value in the corresponding PDF's extracted text and write back a `raw`
string giving a short window around the best plausible match.

The numeric values themselves are NOT changed -- this script only fills
in the `raw` provenance fields. Each numeric value in gold.json was
hand-verified against the source PDF when the file was authored;
locating where in the source the value appears is a deterministic
text-search problem, not a re-extraction.

Disambiguation: when a value appears multiple times in a PDF (e.g.
"3.6" appears in both "Nominal Voltage 3.6V" and "3.6~4.0V"), windows
that also contain a relevant anchor keyword for that field are preferred.

Usage:

    .venv/bin/python tools/build_gold_raw.py

Writes data/gold.json in place. Re-runnable; existing raw strings are
overwritten.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pypdf

PROJECT_ROOT = Path(__file__).resolve().parent.parent
GOLD_PATH = PROJECT_ROOT / "data" / "gold.json"

WINDOW = 60  # chars on each side of a numeric match

# Anchor keywords per scalar field. The first window containing any of
# these (case-insensitive substring) wins; ties broken by text order.
SCALAR_ANCHORS: dict[str, list[str]] = {
    "nominal_voltage_v": [
        "Nominal Voltage", "Nominal voltage", "Working voltage",
        "Voltage", "Nominal",
    ],
    "charge_cutoff_voltage_v": [
        "Charge Voltage", "charge voltage", "Charging voltage",
        "Charge cut-off", "Charge cutoff", "End-of-charge",
        "CC/CV", "Standard charge", "voltage up to",
    ],
    "discharge_cutoff_voltage_v": [
        "Discharge cut-off", "Cut-off Voltage", "Cut off voltage",
        "End Voltage", "End-of-discharge", "Discharge to", "discharge to",
        "to 2.0", "to 2.5", "to 2.75",
    ],
    "max_continuous_discharge_current_a": [
        "Maximum Continuous", "Max. continuous", "Max Continuous",
        "Continuous Discharge", "Continuous Discharging",
        "Maximum Discharge", "Max Discharge",
        "Standard discharge current", "Discharge current",
    ],
    "internal_resistance_mohm": [
        "Internal resistance", "Internal Impedance", "Internal Resistance",
        "AC Impedance", "DC Resistance", "Impedance", "Resistance",
    ],
    "cycle_life": [
        "Cycle Life", "cycle life", "cycles", "circles",
    ],
    "weight_g": [
        "Weight", "weight", "Mass",
    ],
}

# Fields whose canonical unit (in gold) may differ from how the PDF
# expresses the value. When the canonical numeric value isn't found
# directly, we fall back to a window around the anchor keyword.
ANCHOR_FALLBACK_FIELDS = {
    "max_continuous_discharge_current_a",  # PDFs may give C-rate (e.g. "2C5A")
    "weight_g",                            # PDFs may give kg
}

# Anchor keywords for composite fields (capacity / temperature ranges).
COMPOSITE_ANCHORS: dict[str, list[str]] = {
    "capacity": [
        "Nominal Capacity", "Typical Capacity", "Rated Capacity",
        "Capacity",
    ],
    "operating_temperature": [
        "Operating Temperature", "Working temperature", "Discharge Temperature",
        "Operation temperature", "Temperature range",
    ],
    "charge_temperature": [
        "Charging Temperature", "Charge Temperature", "Charging temp",
        "Working temperature ：0",  # 9059156 labels charge range as "Working temperature" inside the charging block
    ],
    "storage_temperature": [
        "Storage Temperature", "Storage temp", "Storage",
    ],
}

# Length of window grabbed for composite fields (anchor + tail)
COMPOSITE_WINDOW = 100


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def extract_pdf_text(pdf_path: Path) -> str:
    """Return the concatenated text of every page in the PDF."""
    reader = pypdf.PdfReader(str(pdf_path))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def _value_pattern(value: float | int) -> str:
    """Build a regex matching the numeric value as it would appear in text.

    Tolerates two PDF-extraction artefacts:
      - trailing zeros after the fractional part (e.g. 4.2 -> "4.20")
      - whitespace introduced by the PDF text extractor (e.g. "1. 0")
    """
    if isinstance(value, int) or (isinstance(value, float) and value.is_integer()):
        v = str(int(value))
        # Integer N can appear as "N", "N.0", "N. 0", "N .0", "N . 0" in PDF text
        return rf"(?<![\d.]){re.escape(v)}(?:\s*\.\s*0+)?(?![\d])"
    # Float with a fractional part: split into int and frac, allow whitespace
    s = repr(float(value))
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    int_part, _, frac_part = s.partition(".")
    return (
        rf"(?<![\d.]){re.escape(int_part)}\s*\.\s*{re.escape(frac_part)}0*(?![\d])"
    )


def _clean(snippet: str) -> str:
    """Collapse whitespace in a snippet and strip."""
    return re.sub(r"\s+", " ", snippet).strip()


def find_value_window(
    text: str,
    value: float | int,
    anchors: list[str],
    extra_patterns: list[str] | None = None,
) -> str | None:
    """Find `value` in `text`, preferring positions near an anchor."""
    patterns = [_value_pattern(value)]
    if extra_patterns:
        patterns.extend(extra_patterns)

    matches: list[re.Match] = []
    for p in patterns:
        matches.extend(re.finditer(p, text))
    if not matches:
        return None

    text_lower = text.lower()
    anchors_lc = [a.lower() for a in anchors]

    best: tuple[int, int, str] | None = None  # (score, position, snippet)
    for m in matches:
        start = max(0, m.start() - WINDOW)
        end = min(len(text), m.end() + WINDOW)
        window = text[start:end]
        wlow = text_lower[start:end]
        score = sum(1 for a in anchors_lc if a in wlow)
        if best is None or score > best[0] or (score == best[0] and m.start() < best[1]):
            best = (score, m.start(), window)

    if best is None:
        return None
    return _clean(best[2])


def find_composite_window(text: str, anchors: list[str]) -> str | None:
    """Return a window starting at the first matching anchor."""
    text_lower = text.lower()
    for anchor in anchors:
        idx = text_lower.find(anchor.lower())
        if idx >= 0:
            end = min(len(text), idx + COMPOSITE_WINDOW)
            return _clean(text[idx:end])
    return None


# ---------------------------------------------------------------------------
# Capacity special handling
# ---------------------------------------------------------------------------

def find_capacity_window(text: str, capacity: dict) -> str | None:
    """Capacity is stored in mAh in gold; PDFs may use mAh OR Ah notation.

    Search for the mAh value first; if not found, also try the Ah form
    (e.g. 86000 mAh -> "86Ah" or "86 Ah").
    """
    nominal_mah = capacity.get("nominal_mah")
    if nominal_mah is None:
        return None
    extra: list[str] = []
    if nominal_mah >= 1000 and float(nominal_mah).is_integer():
        ah_val = nominal_mah / 1000.0
        if ah_val.is_integer():
            ah_str = str(int(ah_val))
        else:
            ah_str = repr(ah_val).rstrip("0").rstrip(".")
        extra.append(rf"\b{re.escape(ah_str)}\s*Ah\b")
    return find_value_window(
        text,
        nominal_mah,
        COMPOSITE_ANCHORS["capacity"],
        extra_patterns=extra,
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    if not GOLD_PATH.is_file():
        print(f"ERROR: {GOLD_PATH} not found", file=sys.stderr)
        return 1

    gold: list[dict] = json.loads(GOLD_PATH.read_text())
    new_gold: list[dict] = []

    for record in gold:
        src = record["source_file"]
        pdf_path = PROJECT_ROOT / src
        if not pdf_path.is_file():
            print(f"[skip] PDF not found for {src}")
            new_gold.append(record)
            continue

        print(f"\n=== {src} ===")
        text = extract_pdf_text(pdf_path)
        new_record = dict(record)

        # Scalar fields -> add `<field>_raw`
        for field, anchors in SCALAR_ANCHORS.items():
            val = record.get(field)
            raw_field = f"{field}_raw"
            if val is None:
                new_record[raw_field] = None
                continue
            raw = find_value_window(text, val, anchors)
            # Unit-conversion fallback: value not found directly (e.g. weight
            # given in kg, current given as C-rate). Grab a window around
            # the anchor instead so the provenance still points at real text.
            if raw is None and field in ANCHOR_FALLBACK_FIELDS:
                raw = find_composite_window(text, anchors)
            new_record[raw_field] = raw
            mark = "ok " if raw else "MISS"
            preview = raw[:70] if raw else "—"
            print(f"  [{mark}] {field}={val} → {preview}")

        # Composite fields -> overwrite the `.raw` sub-field
        # Capacity uses its dedicated finder (handles Ah <-> mAh)
        if record.get("capacity"):
            raw = find_capacity_window(text, record["capacity"])
            new_sub = dict(record["capacity"])
            new_sub["raw"] = raw
            new_record["capacity"] = new_sub
            mark = "ok " if raw else "MISS"
            print(f"  [{mark}] capacity.raw → {raw[:70] if raw else '—'}")

        for parent in ("operating_temperature", "charge_temperature", "storage_temperature"):
            sub = record.get(parent)
            if sub is None:
                continue
            raw = find_composite_window(text, COMPOSITE_ANCHORS[parent])
            new_sub = dict(sub)
            new_sub["raw"] = raw
            new_record[parent] = new_sub
            mark = "ok " if raw else "MISS"
            print(f"  [{mark}] {parent}.raw → {raw[:70] if raw else '—'}")

        new_gold.append(new_record)

    GOLD_PATH.write_text(json.dumps(new_gold, indent=2) + "\n")
    print(f"\n✓ Wrote {GOLD_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
