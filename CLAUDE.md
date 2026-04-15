# CLAUDE.md

Guidance for Claude Code when working in this directory.

## Project

**LLM-Based Battery Datasheet Information Extraction and Validation** — an academic project (Master 1, S2, Complex Data / Industrial Data course). Goal: build a pipeline that extracts structured battery specifications (nominal voltage, capacity, discharge rate, operating temperature, internal resistance, etc.) from unstructured PDF datasheets using LLMs, and validates the output against a knowledge graph / ontology to detect hallucinations.

Full brief: [project.pdf](project.pdf).

## Objectives (three levels)

- **Level 1 — Extraction (minimum required).** Use LLMs to extract specs from the datasheet PDFs into structured JSON. Compare prompting strategies (zero-shot, few-shot). Include a basic evaluation of extraction quality.
- **Level 2 — Knowledge Graph.** Design a battery ontology (Battery, Specification, Unit, …), convert extractions into triples, populate a queryable KG.
- **Level 3 — Hallucination Detection.** Use ontology constraints / graph rules to flag inconsistent, out-of-range, or unsupported values.

Deliverables: code + PDF report via Moodle. Evaluation weighs extraction quality, hallucination detection, KG correctness, report, and task distribution.

## Source PDFs (input datasheets)

Four heterogeneous battery datasheets live at the repo root — these are the working corpus for extraction:

- [16340-battery-datasheet.pdf](16340-battery-datasheet.pdf)
- [3.7V9059156.pdf](3.7V9059156.pdf)
- [CATL-86Ah-3.2V-LiFePO4-Prismatic-Battery-Cell-SpecificationDatasheet.pdf](CATL-86Ah-3.2V-LiFePO4-Prismatic-Battery-Cell-SpecificationDatasheet.pdf)
- [lir2450_EEMB.pdf](lir2450_EEMB.pdf)

They cover different chemistries (Li-ion, LiFePO4) and form factors (cylindrical, prismatic, coin) — extraction code must handle heterogeneous layouts and tables, not a single template.

## Current state

The directory currently contains **only the project brief and the four datasheet PDFs**. No source code, no `requirements.txt`, no notebooks yet. Any implementation work starts from scratch.

## Working notes for Claude

- Language: Python is recommended by the brief.
- Expected output format for Level 1: JSON.
- When adding code, keep the datasheet PDFs at the root (or move them under `data/`) and put code under a clear structure (e.g. `src/`, `notebooks/`, `outputs/`). Confirm layout with the user before restructuring.
- Not a git repo — no `git` commands will work here unless the user initializes one.
- The working directory path contains spaces (`projet 2026-20260415`) — quote paths in shell commands.
- Before claiming an extraction works, actually run it against all four PDFs; they are deliberately heterogeneous and a pipeline that only works on one is not Level 1 complete.
- For hallucination detection (Level 3), the key idea from the brief is that ontology constraints (value ranges, required units, type checks) catch values the LLM invented or that don't match the source — design the ontology with validation in mind, not just storage.
