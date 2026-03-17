"""Data model — xarray-based NetCDF loading and slicing."""

import numpy as np
import xarray as xr
from pathlib import Path

LAT_NAMES = frozenset({"lat", "latitude", "nav_lat", "rlat", "nlat"})
LON_NAMES = frozenset({"lon", "longitude", "nav_lon", "rlon", "nlon"})
TIME_NAMES = frozenset({"time", "t", "times"})

# Dimension names that typically indicate an unstructured spatial column
_UNSTRUCTURED_DIM_NAMES = frozenset({"ncol", "ncells", "nfaces", "cell", "ngrid"})


class DataModel:
    """Manages an open NetCDF dataset and provides slicing operations."""

    def __init__(self, path):
        self.path = Path(path)
        # Use cftime for dates outside nanosecond range; skip timedelta decoding
        # to avoid overflow on variables like SNOW_PERSISTENCE.
        time_coder = xr.coders.CFDatetimeCoder(use_cftime=True)
        self.ds = xr.open_dataset(str(path), decode_times=time_coder, decode_timedelta=False)

    def close(self):
        self.ds.close()

    @property
    def filename(self):
        return self.path.name

    @property
    def plottable_variables(self):
        """Variable names with 2+ dims and numeric dtype, suitable for spatial display.

        Includes both regular-grid vars (last 2 dims are spatial) and
        unstructured vars (last dim is a column index with associated lat/lon).
        """
        result = []
        for name, var in self.ds.data_vars.items():
            if var.size <= 1 or not np.issubdtype(var.dtype, np.number):
                continue
            if len(var.dims) >= 2:
                result.append(name)
            # 1D-spatial unstructured: e.g. (time, ncol) with lat/lon data vars
            # already has >=2 dims if there's a time dim, handled above
        return result

    def dim_roles(self, varname):
        """Classify each dim of a variable as 'time', 'lat', 'lon', or 'other'."""
        var = self.ds[varname]
        roles = {}
        for dim in var.dims:
            dl = dim.lower()
            if dl in TIME_NAMES or self._is_time_coord(dim):
                roles[dim] = "time"
            elif dl in LAT_NAMES:
                roles[dim] = "lat"
            elif dl in LON_NAMES:
                roles[dim] = "lon"
            else:
                roles[dim] = "other"
        return roles

    def _is_time_coord(self, dim):
        if dim in self.ds.coords:
            return np.issubdtype(self.ds[dim].dtype, np.datetime64)
        return False

    def is_land_only(self, varname):
        """Heuristic: detect if a variable covers land only (not global ocean+land)."""
        # Check for landmask/landfrac variables in the dataset
        for name in self.ds.data_vars:
            if name.lower() in ('landmask', 'landfrac'):
                return True
        # Check for high NaN fraction in coordinates (unstructured land grids)
        if self.is_unstructured(varname):
            lat, lon = self.get_unstructured_latlon(varname)
            if lat is not None and np.sum(np.isnan(lat)) / len(lat) > 0.3:
                return True
        # Check for high NaN fraction in first data slice
        scan = self.scan_dims(varname)
        sel = {d: 0 for d in scan}
        try:
            data = self.ds[varname].isel(sel).values.ravel()
            nan_frac = np.sum(np.isnan(data)) / max(data.size, 1)
            if nan_frac > 0.3:
                return True
        except Exception:
            pass
        return False

    def is_unstructured(self, varname):
        """Check if a variable uses an unstructured grid (single spatial column dim)."""
        var = self.ds[varname]
        last_dim = var.dims[-1]
        # Explicit check: known unstructured dim names
        if last_dim.lower() in _UNSTRUCTURED_DIM_NAMES:
            return True
        # Heuristic: last dim is NOT a recognised lat/lon coord and there are
        # 1D lat/lon data_vars or coords with the same dimension
        if last_dim.lower() not in LAT_NAMES | LON_NAMES:
            lat, lon = self._find_latlon_for_dim(last_dim)
            if lat is not None and lon is not None:
                return True
        return False

    def _find_latlon_for_dim(self, dim):
        """Find 1D lat/lon arrays that share the given dimension."""
        lat_arr = lon_arr = None
        # Search both data_vars and coords
        candidates = list(self.ds.data_vars.values()) + list(self.ds.coords.values())
        for v in candidates:
            if v.dims == (dim,):
                vn = v.name.lower()
                if vn in LAT_NAMES and lat_arr is None:
                    lat_arr = v.values
                elif vn in LON_NAMES and lon_arr is None:
                    lon_arr = v.values
        return lat_arr, lon_arr

    def get_unstructured_latlon(self, varname):
        """Return (lat, lon) arrays for the unstructured spatial dim."""
        last_dim = self.ds[varname].dims[-1]
        return self._find_latlon_for_dim(last_dim)

    def spatial_dims(self, varname):
        """Return spatial dims.

        For regular grids: (y_dim, x_dim) — the last two dims.
        For unstructured:  (col_dim,) — just the last dim (single tuple).
        """
        if self.is_unstructured(varname):
            return (self.ds[varname].dims[-1],)
        dims = self.ds[varname].dims
        return dims[-2], dims[-1]

    def scan_dims(self, varname):
        """Return non-spatial dims (scannable), in order."""
        if self.is_unstructured(varname):
            return list(self.ds[varname].dims[:-1])  # all but the column dim
        return list(self.ds[varname].dims[:-2])

    def dim_size(self, varname, dim):
        return self.ds[varname].sizes[dim]

    def dim_coord_values(self, dim):
        """Get coordinate values for a dimension, or None if no coords exist."""
        if dim in self.ds.coords:
            return self.ds.coords[dim].values
        return None

    def get_slice(self, varname, index_sel):
        """Get a 2D DataArray by selecting integer indices on non-spatial dims.

        index_sel: {dim_name: int_index} for each scan dimension.
        """
        return self.ds[varname].isel(index_sel)

    def get_timeseries(self, varname, spatial_sel):
        """Get a DataArray with spatial dims indexed out.

        spatial_sel: {dim_name: int_index} for spatial (and optionally extra) dims.
        """
        return self.ds[varname].isel(spatial_sel)

    # ── Area-average timeseries ──────────────────────────────────

    MAX_AREA_CELLS = 500  # subsample above this to keep it fast

    def get_area_average_timeseries(self, varname, bbox, extra_sel=None):
        """Compute cos(lat)-weighted area-average timeseries over a bounding box.

        Parameters
        ----------
        varname : str
        bbox : tuple (lon_min, lon_max, lat_min, lat_max)
        extra_sel : dict or None
            Index selections for non-time scan dims (e.g. level).

        Returns
        -------
        ts : xr.DataArray  (1-D, along first scan dim)
        n_cells : int  (number of cells used, after subsampling)
        """
        lon_min, lon_max, lat_min, lat_max = bbox

        if self.is_unstructured(varname):
            return self._area_avg_unstructured(varname, bbox, extra_sel)
        else:
            return self._area_avg_regular(varname, bbox, extra_sel)

    def _area_avg_regular(self, varname, bbox, extra_sel):
        lon_min, lon_max, lat_min, lat_max = bbox
        y_dim, x_dim = self.spatial_dims(varname)

        lat_vals = self.dim_coord_values(y_dim)
        lon_vals = self.dim_coord_values(x_dim)
        if lat_vals is None or lon_vals is None:
            raise ValueError("Cannot determine lat/lon coordinates for area average")

        lat_mask = (lat_vals >= lat_min) & (lat_vals <= lat_max)
        lon_mask = (lon_vals >= lon_min) & (lon_vals <= lon_max)

        yi = np.where(lat_mask)[0]
        xi = np.where(lon_mask)[0]
        if yi.size == 0 or xi.size == 0:
            raise ValueError("No grid cells in selected area")

        n_cells = yi.size * xi.size
        # Subsample if too many cells
        if n_cells > self.MAX_AREA_CELLS:
            rng = np.random.default_rng(0)
            # Subsample each axis independently to keep it rectangular
            target_per_axis = max(1, int(np.sqrt(self.MAX_AREA_CELLS)))
            if yi.size > target_per_axis:
                yi = rng.choice(yi, target_per_axis, replace=False)
                yi.sort()
            if xi.size > target_per_axis:
                xi = rng.choice(xi, target_per_axis, replace=False)
                xi.sort()
            n_cells = yi.size * xi.size

        sel = {y_dim: yi, x_dim: xi}
        if extra_sel:
            sel.update(extra_sel)

        sub = self.ds[varname].isel(sel)

        # cos(lat) weights — broadcast over x dim
        weights = np.cos(np.deg2rad(lat_vals[yi]))
        # Build an xarray-compatible weight array along spatial dims only
        weight_da = xr.DataArray(
            np.broadcast_to(weights[:, np.newaxis], (len(yi), len(xi))),
            dims=[y_dim, x_dim],
        )
        # Weight and average over spatial dims
        weighted = (sub * weight_da).sum(dim=[y_dim, x_dim])
        total_w = weight_da.sum(dim=[y_dim, x_dim])
        ts = weighted / total_w

        return ts, n_cells

    def _area_avg_unstructured(self, varname, bbox, extra_sel):
        lon_min, lon_max, lat_min, lat_max = bbox
        (col_dim,) = self.spatial_dims(varname)
        lat, lon = self.get_unstructured_latlon(varname)
        if lat is None or lon is None:
            raise ValueError("Cannot determine lat/lon for unstructured grid")

        # Normalize lons to -180..180 to match spatial canvas
        lon = (np.asarray(lon, dtype=float) + 180.0) % 360.0 - 180.0
        lat = np.asarray(lat, dtype=float)

        mask = (lat >= lat_min) & (lat <= lat_max) & (lon >= lon_min) & (lon <= lon_max)
        col_idx = np.where(mask)[0]
        if col_idx.size == 0:
            raise ValueError("No grid cells in selected area")

        # Subsample if too many columns
        if col_idx.size > self.MAX_AREA_CELLS:
            rng = np.random.default_rng(0)
            col_idx = rng.choice(col_idx, self.MAX_AREA_CELLS, replace=False)
            col_idx.sort()

        n_cells = col_idx.size

        sel = {col_dim: col_idx}
        if extra_sel:
            sel.update(extra_sel)

        sub = self.ds[varname].isel(sel)

        weights = np.cos(np.deg2rad(lat[col_idx]))
        ts = (sub * weights).sum(dim=col_dim) / weights.sum()

        return ts, n_cells

    def get_global_range(self, varname):
        """Compute robust min/max using percentiles to ignore outliers/fill values."""
        var = self.ds[varname]
        if var.size < 10_000_000:
            arr = var.values.ravel()
        else:
            # Sample first, middle, and last slices along the first dim
            scan = self.scan_dims(varname)
            if scan:
                first_dim = scan[0]
                n = self.dim_size(varname, first_dim)
                indices = sorted(set([0, n // 2, n - 1]))
                samples = [var.isel({first_dim: i}).values for i in indices]
                arr = np.concatenate([s.ravel() for s in samples])
            else:
                arr = var.values.ravel()

        finite = arr[np.isfinite(arr)]
        if finite.size == 0:
            return 0.0, 1.0

        # Use 2nd/98th percentile for robust color scaling
        vmin = float(np.percentile(finite, 2))
        vmax = float(np.percentile(finite, 98))

        # Guard against degenerate cases
        if np.isnan(vmin) or np.isnan(vmax):
            return 0.0, 1.0
        if vmin == vmax:
            return vmin - 1.0, vmax + 1.0
        return vmin, vmax
