"""Integration tests for the spatial and aggregation components.

Run from the project root with:

python scripts/test_spatial_aggregation.py --regions /path/to/regions.gpkg

The GeoPackage must contain four dissolved regional polygons, with a
'model_region' column containing North, East, South and West.
"""

import argparse

import geopandas as gpd
import numpy as np

from wind_curtailment.config import ModelConfig
from wind_curtailment.data_loader import CFSRDataLoader
from wind_curtailment.meteorology import WindResource
from wind_curtailment.turbine import Turbine
from wind_curtailment.spatial import SpatialModel
from wind_curtailment.aggregation import WindAggregator


# These are the county-derived installed-capacity shares established
# for the four model regions.
REGIONAL_CAPACITY_SHARES = {
    "North": 0.495934,
    "East": 0.071739,
    "South": 0.294936,
    "West": 0.137391,
}

REGION_ORDER = ("North", "East", "South", "West")


def load_regions(regions_path, layer=None):
    """Load the regional boundaries from a saved GIS file."""

    regions = gpd.read_file(regions_path, layer=layer)

    # Check that the expected region identifier is available.
    if "model_region" not in regions.columns:
        raise ValueError(
            "The regional boundary file must contain a 'model_region' column."
        )

    # Each region should already be represented by one dissolved geometry.
    if regions["model_region"].duplicated().any():
        raise ValueError(
            "Expected one dissolved geometry per region; found duplicate names."
        )

    if regions.crs is None:
        raise ValueError("The regional boundary file has no defined CRS.")

    # Check that all four expected regions are present.
    actual_regions = set(regions["model_region"])
    expected_regions = set(REGION_ORDER)

    if actual_regions != expected_regions:
        raise ValueError(
            f"Expected regions {expected_regions}, found {actual_regions}."
        )

    return regions


def test_spatial_and_aggregation(regions):
    """Run the spatial, regional and national integration tests."""

    # ---------------------------------------------------------------
    # 1. Load January 2009 meteorological data.
    # ---------------------------------------------------------------

    config = ModelConfig()
    loader = CFSRDataLoader(config)
    wind_data = loader.load_month(year=2009, month=1)

    print(f"\nLoaded meteorological data: {wind_data.source_file}")

    assert wind_data.u10.shape == wind_data.v10.shape
    assert wind_data.u10.ndim == 3
    assert wind_data.u10.shape[0] == len(wind_data.timestamps)

    # ---------------------------------------------------------------
    # 2. Calculate wind speed and turbine capacity factor.
    # ---------------------------------------------------------------

    wind_resource = WindResource(config)

    wind_speed_10m = wind_resource.calculate_wind_speed(
        wind_data.u10,
        wind_data.v10,
    )

    wind_speed_80m = wind_resource.extrapolate_to_hub_height(
        wind_speed_10m,
    )

    turbine = Turbine()

    power_kw, capacity_factor = turbine.calculate(wind_speed_80m)

    assert capacity_factor.shape == wind_data.u10.shape
    assert np.all(np.isfinite(capacity_factor))
    assert np.all((capacity_factor >= 0.0) & (capacity_factor <= 1.0))

    print("\nMeteorological and turbine calculations passed.")

    # ---------------------------------------------------------------
    # 3. Build the meteorological grid.
    # ---------------------------------------------------------------

    spatial = SpatialModel()

    grid = spatial.build_grid(
        transform=wind_data.transform,
        height=wind_data.height,
        width=wind_data.width,
        crs=wind_data.crs,
    )

    # There should be one polygon for every raster cell.
    expected_cell_count = wind_data.height * wind_data.width

    assert len(grid) == expected_cell_count
    assert grid["cell_id"].is_unique
    assert grid.crs.to_string() == "EPSG:3035"

    print("\nSpatial grid:")
    print(f"  Number of cells: {len(grid)}")
    print(f"  CRS: {grid.crs}")

    # ---------------------------------------------------------------
    # 4. Intersect the grid with the four model regions.
    # ---------------------------------------------------------------

    intersections = spatial.intersect_regions(grid, regions)

    assert not intersections.empty
    assert set(intersections["model_region"]) == set(REGION_ORDER)
    assert np.all(intersections["intersection_area_m2"] > 0.0)

    print("\nGrid-region intersections:")
    print(f"  Number of intersections: {len(intersections)}")

    # ---------------------------------------------------------------
    # 5. Check how much of each region is covered by the grid.
    # ---------------------------------------------------------------

    coverage = spatial.calculate_coverage(intersections, regions)

    assert np.all(np.isfinite(coverage["coverage_fraction"]))
    assert np.all(coverage["coverage_fraction"] > 0.0)

    # Small numerical tolerance allows for floating-point geometry effects.
    assert np.all(coverage["coverage_fraction"] <= 1.001)

    print("\nRegional raster coverage:")
    print(coverage[["region_area_m2", "covered_area_m2", "coverage_fraction"]])

    # ---------------------------------------------------------------
    # 6. Calculate regional capacity factors using both methods.
    # ---------------------------------------------------------------

    aggregator = WindAggregator(region_order=REGION_ORDER)

    # Area weighting gives partially covered boundary cells proportional
    # influence according to their intersection area.
    regional_cf_area = aggregator.calculate_regional_capacity_factors(
        capacity_factors=capacity_factor,
        timestamps=wind_data.timestamps,
        intersections=intersections,
        method="area",
    )

    # Equal-cell weighting assigns each raster cell to the region with
    # which it has the largest overlap, then gives each assigned cell
    # equal weight.
    regional_cf_equal = aggregator.calculate_regional_capacity_factors(
        capacity_factors=capacity_factor,
        timestamps=wind_data.timestamps,
        intersections=intersections,
        method="equal_cell",
    )

    for regional_cf in (regional_cf_area, regional_cf_equal):
        assert list(regional_cf.columns) == list(REGION_ORDER)
        assert len(regional_cf) == len(wind_data.timestamps)
        assert np.all(np.isfinite(regional_cf.to_numpy()))
        assert np.all(
            (regional_cf.to_numpy() >= 0.0)
            & (regional_cf.to_numpy() <= 1.0)
        )

    print("\nRegional capacity-factor calculations passed.")

    # ---------------------------------------------------------------
    # 7. Calculate national capacity factors.
    # ---------------------------------------------------------------

    national_cf_area = aggregator.calculate_national_capacity_factor(
        regional_capacity_factors=regional_cf_area,
        regional_capacity_shares=REGIONAL_CAPACITY_SHARES,
    )

    national_cf_equal = aggregator.calculate_national_capacity_factor(
        regional_capacity_factors=regional_cf_equal,
        regional_capacity_shares=REGIONAL_CAPACITY_SHARES,
    )

    # Check that the national series is exactly the capacity-weighted
    # combination of the regional series.
    expected_national = sum(
        regional_cf_area[region] * REGIONAL_CAPACITY_SHARES[region]
        for region in REGION_ORDER
    )

    assert np.allclose(national_cf_area, expected_national)
    assert np.all((national_cf_area >= 0.0) & (national_cf_area <= 1.0))
    assert np.all((national_cf_equal >= 0.0) & (national_cf_equal <= 1.0))

    print("\nNational capacity-factor calculations passed.")

    # ---------------------------------------------------------------
    # 8. Print a compact summary for inspection.
    # ---------------------------------------------------------------

    print("\nMean regional capacity factors — area weighting:")
    print(regional_cf_area.mean())

    print("\nMean regional capacity factors — equal-cell weighting:")
    print(regional_cf_equal.mean())

    print("\nMean national capacity factor:")
    print(f"  Area weighting:      {national_cf_area.mean():.4f}")
    print(f"  Equal-cell weighting: {national_cf_equal.mean():.4f}")

    print("\nAll spatial and aggregation tests passed.")


def main():
    """Parse the regional boundary file argument and run the tests."""

    parser = argparse.ArgumentParser(
        description="Test spatial and aggregation components of the wind model."
    )

    parser.add_argument(
        "--regions",
        required=True,
        help="Path to the GeoPackage or other supported regional boundary file.",
    )

    parser.add_argument(
        "--layer",
        default=None,
        help="Optional layer name if the GIS file contains multiple layers.",
    )

    args = parser.parse_args()

    regions = load_regions(args.regions, layer=args.layer)
    test_spatial_and_aggregation(regions)


if __name__ == "__main__":
    main()
