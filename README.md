# LLM-Based Battery Datasheet Extraction & Knowledge Graph

Master 1 — Computer Science, CODIA Track  
University of Strasbourg · 2025–2026  
**Ashkan Motamedifar · Kian Abdolmohammadin**  
Submitted to: Samet Ahmed

---

## What this project does

Extracts structured battery specifications (voltage, capacity, temperature, resistance…)
from heterogeneous PDF datasheets using Claude LLM, evaluates extraction quality, and
promotes the results to a queryable RDF knowledge graph.

| Level | Description | Status |
|-------|-------------|--------|
| 1 | LLM extraction + evaluation (zero-shot vs few-shot) | ✅ Done |
| 2 | OWL 2 ontology + RDF knowledge graph + SPARQL queries | ✅ Done |
| 3 | Hallucination detection via ontology constraints | 🔜 In progress |

---

## Setup (5 minutes)

**Prerequisites:** Python 3.11+.  
An Anthropic API key is **only needed to re-run Level 1** (the LLM extraction step).  
Levels 2 and 3 work entirely on pre-generated files already in the repo — no key required.

```bash
# 1. Clone the repo
git clone <repo-url>
cd <repo-folder>

# 2. Create virtual environment
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. (Only for Level 1) Add your API key
echo "ANTHROPIC_API_KEY=sk-ant-..." > .env
```

---

## Running the pipeline

### Level 1 — Extract specs from PDFs

```bash
# Zero-shot extraction (all 5 PDFs including negative control)
python -m src.extractor --strategy zero-shot

# Few-shot extraction
python -m src.extractor --strategy few-shot

# Evaluate against gold dataset
python -m src.evaluate
```

Outputs land in `out/zero-shot/` and `out/few-shot/`.

### Level 2 — Build the knowledge graph

```bash
# Build the RDF graph from Level 1 output
python -m src.kg_builder

# Run the 6 SPARQL demo queries
python -m src.query_kg
```

Output: `out/kg/battery_kg.ttl` (364 triples, 4 batteries).

---

## Project structure

```
.
├── src/
│   ├── schema.py          # Pydantic v2 BatterySpec model
│   ├── prompts.py         # Zero-shot and few-shot system prompts
│   ├── extractor.py       # PDF → JSON extraction via Claude API
│   ├── evaluate.py        # F1 / precision / recall vs gold dataset
│   ├── kg_builder.py      # JSON → RDF triples (rdflib)
│   └── query_kg.py        # SPARQL query demonstrations
├── ontology/
│   └── battery.ttl        # OWL 2 ontology (battery domain)
├── out/
│   ├── zero-shot/         # Extraction results (zero-shot)
│   ├── few-shot/          # Extraction results (few-shot)
│   └── kg/                # Generated knowledge graph
├── logos/                 # Logo assets for the report
├── report.tex             # LaTeX source of the project report
├── report.pdf             # Compiled report (pre-built, ready to read)
├── requirements.txt
└── .env                   # ← you create this (API key, not committed)
```

The four input datasheets (`*.pdf`) are at the repo root.

---

## Key results (Level 1)

| Strategy | Precision | Recall | F1 | Hallucination rate |
|----------|-----------|--------|----|-------------------|
| Zero-shot | 97.0% | 100.0% | **98.5%** | 3.0% |
| Few-shot | 93.8% | 98.4% | 96.1% | 6.2% |

---

## Report

The compiled PDF is `report.pdf`. To recompile from source:

```bash
pdflatex report.tex && pdflatex report.tex   # two passes for TOC/refs
```

Requires a LaTeX distribution with `mathpazo`, `titlesec`, `natbib`, `tikz`, `hyphenat`.
On macOS with TinyTeX: `tlmgr install mathpazo titlesec natbib hyphenat`.
