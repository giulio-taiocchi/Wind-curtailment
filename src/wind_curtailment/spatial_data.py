
"""Prepare and save the four Irish model-region boundaries."""

from pathlib import Path

import geopandas as gpd
import pandas as pd

from wind_curtailment.config import ModelConfig


# Assign every Republic of Ireland administrative record to a model region.
# Duplicate city/county names deliberately receive the same assignment.
IRELAND_REGION_MAP = {
    "Carlow": "East",
    "Cavan": "North",
    "Clare": "South",
    "Cork": "South",
    "Donegal": "North",
    "Dublin": "East",
    "Dún Laoghaire–Rathdown": "East",
    "Fingal": "East",
    "Galway": "West",
    "Kerry": "South",
    "Kildare": "East",
    "Kilkenny": "East",
    "Laoighis": "East",
    "Leitrim": "West",
    "Limerick": "South",
    "Longford": "East",
    "Louth": "North",
    "Mayo": "West",
    "Meath": "East",
    "Monaghan": "North",
    "North Tipperary": "South",
    "Offaly": "East",
    "Roscommon": "West",
    "Sligo": "West",
    "South Dublin": "East",
    "South Tipperary": "South",
    "Waterford": "South",
    "Westmeath": "East",
    "Wexford": "East",
    "Wicklow": "East",
}

EXPECTED_REGIONS = {"North", "East", "South", "West"}


class SpatialDataPreparer:
    """Builds the model regions from Natural Earth administrative units."""

    def __init__(self, config):
        self.config = config

        # Define the path to the original administrative-boundary shapefile.
        self.admin_file = (
            config.natural_earth_dir
            / "ne_10m_admin_1_states_provinces.shp"
        )

    def load_administrative_units(self):
        """Select the 34 Irish and 26 Northern Irish records."""

        if not self.admin_file.exists():
            raise FileNotFoundError(
                f"Natural Earth administrative file not found: "
                f"{self.admin_file}"
            )

        # Read the original source dataset.
        admin = gpd.read_file(self.admin_file)

        # Select the Republic of Ireland's 34 administrative records.
        ireland = admin.loc[
            admin["admin"] == "Ireland"
        ].copy()

        # Select the 26 Northern Ireland records using Natural Earth's
        # administrative region attribute.
        northern_ireland = admin.loc[
            (admin["admin"] == "United Kingdom")
            & (admin["region"] == "Northern Ireland")
        ].copy()

        # Check the source selection against the records we inspected.
        if len(ireland) != 34:
            raise ValueError(
                f"Expected 34 Republic records, found {len(ireland)}."
            )

        if len(northern_ireland) != 26:
            raise ValueError(
                f"Expected 26 Northern Ireland records, "
                f"found {len(northern_ireland)}."
            )

        # Combine both jurisdictions into one GeoDataFrame.
        units = gpd.GeoDataFrame(
            pd.concat(
                [ireland, northern_ireland],
                ignore_index=True,
            ),
            crs=admin.crs,
        )

        if len(units) != 60:
            raise ValueError(
                f"Expected 60 administrative units, found {len(units)}."
            )

        return units

    def assign_model_regions(self, units):
        """Assign each administrative unit to North, East, South or West."""

        units = units.copy()

        # Apply the explicit county-to-region mapping to the Republic.
        ireland_mask = units["admin"] == "Ireland"
        units.loc[ireland_mask, "model_region"] = (
            units.loc[ireland_mask, "name"].map(IRELAND_REGION_MAP)
        )

        # All 26 Northern Ireland administrative districts belong to North.
        ni_mask = (
            (units["admin"] == "United Kingdom")
            & (units["region"] == "Northern Ireland")
        )
        units.loc[ni_mask, "model_region"] = "North"

        # Fail rather than silently leave an administrative unit unassigned.
        if units["model_region"].isna().any():
            unassigned = units.loc[
                units["model_region"].isna(),
                ["name", "admin"],
            ]
            raise ValueError(
                "Some administrative units have no regional assignment:\n"
                f"{unassigned.to_string(index=False)}"
            )

        # Check that only the four intended model regions were produced.
        actual_regions = set(units["model_region"])
        if actual_regions != EXPECTED_REGIONS:
            raise ValueError(
                f"Unexpected model regions: {actual_regions}"
            )

        return units

    def build_regions(self, units):
        """Dissolve the administrative units into four regional polygons."""

        # Repair invalid geometries before performing spatial unions.
        units = units.copy()
        units["geometry"] = units.geometry.make_valid()

        # Track how many administrative units contribute to each region.
        units["unit_count"] = 1

        # Dissolve all administrative geometries belonging to each region.
        regions = units.dissolve(
            by="model_region",
            aggfunc={"unit_count": "sum"},
        ).reset_index()

        # Keep the four regions in a predictable order.
        regions = regions.set_index("model_region").loc[
            ["North", "East", "South", "West"]
        ].reset_index()

        # Retain the source coordinate reference system (normally EPSG:4326).
        regions = regions[[
            "model_region",
            "unit_count",
            "geometry",
        ]]

        return regions

    def save_regions(self, regions, overwrite=False):
        """Save the four prepared regions to a GeoPackage."""

        output_file = self.config.regions_file

        # Create the destination directory if it does not exist.
        output_file.parent.mkdir(parents=True, exist_ok=True)

        # Protect an existing output unless replacement is explicitly allowed.
        if output_file.exists() and not overwrite:
            raise FileExistsError(
                f"{output_file} already exists. "
                "Use overwrite=True to replace it."
            )

        # Save the regions as one GeoPackage layer.
        regions.to_file(
            output_file,
            layer="model_regions",
            driver="GPKG",
        )

        return output_file

    def prepare(self, overwrite=False):
        """Run the complete spatial-data preparation workflow."""

        units = self.load_administrative_units()
        units = self.assign_model_regions(units)
        regions = self.build_regions(units)

        output_file = self.save_regions(
            regions,
            overwrite=overwrite,
        )

        return regions, output_file


if __name__ == "__main__":
    # Allow preparation to be run directly as a module.
    config = ModelConfig()
    preparer = SpatialDataPreparer(config)

    regions, output_file = preparer.prepare()

    print("\nPrepared model regions:")
    print(regions[["model_region", "unit_count"]])

    print(f"\nSaved regional boundaries to: {output_file}")

