import numpy as np
import pandas as pd


class WindAggregator:
    """Aggregates grid-cell capacity factors into regional and national series."""

    def __init__(self, region_order=("North", "East", "South", "West")):
        # Fix a consistent regional order for all output tables.
        self.region_order = list(region_order)

    def _validate_capacity_factors(self, capacity_factors, timestamps):
        """Check that the input array and time coordinate are consistent."""

        # Require a three-dimensional array: time, row, column.
        if capacity_factors.ndim != 3:
            raise ValueError(
                "Capacity factors must have shape (time, rows, columns)."
            )

        # Ensure that the number of timestamps matches the time dimension.
        if capacity_factors.shape[0] != len(timestamps):
            raise ValueError("Number of timestamps does not match the data.")

        # Reject invalid capacity factors rather than silently aggregating them.
        if not np.all(np.isfinite(capacity_factors)):
            raise ValueError("Capacity-factor array contains missing or infinite values.")

        if np.any((capacity_factors < 0) | (capacity_factors > 1)):
            raise ValueError("Capacity factors must lie between zero and one.")

    def calculate_regional_capacity_factors(
        self,
        capacity_factors,
        timestamps,
        intersections,
        method="area",
    ):
        """Calculate regional capacity-factor time series."""

        # Convert the input to a NumPy array and validate its dimensions and values.
        capacity_factors = np.asarray(capacity_factors, dtype=float)
        self._validate_capacity_factors(capacity_factors, timestamps)

        # Select the spatial weighting scheme.
        if method == "area":
            # Use every cell-region intersection, weighted by its area.
            spatial_data = intersections[
                ["row", "col", "model_region", "intersection_area_m2"]
            ].copy()
            weight_column = "intersection_area_m2"

        elif method == "equal_cell":
            # Assign each cell to only one region, based on its largest overlap.
            spatial_data = (
                intersections.sort_values(
                    "intersection_area_m2",
                    ascending=False,
                )
                .drop_duplicates(subset="cell_id")
                .copy()
            )
            spatial_data["equal_weight"] = 1.0
            weight_column = "equal_weight"

        else:
            raise ValueError("method must be 'area' or 'equal_cell'.")

        # Store one time series for each region.
        regional_series = {}

        for region in self.region_order:

            # Select the grid cells or cell intersections belonging to this region.
            region_data = spatial_data.loc[
                spatial_data["model_region"] == region
            ]

            if region_data.empty:
                raise ValueError(f"No meteorological grid cells found for {region}.")

            # Retrieve the raster row and column indices.
            rows = region_data["row"].to_numpy(dtype=int)
            cols = region_data["col"].to_numpy(dtype=int)

            # Retrieve the corresponding spatial weights.
            weights = region_data[weight_column].to_numpy(dtype=float)

            # Extract the time series at all selected grid cells.
            cell_series = capacity_factors[:, rows, cols]

            # Calculate the weighted spatial average independently at each hour.
            regional_values = np.average(
                cell_series,
                axis=1,
                weights=weights,
            )

            regional_series[region] = regional_values

        # Convert the regional time series into a DataFrame.
        return pd.DataFrame(
            regional_series,
            index=pd.DatetimeIndex(timestamps),
        )

    def calculate_national_capacity_factor(
        self,
        regional_capacity_factors,
        regional_capacity_shares,
    ):
        """Calculate national capacity factor using installed-capacity shares."""

        # Convert the regional shares into a pandas Series.
        shares = pd.Series(regional_capacity_shares, dtype=float)

        # Ensure that every model region has an installed-capacity share.
        shares = shares.reindex(self.region_order)

        if shares.isna().any():
            raise ValueError("Missing installed-capacity share for one or more regions.")

        # Check that the shares are non-negative and sum to one.
        if np.any(shares < 0):
            raise ValueError("Installed-capacity shares cannot be negative.")

        if not np.isclose(shares.sum(), 1.0):
            raise ValueError("Installed-capacity shares must sum to one.")

        # Ensure the regional data contain all required regions.
        regional_data = regional_capacity_factors[self.region_order]

        # Weight each regional capacity factor by its installed-capacity share.
        national = regional_data.mul(shares, axis="columns").sum(axis=1)

        national.name = "National_Capacity_Factor"

        return national
