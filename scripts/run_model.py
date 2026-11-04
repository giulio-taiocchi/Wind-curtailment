
"""Run the wind-generation model for January 2009."""

from wind_curtailment.config import ModelConfig
from wind_curtailment.model import WindCurtailmentModel


# Create the configuration and model.
config = ModelConfig()
model = WindCurtailmentModel(config)

# Run January 2009 using area-weighted spatial aggregation.
result = model.run_month(
    year=2009,
    month=1,
    spatial_method="area",
)

# Display basic information about the run.
print("\nMODEL RUN")
print(f"Source file: {result.wind_data.source_file}")
print(f"Number of timestamps: {len(result.wind_data.timestamps)}")
print(f"Grid cells: {len(result.grid)}")
print(f"Grid-region intersections: {len(result.intersections)}")

# Display the spatial coverage of each region.
print("\nREGIONAL SPATIAL COVERAGE")
print(result.regional_coverage)

# Display the mean capacity factor for each region.
print("\nMEAN REGIONAL CAPACITY FACTORS")
print(result.regional_capacity_factors.mean())

# Display the national capacity-factor statistics.
print("\nNATIONAL CAPACITY FACTOR")
print(f"Mean:   {result.national_capacity_factor.mean():.4f}")
print(f"Std:    {result.national_capacity_factor.std():.4f}")
print(f"Min:    {result.national_capacity_factor.min():.4f}")
print(f"Median: {result.national_capacity_factor.median():.4f}")
print(f"Max:    {result.national_capacity_factor.max():.4f}")

# Combine national and regional capacity factors into one table.
hourly_results = result.regional_capacity_factors.copy()

# Add the national capacity factor as another column.
hourly_results["National"] = result.national_capacity_factor

# Save the hourly time series for subsequent analysis.
output_file = config.data_dir / "january_2009_capacity_factors.csv"
hourly_results.to_csv(output_file)

print(f"\nHourly results saved to: {output_file}")
