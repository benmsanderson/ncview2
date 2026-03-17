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
        self.ds = xr.open_dataset(str(path))

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

    def get_global_range(self, varname):
        """Compute min/max across all data. Samples for large variables."""
        var = self.ds[varname]
        if var.size < 10_000_000:
            vmin = float(np.nanmin(var.values))
            vmax = float(np.nanmax(var.values))
        else:
            # Sample first, middle, and last slices along the first dim
            scan = self.scan_dims(varname)
            if scan:
                first_dim = scan[0]
                n = self.dim_size(varname, first_dim)
                indices = sorted(set([0, n // 2, n - 1]))
                samples = [var.isel({first_dim: i}).values for i in indices]
                arr = np.concatenate([s.ravel() for s in samples])
                vmin, vmax = float(np.nanmin(arr)), float(np.nanmax(arr))
            else:
                vmin = float(np.nanmin(var.values))
                vmax = float(np.nanmax(var.values))

        # Guard against degenerate cases
        if np.isnan(vmin) or np.isnan(vmax):
            return 0.0, 1.0
        if vmin == vmax:
            return vmin - 1.0, vmax + 1.0
        return vmin, vmax
