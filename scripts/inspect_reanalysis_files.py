
"""Inspect CFSR and CFSv2 monthly wind-data files."""

from pathlib import Path

import rasterio

from wind_curtailment.config import ModelConfig


def inspect_file(path):
    """Print the important metadata for one GeoTIFF."""

    print(f"\nFile: {path.name}")

    with rasterio.open(path) as src:
        # Basic raster dimensions and spatial reference.
        print(f"  Dimensions: {src.height} rows x {src.width} columns")
        print(f"  Number of bands: {src.count}")
        print(f"  CRS: {src.crs}")
        print(f"  Bounds: {src.bounds}")
        print(f"  Transform: {src.transform}")
        print(f"  NoData: {src.nodata}")

        # Rasterio stores scale and offset separately from the raw values.
        print(f"  Band scales (first 4): {src.scales[:4]}")
        print(f"  Band offsets (first 4): {src.offsets[:4]}")

        # Band descriptions often contain the variable and timestamp.
        descriptions = src.descriptions

        print("  First 3 band descriptions:")
        for description in descriptions[:3]:
            print(f"    {description}")

        print("  Last 3 band descriptions:")
        for description in descriptions[-3:]:
            print(f"    {description}")

        # Check whether every band has a description.
        described_bands = sum(
            description is not None
            for description in descriptions
        )

        print(
            f"  Bands with descriptions: "
            f"{described_bands}/{src.count}"
        )


def inspect_directory(directory, dataset_name):
    """Find and inspect all GeoTIFF files in a dataset directory."""

    print("\n" + "=" * 70)
    print(f"{dataset_name} FILES")
    print("=" * 70)

    if not directory.exists():
        print(f"Directory not found: {directory}")
        return

    # Search recursively because monthly files may be organised in subfolders.
    files = sorted(directory.rglob("*.tif"))

    print(f"Directory: {directory}")
    print(f"Number of GeoTIFF files: {len(files)}")

    if not files:
        print("No .tif files found.")
        return

    # Print a compact file inventory before inspecting metadata.
    print("\nFile inventory:")
    for path in files:
        print(f"  {path.relative_to(directory)}")

    # Inspect the first and last files, plus a middle file if available.
    selected_indices = sorted({
        0,
        len(files) // 2,
        len(files) - 1,
    })

    print("\nDetailed metadata:")
    for index in selected_indices:
        inspect_file(files[index])


if __name__ == "__main__":
    # Get the shared data directory from the model configuration.
    config = ModelConfig()

    # Inspect the two reanalysis datasets.
    inspect_directory(
        config.data_dir / "CFSR",
        "CFSR",
    )

    inspect_directory(
        config.data_dir / "CFSv2",
        "CFSv2",
    )
