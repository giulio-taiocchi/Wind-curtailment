import numpy as np


class WindResource:
    """Processes meteorological wind data."""

    def __init__(self, config):
        # Store the model configuration.
        self.config = config

    def calculate_wind_speed(self, u, v):
        """Calculate horizontal wind speed from its u and v components."""

        # Calculate the wind-speed magnitude at each grid cell and time.
        return np.hypot(u, v)

    def extrapolate_to_hub_height(self, wind_speed):
        """Extrapolate wind speed from reference height to hub height."""

        # Obtain the height correction factor from the configuration.
        factor = self.config.height_extrapolation_factor()

        # Apply the power-law vertical extrapolation.
        return wind_speed * factor

