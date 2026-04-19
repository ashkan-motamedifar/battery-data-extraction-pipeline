"""Pydantic schema for Level 1 battery datasheet extraction.

One BatterySpec record per source datasheet. All numeric fields are stored
in canonical units encoded in the field name (e.g. `nominal_voltage_v`,
`internal_resistance_mohm`), so the JSON output is self-describing and the
unit can never drift from the value.
"""

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


Chemistry = Literal["Li-ion", "Li-polymer", "LiFePO4", "NiMH", "NiCd", "Other"]
FormFactor = Literal["cylindrical", "prismatic", "pouch", "coin", "other"]


class TemperatureRange(BaseModel):
    """A temperature interval normalized to Celsius.

    Reused for operating / charge / storage temperature. `raw` preserves
    the original string (e.g. "-20~60°C") for Level 3 provenance checks.
    """

    model_config = ConfigDict(extra="forbid")

    min_celsius: float
    max_celsius: float
    raw: Optional[str] = Field(
        default=None,
        description="Original unparsed string from the datasheet.",
    )


class Capacity(BaseModel):
    """Battery capacity normalized to mAh, with its rating conditions.

    Capacity is meaningless without the conditions it was measured under,
    so C-rate and test temperature are first-class optional fields.
    """

    model_config = ConfigDict(extra="forbid")

    nominal_mah: float = Field(..., description="Nominal / typical capacity in mAh.")
    minimum_mah: Optional[float] = Field(
        default=None,
        description="Minimum guaranteed capacity in mAh, if stated.",
    )
    c_rate_condition: Optional[str] = Field(
        default=None,
        description='Discharge C-rate used for the rating, e.g. "0.2C".',
    )
    test_temperature_celsius: Optional[float] = Field(
        default=None,
        description="Temperature at which capacity was measured.",
    )
    raw: Optional[str] = Field(
        default=None,
        description='Original phrase, e.g. "500 mAh (min. 470 mAh) at 0.2C, 25°C".',
    )


class BatterySpec(BaseModel):
    """Level 1 extraction target: one record per datasheet.

    All fields are Optional except `source_file` because no single datasheet
    in the reference corpus contains every field, and the schema must not
    reject partial extractions — the evaluation harness scores coverage.
    """

    model_config = ConfigDict(extra="forbid")

    # --- Identification --------------------------------------------------
    source_file: str = Field(..., description="Path of the source PDF.")
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    chemistry: Optional[Chemistry] = None
    form_factor: Optional[FormFactor] = None

    # --- Required by the task --------------------------------------------
    nominal_voltage_v: Optional[float] = Field(
        default=None,
        description="Nominal voltage in Volts.",
    )
    nominal_voltage_v_raw: Optional[str] = Field(
        default=None,
        description="Original phrase from the datasheet supporting nominal_voltage_v.",
    )
    capacity: Optional[Capacity] = None
    operating_temperature: Optional[TemperatureRange] = Field(
        default=None,
        description="Discharge / general operating temperature range.",
    )

    # --- Useful extras for Level 2 / Level 3 -----------------------------
    charge_temperature: Optional[TemperatureRange] = None
    storage_temperature: Optional[TemperatureRange] = None

    charge_cutoff_voltage_v: Optional[float] = None
    charge_cutoff_voltage_v_raw: Optional[str] = Field(
        default=None,
        description="Original phrase supporting charge_cutoff_voltage_v.",
    )

    discharge_cutoff_voltage_v: Optional[float] = None
    discharge_cutoff_voltage_v_raw: Optional[str] = Field(
        default=None,
        description="Original phrase supporting discharge_cutoff_voltage_v.",
    )

    max_continuous_discharge_current_a: Optional[float] = None
    max_continuous_discharge_current_a_raw: Optional[str] = Field(
        default=None,
        description="Original phrase supporting max_continuous_discharge_current_a "
                    "(may quote a C-rate that was converted to A).",
    )

    internal_resistance_mohm: Optional[float] = None
    internal_resistance_mohm_raw: Optional[str] = Field(
        default=None,
        description="Original phrase supporting internal_resistance_mohm.",
    )

    cycle_life: Optional[int] = Field(
        default=None,
        description="Number of cycles to end-of-life (condition in raw).",
    )
    cycle_life_raw: Optional[str] = Field(
        default=None,
        description="Original phrase supporting cycle_life.",
    )

    weight_g: Optional[float] = None
    weight_g_raw: Optional[str] = Field(
        default=None,
        description="Original phrase supporting weight_g (may quote kg that was converted to g).",
    )
