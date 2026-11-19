"""Apply the two system-level wind-curtailment rules used by McKenna et al."""

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class CurtailmentConfig:
    """Parameters defining one curtailment scenario."""

    snsp_limit: float = 0.60
    partial_load_factor: float = 0.50

    weekday_daytime_min_mw: float = 2503.0
    weekend_daytime_min_mw: float = 2258.0
    night_min_mw: float = 2416.0

    # Provisional local-clock night period; make this configurable.
    night_start_hour: int = 23
    night_end_hour: int = 7

    # Available export capacity; zero represents the no-export case.
    export_capacity_mw: float = 0.0

    def __post_init__(self):
        """Validate scenario parameters."""
        if not 0.0 < self.snsp_limit <= 1.0:
            raise ValueError("SNSP limit must be between 0 and 1.")
        if not 0.0 < self.partial_load_factor <= 1.0:
            raise ValueError("Partial-load factor must be between 0 and 1.")
        if not 0 <= self.night_start_hour <= 23:
            raise ValueError("night_start_hour must be between 0 and 23.")
        if not 0 <= self.night_end_hour <= 23:
            raise ValueError("night_end_hour must be between 0 and 23.")
        if self.export_capacity_mw < 0:
            raise ValueError("Export capacity cannot be negative.")


class CurtailmentModel:
    """Calculate hourly curtailment using two sequential constraints."""

    def __init__(self, config=None):
        self.config = config or CurtailmentConfig()

    def _minimum_synchronous_generation(self, timestamps):
        """Return the applicable minimum synchronous generation per hour."""
        timestamps = pd.DatetimeIndex(timestamps)
        hours = timestamps.hour

        # Identify the configured night period, including midnight crossings.
        if self.config.night_start_hour > self.config.night_end_hour:
            is_night = (
                (hours >= self.config.night_start_hour)
                | (hours < self.config.night_end_hour)
            )
        else:
            is_night = (
                (hours >= self.config.night_start_hour)
                & (hours < self.config.night_end_hour)
            )

        # Saturday and Sunday use the weekend daytime minimum.
        is_weekend = timestamps.dayofweek >= 5

        # Assign the weekday daytime minimum first.
        minimum_generation = np.full(
            len(timestamps),
            self.config.weekday_daytime_min_mw,
            dtype=float,
        )

        # Override weekend and night-time values.
        minimum_generation[is_weekend] = (
            self.config.weekend_daytime_min_mw
        )
        minimum_generation[is_night] = self.config.night_min_mw

        # Apply the partial-load factor specified by the scenario.
        return minimum_generation * self.config.partial_load_factor

    def run(self, timestamps, demand_mw, wind_mw):
        """Calculate hourly curtailment and return detailed results."""
        timestamps = pd.DatetimeIndex(pd.to_datetime(timestamps))
        demand_mw = np.asarray(demand_mw, dtype=float)
        wind_mw = np.asarray(wind_mw, dtype=float)

        # Check that every input series describes the same hourly intervals.
        if not (
            len(timestamps) == len(demand_mw) == len(wind_mw)
        ):
            raise ValueError(
                "Timestamps, demand and wind must have identical lengths."
            )

        # Reject missing or infinite inputs rather than treating them as zero.
        if not (
            np.isfinite(demand_mw).all()
            and np.isfinite(wind_mw).all()
        ):
            raise ValueError("Demand and wind must contain finite values.")

        if np.any(demand_mw < 0) or np.any(wind_mw < 0):
            raise ValueError("Demand and wind cannot be negative.")

        # Treat available exports as an additional sink for wind generation.
        export_mw = np.full(
            len(timestamps),
            self.config.export_capacity_mw,
            dtype=float,
        )
        effective_demand_mw = demand_mw + export_mw

        # Obtain the synchronous-generation requirement for each hour.
        minimum_sync_mw = self._minimum_synchronous_generation(timestamps)

        # Calculate net demand before curtailment.
        net_demand_before_mw = effective_demand_mw - wind_mw

        # Rule 1: retain sufficient net demand for synchronous generation.
        curtailment_rule1_mw = np.minimum(
            wind_mw,
            np.maximum(
                0.0,
                minimum_sync_mw - net_demand_before_mw,
            ),
        )

        # Calculate the wind remaining after applying Rule 1.
        wind_after_rule1_mw = wind_mw - curtailment_rule1_mw

        # Rule 2: limit wind penetration to the configured SNSP fraction.
        maximum_wind_allowed_mw = (
            self.config.snsp_limit * effective_demand_mw
        )
        curtailment_rule2_mw = np.maximum(
            0.0,
            wind_after_rule1_mw - maximum_wind_allowed_mw,
        )

        # Combine both sources of curtailment.
        total_curtailment_mw = (
            curtailment_rule1_mw + curtailment_rule2_mw
        )
        delivered_wind_mw = wind_mw - total_curtailment_mw

        # Calculate system net demand and the resulting SNSP.
        net_demand_after_mw = effective_demand_mw - delivered_wind_mw
        actual_snsp = np.divide(
            delivered_wind_mw,
            effective_demand_mw,
            out=np.full(len(timestamps), np.nan),
            where=effective_demand_mw > 0,
        )

        # Preserve all intermediate values for diagnostics and validation.
        return pd.DataFrame({
            "timestamp": timestamps,
            "demand_mw": demand_mw,
            "export_mw": export_mw,
            "effective_demand_mw": effective_demand_mw,
            "available_wind_mw": wind_mw,
            "minimum_sync_mw": minimum_sync_mw,
            "net_demand_before_mw": net_demand_before_mw,
            "curtailment_rule1_mw": curtailment_rule1_mw,
            "wind_after_rule1_mw": wind_after_rule1_mw,
            "curtailment_rule2_mw": curtailment_rule2_mw,
            "total_curtailment_mw": total_curtailment_mw,
            "delivered_wind_mw": delivered_wind_mw,
            "net_demand_after_mw": net_demand_after_mw,
            "actual_snsp": actual_snsp,
        })

    @staticmethod
    def summarise(hourly_results):
        """Calculate annual and overall energy and curtailment statistics."""
        results = hourly_results.copy()
        results["year"] = results["timestamp"].dt.year

        def calculate_metrics(group):
            """Calculate energy totals and curtailment percentage."""
            available = group["available_wind_mw"].sum()
            curtailed = group["total_curtailment_mw"].sum()
            delivered = group["delivered_wind_mw"].sum()

            percentage = (
                100.0 * curtailed / available
                if available > 0
                else np.nan
            )

            return pd.Series({
                "hours": len(group),
                "available_wind_energy_mwh": available,
                "curtailed_energy_mwh": curtailed,
                "delivered_wind_energy_mwh": delivered,
                "curtailment_percentage": percentage,
                "mean_demand_mw": group["demand_mw"].mean(),
                "mean_wind_mw": group["available_wind_mw"].mean(),
                "hours_with_curtailment": (
                    group["total_curtailment_mw"] > 0
                ).sum(),
            })

        # Summarise each year separately.
        annual = (
            results.groupby("year")
            .apply(calculate_metrics, include_groups=False)
            .reset_index()
        )

        # Also calculate metrics across the complete input period.
        overall = calculate_metrics(results).to_frame().T
        overall.insert(0, "year", "ALL")

        return pd.concat([annual, overall], ignore_index=True)
