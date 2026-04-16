"""Level 2 -- SPARQL query demonstrations over the battery knowledge graph.

Runs a small suite of SPARQL queries against `out/kg/battery_kg.ttl`
and pretty-prints the results. The queries are chosen to show that the
KG is actually queryable in realistic engineering-style ways:

  Q1  Who manufactures what?
  Q2  All LiFePO4 batteries with their nominal voltage.
  Q3  All batteries with nominal capacity > 1 Ah, sorted by capacity.
  Q4  Batteries that can operate at or below -10 C.
  Q5  Count of batteries per chemistry / per form factor.
  Q6  Cutoff-voltage spread: charge / nominal / discharge per battery.

Run from the project root:

    .venv/bin/python -m src.query_kg
"""

from __future__ import annotations

import argparse
from pathlib import Path

from rdflib import Graph


DEFAULT_KG = Path("out/kg/battery_kg.ttl")


# ----------------------------------------------------------------------------
# Query bank
# ----------------------------------------------------------------------------

PREFIX = """
PREFIX bat:  <http://battery-kg.org/ontology#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
"""

Q1 = PREFIX + """
SELECT ?model ?manufacturer WHERE {
  ?b a bat:Battery ;
     bat:modelName ?model ;
     bat:producedBy ?mfrNode .
  ?mfrNode bat:manufacturerName ?manufacturer .
}
ORDER BY ?manufacturer
"""

Q2 = PREFIX + """
SELECT ?model ?voltage WHERE {
  ?b a bat:Battery ;
     bat:modelName ?model ;
     bat:hasChemistry bat:LiFePO4 ;
     bat:hasNominalVoltage ?qv .
  ?qv bat:numericValue ?voltage .
}
ORDER BY ?model
"""

Q3 = PREFIX + """
SELECT ?model ?capacity_mah WHERE {
  ?b a bat:Battery ;
     bat:modelName ?model ;
     bat:hasCapacity ?qv .
  ?qv bat:numericValue ?capacity_mah ;
      bat:hasUnit bat:MilliampHour .
  FILTER (?capacity_mah > 1000)
}
ORDER BY DESC(?capacity_mah)
"""

Q4 = PREFIX + """
SELECT ?model ?tmin WHERE {
  ?b a bat:Battery ;
     bat:modelName ?model ;
     bat:hasOperatingTemperatureRange ?tr .
  ?tr bat:minCelsius ?tmin .
  FILTER (?tmin <= -10)
}
ORDER BY ?tmin
"""

Q5 = PREFIX + """
SELECT ?chemistry (COUNT(?b) AS ?n) WHERE {
  ?b a bat:Battery ;
     bat:hasChemistry ?c .
  ?c rdfs:label ?chemistry .
}
GROUP BY ?chemistry
ORDER BY DESC(?n)
"""

Q6 = PREFIX + """
SELECT ?model ?discharge ?nominal ?charge WHERE {
  ?b a bat:Battery ;
     bat:modelName ?model ;
     bat:hasNominalVoltage         ?nv ;
     bat:hasChargeCutoffVoltage    ?cv ;
     bat:hasDischargeCutoffVoltage ?dv .
  ?nv bat:numericValue ?nominal .
  ?cv bat:numericValue ?charge .
  ?dv bat:numericValue ?discharge .
}
ORDER BY ?model
"""


QUERIES = [
    ("Q1 -- Who manufactures what?",                  Q1),
    ("Q2 -- LiFePO4 batteries and their voltage",     Q2),
    ("Q3 -- Batteries with capacity > 1 Ah",          Q3),
    ("Q4 -- Batteries operating at or below -10 C",   Q4),
    ("Q5 -- Batteries grouped by chemistry",          Q5),
    ("Q6 -- Cutoff voltage window per battery",       Q6),
]


# ----------------------------------------------------------------------------
# Pretty printing
# ----------------------------------------------------------------------------

def _render(results) -> str:
    rows = [list(r) for r in results]
    if not rows:
        return "  (no results)"

    vars_ = [str(v) for v in results.vars]
    cols = [vars_] + [[str(c) for c in row] for row in rows]
    widths = [max(len(c[i]) for c in cols) for i in range(len(vars_))]

    def _fmt(row: list[str]) -> str:
        return "  " + "  ".join(c.ljust(w) for c, w in zip(row, widths))

    sep = "  " + "  ".join("-" * w for w in widths)
    lines = [_fmt(vars_), sep]
    for row in rows:
        lines.append(_fmt([str(c) for c in row]))
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kg", type=Path, default=DEFAULT_KG,
                        help=f"Path to the KG Turtle file (default: {DEFAULT_KG}).")
    args = parser.parse_args()

    if not args.kg.is_file():
        print(f"ERROR: KG file not found: {args.kg}")
        print("Hint: run `python -m src.kg_builder` first.")
        return 1

    g = Graph()
    g.parse(args.kg, format="turtle")
    print(f"Loaded {len(g)} triples from {args.kg}\n")

    for title, query in QUERIES:
        print("=" * 72)
        print(title)
        print("=" * 72)
        res = g.query(query)
        print(_render(res))
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
