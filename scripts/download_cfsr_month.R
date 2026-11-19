
# Download CFSR 10 m wind components in manageable time chunks,
# assemble each month, and write a GeoTIFF for the Python model.

library(ncdf4)
library(terra)

# ------------------------------------------------------------
# Configuration
# ------------------------------------------------------------

data_dir <- path.expand(
  "~/Projects/Wind_curtailment_data/CFSR"
)

chunk_dir <- file.path(data_dir, "chunks")
dir.create(chunk_dir, recursive = TRUE, showWarnings = FALSE)

# Read the year and month from command-line arguments.
args <- commandArgs(trailingOnly = TRUE)

if (length(args) != 2) {
  stop("Usage: Rscript download_cfsr_month.R YEAR MONTH")
}

year <- as.integer(args[1])
month <- as.integer(args[2])

if (is.na(year) || is.na(month) || month < 1 || month > 12) {
  stop("Invalid year or month.")
}

# Request at most ten days per NCSS download.
chunk_hours <- 10 * 24

# Give the NCAR server time to respond to larger requests.
options(timeout = 300)

# NCAR dataset identifier for CFSR.
dataset_path <- sprintf(
  "files/g/d093001/%d/wnd10m.gdas.%04d%02d.grb2",
  year, year, month
)

base_url <- paste0(
  "https://thredds.rda.ucar.edu/thredds/ncss/grid/",
  dataset_path
)

# ------------------------------------------------------------
# Helper: open a NetCDF file and check its time dimension
# ------------------------------------------------------------

get_time_count <- function(path) {

  nc <- nc_open(path)
  on.exit(nc_close(nc))

  length(ncvar_get(nc, "time"))
}

# ------------------------------------------------------------
# Helper: download one time chunk, with retries
# ------------------------------------------------------------

download_chunk <- function(start_time, end_time, expected_hours,
                           chunk_number) {

  chunk_file <- file.path(
    chunk_dir,
    sprintf(
      "cfsr_10m_%04d%02d_chunk%02d.nc",
      year, month, chunk_number
    )
  )

  # Reuse a previously downloaded chunk if it is valid.
  if (file.exists(chunk_file)) {

    existing_hours <- tryCatch(
      get_time_count(chunk_file),
      error = function(e) NA_integer_
    )

    if (!is.na(existing_hours) &&
        existing_hours == expected_hours) {

      message("Reusing existing chunk: ", basename(chunk_file))
      return(chunk_file)
    }

    # Remove incomplete or invalid files before retrying.
    file.remove(chunk_file)
  }

  # Format the requested UTC time interval.
  start_string <- format(
    start_time,
    "%Y-%m-%dT%H:%M:%SZ",
    tz = "UTC"
  )

  end_string <- format(
    end_time,
    "%Y-%m-%dT%H:%M:%SZ",
    tz = "UTC"
  )

  # Construct the NCSS request for both wind components.
  request_url <- paste0(
    base_url,
    "?var=u-component_of_wind_height_above_ground",
    "&var=v-component_of_wind_height_above_ground",
    "&north=56&south=51&west=349&east=355",
    "&time_start=", start_string,
    "&time_end=", end_string,
    "&accept=netcdf"
  )

  # Retry failed requests up to three times.
  for (attempt in seq_len(3)) {

    message(
      "Downloading chunk ", chunk_number,
      " (", start_string, " to ", end_string, ")",
      " — attempt ", attempt
    )

    success <- tryCatch({

      download.file(
        request_url,
        destfile = chunk_file,
        mode = "wb",
        method = "libcurl",
        quiet = FALSE
      )

      # Check that the server returned a readable NetCDF file.
      downloaded_hours <- get_time_count(chunk_file)

      if (downloaded_hours != expected_hours) {
        stop(
          "Unexpected time count: received ",
          downloaded_hours,
          ", expected ",
          expected_hours
        )
      }

      TRUE

    }, error = function(e) {

      message("Download failed: ", conditionMessage(e))

      if (file.exists(chunk_file)) {
        file.remove(chunk_file)
      }

      FALSE
    })

    if (success) {
      return(chunk_file)
    }

    if (attempt < 3) {
      Sys.sleep(10)
    }
  }

  stop("Could not download chunk ", chunk_number)
}

# ------------------------------------------------------------
# Calculate the number of hours in the requested month
# ------------------------------------------------------------

month_start <- as.POSIXct(
  sprintf("%04d-%02d-01 01:00:00", year, month),
  format = "%Y-%m-%d %H:%M:%S",
  tz = "UTC"
)

first_of_month <- as.Date(
  sprintf("%04d-%02d-01", year, month)
)

next_month <- seq.Date(
  first_of_month,
  by = "month",
  length.out = 2
)[2]

days_in_month <- as.integer(next_month - first_of_month)
month_hours <- days_in_month * 24

message("Processing ", year, "-", sprintf("%02d", month))
message("Expected hourly observations: ", month_hours)

# ------------------------------------------------------------
# Download and assemble all chunks
# ------------------------------------------------------------

# The first dimension is longitude, the second latitude,
# and the third dimension is time.
u_month <- NULL
v_month <- NULL

longitude <- NULL
latitude <- NULL

hours_downloaded <- 0
chunk_number <- 0

while (hours_downloaded < month_hours) {

  chunk_number <- chunk_number + 1

  # Determine the time interval for this chunk.
  hours_this_chunk <- min(
    chunk_hours,
    month_hours - hours_downloaded
  )

  chunk_start <- month_start + hours_downloaded * 3600

  chunk_end <- chunk_start +
    (hours_this_chunk - 1) * 3600

  # Download or reuse the NetCDF chunk.
  chunk_file <- download_chunk(
    chunk_start,
    chunk_end,
    hours_this_chunk,
    chunk_number
  )

  # Open the chunk and read its coordinates and data.
  nc <- nc_open(chunk_file)

  chunk_lon <- ncvar_get(nc, "longitude") - 360
  chunk_lat <- ncvar_get(nc, "latitude")

  chunk_u <- ncvar_get(
    nc,
    "u-component_of_wind_height_above_ground"
  )

  chunk_v <- ncvar_get(
    nc,
    "v-component_of_wind_height_above_ground"
  )

  nc_close(nc)

  # Check that the grid is consistent across all chunks.
  if (is.null(longitude)) {

    longitude <- chunk_lon
    latitude <- chunk_lat

    # Allocate the complete monthly arrays.
    u_month <- array(
      NA_real_,
      dim = c(length(longitude), length(latitude), month_hours)
    )

    v_month <- array(
      NA_real_,
      dim = c(length(longitude), length(latitude), month_hours)
    )

  } else {

    stopifnot(
      isTRUE(all.equal(longitude, chunk_lon)),
      isTRUE(all.equal(latitude, chunk_lat))
    )
  }

  # Insert this chunk into its correct position in the month.
  first_hour <- hours_downloaded + 1
  last_hour <- hours_downloaded + hours_this_chunk

  u_month[, , first_hour:last_hour] <- chunk_u
  v_month[, , first_hour:last_hour] <- chunk_v

  hours_downloaded <- last_hour

  message(
    "Assembled ", hours_downloaded,
    " / ", month_hours, " hourly observations"
  )
}

# ------------------------------------------------------------
# Convert the monthly arrays into a GeoTIFF
# ------------------------------------------------------------

# Calculate the raster extent from cell-centre coordinates.
dx <- median(abs(diff(longitude)))
dy <- median(abs(diff(latitude)))

wind_raster <- rast(
  nrows = length(latitude),
  ncols = length(longitude),
  nlyrs = 2 * month_hours,
  xmin = min(longitude) - dx / 2,
  xmax = max(longitude) + dx / 2,
  ymin = min(latitude) - dy / 2,
  ymax = max(latitude) + dy / 2,
  crs = "EPSG:4326"
)

# Store values in raster cell order: west-to-east,
# then north-to-south, with all u bands before all v bands.
n_cells <- length(longitude) * length(latitude)

band_values <- matrix(
  NA_real_,
  nrow = n_cells,
  ncol = 2 * month_hours
)

for (i in seq_len(month_hours)) {

  u_matrix <- t(u_month[, , i])
  v_matrix <- t(v_month[, , i])

  band_values[, i] <- as.vector(t(u_matrix))
  band_values[, month_hours + i] <- as.vector(t(v_matrix))
}

values(wind_raster) <- band_values

# Reconstruct the expected monthly UTC timestamps.
timestamps <- month_start +
  (seq_len(month_hours) - 1) * 3600

time_labels <- format(
  timestamps,
  "%Y-%m-%d %H:%M:%S",
  tz = "UTC"
)

names(wind_raster) <- c(
  paste("u", time_labels),
  paste("v", time_labels)
)

# Use the filename pattern expected by the Python loader.
output_file <- file.path(
  data_dir,
  sprintf(
    "cfsr_10m_%04d%02d_xm11_m5_y51_56.tif",
    year, month
  )
)

writeRaster(
  wind_raster,
  output_file,
  overwrite = TRUE,
  datatype = "FLT4S",
  gdal = c("COMPRESS=LZW")
)

message("Monthly GeoTIFF written: ", output_file)
message("Bands written: ", nlyr(wind_raster))
