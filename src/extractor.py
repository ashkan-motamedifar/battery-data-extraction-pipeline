"""Level 1 battery datasheet extractor.

Feeds each PDF to Claude as a native `document` block and asks the
model to emit a JSON object that matches our `BatterySpec` Pydantic
schema. The returned text is then validated client-side with Pydantic
(`BatterySpec.model_validate_json`), which gives us the same type
guarantees as `messages.parse(output_format=...)` without running into
that endpoint's schema-complexity ceiling.

Writes one JSON per PDF plus a combined `extractions.json`.

Run from the project root:

    .venv/bin/python -m src.extractor \\
        --input-dir . \\
        --output-dir out

Uses the official Anthropic Python SDK, defaults to `claude-opus-4-6`
with adaptive thinking, and retries once on JSON / validation errors
with the error fed back into the prompt as self-correction context.
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
import time
from pathlib import Path
from typing import Iterable

from anthropic import Anthropic, APIError
from dotenv import load_dotenv
from pydantic import ValidationError

from src.schema import BatterySpec

# Load ANTHROPIC_API_KEY (and any other env vars) from a local .env file
# at the project root, so the user doesn't have to `source` anything.
# `.env` is gitignored — never commit it.
load_dotenv()


DEFAULT_MODEL = "claude-opus-4-6"

# Datasheets present in the reference corpus. `project.pdf` is included
# deliberately as a negative control — it's the assignment brief, not a
# datasheet, and the extractor should return an almost-empty BatterySpec
# (source_file set, everything else None) rather than hallucinate values.
DEFAULT_PDFS = [
    "lir2450_EEMB.pdf",
    "16340-battery-datasheet.pdf",
    "3.7V9059156.pdf",
    "CATL-86Ah-3.2V-LiFePO4-Prismatic-Battery-Cell-SpecificationDatasheet.pdf",
    "project.pdf",
]


SYSTEM_PROMPT = """You are a meticulous battery-datasheet information \
extractor. You are given a single PDF and must return a structured \
`BatterySpec` record describing it.

Rules:

1. EXTRACT ONLY EXPLICIT VALUES. If a field is not clearly stated in the \
PDF, leave it null. Never guess, interpolate, or compute values the \
datasheet does not give.

2. NORMALIZE UNITS to the canonical unit encoded in each field name:
   - `nominal_voltage_v` → volts
   - `capacity.nominal_mah` / `capacity.minimum_mah` → milliamp-hours \
(convert Ah → mAh by ×1000)
   - all `*_celsius` fields → degrees Celsius
   - `max_continuous_discharge_current_a` → amperes (convert mA → A by \
÷1000; if given as a C-rate multiplied by the rated capacity, compute \
the absolute amps and put the original C-rate in `capacity.c_rate_condition`)
   - `internal_resistance_mohm` → milliohms (convert Ω → mΩ by ×1000)
   - `weight_g` → grams

3. PRESERVE RAW STRINGS. On `TemperatureRange` and `Capacity`, fill the \
`raw` field with the exact substring you based the values on (e.g. \
"-20~60°C", "500 mAh (min. 470 mAh) at 0.2C, 25°C"). This is used later \
to detect hallucinations.

4. OPERATING TEMPERATURE is the discharge / general-use temperature \
range. If the datasheet lists separate charge and discharge temperature \
ranges, put the discharge range in `operating_temperature` and the \
charge range in `charge_temperature`. If only one operating range is \
given, put it in `operating_temperature` and leave `charge_temperature` \
null.

5. NON-DATASHEET PDFs. If the document is not actually a battery \
datasheet (e.g. a project brief, a review article, a marketing flyer), \
fill only `source_file` and leave every technical field null. Do not \
invent specs to fill the schema.

6. PREFER null OVER HALLUCINATION. Missing information is always \
acceptable; fabricated information is not.

OUTPUT FORMAT. Respond with a SINGLE JSON object matching the BatterySpec \
schema provided in the user message. No prose, no markdown fences, no \
commentary before or after — just the raw JSON object, starting with `{` \
and ending with `}`."""


# Pydantic emits a schema with $defs + $ref and a lot of `anyOf:
# [..., null]` branches from Optional fields. Claude handles that fine
# in an instruction prompt, and it keeps the source of truth (the
# Pydantic model) in one place.
BATTERY_SPEC_SCHEMA_JSON = json.dumps(
    BatterySpec.model_json_schema(),
    indent=2,
)


def encode_pdf_block(pdf_path: Path) -> dict:
    """Return an Anthropic `document` content block for a local PDF."""
    data = base64.standard_b64encode(pdf_path.read_bytes()).decode("ascii")
    return {
        "type": "document",
        "source": {
            "type": "base64",
            "media_type": "application/pdf",
            "data": data,
        },
    }


def _extract_json_object(text: str) -> str:
    """Pull the first JSON object out of a Claude response.

    The prompt tells Claude to emit raw JSON, but we defensively handle
    the case where it wraps the output in a ```json … ``` fence or
    prefixes a short sentence.
    """
    s = text.strip()
    if s.startswith("```"):
        # Strip the opening fence (``` or ```json) and the closing ```
        s = s.split("\n", 1)[1] if "\n" in s else s[3:]
        if s.endswith("```"):
            s = s[: -3]
        s = s.strip()
    # If there's still leading prose, find the first `{` and last `}`.
    start = s.find("{")
    end = s.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError(f"no JSON object found in response: {text[:200]!r}")
    return s[start : end + 1]


def _call_claude(
    client: Anthropic,
    pdf_path: Path,
    model: str,
    user_text: str,
) -> str:
    """One round-trip to Claude. Returns the text of the first text block."""
    message = client.messages.create(
        model=model,
        max_tokens=4096,
        thinking={"type": "adaptive"},
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": [
                    encode_pdf_block(pdf_path),
                    {"type": "text", "text": user_text},
                ],
            }
        ],
    )
    # With adaptive thinking the response can contain ThinkingBlocks
    # before the final TextBlock — grab the last text block.
    text_blocks = [b for b in message.content if getattr(b, "type", None) == "text"]
    if not text_blocks:
        raise RuntimeError(
            f"Claude returned no text blocks for {pdf_path.name}; "
            f"stop_reason={message.stop_reason}"
        )
    return text_blocks[-1].text


def extract_one(
    client: Anthropic,
    pdf_path: Path,
    model: str,
) -> BatterySpec:
    """Run structured extraction on a single PDF and return the BatterySpec.

    Strategy: ask Claude for a JSON object that matches the BatterySpec
    schema, parse it, validate with Pydantic. On JSON-parse or
    validation failure, retry once with the error fed back into the
    prompt — that's usually enough for Claude to self-correct.
    """
    base_instruction = (
        f"Extract a BatterySpec for the PDF above and return it as a "
        f"JSON object. Set `source_file` to exactly: {pdf_path.name}\n\n"
        f"The JSON must validate against this schema:\n\n"
        f"{BATTERY_SPEC_SCHEMA_JSON}"
    )

    last_error: Exception | None = None
    for attempt in range(2):
        if attempt == 0:
            user_text = base_instruction
        else:
            user_text = (
                f"{base_instruction}\n\n"
                f"Your previous response failed validation with this error:\n"
                f"{last_error}\n\n"
                f"Return a corrected JSON object that fixes this issue."
            )

        raw = _call_claude(client, pdf_path, model, user_text)
        try:
            json_text = _extract_json_object(raw)
            spec = BatterySpec.model_validate_json(json_text)
        except (ValueError, ValidationError) as exc:
            last_error = exc
            continue

        # Force source_file to the filename we actually processed.
        return spec.model_copy(update={"source_file": pdf_path.name})

    raise RuntimeError(
        f"Claude failed to produce a valid BatterySpec for {pdf_path.name} "
        f"after 2 attempts. Last error: {last_error}"
    )


def run(
    input_dir: Path,
    output_dir: Path,
    pdfs: Iterable[str],
    model: str,
) -> int:
    client = Anthropic()
    output_dir.mkdir(parents=True, exist_ok=True)

    combined: list[dict] = []
    failures: list[tuple[str, str]] = []

    for name in pdfs:
        pdf_path = input_dir / name
        if not pdf_path.is_file():
            failures.append((name, "file not found"))
            print(f"[skip] {name}: not found", file=sys.stderr)
            continue

        print(f"[extract] {name} ... ", end="", flush=True)
        t0 = time.time()
        try:
            spec = extract_one(client, pdf_path, model)
        except (APIError, ValidationError, RuntimeError) as exc:
            failures.append((name, f"{type(exc).__name__}: {exc}"))
            print(f"FAILED ({type(exc).__name__})", file=sys.stderr)
            continue

        dt = time.time() - t0
        out_path = output_dir / f"{pdf_path.stem}.json"
        out_path.write_text(spec.model_dump_json(indent=2))
        combined.append(spec.model_dump(mode="json"))
        print(f"ok ({dt:.1f}s) → {out_path}")

    combined_path = output_dir / "extractions.json"
    combined_path.write_text(json.dumps(combined, indent=2))
    print(f"\nWrote {len(combined)} record(s) to {combined_path}")

    if failures:
        print("\nFailures:", file=sys.stderr)
        for name, reason in failures:
            print(f"  - {name}: {reason}", file=sys.stderr)
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path("."),
        help="Directory containing the PDFs (default: current dir).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("out"),
        help="Where to write per-PDF JSON and combined extractions.json.",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Claude model ID (default: {DEFAULT_MODEL}).",
    )
    parser.add_argument(
        "--pdfs",
        nargs="*",
        default=DEFAULT_PDFS,
        help="PDF filenames (relative to --input-dir) to process.",
    )
    args = parser.parse_args()
    return run(args.input_dir, args.output_dir, args.pdfs, args.model)


if __name__ == "__main__":
    raise SystemExit(main())
