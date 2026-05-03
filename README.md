# LLM-Based Battery Datasheet Extraction & Validation

**Master 1 — Computer Science · CODIA Track**
University of Strasbourg · 2025–2026

**Authors:** Ashkan Motamedifar · Kian Abdolmohammadian
**Submitted to:** Assoc. Prof. Ahmed Samet

---

## What to read first

| File | Purpose |
|---|---|
| **`report.pdf`** | Full project report — read this first |
| **`slides/slides.pdf`** | Oral defense slides |
| **`README.md`** | This file — how to run the code |

---

## What this project does

A three-level pipeline that extracts structured battery specifications from PDF datasheets, builds a knowledge graph, and validates the result to detect LLM hallucinations.

| Level | What it does |
|---|---|
| **1** | LLM extraction of specs from PDF → JSON (zero-shot vs few-shot) |
| **2** | OWL 2 ontology + JSON → RDF knowledge graph (Turtle) |
| **3** | 8 SPARQL validation rules → hallucination detection |

**Headline results:** 97 % F1 on extraction · 389 triples in the graph · all 8 validation rules fire correctly on a corrupted control graph.

---

## Setup (5 minutes)

**Requirements:** Python 3.11 or later.

### Step 0 — Place the input PDFs at the repo root

To keep the submission small, the four input datasheets are **not bundled** in the archive. Please place these files (the same ones you provided in the project assignment) at the **root of this folder**, with their original filenames:

```
16340-battery-datasheet.pdf
3.7V9059156.pdf
CATL-86Ah-3.2V-LiFePO4-Prismatic-Battery-Cell-SpecificationDatasheet.pdf
lir2450_EEMB.pdf
project.pdf                ← the original project brief, used as a negative-control input
```

Without these PDFs, Level 1 cannot be re-run. Levels 2 and 3 still work because their inputs (the JSON extractions) are already committed under `out/`.

### Step 1–3 — Install

```bash
# 1. Create a virtual environment
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. (Only needed to RE-RUN Level 1) — provide an Anthropic API key
echo "ANTHROPIC_API_KEY=sk-ant-..." > .env
```

> **Note:** All extraction outputs and the knowledge graph are **already committed** under `out/`. You can run Levels 2 and 3 without re-running Level 1, and therefore without an API key or the input PDFs.

---

## How to run each level

### Level 1 — Extract from PDFs (requires API key)

```bash
# Zero-shot extraction (best strategy in our experiments)
python -m src.extractor --strategy zero-shot

# Few-shot extraction
python -m src.extractor --strategy few-shot

# Compare against gold dataset → precision / recall / F1
python -m src.evaluate
```
Outputs: `out/zero-shot/*.json`, `out/few-shot/*.json`

### Level 2 — Build the knowledge graph

```bash
# JSON → RDF triples in Turtle format
python -m src.kg_builder

# Run 6 demonstration SPARQL queries on the graph
python -m src.query_kg
```
Output: `out/kg/battery_kg.ttl` (389 triples, 4 batteries)

### Level 3 — Validate the graph

```bash
# Run all 8 SPARQL validation rules
python -m src.validate_kg
```
Detects: missing units, voltage hierarchy violations, value/raw-text mismatches (the hallucination check), out-of-range nominal voltage, etc.

---

## Project structure

```
.
├── README.md                    ← you are here
├── report.pdf                   ← the full project report
├── requirements.txt
│
├── *.pdf                        ← four input datasheets + project.pdf (NOT bundled — see Setup Step 0)
│
├── src/
│   ├── schema.py                Pydantic v2 BatterySpec model (Level 1)
│   ├── prompts.py               Zero-shot and few-shot LLM prompts
│   ├── extractor.py             PDF → JSON via Claude API
│   ├── evaluate.py              Precision / recall / F1 vs gold dataset
│   ├── kg_builder.py            JSON → RDF triples using rdflib (Level 2)
│   ├── query_kg.py              SPARQL query demonstrations
│   └── validate_kg.py           8 SPARQL validation rules (Level 3)
│
├── ontology/
│   ├── battery.owl              OWL 2 ontology (authored in Protégé)
│   └── battery.ttl              same ontology, Turtle serialisation
│
├── data/
│   └── gold.json                Hand-annotated reference for evaluation
│
├── tools/
│   └── build_gold_raw.py        Helper to build the gold dataset
│
├── out/
│   ├── zero-shot/               Level 1 extraction results — zero-shot
│   ├── few-shot/                Level 1 extraction results — few-shot
│   ├── kg/                      Level 2 generated knowledge graph
│   └── *.json                   per-PDF extraction outputs
│
└── slides/
    └── slides.pdf               oral defense slides
```

---

## Key results

| Strategy | Precision | Recall | F1 | Hallucination rate |
|---|---|---|---|---|
| **Zero-shot** | 97.0 % | 97.0 % | **97.0 %** | 3.0 % |
| Few-shot | 93.9 % | 96.9 % | 95.4 % | 6.1 % |

Counter-intuitive finding: the few-shot example leaked stylistic noise (a "Co Ltd" suffix from the example datasheet propagated to other batteries), making it perform *worse* than zero-shot. Detailed analysis is in the report.

---

## Task distribution

| Author | Responsibility |
|---|---|
| **Ashkan Motamedifar** | Level 1 — schema design, extractor, prompts, evaluation · Report writing · Slides preparation |
| **Kian Abdolmohammadian** | Level 2 — ontology design, RDF builder, SPARQL queries · Level 3 — validation rules |
