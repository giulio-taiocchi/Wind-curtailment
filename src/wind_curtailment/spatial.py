import geopandas as gpd
import numpy as np
import pandas as pd

from shapely.geometry import Polygon


class SpatialModel:
    """Builds the meteorological grid and intersects it with model regions."""

    def __init__(self, equal_area_crs="EPSG:3035"):
        # Use an equal-area projection for calculating intersection areas.
        self.equal_area_crs = equal_area_crs

    def build_grid(self, transform, height, width, crs):
        """Create one polygon for every meteorological raster cell."""

        cells = []

        # Iterate over every raster row and column.
        for row in range(height):
            for col in range(width):

                # Convert the four pixel corners into coordinates in the raster CRS.
                x0, y0 = transform * (col, row)
                x1, y1 = transform * (col + 1, row)
                x2, y2 = transform * (col + 1, row + 1)
                x3, y3 = transform * (col, row + 1)

                # Construct a polygon representing this raster cell.
                geometry = Polygon([
                    (x0, y0),
                    (x1, y1),
                    (x2, y2),
                    (x3, y3),
                ])

                # Keep the original raster indices to retrieve its data later.
                cells.append({
                    "row": row,
                    "col": col,
                    "cell_id": row * width + col,
                    "geometry": geometry,
                })

        # Create a GeoDataFrame in the original raster coordinate system.
        grid = gpd.GeoDataFrame(
            cells,
            geometry="geometry",
            crs=crs,
        )

        # Reproject the grid to the equal-area CRS before measuring areas.
        return grid.to_crs(self.equal_area_crs)

    def intersect_regions(self, grid, regions_gdf):
        """Intersect grid cells with the supplied regional polygons."""

        # Check that the regional GeoDataFrame has the required region identifier.
        if "model_region" not in regions_gdf.columns:
            raise ValueError("regions_gdf must contain a 'model_region' column.")

        if regions_gdf.crs is None:
            raise ValueError("Regional boundaries must have a defined CRS.")

        # Reproject the regions to the same equal-area CRS as the grid.
        regions = regions_gdf[["model_region", "geometry"]].copy()
        regions = regions.to_crs(self.equal_area_crs)

        # Repair invalid geometries before performing the overlay.
        regions["geometry"] = regions.geometry.make_valid()

        # Intersect every grid cell with the regional boundaries.
        intersections = gpd.overlay(
            grid,
            regions,
            how="intersection",
            keep_geom_type=True,
        )

        # Calculate the area of each grid-cell/region intersection in square metres.
        intersections["intersection_area_m2"] = intersections.geometry.area

        # Remove any zero-area intersections.
        intersections = intersections.loc[
            intersections["intersection_area_m2"] > 0
        ].copy()

        return intersections

    def assign_cells_to_regions(self, intersections):
        """Assign each grid cell to the region with its largest overlap."""

        # For each cell, select the region with the largest intersection area.
        largest_overlaps = (
            intersections.sort_values("intersection_area_m2", ascending=False)
            .drop_duplicates(subset="cell_id")
            .copy()
        )

        return largest_overlaps[
            ["cell_id", "row", "col", "model_region", "intersection_area_m2"]
        ].reset_index(drop=True)

    def calculate_coverage(self, intersections, regions_gdf):
        """Calculate the fraction of each region covered by the raster grid."""

        # Measure the full area of each region in the equal-area projection.
        regions = regions_gdf[["model_region", "geometry"]].to_crs(
            self.equal_area_crs
        )
        regions["region_area_m2"] = regions.geometry.area

        # Sum the raster intersection areas within each region.
        covered = (
            intersections.groupby("model_region")["intersection_area_m2"]
            .sum()
            .rename("covered_area_m2")
        )

        # Combine full and covered areas into one summary table.
        coverage = regions.set_index("model_region")[["region_area_m2"]].join(
            covered
        )
        coverage["covered_area_m2"] = coverage["covered_area_m2"].fillna(0.0)

        # Calculate the fraction of each region covered by the meteorological grid.
        coverage["coverage_fraction"] = (
            coverage["covered_area_m2"] / coverage["region_area_m2"]
        )

        return coverage
