# Download the hourly 10 m wind components needed for the
# January 2009–December 2012 wind-curtailment analysis.

library(windscape)

# Keep the meteorological data outside the source-code repository.
data_dir <- path.expand("/home/giulio/Projects/Wind_curtailment_data")

# Match the geographic bounds of the existing January 2009 file.
longitude_limits <- c(-11, -5)
latitude_limits <- c(51, 56)

# Download CFSR for 2009–2010.
# Existing monthly files are skipped, so January 2009 is retained.
cfsr_files <- download_wind_data(
  source = "cfsr",
  level = "10m",
  xlim = longitude_limits,
  ylim = latitude_limits,
  years = 2009:2010,
  months = 1:12,
  dir = file.path(data_dir, "CFSR"),
  overwrite = FALSE,
  quiet = FALSE
)

# Download CFSv2 for 2011–2012.
cfsv2_files <- download_wind_data(
  source = "cfsv2",
  level = "10m",
  xlim = longitude_limits,
  ylim = latitude_limits,
  years = 2011:2012,
  months = 1:12,
  dir = file.path(data_dir, "CFSv2"),
  overwrite = FALSE,
  quiet = FALSE
)

# Print the files returned by the downloader for a quick record.
cat("CFSR files returned:", length(cfsr_files), "\n")
cat("CFSv2 files returned:", length(cfsv2_files), "\n")
