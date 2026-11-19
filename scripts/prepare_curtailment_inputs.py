
"""Prepare aligned wind and demand inputs for the curtailment model.

Wind and demand are paired by row order, following the working approach
used for the 2009 preparation. Repeated demand timestamps are preserved.
Rows with missing or invalid demand/wind values are excluded.
"""

from pathlib import Path

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------
# Project paths and scenario settings
# ---------------------------------------------------------------------

DATA_DIR = Path.home() / "Projects" / "Wind_curtailment_data"

WIND_DIR = DATA_DIR / "wind_processed"
DEMAND_DIR = DATA_DIR / "demand_processed"
OUTPUT_DIR = DATA_DIR / "curtailment_inputs"

YEARS = (2009, 2010, 2011, 2012)

# Installed capacity is used here to convert capacity factor into MW.
# Keep this consistent with the curtailment scenario.
INSTALLED_CAPACITY_MW = 5061.0


# ---------------------------------------------------------------------
# Column detection
# ---------------------------------------------------------------------

def find_column(dataframe, candidates, description):
    """Find a column using a list of accepted column-name variants."""

    # Normalise names so that spaces and capitalisation do not matter.
    normalised = {
        str(column).strip().lower().replace(" ", "_"): column
        for column in dataframe.columns
    }

    # Return the first matching candidate.
    for candidate in candidates:
        key = candidate.strip().lower().replace(" ", "_")
        if key in normalised:
            return normalised[key]

    # Give a useful error if the expected column cannot be identified.
    raise ValueError(
        f"Could not identify the {description} column. "
        f"Available columns: {list(dataframe.columns)}"
    )


def find_wind_capacity_factor_column(dataframe):
    """Identify the national capacity-factor column in the wind file."""

    # Try common explicit names first.
    candidates = [
        "national_capacity_factor",
        "national_cf",
        "wind_capacity_factor",
        "national",
        "National CF",
    ]

    try:
        return find_column(dataframe, candidates, "national wind capacity factor")
    except ValueError:
        pass

    # If names differ, look for a column containing both 'national'
    # and either 'capacity' or 'cf'.
    for column in dataframe.columns:
        name = str(column).strip().lower()
        if "national" in name and ("capacity" in name or "cf" in name):
            return column

    raise ValueError(
        "Could not identify the national wind capacity-factor column. "
        f"Available columns: {list(dataframe.columns)}"
    )


# ---------------------------------------------------------------------
# Prepare one year
# ---------------------------------------------------------------------

def prepare_year(year):
    """Align wind and demand data and save the curtailment input file."""

    print(f"\nPreparing curtailment inputs for {year}...")

    # Construct the annual input filenames.
    wind_file = WIND_DIR / f"wind_capacity_factor_{year}.csv"
    demand_file = DEMAND_DIR / f"demand_{year}.csv"

    # Check that both required files exist before reading them.
    if not wind_file.exists():
        raise FileNotFoundError(f"Wind file not found: {wind_file}")

    if not demand_file.exists():
        raise FileNotFoundError(f"Demand file not found: {demand_file}")

    # Read the two annual datasets.
    wind = pd.read_csv(wind_file)
    demand = pd.read_csv(demand_file)

    # Identify the relevant columns without assuming exact capitalisation.
    wind_timestamp_col = find_column(
        wind,
        ["timestamp", "datetime", "date_time"],
        "wind timestamp",
    )

    wind_cf_col = find_wind_capacity_factor_column(wind)

    demand_timestamp_col = find_column(
    demand,
    [
        "timestamp",
        "datetime",
        "date_time",
        "local_timestamp",
        "wall_clock_label",
    ],
    "demand timestamp",
)

    demand_value_col = find_column(
        demand,
        [
            "demand_mw",
            "normalised_demand_mw",
            "normalized_demand_mw",
            "normalised_demand",
            "normalized_demand",
            "demand",
        ],
        "demand",
    )

    # Parse wind timestamps as UTC and demand timestamps as recorded.
    wind_timestamps = pd.to_datetime(
        wind[wind_timestamp_col],
        utc=True,
        errors="coerce",
    )

    demand_timestamps = pd.to_datetime(
        demand[demand_timestamp_col],
        errors="coerce",
    )

    # Convert the numerical input columns explicitly.
    wind_cf = pd.to_numeric(wind[wind_cf_col], errors="coerce")
    demand_mw = pd.to_numeric(demand[demand_value_col], errors="coerce")

    # Check that the annual series are sufficiently close in length.
    # A one-row difference is allowed, as in the previous 2009 workflow.
    wind_rows = len(wind)
    demand_rows = len(demand)

    if abs(wind_rows - demand_rows) > 1:
        raise ValueError(
            f"{year}: wind and demand lengths differ by more than one row "
            f"(wind={wind_rows}, demand={demand_rows}). "
            "Check the annual input files before aligning them."
        )

    # Trim both series to the shorter length, preserving their original order.
    number_of_rows = min(wind_rows, demand_rows)

    wind = wind.iloc[:number_of_rows].reset_index(drop=True)
    demand = demand.iloc[:number_of_rows].reset_index(drop=True)

    wind_timestamps = wind_timestamps.iloc[:number_of_rows].reset_index(drop=True)
    demand_timestamps = demand_timestamps.iloc[:number_of_rows].reset_index(drop=True)
    wind_cf = wind_cf.iloc[:number_of_rows].reset_index(drop=True)
    demand_mw = demand_mw.iloc[:number_of_rows].reset_index(drop=True)

    # Check the relationship between the first wind and demand timestamps.
    # The wind timestamps represent the end of each hourly interval.
    # For 2010–2012, demand labels represent the beginning of that interval.
    first_wind_timestamp = wind_timestamps.iloc[0].tz_localize(None)
    first_demand_timestamp = demand_timestamps.iloc[0]

    # Calculate the difference between the first timestamps.
    timestamp_offset = first_wind_timestamp - first_demand_timestamp

    # The supported conventions are:
    #   0 hours: demand and wind timestamps use the same label.
    #   1 hour: demand labels the interval start and wind labels its end.
    if timestamp_offset not in (pd.Timedelta(hours=0), pd.Timedelta(hours=1)):
        raise ValueError(
            f"{year}: unexpected timestamp relationship. "
            f"Wind: {first_wind_timestamp}; "
            f"demand: {first_demand_timestamp}; "
            f"offset: {timestamp_offset}. "
            "Inspect the timestamp conventions before proceeding."
        )

    print(f"  Wind-demand timestamp offset:    {timestamp_offset}")

    # Build the aligned dataset by row order.
    aligned = pd.DataFrame(
        {
            "timestamp": demand_timestamps,
            "wind_timestamp_utc": wind_timestamps,
            "demand_mw": demand_mw,
            "wind_capacity_factor": wind_cf,
        }
    )

    # Remove rows with missing values or invalid capacity factors.
    valid = (
        aligned["timestamp"].notna()
        & aligned["wind_timestamp_utc"].notna()
        & np.isfinite(aligned["demand_mw"])
        & np.isfinite(aligned["wind_capacity_factor"])
        & aligned["demand_mw"].ge(0)
        & aligned["wind_capacity_factor"].between(0, 1)
    )

    aligned = aligned.loc[valid].copy()

    # Convert capacity factor into available wind power in MW.
    aligned["wind_mw"] = (
        aligned["wind_capacity_factor"] * INSTALLED_CAPACITY_MW
    )

    # Create the output directory if it does not already exist.
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Save the aligned annual input dataset.
    output_file = OUTPUT_DIR / f"curtailment_inputs_{year}.csv"
    aligned.to_csv(output_file, index=False)

    # Count repeated local timestamp labels without removing them.
    repeated_timestamps = int(
        aligned["timestamp"].duplicated(keep=False).sum()
    )

    # Report the preparation results.
    print(f"  Wind rows before alignment:       {wind_rows}")
    print(f"  Demand rows before alignment:     {demand_rows}")
    print(f"  Rows after length alignment:     {number_of_rows}")
    print(f"  Valid aligned rows:               {len(aligned)}")
    print(f"  Rows excluded as invalid:         {number_of_rows - len(aligned)}")
    print(f"  Rows with repeated timestamp:     {repeated_timestamps}")
    print(f"  Mean wind capacity factor:        {aligned['wind_capacity_factor'].mean():.4f}")
    print(f"  Mean demand:                      {aligned['demand_mw'].mean():.2f} MW")
    print(f"  Output:                           {output_file}")

    # Return a compact summary for the four-year report.
    return {
        "year": year,
        "wind_rows": wind_rows,
        "demand_rows": demand_rows,
        "aligned_rows": len(aligned),
        "excluded_rows": number_of_rows - len(aligned),
        "repeated_timestamp_rows": repeated_timestamps,
        "mean_wind_capacity_factor": aligned["wind_capacity_factor"].mean(),
        "mean_demand_mw": aligned["demand_mw"].mean(),
        "output_file": str(output_file),
    }


# ---------------------------------------------------------------------
# Prepare all four years
# ---------------------------------------------------------------------

def main():
    """Prepare and summarise the four annual curtailment input datasets."""

    summaries = []

    # Process each year independently so that errors identify the year.
    for year in YEARS:
        summaries.append(prepare_year(year))

    # Combine the annual preparation summaries.
    summary = pd.DataFrame(summaries)

    # Save the summary alongside the annual input files.
    summary_file = OUTPUT_DIR / "curtailment_inputs_summary.csv"
    summary.to_csv(summary_file, index=False)

    print("\nFOUR-YEAR CURTAILMENT INPUT SUMMARY")
    print(
        summary[
            [
                "year",
                "wind_rows",
                "demand_rows",
                "aligned_rows",
                "excluded_rows",
                "mean_wind_capacity_factor",
                "mean_demand_mw",
            ]
        ].to_string(index=False)
    )

    print(f"\nSummary output: {summary_file}")


if __name__ == "__main__":
    main()

