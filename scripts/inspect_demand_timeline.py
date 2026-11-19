#!/usr/bin/env python3
"""
Inspect missing and duplicated hourly labels in the processed ESBM demand data.

This is a diagnostic only: it does not alter timestamps, assign a timezone,
fill missing values, or remove duplicate rows.
"""

from pathlib import Path

import pandas as pd


# Use the default output location created by process_demand.py.
DATA_DIR = Path.home() / "Projects" / "Wind_curtailment_data" / "demand_processed"
INPUT_FILE = DATA_DIR / "demand_2009_2012.csv"
OUTPUT_FILE = DATA_DIR / "demand_timeline_anomalies.csv"

# Columns needed to interpret each source row and inspect nearby values.
DISPLAY_COLUMNS = [
    "year",
    "row_in_sheet",
    "month",
    "day",
    "hour",
    "wall_clock_label",
    "demand_normalised",
    "demand_mw",
    "wind_cf_esbm",
]


def inspect_year(frame: pd.DataFrame, year: int) -> list[dict]:
    """Print and record duplicate labels and missing labels for one year."""

    annual = frame.loc[frame["year"] == year].copy()
    annual["wall_clock_label"] = pd.to_datetime(annual["wall_clock_label"])

    print(f"\n{'=' * 72}")
    print(f"YEAR {year}")
    print(f"{'=' * 72}")

    # Find every row participating in a duplicated wall-clock label.
    duplicate_mask = annual["wall_clock_label"].duplicated(keep=False)
    duplicates = annual.loc[duplicate_mask].sort_values(
        ["wall_clock_label", "row_in_sheet"]
    )

    if duplicates.empty:
        print("\nNo duplicated wall-clock labels.")
    else:
        print("\nDUPLICATED LABELS AND THEIR SOURCE ROWS")
        print(duplicates[DISPLAY_COLUMNS].to_string(index=False))

    # Build the complete hourly sequence between the first and last labels.
    # Any absent labels are reported, but not inserted into the data.
    unique_labels = pd.DatetimeIndex(
        annual["wall_clock_label"].drop_duplicates().sort_values()
    )
    expected = pd.date_range(
        unique_labels.min(), unique_labels.max(), freq="h"
    )
    missing_labels = expected.difference(unique_labels)

    if len(missing_labels) == 0:
        print("\nNo missing labels between first and last timestamps.")
    else:
        print("\nMISSING LABELS BETWEEN FIRST AND LAST OBSERVATIONS")
        for missing in missing_labels:
            print(f"  {missing}")

            # Show the source rows immediately before and after the gap.
            before = annual.loc[
                annual["wall_clock_label"] < missing
            ].tail(2)
            after = annual.loc[
                annual["wall_clock_label"] > missing
            ].head(2)
            neighbours = pd.concat([before, after]).sort_values("row_in_sheet")
            print(neighbours[DISPLAY_COLUMNS].to_string(index=False))

    # Report the first and last rows explicitly, particularly relevant to
    # 2009, whose first recorded hour is 01:00.
    print("\nFIRST THREE SOURCE ROWS")
    print(annual.head(3)[DISPLAY_COLUMNS].to_string(index=False))
    print("\nLAST THREE SOURCE ROWS")
    print(annual.tail(3)[DISPLAY_COLUMNS].to_string(index=False))

    # Record anomalies in a machine-readable table for later reproducibility.
    records = []

    for _, row in duplicates.iterrows():
        records.append(
            {
                "year": year,
                "anomaly": "duplicate",
                "wall_clock_label": row["wall_clock_label"],
                "row_in_sheet": row["row_in_sheet"],
                "month": row["month"],
                "day": row["day"],
                "hour": row["hour"],
                "demand_mw": row["demand_mw"],
                "wind_cf_esbm": row["wind_cf_esbm"],
            }
        )

    for missing in missing_labels:
        records.append(
            {
                "year": year,
                "anomaly": "missing",
                "wall_clock_label": missing,
                "row_in_sheet": pd.NA,
                "month": missing.month,
                "day": missing.day,
                "hour": missing.hour,
                "demand_mw": pd.NA,
                "wind_cf_esbm": pd.NA,
            }
        )

    return records


def main() -> None:
    """Inspect all annual series and save a compact anomaly report."""

    if not INPUT_FILE.is_file():
        raise FileNotFoundError(
            f"Processed demand file not found: {INPUT_FILE}\n"
            "Run scripts/process_demand.py first."
        )

    # Read the processed data without changing source row order.
    demand = pd.read_csv(INPUT_FILE)
    demand["wall_clock_label"] = pd.to_datetime(demand["wall_clock_label"])

    anomaly_records = []

    for year in (2009, 2010, 2011, 2012):
        anomaly_records.extend(inspect_year(demand, year))

    # Save all anomaly records so the results can be checked and reused.
    anomalies = pd.DataFrame(anomaly_records)
    anomalies.to_csv(OUTPUT_FILE, index=False)

    print(f"\nSaved anomaly report: {OUTPUT_FILE}")
    print(
        "\nNo timestamps were changed. No rows were removed, added, "
        "interpolated, or timezone-converted."
    )


if __name__ == "__main__":
    main()
