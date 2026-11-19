# Download and convert one month of CFSv2 10 m wind data.
#
# Usage:
#   Rscript scripts/download_cfsv2_month.R 2011 1
#
# Output:
#   ~/Projects/Wind_curtailment_data/CFSv2/
#       cfsv2_10m_201101_xm11_m5_y51_56.tif
#
# The NetCDF chunks are retained in CFSv2/chunks/YYYYMM so that
# successfully downloaded chunks can be reused if a later chunk fails.

suppressPackageStartupMessages({
  library(ncdf4)
  library(terra)
})

# ------------------------------------------------------------
# 1. Global download settings and command-line arguments
# ------------------------------------------------------------

# NCSS requests can take longer than R's default 60-second timeout.
options(timeout = 600)

args <- commandArgs(trailingOnly = TRUE)

if (length(args) != 2) {
  stop("Usage: Rscript scripts/download_cfsv2_month.R YEAR MONTH")
}

year <- suppressWarnings(as.integer(args[1]))
month <- suppressWarnings(as.integer(args[2]))

if (is.na(year) || is.na(month) ||
    year < 2011 || year > 2012 ||
    month < 1 || month > 12) {
  stop("This script supports CFSv2 data for 2011 and 2012.")
}

# Use smaller three-day requests to reduce timeout risk.
chunk_hours <- 72L
max_attempts <- 4L
retry_delay_seconds <- 10

# ------------------------------------------------------------
# 2. Paths and archive filename
# ------------------------------------------------------------

data_dir <- path.expand("~/Projects/Wind_curtailment_data")
output_dir <- file.path(data_dir, "CFSv2")
chunk_dir <- file.path(
  output_dir,
  "chunks",
  sprintf("%04d%02d", year, month)
)

dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)
dir.create(chunk_dir, recursive = TRUE, showWarnings = FALSE)

# The archive changes product naming during the first quarter of 2011.
product <- if (year == 2011 && month <= 3) "gdas" else "cdas1"

dataset_file <- sprintf(
  "wnd10m.%s.%04d%02d.grb2",
  product, year, month
)

dataset_path <- sprintf(
  "files/g/d094001/%d/%s",
  year, dataset_file
)

base_url <- paste0(
  "https://thredds.rda.ucar.edu/thredds/ncss/grid/",
  dataset_path
)

output_file <- file.path(
  output_dir,
  sprintf(
    "cfsv2_10m_%04d%02d_xm11_m5_y51_56.tif",
    year, month
  )
)

# ------------------------------------------------------------
# 3. Monthly time interval
# ------------------------------------------------------------

month_start_date <- as.Date(sprintf("%04d-%02d-01", year, month))
next_month_date <- seq(
  month_start_date,
  by = "month",
  length.out = 2
)[2]

days_in_month <- as.integer(next_month_date - month_start_date)

# The archive convention is 01:00 UTC on day one through
# 00:00 UTC on the first day of the following month.
month_start <- as.POSIXct(
  paste0(month_start_date, " 01:00:00"),
  tz = "UTC"
)

n_hours <- days_in_month * 24L

# Each chunk is at most 72 hourly records.
chunk_offsets <- seq.int(0L, n_hours - 1L, by = chunk_hours)

cat("CFSv2 dataset:", dataset_path, "\n")
cat("Monthly observations expected:", n_hours, "\n")
cat("Chunk size:", chunk_hours, "hours\n")
cat("Number of chunks:", length(chunk_offsets), "\n")

# ------------------------------------------------------------
# 4. Read and validate one NetCDF chunk
# ------------------------------------------------------------

read_chunk <- function(path, expected_hours, expected_start) {
  nc <- nc_open(path)
  on.exit(nc_close(nc), add = TRUE)

  lon <- as.numeric(ncvar_get(nc, "longitude"))
  lat <- as.numeric(ncvar_get(nc, "latitude"))
  time <- as.numeric(ncvar_get(nc, "time"))

  # Check the number and spacing of the time coordinates.
  if (length(time) != expected_hours) {
    stop("Unexpected number of timestamps in: ", path)
  }

  if (length(time) > 1L && any(abs(diff(time) - 1) > 1e-6)) {
    stop("Non-hourly timestamps in: ", path)
  }

  # Check that the time coordinate refers to the requested period.
  time_units <- ncatt_get(nc, "time", "units")$value

  if (is.null(time_units) || length(time_units) != 1L ||
      is.na(time_units)) {
    stop("Missing or invalid time units in: ", path)
  }

  origin_text <- sub(
    "^.*since[[:space:]]+",
    "",
    time_units,
    ignore.case = TRUE
  )

  time_origin <- as.POSIXct(
    origin_text,
    tz = "UTC",
    tryFormats = c(
      "%Y-%m-%dT%H:%M:%OSZ",
      "%Y-%m-%d %H:%M:%OS",
      "%Y-%m-%dT%H:%M:%OS"
    )
  )

  if (is.na(time_origin)) {
    stop("Could not parse NetCDF time origin: ", time_units)
  }

  # CFSv2 time units are hourly in this dataset.
  actual_times <- as.numeric(time_origin) + time * 3600
  expected_times <- as.numeric(expected_start) +
    (seq_len(expected_hours) - 1L) * 3600

  if (length(actual_times) != length(expected_times) ||
      any(abs(actual_times - expected_times) > 1)) {
    stop("Chunk timestamps do not match the requested interval: ", path)
  }

  # Read both horizontal wind components.
  u_raw <- ncvar_get(
    nc,
    "u-component_of_wind_height_above_ground",
    collapse_degen = FALSE
  )

  v_raw <- ncvar_get(
    nc,
    "v-component_of_wind_height_above_ground",
    collapse_degen = FALSE
  )

  # Expected NetCDF dimensions: longitude x latitude x height x time.
  du <- dim(u_raw)
  dv <- dim(v_raw)

  if (length(du) != 4L || length(dv) != 4L ||
      du[3] != 1L || dv[3] != 1L ||
      du[4] != expected_hours || dv[4] != expected_hours ||
      du[1] != length(lon) || dv[1] != length(lon) ||
      du[2] != length(lat) || dv[2] != length(lat)) {
    stop("Unexpected wind-variable dimensions in: ", path)
  }

  # Drop the singleton height dimension, preserving lon x lat x time.
  u <- array(u_raw, dim = c(du[1], du[2], du[4]))
  v <- array(v_raw, dim = c(dv[1], dv[2], dv[4]))

  if (any(!is.finite(u)) || any(!is.finite(v))) {
    stop("Non-finite wind values found in: ", path)
  }

  list(
    longitude = lon,
    latitude = lat,
    u = u,
    v = v
  )
}

# ------------------------------------------------------------
# 5. Download chunks and assemble the monthly arrays
# ------------------------------------------------------------

longitude <- NULL
latitude <- NULL
u_month <- NULL
v_month <- NULL

for (chunk_number in seq_along(chunk_offsets)) {
  offset <- chunk_offsets[chunk_number]

  this_chunk_hours <- min(
    chunk_hours,
    n_hours - offset
  )

  chunk_start <- month_start + offset * 3600
  chunk_end <- chunk_start + (this_chunk_hours - 1L) * 3600

  start_string <- format(
    chunk_start,
    "%Y-%m-%dT%H:%M:%SZ",
    tz = "UTC"
  )

  end_string <- format(
    chunk_end,
    "%Y-%m-%dT%H:%M:%SZ",
    tz = "UTC"
  )

  chunk_file <- file.path(
    chunk_dir,
    sprintf("chunk_%03d.nc", chunk_number)
  )

  cat(
    "\nChunk", chunk_number, "of", length(chunk_offsets),
    ":", start_string, "to", end_string, "\n"
  )

  # Reuse an existing chunk only after validating its time and grid data.
  chunk <- NULL

  if (file.exists(chunk_file)) {
    chunk <- tryCatch(
      read_chunk(chunk_file, this_chunk_hours, chunk_start),
      error = function(e) {
        message("Existing chunk is invalid: ", conditionMessage(e))
        NULL
      }
    )

    if (!is.null(chunk)) {
      cat("Using existing validated chunk.\n")
    } else {
      unlink(chunk_file)
    }
  }

  # Download to a temporary file so an interrupted transfer cannot
  # leave a partial file that looks like a completed chunk.
  if (is.null(chunk)) {
    request_url <- paste0(
      base_url,
      "?var=u-component_of_wind_height_above_ground",
      "&var=v-component_of_wind_height_above_ground",
      "&north=56&south=51&west=349&east=355",
      "&time_start=", start_string,
      "&time_end=", end_string,
      "&accept=netcdf"
    )

    temporary_file <- paste0(chunk_file, ".part")
    downloaded <- FALSE

    for (attempt in seq_len(max_attempts)) {
      cat("Download attempt", attempt, "of", max_attempts, "\n")
      unlink(temporary_file)

      # Download and validate within the retry loop.
      attempt_result <- tryCatch({
        download_status <- suppressWarnings(
          download.file(
            request_url,
            destfile = temporary_file,
            mode = "wb",
            method = "libcurl",
            quiet = FALSE
          )
        )

        if (!identical(download_status, 0L) &&
            !identical(download_status, 0)) {
          stop("download.file returned a non-zero status.")
        }

        if (!file.exists(temporary_file) ||
            file.info(temporary_file)$size < 100) {
          stop("Downloaded file is missing or unexpectedly small.")
        }

        # A successful HTTP transfer is not enough: parse and validate it.
        validated_chunk <- read_chunk(
          temporary_file,
          this_chunk_hours,
          chunk_start
        )

        # Promote the temporary file only after successful validation.
        if (!file.rename(temporary_file, chunk_file)) {
          stop("Could not move validated chunk into its final location.")
        }

        validated_chunk
      }, error = function(e) {
        message("Attempt failed: ", conditionMessage(e))
        NULL
      })

      if (!is.null(attempt_result)) {
        chunk <- attempt_result
        downloaded <- TRUE
        break
      }

      unlink(temporary_file)

      if (attempt < max_attempts) {
        cat("Waiting", retry_delay_seconds, "seconds before retrying.\n")
        Sys.sleep(retry_delay_seconds)
      }
    }

    if (!downloaded) {
      stop(
        "Failed to download and validate chunk ", chunk_number,
        ". Completed chunks have been retained for the next run."
      )
    }
  }

  # Initialise monthly arrays using the first chunk's spatial grid.
  if (is.null(longitude)) {
    longitude <- chunk$longitude
    latitude <- chunk$latitude

    nlon <- length(longitude)
    nlat <- length(latitude)

    u_month <- array(
      NA_real_,
      dim = c(nlon, nlat, n_hours)
    )

    v_month <- array(
      NA_real_,
      dim = c(nlon, nlat, n_hours)
    )
  } else {
    # Require an identical grid for every chunk in the month.
    if (length(chunk$longitude) != length(longitude) ||
        length(chunk$latitude) != length(latitude) ||
        max(abs(chunk$longitude - longitude)) > 1e-6 ||
        max(abs(chunk$latitude - latitude)) > 1e-6) {
      stop("Spatial grid changed between chunks.")
    }
  }

  # Insert the chunk at its correct position in the monthly time axis.
  indices <- seq.int(offset + 1L, offset + this_chunk_hours)
  u_month[, , indices] <- chunk$u
  v_month[, , indices] <- chunk$v

  cat(
    "u range:", range(chunk$u),
    "| v range:", range(chunk$v), "\n"
  )
}

# Ensure that every expected hourly value was populated.
if (anyNA(u_month) || anyNA(v_month)) {
  stop("Monthly arrays contain missing values after chunk assembly.")
}

# ------------------------------------------------------------
# 6. Standardise longitude and latitude orientation
# ------------------------------------------------------------

# Convert longitudes from 0-360 to -180-180 degrees.
longitude[longitude > 180] <- longitude[longitude > 180] - 360

# Ensure longitude increases west-to-east.
if (all(diff(longitude) < 0)) {
  longitude <- rev(longitude)
  u_month <- u_month[rev(seq_along(longitude)), , , drop = FALSE]
  v_month <- v_month[rev(seq_along(longitude)), , , drop = FALSE]
} else if (!all(diff(longitude) > 0)) {
  stop("Longitude coordinates are not strictly monotonic.")
}

# Ensure latitude decreases north-to-south.
if (all(diff(latitude) > 0)) {
  latitude <- rev(latitude)
  u_month <- u_month[, rev(seq_along(latitude)), , drop = FALSE]
  v_month <- v_month[, rev(seq_along(latitude)), , drop = FALSE]
} else if (!all(diff(latitude) < 0)) {
  stop("Latitude coordinates are not strictly monotonic.")
}

# ------------------------------------------------------------
# 7. Check grid regularity for GeoTIFF representation
# ------------------------------------------------------------

dx_values <- diff(longitude)
dy_values <- abs(diff(latitude))

dx <- mean(dx_values)
dy <- mean(dy_values)

# The CFSv2 Gaussian latitude grid is very slightly non-uniform.
# A regular GeoTIFF affine transform approximates it; reject larger
# deviations rather than silently accepting a substantially irregular grid.
if (max(abs(dx_values - dx)) > 0.001 ||
    max(abs(dy_values - dy)) > 0.001) {
  stop("Grid is too irregular for this GeoTIFF conversion.")
}

cat(
  "\nGrid dimensions:", length(longitude), "columns x",
  length(latitude), "rows\n"
)
cat("Mean longitude spacing:", dx, "degrees\n")
cat("Mean latitude spacing:", dy, "degrees\n")

# Construct raster bounds from the outermost cell centres.
xmin <- min(longitude) - dx / 2
xmax <- max(longitude) + dx / 2
ymin <- min(latitude) - dy / 2
ymax <- max(latitude) + dy / 2

# ------------------------------------------------------------
# 8. Create the GeoTIFF
# ------------------------------------------------------------

r <- rast(
  nrows = length(latitude),
  ncols = length(longitude),
  nlyrs = 2L * n_hours,
  xmin = xmin,
  xmax = xmax,
  ymin = ymin,
  ymax = ymax,
  crs = "EPSG:4326"
)

# NetCDF arrays are longitude x latitude. R stores matrices column-wise,
# so as.vector(array[,,time]) traverses longitude first and latitude second.
# That is the same order as raster cells: west-to-east across each row,
# then north-to-south down the rows. Do not transpose these matrices.
n_cells <- length(longitude) * length(latitude)

band_values <- matrix(
  NA_real_,
  nrow = n_cells,
  ncol = 2L * n_hours
)

for (i in seq_len(n_hours)) {
  band_values[, i] <- as.vector(u_month[, , i])
  band_values[, n_hours + i] <- as.vector(v_month[, , i])
}

values(r) <- band_values

# Label each band with its UTC timestamp; all u bands precede all v bands.
timestamps <- month_start + (seq_len(n_hours) - 1L) * 3600

time_labels <- format(
  timestamps,
  "%Y-%m-%d %H:%M:%S",
  tz = "UTC"
)

names(r) <- c(
  paste("u", time_labels),
  paste("v", time_labels)
)

# Write floating-point wind components in metres per second.
writeRaster(
  r,
  output_file,
  overwrite = TRUE,
  datatype = "FLT4S",
  gdal = c("COMPRESS=DEFLATE", "PREDICTOR=3")
)

# ------------------------------------------------------------
# 9. Verify the written GeoTIFF
# ------------------------------------------------------------

check <- rast(output_file)

if (nlyr(check) != 2L * n_hours) {
  stop("Output GeoTIFF has an unexpected number of bands.")
}

if (nrow(check) != length(latitude) ||
    ncol(check) != length(longitude)) {
  stop("Output GeoTIFF has unexpected spatial dimensions.")
}

# Check that the first u and first v bands contain finite values.
if (any(!is.finite(values(check[[1]]))) ||
    any(!is.finite(values(check[[n_hours + 1L]])))) {
  stop("Output GeoTIFF contains non-finite values.")
}

# Check that the first and last band labels retain the expected timestamps.
expected_first_u <- paste("u", format(
  month_start, "%Y-%m-%d %H:%M:%S", tz = "UTC"
))
expected_last_u <- paste("u", format(
  timestamps[n_hours], "%Y-%m-%d %H:%M:%S", tz = "UTC"
))
expected_first_v <- paste("v", format(
  month_start, "%Y-%m-%d %H:%M:%S", tz = "UTC"
))
expected_last_v <- paste("v", format(
  timestamps[n_hours], "%Y-%m-%d %H:%M:%S", tz = "UTC"
))

if (!identical(names(check)[1], expected_first_u) ||
    !identical(names(check)[n_hours], expected_last_u) ||
    !identical(names(check)[n_hours + 1L], expected_first_v) ||
    !identical(names(check)[2L * n_hours], expected_last_v)) {
  stop("Output GeoTIFF band names do not match the expected timestamps.")
}

cat("\nMonthly conversion complete.\n")
cat("Output:", output_file, "\n")
cat(
  "Dimensions:", nrow(check), "rows x", ncol(check),
  "columns\n"
)
cat("Bands:", nlyr(check), "\n")
cat("Expected hourly observations:", n_hours, "\n")
cat("Validated chunks retained in:", chunk_dir, "\n")
