
"""Run a wind-curtailment scenario from aligned hourly input data."""

import argparse
from pathlib import Path

import pandas as pd

from wind_curtailment.curtailment import (
    CurtailmentConfig,
    CurtailmentModel,
)


def parse_arguments():
    """Define command-line options for the scenario."""

    parser = argparse.ArgumentParser(
        description="Run the hourly wind-curtailment model."
    )

    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="CSV containing aligned hourly demand and wind capacity factor.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path.home() / "Projects" / "Wind_curtailment_data"
        / "curtailment_results",
    )
    parser.add_argument(
        "--wind-capacity-mw",
        type=float,
        default=5061.0,
    )
    parser.add_argument(
        "--snsp-limit",
        type=float,
        default=0.60,
    )
    parser.add_argument(
        "--export-mw",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--demand-growth-factor",
        type=float,
        default=1.0,
        help="Demand multiplier. Use 1.17 for the paper's 2020 projection "
             "once the demand MW reference has been verified.",
    )
    parser.add_argument(
        "--night-start",
        type=int,
        default=23,
    )
    parser.add_argument(
        "--night-end",
        type=int,
        default=7,
    )

    return parser.parse_args()


def main():
    """Load inputs, run curtailment and save hourly and annual outputs."""

    args = parse_arguments()

    # Load the prepared hourly input series.
    data = pd.read_csv(args.input)

    required_columns = {
        "timestamp",
        "demand_mw",
        "wind_capacity_factor",
    }

    missing_columns = required_columns.difference(data.columns)
    if missing_columns:
        raise ValueError(
            f"Input CSV is missing columns: {sorted(missing_columns)}"
        )

    # Parse timestamps and convert wind capacity factor to available wind MW.
    timestamps = pd.to_datetime(data["timestamp"])
    demand_mw = (
        data["demand_mw"].to_numpy(dtype=float)
        * args.demand_growth_factor
    )
    wind_capacity_factor = data["wind_capacity_factor"].to_numpy(
        dtype=float
    )

    if (
        (wind_capacity_factor < 0).any()
        or (wind_capacity_factor > 1).any()
    ):
        raise ValueError(
            "Wind capacity factors must lie between zero and one."
        )

    wind_mw = wind_capacity_factor * args.wind_capacity_mw

    # Configure the curtailment scenario.
    config = CurtailmentConfig(
        snsp_limit=args.snsp_limit,
        export_capacity_mw=args.export_mw,
        night_start_hour=args.night_start,
        night_end_hour=args.night_end,
    )

    # Run the two curtailment rules.
    model = CurtailmentModel(config)
    hourly_results = model.run(
        timestamps=timestamps,
        demand_mw=demand_mw,
        wind_mw=wind_mw,
    )

    # Calculate annual and overall energy statistics.
    summary = model.summarise(hourly_results)

    # Save the detailed hourly results and summary.
    args.output_dir.mkdir(parents=True, exist_ok=True)

    hourly_path = args.output_dir / "curtailment_hourly.csv"
    summary_path = args.output_dir / "curtailment_summary.csv"

    hourly_results.to_csv(hourly_path, index=False)
    summary.to_csv(summary_path, index=False)

    # Print a concise report for the completed scenario.
    print("\nCURTAILMENT SCENARIO")
    print(f"Wind capacity:       {args.wind_capacity_mw:.1f} MW")
    print(f"SNSP limit:          {args.snsp_limit:.0%}")
    print(f"Export availability: {args.export_mw:.1f} MW")
    print(f"Demand multiplier:   {args.demand_growth_factor:.3f}")

    print("\nCURTAILMENT SUMMARY")
    print(summary.to_string(index=False))

    print("\nOUTPUT FILES")
    print(hourly_path)
    print(summary_path)


if __name__ == "__main__":
    main()
