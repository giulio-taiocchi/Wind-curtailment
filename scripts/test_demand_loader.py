"""Integration check for the installed wind_curtailment demand package."""

from pathlib import Path

from wind_curtailment.demand import ESBMDemandLoader


# Read the workbook from the project's shared data directory.
workbook = Path.home() / "Projects" / "Wind_curtailment_data" / "ESBM v1.4.xlsx"
loader = ESBMDemandLoader(workbook)

for year in (2009, 2010, 2011, 2012):
    data = loader.load_year(year)
    print(data.validation_report())

# This reproduces the ESBM workbook's default peak-demand scaling input.
# It is deliberately explicit rather than assumed to be each year's measured peak.
example = loader.load_year(2010)
print("First three demand values (MW), using 7630.74 MW:")
print(example.demand_mw(7630.74).head(3))
