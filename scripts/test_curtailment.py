
"""Basic checks for the two curtailment rules."""

import numpy as np
import pandas as pd

from wind_curtailment.curtailment import (
    CurtailmentConfig,
    CurtailmentModel,
)


# Use a weekday daytime timestamp so the weekday minimum applies.
timestamps = pd.to_datetime(
    [
        "2020-01-06 12:00",
        "2020-01-06 12:00",
        "2020-01-06 12:00",
    ]
)

demand_mw = np.array([4000.0, 4000.0, 4000.0])
wind_mw = np.array([2000.0, 4000.0, 5000.0])

config = CurtailmentConfig(
    snsp_limit=0.60,
    export_capacity_mw=0.0,
)

model = CurtailmentModel(config)
results = model.run(timestamps, demand_mw, wind_mw)

# With no constraint triggered, the first hour should have no curtailment.
assert results.loc[0, "total_curtailment_mw"] == 0.0

# In the second hour, the SNSP limit should curtail wind to 60% of demand.
assert np.isclose(
    results.loc[1, "total_curtailment_mw"],
    1600.0,
)

# In the third hour, Rule 1 should act first.
assert results.loc[2, "curtailment_rule1_mw"] > 0.0

# The final delivered wind must not exceed the SNSP limit.
assert (
    results["delivered_wind_mw"]
    <= config.snsp_limit * results["effective_demand_mw"] + 1e-9
).all()

# No hourly curtailment can exceed the available wind power.
assert (
    results["total_curtailment_mw"]
    <= results["available_wind_mw"] + 1e-9
).all()

print(results.to_string(index=False))
print("\nAll curtailment tests passed.")
