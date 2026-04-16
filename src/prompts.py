"""Prompting strategies for Level 1 battery datasheet extraction.

ZERO_SHOT_PROMPT: no examples, just instructions.
FEW_SHOT_PROMPT:  one worked example (LIR2450) added before the extraction request.
                  The example is chosen to demonstrate three tricky cases:
                    1. "120±10 mAh" → nominal_mah=120, minimum_mah=null  (tolerance ≠ minimum)
                    2. "﹣20℃—60℃"   → min_celsius=-20, max_celsius=60   (non-ASCII dash)
                    3. charge_temperature: null                           (not stated separately)
"""

_BASE_RULES = """\
You are a meticulous battery-datasheet information extractor.

Rules:
1. Extract ONLY values explicitly stated in the document. Do NOT infer, calculate, or guess.
2. Normalize units: capacity → mAh (convert Ah × 1000), voltage → V, temperature → °C, \
resistance → mΩ, current → A.
3. For every composite field (capacity, temperature ranges) copy the exact original phrase \
into the `raw` sub-field.
4. `operating_temperature` is the general discharge / operating range. \
If a separate charge temperature range is stated, put it in `charge_temperature`.
5. If this document is NOT a battery datasheet (e.g. a project brief, report, or instructions), \
return all technical fields as null.
6. Prefer null over a hallucinated value. When in doubt, use null.
7. For capacity, use the row explicitly labelled "Nominal Capacity". \
Do NOT use "Typical Capacity" or a value from the product title unless no \
"Nominal Capacity" row exists.
8. A tolerance like "120±10 mAh" means nominal=120, NOT minimum=110. \
Only set minimum_mah if the document has an explicit "minimum" or "min." label.

OUTPUT FORMAT. Respond with a SINGLE JSON object — no markdown fences, \
no extra commentary — starting with { and ending with }.\
"""

ZERO_SHOT_PROMPT = _BASE_RULES

# ---------------------------------------------------------------------------
# Few-shot example: LIR2450 coin cell (EEMB)
# ---------------------------------------------------------------------------
_FEW_SHOT_EXAMPLE = '''
--- EXAMPLE (do not extract — use only as a format and reasoning guide) ---

Document: lir2450_EEMB.pdf
Key text snippets from the datasheet:
  • "Nominal Voltage: 3.6V"
  • "Nominal Capacity: 120±10mAh  (0.2C discharge at 20°C)"
  • "Standard Charge: 0.1C CC/CV to 4.2V"
  • "Cut-off Voltage: 2.75V"
  • "Internal Impedance: ≤400mΩ"
  • "Operating Temperature: ﹣20℃—60℃"
  • "Cycle Life: ≥300 cycles"
  • "Weight: Approx. 5g"
  • No separate charge-temperature range listed.
  • No maximum continuous discharge current listed.

Correct extraction:
{
  "source_file": "lir2450_EEMB.pdf",
  "manufacturer": "EEMB Co., Ltd.",
  "model": "LIR2450",
  "chemistry": "Li-ion",
  "form_factor": "coin",
  "nominal_voltage_v": 3.6,
  "capacity": {
    "nominal_mah": 120.0,
    "minimum_mah": null,
    "c_rate_condition": "0.2C",
    "test_temperature_celsius": 20.0,
    "raw": "Nominal Capacity: 120±10mAh  (0.2C discharge at 20°C)"
  },
  "operating_temperature": {
    "min_celsius": -20.0,
    "max_celsius": 60.0,
    "raw": "﹣20℃—60℃"
  },
  "charge_temperature": null,
  "storage_temperature": null,
  "charge_cutoff_voltage_v": 4.2,
  "discharge_cutoff_voltage_v": 2.75,
  "max_continuous_discharge_current_a": null,
  "internal_resistance_mohm": 400.0,
  "cycle_life": 300,
  "weight_g": 5.0
}

Reasoning notes:
- "120±10 mAh" is a tolerance band, NOT an explicit minimum guarantee → minimum_mah = null.
- Only one temperature range is listed → charge_temperature = null.
- No max continuous discharge current is stated → null (do not infer from C-rate).
--- END EXAMPLE ---
'''

FEW_SHOT_PROMPT = _BASE_RULES + "\n" + _FEW_SHOT_EXAMPLE
