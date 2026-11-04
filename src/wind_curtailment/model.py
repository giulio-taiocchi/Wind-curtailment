
"""Coordinate the complete wind-generation modelling workflow."""

from dataclasses import dataclass

import geopandas as gpd
import numpy as np

from wind_curtailment.config import ModelConfig
from wind_curtailment.data_loader import CFSRDataLoader
from wind_curtailment.meteorology import WindResource
from wind_curtailment.turbine import Turbine
from wind_curtailment.spatial import SpatialModel
from wind_curtailment.aggregation import WindAggregator


@dataclass
class ModelRunResult:
    """Collect the outputs produced by one monthly model run."""

    wind_data: object
    wind_speed_10m: np.ndarray
    wind_speed_80m: np.ndarray
    power_kw: np.ndarray
    capacity_factor: np.ndarray
    grid: gpd.GeoDataFrame
    intersections: gpd.GeoDataFrame
    regional_coverage: object
    regional_capacity_factors: object
    national_capacity_factor: object


class WindCurtailmentModel:
    """Run the wind-generation model for a specified month."""

    def __init__(self, config=None, turbine=None):
        # Use the default configuration unless the caller supplies one.
        self.config = config if config is not None else ModelConfig()

        # Construct the individual model components.
        self.data_loader = CFSRDataLoader(self.config)
        self.wind_resource = WindResource(self.config)
        self.turbine = turbine if turbine is not None else Turbine()

        self.spatial = SpatialModel(
            equal_area_crs=self.config.equal_area_crs
        )

        self.aggregator = WindAggregator(
            region_order=self.config.region_order
        )

    def load_regions(self):
        """Load the previously prepared four-region GeoPackage."""

        if not self.config.regions_file.exists():
            raise FileNotFoundError(
                f"Regional boundary file not found: "
                f"{self.config.regions_file}. "
                "Run the spatial-data preparation module first."
            )

        # Read the saved regional polygons, rather than relying on notebook
        # variables or reconstructing boundaries during every model run.
        regions = gpd.read_file(
            self.config.regions_file,
            layer="model_regions",
        )

        # Check that the saved file contains the expected regions.
        actual_regions = set(regions["model_region"])
        expected_regions = set(self.config.region_order)

        if actual_regions != expected_regions:
            raise ValueError(
                f"Expected regions {expected_regions}, "
                f"found {actual_regions}."
            )

        return regions

    def run_month(self, year, month, spatial_method="area"):
        """Run the complete model for one calendar month."""

        # Check that the requested month and year are valid.
        if not self.config.starting_year <= year <= self.config.end_year:
            raise ValueError(
                f"Year must be between {self.config.starting_year} "
                f"and {self.config.end_year}."
            )

        if not 1 <= month <= 12:
            raise ValueError("Month must be between 1 and 12.")

        # -----------------------------------------------------------
        # 1. Load the hourly meteorological wind components.
        # -----------------------------------------------------------

        wind_data = self.data_loader.load_month(year, month)

        # -----------------------------------------------------------
        # 2. Calculate wind speed at 10 m and extrapolate to 80 m.
        # -----------------------------------------------------------

        wind_speed_10m = self.wind_resource.calculate_wind_speed(
            wind_data.u10,
            wind_data.v10,
        )

        wind_speed_80m = self.wind_resource.extrapolate_to_hub_height(
            wind_speed_10m,
        )

        # -----------------------------------------------------------
        # 3. Calculate turbine power and capacity factor.
        # -----------------------------------------------------------

        power_kw, capacity_factor = self.turbine.calculate(
            wind_speed_80m
        )

        # The current aggregation implementation requires finite values.
        # Fail explicitly rather than silently treating missing data as zero.
        if not np.all(np.isfinite(capacity_factor)):
            raise ValueError(
                "Capacity-factor array contains missing or infinite values. "
                "Missing-data handling must be addressed before aggregation."
            )

        # -----------------------------------------------------------
        # 4. Load the saved regions and construct the meteorological grid.
        # -----------------------------------------------------------

        regions = self.load_regions()

        grid = self.spatial.build_grid(
            transform=wind_data.transform,
            height=wind_data.height,
            width=wind_data.width,
            crs=wind_data.crs,
        )

        # Intersect every meteorological cell with the regional boundaries.
        intersections = self.spatial.intersect_regions(
            grid,
            regions,
        )

        # -----------------------------------------------------------
        # 5. Check regional spatial coverage.
        # -----------------------------------------------------------

        regional_coverage = self.spatial.calculate_coverage(
            intersections,
            regions,
        )

        # -----------------------------------------------------------
        # 6. Aggregate grid-cell capacity factors into regional series.
        # -----------------------------------------------------------

        regional_capacity_factors = (
            self.aggregator.calculate_regional_capacity_factors(
                capacity_factors=capacity_factor,
                timestamps=wind_data.timestamps,
                intersections=intersections,
                method=spatial_method,
            )
        )

        # -----------------------------------------------------------
        # 7. Calculate the national capacity-factor time series.
        # -----------------------------------------------------------

        national_capacity_factor = (
            self.aggregator.calculate_national_capacity_factor(
                regional_capacity_factors=regional_capacity_factors,
                regional_capacity_shares=(
                    self.config.regional_capacity_shares
                ),
            )
        )

        # -----------------------------------------------------------
        # 8. Return all outputs in one structured result.
        # -----------------------------------------------------------

        return ModelRunResult(
            wind_data=wind_data,
            wind_speed_10m=wind_speed_10m,
            wind_speed_80m=wind_speed_80m,
            power_kw=power_kw,
            capacity_factor=capacity_factor,
            grid=grid,
            intersections=intersections,
            regional_coverage=regional_coverage,
            regional_capacity_factors=regional_capacity_factors,
            national_capacity_factor=national_capacity_factor,
        )

