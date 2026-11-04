import numpy as np

from wind_curtailment.config import ModelConfig
from wind_curtailment.data_loader import CFSRDataLoader
from wind_curtailment.meteorology import WindResource


# Initialise the configuration and data loader.
config = ModelConfig()
loader = CFSRDataLoader(config)

# Load January 2009.
wind_data = loader.load_month(year=2009, month=1)

# Inspect the loaded data and its time coordinate.
print(f"Loaded: {wind_data.source_file}")
print(f"Grid dimensions: {wind_data.height} rows x {wind_data.width} columns")
print(f"CRS: {wind_data.crs}")
print(f"u10 shape: {wind_data.u10.shape}")
print(f"v10 shape: {wind_data.v10.shape}")
print(f"Number of timestamps: {len(wind_data.timestamps)}")
print(f"First timestamp: {wind_data.timestamps[0]}")
print(f"Last timestamp: {wind_data.timestamps[-1]}")


# Initialise the meteorological processor.
wind = WindResource(config)

# Calculate wind speed at 10 m and extrapolate to 80 m.
wind_speed_10m = wind.calculate_wind_speed(
    wind_data.u10, wind_data.v10
)
wind_speed_80m = wind.extrapolate_to_hub_height(wind_speed_10m)


# Display basic diagnostics.
print("\n10 m wind speed:")
print(f"  Mean: {wind_speed_10m.mean():.3f} m/s")
print(f"  Min:  {wind_speed_10m.min():.3f} m/s")
print(f"  Max:  {wind_speed_10m.max():.3f} m/s")

print("\n80 m wind speed:")
print(f"  Mean: {wind_speed_80m.mean():.3f} m/s")
print(f"  Min:  {wind_speed_80m.min():.3f} m/s")
print(f"  Max:  {wind_speed_80m.max():.3f} m/s")


# Check that timestamps are hourly and strictly increasing.
time_differences = [
    (wind_data.timestamps[i + 1] - wind_data.timestamps[i]).total_seconds()
    for i in range(len(wind_data.timestamps) - 1)
]

assert all(dt == 3600 for dt in time_differences)

# Verify the vertical extrapolation.
expected_80m = (
    wind_speed_10m * config.height_extrapolation_factor()
)
assert np.allclose(wind_speed_80m, expected_80m, equal_nan=True)

print("\nMeteorology and timestamp tests passed.")
