
"""Run the Irish wind-curtailment model for 2009–2012.

Uses a common scenario across all years:
    Installed wind capacity: 5061 MW
    SNSP limit:              60%
    Interconnector exports:  0 MW
    Demand multiplier:       1.0

Outputs:
    One hourly results CSV per year.
    One combined hourly results CSV.
    One annual and four-year summary CSV.
"""

from pathlib import Path

import pandas as pd

from wind_curtailment.curtailment import (
    CurtailmentConfig,
    CurtailmentModel,
)


# ---------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------

DATA_DIR = Path.home() / "Projects" / "Wind_curtailment_data"

INPUT_DIR = DATA_DIR / "curtailment_inputs"
OUTPUT_DIR = DATA_DIR / "curtailment_results"

YEARS = (2009, 2010, 2011, 2012)

# Scenario assumptions.
INSTALLED_CAPACITY_MW = 5061.0
SNSP_LIMIT = 0.60
EXPORT_CAPACITY_MW = 0.0
DEMAND_MULTIPLIER = 1.0


# ---------------------------------------------------------------------
# Run one year
# ---------------------------------------------------------------------

def run_year(year, model):
    """Run the curtailment model for one year."""

    print(f"\nRunning curtailment model for {year}...")

    # Locate and check the prepared annual input file.
    input_file = INPUT_DIR / f"curtailment_inputs_{year}.csv"

    if not input_file.exists():
        raise FileNotFoundError(f"Input file not found: {input_file}")

    # Load the prepared demand and wind data.
    data = pd.read_csv(input_file)

    # Parse the original demand timestamp labels.
    # These are retained for consistency with the preparation stage.
    timestamps = pd.to_datetime(data["timestamp"], errors="raise")

    # Apply the demand multiplier to the demand series.
    demand_mw = (
        pd.to_numeric(data["demand_mw"], errors="raise")
        * DEMAND_MULTIPLIER
    )

    # Recalculate available wind power from capacity factor.
    # This ensures installed capacity is controlled by this scenario.
    wind_capacity_factor = pd.to_numeric(
        data["wind_capacity_factor"],
        errors="raise",
    )

    wind_mw = wind_capacity_factor * INSTALLED_CAPACITY_MW

    # Run the hourly curtailment model.
    hourly_results = model.run(
        timestamps=timestamps,
        demand_mw=demand_mw,
        wind_mw=wind_mw,
    )

    # Add the year explicitly to make combined results easy to inspect.
    hourly_results.insert(0, "year", year)

    # Save the detailed hourly results for this year.
    output_file = OUTPUT_DIR / f"curtailment_results_{year}.csv"
    hourly_results.to_csv(output_file, index=False)

    # Calculate a summary for this year.
    summary = model.summarise(hourly_results)

    # Keep the annual row, rather than any overall row.
    summary = summary.loc[summary["year"].astype(str) != "ALL"].copy()

    # Report the main annual results.
    row = summary.iloc[0]

    print(f"  Hours modelled:              {int(row['hours'])}")
    print(f"  Available wind energy:       {row['available_wind_energy_mwh']:,.0f} MWh")
    print(f"  Curtailed wind energy:       {row['curtailed_energy_mwh']:,.0f} MWh")
    print(f"  Delivered wind energy:       {row['delivered_wind_energy_mwh']:,.0f} MWh")
    print(f"  Curtailment:                 {row['curtailment_percentage']:.2f}%")
    print(f"  Hours with curtailment:      {int(row['hours_with_curtailment'])}")
    print(f"  Output:                      {output_file}")

    return hourly_results, summary


# ---------------------------------------------------------------------
# Run all four years
# ---------------------------------------------------------------------

def main():
    """Run all years and produce combined results."""

    # Create the output directory if necessary.
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Construct one common model configuration for every year.
    config = CurtailmentConfig(
        snsp_limit=SNSP_LIMIT,
        export_capacity_mw=EXPORT_CAPACITY_MW,
    )

    model = CurtailmentModel(config)

    all_hourly_results = []
    all_annual_summaries = []

    # Process each year using the same model configuration.
    for year in YEARS:
        hourly, summary = run_year(year, model)

        all_hourly_results.append(hourly)
        all_annual_summaries.append(summary)

    # Combine the hourly results across all four years.
    combined_hourly = pd.concat(
        all_hourly_results,
        ignore_index=True,
    )

    # Save the combined hourly results.
    combined_hourly_file = OUTPUT_DIR / "curtailment_results_2009_2012.csv"
    combined_hourly.to_csv(combined_hourly_file, index=False)

    # Combine the annual summary rows.
    annual_summary = pd.concat(
        all_annual_summaries,
        ignore_index=True,
    )

    # Calculate a four-year summary from the combined hourly results.
    # This computes total curtailed energy divided by total available
    # wind energy, rather than averaging the annual percentages.
    overall_summary = model.summarise(combined_hourly)

    overall_row = overall_summary.loc[
        overall_summary["year"].astype(str) == "ALL"
    ].copy()

    # Append the four-year total to the annual summary table.
    final_summary = pd.concat(
        [annual_summary, overall_row],
        ignore_index=True,
    )

    # Save the annual and four-year summary.
    summary_file = OUTPUT_DIR / "curtailment_summary_2009_2012.csv"
    final_summary.to_csv(summary_file, index=False)

    # Display the main results.
    display_columns = [
        "year",
        "hours",
        "available_wind_energy_mwh",
        "curtailed_energy_mwh",
        "delivered_wind_energy_mwh",
        "curtailment_percentage",
        "hours_with_curtailment",
    ]

    print("\nCURTAILMENT RESULTS: 2009–2012")
    print(
        final_summary[display_columns].to_string(
            index=False,
            formatters={
                "available_wind_energy_mwh": "{:,.0f}".format,
                "curtailed_energy_mwh": "{:,.0f}".format,
                "delivered_wind_energy_mwh": "{:,.0f}".format,
                "curtailment_percentage": "{:.2f}%".format,
            },
        )
    )

    print("\nSCENARIO")
    print(f"  Installed capacity: {INSTALLED_CAPACITY_MW:.0f} MW")
    print(f"  SNSP limit:          {SNSP_LIMIT:.0%}")
    print(f"  Exports:             {EXPORT_CAPACITY_MW:.0f} MW")
    print(f"  Demand multiplier:   {DEMAND_MULTIPLIER:.2f}")

    print(f"\nCombined hourly output: {combined_hourly_file}")
    print(f"Summary output:         {summary_file}")


if __name__ == "__main__":
    main()
