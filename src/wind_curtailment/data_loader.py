"""Load hourly 10 m wind components from CFSR and CFSv2 GeoTIFFs."""

from calendar import monthrange
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import rasterio


@dataclass
class WindData:
    """Wind components together with raster and time metadata."""

    u10: np.ndarray
    v10: np.ndarray
    timestamps: tuple
    transform: object
    crs: object
    height: int
    width: int
    source_file: Path


class ReanalysisDataLoader:
    """Select the appropriate reanalysis archive and load one month.

    CFSR is used for 2009-2010.
    CFSv2 is used for 2011-2012.
    Both archives store all u-component bands followed by all v bands.
    """

    DATASETS = {
        "CFSR": {
            "first_year": 2009,
            "last_year": 2010,
            "directory": "CFSR",
            "prefix": "cfsr_10m",
        },
        "CFSv2": {
            "first_year": 2011,
            "last_year": 2012,
            "directory": "CFSv2",
            "prefix": "cfsv2_10m",
        },
    }

    def __init__(self, config):
        self.config = config

    def _dataset_for_year(self, year):
        """Return the dataset configuration for the requested year."""

        for dataset_name, details in self.DATASETS.items():
            if details["first_year"] <= year <= details["last_year"]:
                return dataset_name, details

        raise ValueError(
            f"No reanalysis dataset configured for {year}. "
            "Supported years are 2009-2012."
        )

    @staticmethod
    def _parse_timestamp(description):
        """Parse a band description and normalise its time to UTC."""

        # Band descriptions have the form 'u 2009-01-01 01:00:00'.
        timestamp = datetime.fromisoformat(description[2:])

        # The descriptions are normally timezone-naive UTC timestamps.
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        else:
            timestamp = timestamp.astimezone(timezone.utc)

        return timestamp

    def load_month(self, year, month):
        """Load one month of 10 m u/v wind-component data."""

        if not 1 <= month <= 12:
            raise ValueError("Month must be between 1 and 12.")

        # Select CFSR or CFSv2 based on the requested year.
        dataset_name, details = self._dataset_for_year(year)

        data_dir = self.config.data_dir / details["directory"]
        pattern = f'{details["prefix"]}_{year}{month:02d}_*.tif'
        files = list(data_dir.glob(pattern))

        # Require exactly one matching monthly file.
        if len(files) != 1:
            raise FileNotFoundError(
                f"Expected exactly one {dataset_name} file matching "
                f"{data_dir / pattern}; found {len(files)}."
            )

        file_path = files[0]

        with rasterio.open(file_path) as src:
            # Read all bands into memory as floating-point values.
            raw_data = src.read().astype(np.float32)

            # Replace declared NoData values before applying scale and offset.
            if src.nodata is not None:
                raw_data[raw_data == src.nodata] = np.nan

            # Convert stored integer values to physical wind-component values.
            scales = np.asarray(
                src.scales, dtype=np.float32
            )[:, None, None]

            offsets = np.asarray(
                src.offsets, dtype=np.float32
            )[:, None, None]

            data = raw_data * scales + offsets

            # The first half of the bands should be u; the second half v.
            if src.count % 2 != 0:
                raise ValueError(
                    f"{file_path} has an odd number of raster bands."
                )

            n_times = src.count // 2

            # Check the number of hourly observations for this calendar month.
            expected_hours = monthrange(year, month)[1] * 24

            if n_times != expected_hours:
                raise ValueError(
                    f"{file_path} contains {n_times} hourly observations; "
                    f"expected {expected_hours} for {year}-{month:02d}."
                )

            # Read and validate the band descriptions.
            descriptions = src.descriptions

            if any(description is None for description in descriptions):
                raise ValueError(
                    f"{file_path} contains bands without descriptions."
                )

            u_descriptions = descriptions[:n_times]
            v_descriptions = descriptions[n_times:]

            if not all(d.startswith("u ") for d in u_descriptions):
                raise ValueError(
                    "The first group of bands must contain u components."
                )

            if not all(d.startswith("v ") for d in v_descriptions):
                raise ValueError(
                    "The second group of bands must contain v components."
                )

            # Parse the timestamps for each component.
            u_times = tuple(
                self._parse_timestamp(d) for d in u_descriptions
            )

            v_times = tuple(
                self._parse_timestamp(d) for d in v_descriptions
            )

            # Ensure u and v refer to precisely the same hours.
            if u_times != v_times:
                raise ValueError(
                    "The u and v component timestamps do not match."
                )

            # Ensure the timestamps form a continuous hourly sequence.
            one_hour = timedelta(hours=1)

            if any(
                current - previous != one_hour
                for previous, current in zip(u_times[:-1], u_times[1:])
            ):
                raise ValueError(
                    f"{file_path} has a non-hourly or irregular time axis."
                )

            # Separate the u and v arrays.
            u10 = data[:n_times]
            v10 = data[n_times:]

            # Preserve the raster metadata needed by the spatial model.
            transform = src.transform
            crs = src.crs
            height = src.height
            width = src.width

        return WindData(
            u10=u10,
            v10=v10,
            timestamps=u_times,
            transform=transform,
            crs=crs,
            height=height,
            width=width,
            source_file=file_path,
        )


# Keep the old class name available for compatibility with existing scripts.
CFSRDataLoader = ReanalysisDataLoader
