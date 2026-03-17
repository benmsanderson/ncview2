#!/usr/bin/env python
"""Generate synthetic test NetCDF data for ncview2 development.

Creates test_data.nc with:
  - sst        (time, lat, lon)  — sea surface temperature (always positive)
  - sst_anomaly (time, lat, lon) — anomaly field (positive & negative)
  - temp_3d    (time, depth, lat, lon) — 4D temperature field
"""

import numpy as np
import xarray as xr

# --- Coordinates ---
times = np.arange("2020-01-01", "2021-01-01", dtype="datetime64[D]")  # 366 days
lats = np.linspace(-90, 90, 91)
lons = np.linspace(-180, 179, 180)
depths = np.array([0, 10, 50, 100, 200, 500, 1000, 2000], dtype=float)

nt, ny, nx, nz = len(times), len(lats), len(lons), len(depths)
rng = np.random.default_rng(42)

# --- SST: latitude-dependent + seasonal cycle + noise ---
lat_rad = np.deg2rad(lats)
base_sst = 25 * np.cos(lat_rad)[:, np.newaxis] * np.ones(nx)
day_of_year = np.arange(nt)
seasonal = (
    10
    * np.sin(2 * np.pi * day_of_year / 365)[:, np.newaxis, np.newaxis]
    * np.cos(lat_rad)[np.newaxis, :, np.newaxis]
)
noise = rng.normal(0, 0.8, (nt, ny, nx))
sst = base_sst[np.newaxis, :, :] + seasonal + noise

# --- SST anomaly ---
sst_anom = sst - base_sst[np.newaxis, :, :]

# --- 4D temperature: decays with depth ---
depth_factor = np.exp(-depths / 300)  # (nz,)
temp_3d = sst[:, np.newaxis, :, :] * depth_factor[np.newaxis, :, np.newaxis, np.newaxis]
temp_3d += rng.normal(0, 0.3, (nt, nz, ny, nx))

# --- Simple land masking (crude continents) ---
lon2d, lat2d = np.meshgrid(lons, lats)
land = (
    ((lat2d > 20) & (lat2d < 70) & (lon2d > -130) & (lon2d < -60))  # N. America
    | ((lat2d > -60) & (lat2d < 15) & (lon2d > -80) & (lon2d < -35))  # S. America
    | ((lat2d > -40) & (lat2d < 40) & (lon2d > -20) & (lon2d < 55))  # Africa
    | ((lat2d > 10) & (lat2d < 70) & (lon2d > 60) & (lon2d < 140))  # Asia
    | ((lat2d > -50) & (lat2d < -10) & (lon2d > 110) & (lon2d < 155))  # Australia
)
sst[:, land] = np.nan
sst_anom[:, land] = np.nan
temp_3d[:, :, land] = np.nan

# --- Build dataset ---
ds = xr.Dataset(
    {
        "sst": (
            ["time", "lat", "lon"],
            sst.astype(np.float32),
            {"units": "degC", "long_name": "Sea Surface Temperature"},
        ),
        "sst_anomaly": (
            ["time", "lat", "lon"],
            sst_anom.astype(np.float32),
            {"units": "degC", "long_name": "SST Anomaly"},
        ),
        "temp_3d": (
            ["time", "depth", "lat", "lon"],
            temp_3d.astype(np.float32),
            {"units": "degC", "long_name": "Ocean Temperature"},
        ),
    },
    coords={
        "time": times,
        "lat": ("lat", lats, {"units": "degrees_north", "long_name": "Latitude"}),
        "lon": ("lon", lons, {"units": "degrees_east", "long_name": "Longitude"}),
        "depth": ("depth", depths, {"units": "m", "long_name": "Depth", "positive": "down"}),
    },
    attrs={"title": "Synthetic test data for ncview2", "Conventions": "CF-1.8"},
)

outfile = "test_data.nc"
ds.to_netcdf(outfile)
print(f"Created {outfile}")
print(ds)
