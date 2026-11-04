from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import rasterio


@dataclass
class WindData:
    """Stores wind components and the spatial and temporal raster metadata."""

    u10: np.ndarray
    v10: np.ndarray
    timestamps: tuple
    transform: object
    crs: object
    height: int
    width: int
    source_file: Path


class CFSRDataLoader:
    """Loads CFSR wind data from GeoTIFF files."""

    def __init__(self, config):
        # Store the model configuration.
        self.config = config

    def load_month(self, year, month):
        """Load one month of CFSR 10 m wind-component data."""

        # Find the GeoTIFF matching the requested year and month.
        cfsr_dir = self.config.data_dir / "CFSR"
        pattern = f"cfsr_10m_{year}{month:02d}_*.tif"
        files = list(cfsr_dir.glob(pattern))

        # Require exactly one matching file.
        if len(files) != 1:
            raise FileNotFoundError(
                f"Expected one file matching {pattern}, found {len(files)}"
            )

        file_path = files[0]

        # Open the GeoTIFF and read its contents.
        with rasterio.open(file_path) as src:
            raw_data = src.read().astype(np.float32)

            # Replace any declared NoData values with NaN before scaling.
            if src.nodata is not None:
                raw_data[raw_data == src.nodata] = np.nan

            # Convert stored values into physical wind-component values.
            scales = np.asarray(src.scales, dtype=np.float32)[:, None, None]
            offsets = np.asarray(src.offsets, dtype=np.float32)[:, None, None]
            data = raw_data * scales + offsets

            # Check that the bands can be divided equally between u and v.
            if src.count % 2 != 0:
                raise ValueError("Expected an even number of raster bands.")

            n_times = src.count // 2

            # Read the band descriptions, which contain component and time.
            descriptions = src.descriptions

            if any(description is None for description in descriptions):
                raise ValueError("Some raster bands have no descriptions.")

            # Separate the u and v band descriptions.
            u_descriptions = descriptions[:n_times]
            v_descriptions = descriptions[n_times:]

            # Check that the descriptions identify the expected components.
            if not all(d.startswith("u ") for d in u_descriptions):
                raise ValueError("Expected the first group of bands to contain u.")

            if not all(d.startswith("v ") for d in v_descriptions):
                raise ValueError("Expected the second group of bands to contain v.")

            # Extract timestamps from the descriptions.
            u_times = [
                datetime.fromisoformat(d[2:]).replace(tzinfo=timezone.utc)
                for d in u_descriptions
            ]

            v_times = [
                datetime.fromisoformat(d[2:]).replace(tzinfo=timezone.utc)
                for d in v_descriptions
            ]

            # Ensure the u and v components refer to the same hours.
            if u_times != v_times:
                raise ValueError("The u and v component timestamps do not match.")

            # Split the physical data into the two wind components.
            u10 = data[:n_times]
            v10 = data[n_times:]

            # Preserve the raster's spatial metadata.
            transform = src.transform
            crs = src.crs
            height = src.height
            width = src.width

        # Return the data and metadata together.
        return WindData(
            u10=u10,
            v10=v10,
            timestamps=tuple(u_times),
            transform=transform,
            crs=crs,
            height=height,
            width=width,
            source_file=file_path,
        )
