import numpy as np

from wind_curtailment.turbine import Turbine


# Initialise the turbine model.
turbine = Turbine()

# Test representative wind speeds, including the operating thresholds.
wind_speeds = np.array([
    0.0,
    2.5,
    3.0002,
    5.0,
    10.0,
    12.9944,
    13.0,
    25.0,
    25.01,
])

# Calculate power and capacity factor.
power, capacity_factor = turbine.calculate(wind_speeds)

# Print the results for inspection.
for speed, output, cf in zip(wind_speeds, power, capacity_factor):
    print(
        f"Wind speed: {speed:7.4f} m/s | "
        f"Power: {output:8.3f} kW | "
        f"Capacity factor: {cf:.4f}"
    )

# Check the physical limits of the turbine output.
assert np.all(power >= 0.0)
assert np.all(power <= turbine.rated_power_kw)
assert np.all(capacity_factor >= 0.0)
assert np.all(capacity_factor <= 1.0)

# Check the cut-in, rated and cut-out behaviour.
assert power[0] == 0.0
assert power[1] == 0.0
assert power[5] == turbine.rated_power_kw
assert power[6] == turbine.rated_power_kw
assert power[7] == turbine.rated_power_kw
assert power[8] == 0.0

print("\nTurbine tests passed.")
