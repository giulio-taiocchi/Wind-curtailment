"""Build hourly regional and national wind capacity factors for 2009-2012."""

import argparse

import pandas as pd

from wind_curtailment.config import ModelConfig
from wind_curtailment.model import WindCurtailmentModel


def build_year(year, spatial_method="area", model=None, config=None):
    """Run all 12 months and save one annual capacity-factor time series."""

    # Reuse the supplied model/config, or create them if called independently.
    config = config if config is not None else ModelConfig()
    model = model if model is not None else WindCurtailmentModel(config)

    monthly_results = []

    for month in range(1, 13):
        print(f"\nProcessing {year}-{month:02d}...")

        # Run the complete meteorological, turbine and spatial workflow.
        result = model.run_month(
            year=year,
            month=month,
            spatial_method=spatial_method,
        )

        # Combine the four regional series and the national series.
        monthly = result.regional_capacity_factors.copy()
        monthly["National"] = result.national_capacity_factor

        # Make timestamps an explicit column for CSV storage.
        monthly.index.name = "timestamp"
        monthly = monthly.reset_index()

        monthly_results.append(monthly)

    # Combine the 12 monthly tables into one chronological annual series.
    annual = pd.concat(monthly_results, ignore_index=True)

    # Ensure timestamps are consistently represented as UTC.
    annual["timestamp"] = pd.to_datetime(
        annual["timestamp"],
        utc=True,
    )

    annual = annual.sort_values("timestamp").reset_index(drop=True)

    # Check for duplicate timestamps at monthly boundaries.
    if annual["timestamp"].duplicated().any():
        duplicates = annual.loc[
            annual["timestamp"].duplicated(keep=False),
            "timestamp",
        ]

        raise ValueError(
            f"Duplicate wind timestamps found for {year}:\n"
            f"{duplicates.to_string(index=False)}"
        )

    # Check the expected number of hourly observations.
    expected_hours = (
        8784 if pd.Timestamp(year, 12, 31).is_leap_year else 8760
    )

    if len(annual) != expected_hours:
        raise ValueError(
            f"Expected {expected_hours} hourly observations for {year}, "
            f"but found {len(annual)}."
        )

    # Check the complete timestamp sequence, not just its length.
    expected_timestamps = pd.date_range(
        start=f"{year}-01-01 01:00:00",
        periods=expected_hours,
        freq="h",
        tz="UTC",
    )

    if not pd.DatetimeIndex(annual["timestamp"]).equals(
        expected_timestamps
    ):
        raise ValueError(
            f"The timestamps for {year} are not a continuous UTC hourly "
            "sequence beginning at 01:00 on 1 January."
        )

    # Save the annual time series independently of the current session.
    output_dir = config.data_dir / "wind_processed"
    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / f"wind_capacity_factor_{year}.csv"
    annual.to_csv(output_file, index=False)

    print("\nANNUAL WIND SERIES")
    print(f"Year:             {year}")
    print(f"Hourly records:   {len(annual)}")
    print(f"First timestamp:  {annual['timestamp'].iloc[0]}")
    print(f"Last timestamp:   {annual['timestamp'].iloc[-1]}")
    print(f"Mean national CF: {annual['National'].mean():.4f}")
    print(f"Output:           {output_file}")

    return annual


def build_all_years(
    years=(2009, 2010, 2011, 2012),
    spatial_method="area",
):
    """Build all requested years and save a combined annual summary."""

    # Initialise one model and reuse it for all four years.
    config = ModelConfig()
    model = WindCurtailmentModel(config)

    summaries = []

    for year in years:
        annual = build_year(
            year=year,
            spatial_method=spatial_method,
            model=model,
            config=config,
        )

        # Since each row represents one hour, summing CF gives equivalent
        # full-load hours. Multiplication by installed MW gives MWh.
        summaries.append(
            {
                "year": year,
                "hours": len(annual),
                "mean_national_capacity_factor": annual["National"].mean(),
                "wind_energy_mwh_at_5061_mw": (
                    annual["National"].sum() * 5061.0
                ),
            }
        )

    # Save a compact summary for comparison across the four years.
    summary = pd.DataFrame(summaries)

    output_dir = config.data_dir / "wind_processed"
    output_dir.mkdir(parents=True, exist_ok=True)

    summary_file = output_dir / "wind_four_year_summary.csv"
    summary.to_csv(summary_file, index=False)

    print("\nFOUR-YEAR WIND SUMMARY")
    print(summary.to_string(index=False))
    print(f"\nSummary output: {summary_file}")

    return summary


if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description="Build annual wind capacity factors for 2009-2012."
    )

    parser.add_argument(
        "--years",
        nargs="+",
        type=int,
        default=[2009, 2010, 2011, 2012],
        help="Years to process (default: 2009 2010 2011 2012).",
    )

    parser.add_argument(
        "--spatial-method",
        choices=["area", "equal"],
        default="area",
        help="Spatial weighting method (default: area).",
    )

    args = parser.parse_args()

    build_all_years(
        years=tuple(args.years),
        spatial_method=args.spatial_method,
    )
