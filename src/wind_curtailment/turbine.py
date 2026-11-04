import numpy as np


class Turbine:
    """Converts hub-height wind speeds into turbine power and capacity factor."""

    def __init__(
        self,
        rated_power_kw=1000.0,
        cut_in_speed=3.0002,
        rated_speed=12.9944,
        cut_out_speed=25.0,
    ):
        # Store the turbine's rated power and operating wind-speed thresholds.
        self.rated_power_kw = float(rated_power_kw)
        self.cut_in_speed = float(cut_in_speed)
        self.rated_speed = float(rated_speed)
        self.cut_out_speed = float(cut_out_speed)

        # Coefficients of the provisional fifth-order power-curve polynomial.
        # np.polyval expects coefficients in descending order of polynomial power.
        self.power_curve_coefficients = (
            0.0015,
            -0.1967,
            4.0058,
            -19.268,
            43.607,
            -50.0,
        )

        # Check that the turbine's operating thresholds are physically ordered.
        if not (
            0 <= self.cut_in_speed < self.rated_speed < self.cut_out_speed
        ):
            raise ValueError("Turbine wind-speed thresholds are inconsistent.")

        if self.rated_power_kw <= 0:
            raise ValueError("Rated power must be positive.")

    def calculate_power(self, wind_speed):
        """Calculate electrical power output in kW for an array of wind speeds."""

        # Convert the input to a NumPy array so scalar and array inputs both work.
        wind_speed = np.asarray(wind_speed, dtype=float)

        # Evaluate the polynomial over the input wind-speed values.
        polynomial_power = np.polyval(
            self.power_curve_coefficients,
            wind_speed,
        )

        # Start with zero output: this covers speeds below cut-in and above cut-out.
        power = np.zeros_like(wind_speed, dtype=float)

        # Between cut-in and rated speed, use the polynomial power curve.
        partial_load = (
            (wind_speed >= self.cut_in_speed)
            & (wind_speed < self.rated_speed)
        )
        power = np.where(
            partial_load,
            np.clip(polynomial_power, 0.0, self.rated_power_kw),
            power,
        )

        # Between rated speed and cut-out speed, the turbine produces rated power.
        rated_operation = (
            (wind_speed >= self.rated_speed)
            & (wind_speed <= self.cut_out_speed)
        )
        power = np.where(
            rated_operation,
            self.rated_power_kw,
            power,
        )

        return power

    def calculate_capacity_factor(self, power):
        """Convert power output into a dimensionless capacity factor."""

        # Divide output power by the turbine's rated power.
        return np.asarray(power, dtype=float) / self.rated_power_kw

    def calculate(self, wind_speed):
        """Calculate both power and capacity factor from wind speed."""

        # Calculate power first, then derive capacity factor from it.
        power = self.calculate_power(wind_speed)
        capacity_factor = self.calculate_capacity_factor(power)

        return power, capacity_factor
