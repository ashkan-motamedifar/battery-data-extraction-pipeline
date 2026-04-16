"""Level 2 -- Knowledge Graph builder.

Reads the JSON output of the Level 1 extractor and converts it into an
RDF graph conforming to `ontology/battery.ttl`. Every numeric
specification becomes a QuantityValue node carrying (value, unit,
raw-source-text), preserving the provenance needed for Level 3.

Run from the project root:

    .venv/bin/python -m src.kg_builder \\
        --extractions out/zero-shot/extractions.json \\
        --ontology    ontology/battery.ttl \\
        --output      out/kg/battery_kg.ttl
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Optional

from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import OWL, RDF, RDFS, XSD

# --- Namespaces --------------------------------------------------------------
BAT     = Namespace("http://battery-kg.org/ontology#")
BATTERY = Namespace("http://battery-kg.org/resource/battery/")
MFR     = Namespace("http://battery-kg.org/resource/manufacturer/")
QV      = Namespace("http://battery-kg.org/resource/qv/")
TRANGE  = Namespace("http://battery-kg.org/resource/tempRange/")


# --- Unit map: (field-name-suffix in the schema)  ->  ontology Unit IRI ------
UNIT_MAP = {
    "v":    BAT.Volt,
    "mah":  BAT.MilliampHour,
    "mohm": BAT.MilliOhm,
    "a":    BAT.Ampere,
    "g":    BAT.Gram,
}

# --- Chemistry / FormFactor map ---------------------------------------------
CHEMISTRY_MAP = {
    "Li-ion":     BAT.LiIon,
    "Li-polymer": BAT.LiPolymer,
    "LiFePO4":    BAT.LiFePO4,
    "NiMH":       BAT.NiMH,
    "NiCd":       BAT.NiCd,
    "Other":      BAT.OtherChemistry,
}
FORM_FACTOR_MAP = {
    "cylindrical": BAT.Cylindrical,
    "prismatic":   BAT.Prismatic,
    "pouch":       BAT.Pouch,
    "coin":        BAT.Coin,
    "other":       BAT.OtherFormFactor,
}


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------

_SLUG_RE = re.compile(r"[^A-Za-z0-9]+")


def _slug(text: str) -> str:
    """Turn arbitrary text into a URI-safe slug."""
    return _SLUG_RE.sub("_", text.strip()).strip("_") or "unknown"


def _battery_uri(spec: dict) -> URIRef:
    model = spec.get("model") or Path(spec["source_file"]).stem
    return BATTERY[_slug(model)]


def _manufacturer_uri(name: str) -> URIRef:
    return MFR[_slug(name)]


def _qv_uri(battery_slug: str, field: str) -> URIRef:
    return QV[f"{battery_slug}__{field}"]


def _trange_uri(battery_slug: str, which: str) -> URIRef:
    return TRANGE[f"{battery_slug}__{which}"]


# ----------------------------------------------------------------------------
# Triple emission
# ----------------------------------------------------------------------------

def _add_quantity_value(
    g: Graph,
    subject: URIRef,
    predicate: URIRef,
    battery_slug: str,
    field: str,
    numeric_value: float,
    unit: URIRef,
    *,
    minimum_value: Optional[float] = None,
    raw_text: Optional[str] = None,
    c_rate: Optional[str] = None,
    test_temperature_c: Optional[float] = None,
) -> None:
    """Create a QuantityValue node and link it to the subject Battery."""
    qv = _qv_uri(battery_slug, field)
    g.add((subject, predicate, qv))
    g.add((qv, RDF.type, BAT.QuantityValue))
    g.add((qv, BAT.numericValue, Literal(numeric_value, datatype=XSD.decimal)))
    g.add((qv, BAT.hasUnit, unit))
    if minimum_value is not None:
        g.add((qv, BAT.minimumValue, Literal(minimum_value, datatype=XSD.decimal)))
    if raw_text:
        g.add((qv, BAT.rawText, Literal(raw_text, datatype=XSD.string)))
    if c_rate:
        g.add((qv, BAT.conditionCRate, Literal(c_rate, datatype=XSD.string)))
    if test_temperature_c is not None:
        g.add((qv, BAT.conditionTemperatureCelsius,
               Literal(test_temperature_c, datatype=XSD.decimal)))


def _add_temp_range(
    g: Graph,
    subject: URIRef,
    predicate: URIRef,
    battery_slug: str,
    which: str,
    trange: dict,
) -> None:
    node = _trange_uri(battery_slug, which)
    g.add((subject, predicate, node))
    g.add((node, RDF.type, BAT.TemperatureRange))
    g.add((node, BAT.minCelsius, Literal(trange["min_celsius"], datatype=XSD.decimal)))
    g.add((node, BAT.maxCelsius, Literal(trange["max_celsius"], datatype=XSD.decimal)))
    if trange.get("raw"):
        g.add((node, BAT.rawText, Literal(trange["raw"], datatype=XSD.string)))


# ----------------------------------------------------------------------------
# Per-spec conversion
# ----------------------------------------------------------------------------

def _add_battery(g: Graph, spec: dict) -> None:
    """Add all triples for one BatterySpec record to the graph."""
    # Skip negative-control / empty records (project.pdf returns all nulls)
    if spec.get("nominal_voltage_v") is None and spec.get("capacity") is None:
        return

    bat_uri = _battery_uri(spec)
    bat_slug = _slug(spec.get("model") or Path(spec["source_file"]).stem)

    g.add((bat_uri, RDF.type, BAT.Battery))
    g.add((bat_uri, BAT.sourceFile, Literal(spec["source_file"], datatype=XSD.string)))
    if spec.get("model"):
        g.add((bat_uri, BAT.modelName, Literal(spec["model"], datatype=XSD.string)))

    # Manufacturer
    if mfr := spec.get("manufacturer"):
        m_uri = _manufacturer_uri(mfr)
        g.add((m_uri, RDF.type, BAT.Manufacturer))
        g.add((m_uri, BAT.manufacturerName, Literal(mfr, datatype=XSD.string)))
        g.add((bat_uri, BAT.producedBy, m_uri))

    # Chemistry
    if chem := spec.get("chemistry"):
        if chem in CHEMISTRY_MAP:
            g.add((bat_uri, BAT.hasChemistry, CHEMISTRY_MAP[chem]))

    # Form factor
    if ff := spec.get("form_factor"):
        if ff in FORM_FACTOR_MAP:
            g.add((bat_uri, BAT.hasFormFactor, FORM_FACTOR_MAP[ff]))

    # Nominal voltage
    if (v := spec.get("nominal_voltage_v")) is not None:
        _add_quantity_value(g, bat_uri, BAT.hasNominalVoltage,
                            bat_slug, "nominalVoltage", v, BAT.Volt)

    # Capacity
    if cap := spec.get("capacity"):
        _add_quantity_value(
            g, bat_uri, BAT.hasCapacity, bat_slug, "capacity",
            cap["nominal_mah"], BAT.MilliampHour,
            minimum_value=cap.get("minimum_mah"),
            raw_text=cap.get("raw"),
            c_rate=cap.get("c_rate_condition"),
            test_temperature_c=cap.get("test_temperature_celsius"),
        )

    # Cutoff voltages
    if (v := spec.get("charge_cutoff_voltage_v")) is not None:
        _add_quantity_value(g, bat_uri, BAT.hasChargeCutoffVoltage,
                            bat_slug, "chargeCutoff", v, BAT.Volt)
    if (v := spec.get("discharge_cutoff_voltage_v")) is not None:
        _add_quantity_value(g, bat_uri, BAT.hasDischargeCutoffVoltage,
                            bat_slug, "dischargeCutoff", v, BAT.Volt)

    # Max continuous discharge current
    if (a := spec.get("max_continuous_discharge_current_a")) is not None:
        _add_quantity_value(g, bat_uri, BAT.hasMaxContinuousDischargeCurrent,
                            bat_slug, "maxDischargeCurrent", a, BAT.Ampere)

    # Internal resistance
    if (r := spec.get("internal_resistance_mohm")) is not None:
        _add_quantity_value(g, bat_uri, BAT.hasInternalResistance,
                            bat_slug, "internalResistance", r, BAT.MilliOhm)

    # Weight
    if (w := spec.get("weight_g")) is not None:
        _add_quantity_value(g, bat_uri, BAT.hasWeight,
                            bat_slug, "weight", w, BAT.Gram)

    # Cycle life (integer data property, no unit)
    if (c := spec.get("cycle_life")) is not None:
        g.add((bat_uri, BAT.cycleLife, Literal(int(c), datatype=XSD.integer)))

    # Temperature ranges
    if tr := spec.get("operating_temperature"):
        _add_temp_range(g, bat_uri, BAT.hasOperatingTemperatureRange,
                        bat_slug, "operating", tr)
    if tr := spec.get("charge_temperature"):
        _add_temp_range(g, bat_uri, BAT.hasChargeTemperatureRange,
                        bat_slug, "charge", tr)
    if tr := spec.get("storage_temperature"):
        _add_temp_range(g, bat_uri, BAT.hasStorageTemperatureRange,
                        bat_slug, "storage", tr)


# ----------------------------------------------------------------------------
# Entry point
# ----------------------------------------------------------------------------

def build_graph(extractions_path: Path, ontology_path: Path) -> Graph:
    g = Graph()
    g.bind("bat",     BAT)
    g.bind("battery", BATTERY)
    g.bind("mfr",     MFR)
    g.bind("qv",      QV)
    g.bind("trange",  TRANGE)
    g.bind("owl",     OWL)
    g.bind("xsd",     XSD)

    # Load the ontology so the KG file is self-contained
    g.parse(ontology_path, format="turtle")

    records: list[dict] = json.loads(extractions_path.read_text())
    for spec in records:
        _add_battery(g, spec)

    return g


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--extractions", type=Path,
                        default=Path("out/zero-shot/extractions.json"),
                        help="Level 1 JSON output (default: out/zero-shot/extractions.json).")
    parser.add_argument("--ontology", type=Path,
                        default=Path("ontology/battery.ttl"),
                        help="Path to the battery ontology (default: ontology/battery.ttl).")
    parser.add_argument("--output", type=Path,
                        default=Path("out/kg/battery_kg.ttl"),
                        help="Output Turtle file (default: out/kg/battery_kg.ttl).")
    args = parser.parse_args()

    if not args.extractions.is_file():
        print(f"ERROR: extractions file not found: {args.extractions}", file=sys.stderr)
        return 1
    if not args.ontology.is_file():
        print(f"ERROR: ontology file not found: {args.ontology}", file=sys.stderr)
        return 1

    g = build_graph(args.extractions, args.ontology)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    g.serialize(destination=str(args.output), format="turtle")

    # Quick stats
    n_batteries = len(list(g.subjects(RDF.type, BAT.Battery)))
    n_qv        = len(list(g.subjects(RDF.type, BAT.QuantityValue)))
    n_tr        = len(list(g.subjects(RDF.type, BAT.TemperatureRange)))
    n_mfr       = len(list(g.subjects(RDF.type, BAT.Manufacturer)))
    print(f"[kg] wrote {len(g)} triples to {args.output}")
    print(f"[kg]   batteries      : {n_batteries}")
    print(f"[kg]   manufacturers  : {n_mfr}")
    print(f"[kg]   quantity values: {n_qv}")
    print(f"[kg]   temperature rgs: {n_tr}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
