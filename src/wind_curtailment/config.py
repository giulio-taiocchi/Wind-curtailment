
from pathlib import Path


class ModelConfig:
    """Stores configuration parameters and paths for the wind model."""

    def __init__(self):
        # Wind-height and extrapolation parameters.
        self.reference_height = 10.0
        self.hub_height = 80.0
        self.wind_shear_exp = 1.0 / 7.0

        # Modelled period.
        self.starting_year = 2009
        self.end_year = 2012

        # Shared location for the original meteorological and spatial data.
        self.data_dir = (
            Path.home() / "Projects" / "Wind_curtailment_data"
        )

        # Locations of the Natural Earth source files and prepared regions.
        self.spatial_metadata_dir = self.data_dir / "spatial_metadata"
        self.natural_earth_dir = (
            self.spatial_metadata_dir / "natural_earth"
        )
        self.regions_file = self.spatial_metadata_dir / "regions.gpkg"

        # Equal-area projection used for spatial calculations.
        self.equal_area_crs = "EPSG:3035"

        # County-derived installed-capacity shares.
        self.regional_capacity_shares = {
            "North": 0.495934,
            "East": 0.071739,
            "South": 0.294936,
            "West": 0.137391,
        }

        self.region_order = ("North", "East", "South", "West")

    def height_extrapolation_factor(self):
        """Return the wind-speed scaling factor for the hub height."""
        return (
            self.hub_height / self.reference_height
        ) ** self.wind_shear_exp

