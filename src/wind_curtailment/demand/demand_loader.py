"""Load the hourly demand profiles supplied with the ESBM workbook.

The workbook stores demand as a normalised profile, not as MW.  Conversion to
MW is deliberately explicit: callers must provide a peak-demand assumption.
The source's calendar labels are retained as naive wall-clock timestamps; no
UTC or daylight-saving correction is silently applied.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd


DEFAULT_WORKBOOK = (
    Path.home() / "Projects" / "Wind_curtailment_data" / "ESBM v1.4.xlsx"
)
SUPPORTED_YEARS = (2009, 2010, 2011, 2012)
SOURCE_COLUMNS = (
    "Year",
    "Month",
    "Day",
    "Hour",
    "Wind national capacity factor",
    "Normalised demand (1 equals the peak demand for the year)",
)
COLUMN_MAP = {
    "Year": "year",
    "Month": "month",
    "Day": "day",
    "Hour": "hour",
    "Wind national capacity factor": "wind_capacity_factor",
    "Normalised demand (1 equals the peak demand for the year)": "normalised_demand",
}


@dataclass(frozen=True)
class DemandData:
    """One year's ESBM demand and wind-profile data.

    ``frame`` contains the original calendar fields, a naive ``timestamp_local``
    label, the normalised demand and the workbook's wind capacity factor.
    Duplicate wall-clock labels are retained and explicitly flagged.
    """

    year: int
    frame: pd.DataFrame
    source_file: Path

    @property
    def timestamps(self) -> pd.DatetimeIndex:
        """Return source wall-clock labels (naive; not UTC)."""
        return pd.DatetimeIndex(self.frame["timestamp_local"], name="timestamp_local")

    @property
    def normalised_demand(self) -> pd.Series:
        """Return the dimensionless demand profile."""
        return self.frame["normalised_demand"].copy()

    @property
    def wind_capacity_factor(self) -> pd.Series:
        """Return the wind capacity-factor series supplied in the workbook."""
        return self.frame["wind_capacity_factor"].copy()

    def demand_mw(self, peak_demand_mw: float) -> pd.Series:
        """Scale normalised demand using an explicitly supplied peak in MW.

        The workbook's default model input is 7630.74 MW, but that is a model
        setting rather than a separate measured peak for each data year.
        """
        if peak_demand_mw <= 0:
            raise ValueError("peak_demand_mw must be positive")
        return self.frame["normalised_demand"] * float(peak_demand_mw)

    def validation_report(self) -> dict[str, int | float | str]:
        """Summarise row counts, missing values and repeated clock labels."""
        return {
            "year": self.year,
            "rows": len(self.frame),
            "missing_normalised_demand": int(self.frame["normalised_demand"].isna().sum()),
            "missing_wind_capacity_factor": int(self.frame["wind_capacity_factor"].isna().sum()),
            "duplicate_wall_clock_labels": int(self.frame["timestamp_local"].duplicated(keep=False).sum()),
            "first_timestamp_label": str(self.frame["timestamp_local"].iloc[0]),
            "last_timestamp_label": str(self.frame["timestamp_local"].iloc[-1]),
        }


class ESBMDemandLoader:
    """Read the 2009–2012 hourly profiles from ``ESBM v1.4.xlsx``."""

    def __init__(self, workbook_path: str | Path = DEFAULT_WORKBOOK) -> None:
        self.workbook_path = Path(workbook_path).expanduser()
        if not self.workbook_path.is_file():
            raise FileNotFoundError(
                f"ESBM workbook not found: {self.workbook_path}\n"
                "Pass the workbook path explicitly if it is stored elsewhere."
            )

    def load_year(self, year: int) -> DemandData:
        """Load one year's data without altering source time labels."""
        if year not in SUPPORTED_YEARS:
            raise ValueError(f"year must be one of {SUPPORTED_YEARS}; got {year}")

        sheet_name = f"{year} data"
        # Row 1 is an instruction; row 2 contains the actual column headings.
        raw = pd.read_excel(
            self.workbook_path,
            sheet_name=sheet_name,
            header=1,
            usecols="A:F",
            engine="openpyxl",
        )
        raw = raw.dropna(how="all").copy()

        if tuple(raw.columns) != SOURCE_COLUMNS:
            raise ValueError(
                f"Unexpected columns in sheet {sheet_name!r}: {list(raw.columns)!r}"
            )

        # Rename columns to stable Python identifiers and enforce numeric types.
        frame = raw.rename(columns=COLUMN_MAP).copy()
        numeric_columns = list(COLUMN_MAP.values())
        for column in numeric_columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")

        # Calendar fields must be present and valid; demand itself may contain
        # a source blank (the 2010 sheet has one), which is preserved as NaN.
        calendar_columns = ["year", "month", "day", "hour"]
        if frame[calendar_columns].isna().any().any():
            raise ValueError(f"Missing calendar fields in sheet {sheet_name!r}")
        if not (frame["year"] == year).all():
            raise ValueError(f"Sheet {sheet_name!r} contains an unexpected year")
        if not frame["hour"].between(0, 23).all():
            raise ValueError(f"Invalid hour values in sheet {sheet_name!r}")

        # Convert the source's local calendar labels to naive timestamps. This
        # intentionally permits duplicates at the autumn clock change.
        frame["timestamp_local"] = pd.to_datetime(
            {
                "year": frame["year"].astype(int),
                "month": frame["month"].astype(int),
                "day": frame["day"].astype(int),
                "hour": frame["hour"].astype(int),
            },
            errors="raise",
        )

        # Keep a record index so duplicated wall-clock hours remain distinguishable.
        frame.insert(0, "record_index", range(len(frame)))
        frame["duplicate_wall_clock_label"] = frame["timestamp_local"].duplicated(keep=False)

        # Check physical ranges without filling or clipping source values.
        wind = frame["wind_capacity_factor"].dropna()
        demand = frame["normalised_demand"].dropna()
        if not wind.between(0.0, 1.0).all():
            raise ValueError(f"Wind capacity factors outside [0, 1] in {sheet_name!r}")
        if not demand.between(0.0, 1.0).all():
            raise ValueError(f"Normalised demand outside [0, 1] in {sheet_name!r}")

        return DemandData(
            year=year,
            frame=frame.reset_index(drop=True),
            source_file=self.workbook_path,
        )

    def load_all(self, years: Iterable[int] = SUPPORTED_YEARS) -> pd.DataFrame:
        """Load selected years into one table, preserving each sheet's row order."""
        frames = [self.load_year(year).frame for year in years]
        if not frames:
            raise ValueError("At least one year must be requested")
        return pd.concat(frames, ignore_index=True)
