#!/usr/bin/env python3
"""
Process the hourly demand and wind data in the ESBM v1.4 workbook.

The script deliberately preserves the workbook's original row order and
Year/Month/Day/Hour labels. It does NOT assign a timezone or resolve the
daylight-saving-time (DST) duplicate/missing hours. Those decisions should
be made separately, once the workbook's timestamp convention is established.

Outputs:
    demand_<year>.csv
    demand_2009_2012.csv
    demand_diagnostics.csv
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


# The ESBM workbook stores the data on row 2, so pandas must skip row 1.
YEARS = (2009, 2010, 2011, 2012)

# Exact source column headings in ESBM v1.4.xlsx.
SOURCE_COLUMNS = {
    "Year": "year",
    "Month": "month",
    "Day": "day",
    "Hour": "hour",
    "Wind national capacity factor": "wind_cf_esbm",
    "Normalised demand (1 equals the peak demand for the year)": "demand_normalised",
}


def load_year(workbook: Path, year: int, peak_demand_mw: float) -> tuple[pd.DataFrame, dict]:
    """Load one annual sheet, preserve its labels, and calculate demand in MW."""

    sheet_name = f"{year} data"

    # Read the annual data table; the first row is explanatory text and row 2
    # contains the actual column headers.
    raw = pd.read_excel(workbook, sheet_name=sheet_name, header=1, engine="openpyxl")

    # Keep only the six expected columns and fail clearly if the workbook
    # layout has changed.
    missing_columns = [name for name in SOURCE_COLUMNS if name not in raw.columns]
    if missing_columns:
        raise ValueError(
            f"Sheet '{sheet_name}' is missing expected columns: {missing_columns}"
        )
    data = raw[list(SOURCE_COLUMNS)].rename(columns=SOURCE_COLUMNS).copy()

    # Retain the row's position in the original worksheet. This is important
    # because repeated DST labels cannot safely be distinguished by timestamp.
    data.insert(0, "row_in_sheet", np.arange(len(data), dtype=int))

    # Convert the calendar fields to numeric values without changing their
    # original meaning. The source labels remain in the output CSV.
    for column in ("year", "month", "day", "hour"):
        data[column] = pd.to_numeric(data[column], errors="raise").astype("int64")

    # Check that every row belongs to the sheet named for its year.
    if not data["year"].eq(year).all():
        raise ValueError(f"Sheet '{sheet_name}' contains rows for another year.")

    # Construct a naive wall-clock label for diagnostics and convenient
    # inspection. It is intentionally NOT localised to a timezone or UTC.
    calendar_date = pd.to_datetime(
        data[["year", "month", "day"]].rename(
            columns={"year": "year", "month": "month", "day": "day"}
        ),
        errors="raise",
    )
    data.insert(
        5,
        "wall_clock_label",
        calendar_date + pd.to_timedelta(data["hour"], unit="h"),
    )

    # Convert the normalised demand into MW using an explicit, configurable
    # peak-demand reference. Missing source values remain NaN.
    data["demand_mw"] = data["demand_normalised"] * peak_demand_mw

    # Basic data-quality checks: do not silently clip or fill source values.
    if not data["hour"].between(0, 23).all():
        raise ValueError(f"Sheet '{sheet_name}' contains an hour outside 0..23.")
    if not data["wind_cf_esbm"].dropna().between(0.0, 1.0).all():
        raise ValueError(f"Sheet '{sheet_name}' contains a wind CF outside 0..1.")
    if not data["demand_normalised"].dropna().between(0.0, 1.0).all():
        raise ValueError(f"Sheet '{sheet_name}' contains normalised demand outside 0..1.")

    # Count duplicate wall-clock labels, but retain every row. These are
    # expected to occur around the autumn clock change in this workbook.
    duplicate_mask = data["wall_clock_label"].duplicated(keep=False)

    # Count missing labels between the first and last observed labels. This is
    # diagnostic only; it does not infer whether a gap is a DST transition.
    observed_labels = pd.DatetimeIndex(data["wall_clock_label"].dropna().unique())
    if len(observed_labels):
        expected_labels = pd.date_range(
            observed_labels.min(), observed_labels.max(), freq="h"
        )
        missing_between = expected_labels.difference(observed_labels)
    else:
        missing_between = pd.DatetimeIndex([])

    # Summarise the annual sheet without imposing a UTC interpretation.
    expected_calendar_hours = 8784 if year == 2012 else 8760
    diagnostics = {
        "year": year,
        "rows": int(len(data)),
        "expected_calendar_hours": expected_calendar_hours,
        "row_count_difference": int(len(data) - expected_calendar_hours),
        "missing_normalised_demand": int(data["demand_normalised"].isna().sum()),
        "missing_demand_mw": int(data["demand_mw"].isna().sum()),
        "missing_wind_capacity_factor": int(data["wind_cf_esbm"].isna().sum()),
        "duplicate_wall_clock_rows": int(duplicate_mask.sum()),
        "duplicate_wall_clock_labels": int(
            data.loc[duplicate_mask, "wall_clock_label"].nunique()
        ),
        "missing_labels_between_first_last": int(len(missing_between)),
        "first_wall_clock_label": str(data["wall_clock_label"].min()),
        "last_wall_clock_label": str(data["wall_clock_label"].max()),
        "normalised_demand_min": float(data["demand_normalised"].min()),
        "normalised_demand_max": float(data["demand_normalised"].max()),
        "demand_mw_min": float(data["demand_mw"].min()),
        "demand_mw_max": float(data["demand_mw"].max()),
        "wind_cf_min": float(data["wind_cf_esbm"].min()),
        "wind_cf_max": float(data["wind_cf_esbm"].max()),
    }

    return data, diagnostics


def main() -> None:
    """Parse command-line options, process all years, and write CSV outputs."""

    default_data_dir = Path.home() / "Projects" / "Wind_curtailment_data"

    parser = argparse.ArgumentParser(
        description="Convert ESBM hourly normalised demand into MW and report time-label diagnostics."
    )
    parser.add_argument(
        "--workbook",
        type=Path,
        default=default_data_dir / "ESBM v1.4.xlsx",
        help="Path to the ESBM v1.4 Excel workbook.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=default_data_dir / "demand_processed",
        help="Directory in which processed CSV files will be written.",
    )
    parser.add_argument(
        "--peak-demand-mw",
        type=float,
        default=7630.74,
        help="Reference peak demand in MW used to scale normalised demand (default: 7630.74).",
    )
    args = parser.parse_args()

    # Validate paths and the demand scaling parameter before processing.
    if not args.workbook.is_file():
        raise FileNotFoundError(f"Workbook not found: {args.workbook}")
    if not np.isfinite(args.peak_demand_mw) or args.peak_demand_mw <= 0:
        raise ValueError("--peak-demand-mw must be a positive finite number.")

    args.output_dir.mkdir(parents=True, exist_ok=True)

    annual_frames = []
    annual_diagnostics = []

    # Process each annual worksheet independently so that anomalies remain
    # visible rather than being hidden by concatenation or resampling.
    for year in YEARS:
        frame, diagnostics = load_year(args.workbook, year, args.peak_demand_mw)
        annual_frames.append(frame)
        annual_diagnostics.append(diagnostics)

        output_file = args.output_dir / f"demand_{year}.csv"
        frame.to_csv(output_file, index=False)
        print(f"Wrote {output_file} ({len(frame):,} rows)")

    # Concatenate in source-year and source-row order. Do not sort or
    # de-duplicate the wall-clock labels.
    combined = pd.concat(annual_frames, ignore_index=True)
    combined_file = args.output_dir / "demand_2009_2012.csv"
    combined.to_csv(combined_file, index=False)
    print(f"Wrote {combined_file} ({len(combined):,} rows)")

    # Write a compact diagnostic table for quick review and reproducibility.
    diagnostics_frame = pd.DataFrame(annual_diagnostics)
    diagnostics_file = args.output_dir / "demand_diagnostics.csv"
    diagnostics_frame.to_csv(diagnostics_file, index=False)
    print(f"Wrote {diagnostics_file}")

    # Also save the scaling assumption and processing choices alongside the
    # data, so downstream analysis can recover exactly how demand was formed.
    metadata = {
        "source_workbook": str(args.workbook.resolve()),
        "peak_demand_mw": args.peak_demand_mw,
        "timezone_assigned": None,
        "dst_resolved": False,
        "row_order_preserved": True,
        "missing_values_filled": False,
        "years": list(YEARS),
    }
    metadata_file = args.output_dir / "demand_processing_metadata.json"
    metadata_file.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {metadata_file}")

    # Print the key diagnostics in the terminal.
    print("\nDEMAND DATA DIAGNOSTICS")
    print(
        diagnostics_frame[
            [
                "year",
                "rows",
                "missing_normalised_demand",
                "duplicate_wall_clock_rows",
                "missing_labels_between_first_last",
                "first_wall_clock_label",
                "last_wall_clock_label",
            ]
        ].to_string(index=False)
    )
    print(f"\nPeak-demand reference: {args.peak_demand_mw:,.2f} MW")
    print("DST handling: not applied; original labels and row order preserved.")


if __name__ == "__main__":
    main()
