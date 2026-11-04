import rasterio

from wind_curtailment.config import ModelConfig


# Locate the January 2009 CFSR file.
config = ModelConfig()
cfsr_dir = config.data_dir / "CFSR"
files = list(cfsr_dir.glob("cfsr_10m_200901_*.tif"))

if len(files) != 1:
    raise FileNotFoundError(f"Expected one file, found {len(files)}")

# Inspect the raster metadata.
with rasterio.open(files[0]) as src:

    print("General metadata:")
    print(src.meta)

    print("\nDataset tags:")
    print(src.tags())

    print("\nFirst five band descriptions:")
    print(src.descriptions[:5])

    print("\nFirst band tags:")
    print(src.tags(1))

    print("\nLast band tags:")
    print(src.tags(src.count))
