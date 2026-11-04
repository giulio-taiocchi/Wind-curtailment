"""Inspect province-related attributes for Irish administrative units."""

from pathlib import Path

import geopandas as gpd


# Locate the saved Natural Earth administrative dataset.
data_dir = (
    Path.home()
    / "Projects"
    / "Wind_curtailment_data"
    / "spatial_metadata"
    / "natural_earth"
)

admin_file = data_dir / "ne_10m_admin_1_states_provinces.shp"
admin = gpd.read_file(admin_file)

# Select the 34 Republic of Ireland administrative records.
ireland = admin.loc[admin["admin"] == "Ireland"].copy()

# Select the 26 Northern Ireland districts using the same geographic
# bounding-box criterion as our earlier inspection.
uk = admin.loc[admin["admin"] == "United Kingdom"].copy()

ni = uk.loc[
    uk.geometry.bounds["minx"].between(-9.0, -5.0)
    & uk.geometry.bounds["maxx"].between(-9.0, -5.0)
    & uk.geometry.bounds["miny"].between(53.5, 56.0)
    & uk.geometry.bounds["maxy"].between(53.5, 56.0)
].copy()

# Combine the two sets of administrative units.
units = gpd.GeoDataFrame(
    gpd.pd.concat([ireland, ni], ignore_index=True),
    crs=admin.crs,
)

# Inspect fields that may help identify province-level groupings.
fields = [
    "name",
    "admin",
    "iso_3166_2",
    "type_en",
    "region",
    "region_sub",
    "provnum_ne",
    "adm1_code",
]

print("Administrative units:", len(units))
print("\nProvince-related attributes:")
print(
    units[fields]
    .sort_values(["admin", "name"])
    .to_string(index=False)
)

# Check whether these attributes contain useful grouping information.
for field in ["region", "region_sub", "provnum_ne"]:
    print(f"\nUnique values in {field}:")
    print(units[field].value_counts(dropna=False).to_string())
