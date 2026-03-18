"""Data model — xarray-based NetCDF loading and slicing."""

import os
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

    def __init__(self, paths):
        # Accept a single path or a list of paths.
        if isinstance(paths, (str, Path)):
            paths = [Path(paths)]
        else:
            paths = sorted(Path(p) for p in paths)

        self.paths = paths
        self._multi = len(paths) > 1

        if not self._multi:
            self.ds = xr.open_dataset(
                str(paths[0]), decode_times=True, decode_timedelta=False,
            )
        else:
            # Open first file for metadata (variable list, attrs, coords)
            self.ds = xr.open_dataset(
                str(paths[0]), decode_times=True, decode_timedelta=False,
            )
            self._build_multifile_index()

    def _detect_hdf5(self):
        """Check if the first file is HDF5 (NetCDF-4) or classic NetCDF-3."""
        try:
            import h5py
            with h5py.File(str(self.paths[0]), "r"):
                return True
        except Exception:
            return False

    def _build_multifile_index(self):
        """Build time-to-file mapping. Uses h5py for HDF5 files, xarray otherwise."""
        self._is_hdf5 = self._detect_hdf5()

        # Detect time dimension name
        self._time_dim = None
        for d in self.ds.dims:
            if d.lower() in TIME_NAMES or (
                d in self.ds.coords and np.issubdtype(self.ds[d].dtype, np.datetime64)
            ):
                self._time_dim = d
                break

        offsets = []      # [(global_start, global_end, file_idx), ...]
        time_raw = []     # raw numeric time values from each file
        valid_paths = []  # paths that opened successfully
        total = 0

        if self._is_hdf5:
            import h5py
            for i, p in enumerate(self.paths):
                try:
                    with h5py.File(str(p), "r") as h:
                        if self._time_dim and self._time_dim in h:
                            n = h[self._time_dim].shape[0]
                            time_raw.append(h[self._time_dim][:])
                        else:
                            n = 1
                            time_raw.append(np.array([total], dtype=float))
                except OSError:
                    continue
                offsets.append((total, total + n, i))
                valid_paths.append(p)
                total += n
        else:
            for i, p in enumerate(self.paths):
                try:
                    with xr.open_dataset(str(p), decode_times=False) as tmp:
                        if self._time_dim and self._time_dim in tmp:
                            n = tmp.dims[self._time_dim]
                            time_raw.append(tmp[self._time_dim].values)
                        else:
                            n = 1
                            time_raw.append(np.array([total], dtype=float))
                except Exception:
                    continue
                offsets.append((total, total + n, i))
                valid_paths.append(p)
                total += n

        self._file_offsets = offsets
        self._total_time = total
        self.paths = valid_paths

        if not time_raw:
            raise ValueError("No files could be opened successfully.")

        # Decode concatenated time coordinate
        raw = np.concatenate(time_raw)
        if self._time_dim and self._time_dim in self.ds.coords:
            units = (self.ds[self._time_dim].encoding.get("units")
                     or self.ds[self._time_dim].attrs.get("units", ""))
            calendar = (self.ds[self._time_dim].encoding.get("calendar")
                        or self.ds[self._time_dim].attrs.get("calendar", "standard"))
            if units:
                import cftime
                self._time_values = np.array(cftime.num2date(raw, units, calendar))
            else:
                self._time_values = raw
        else:
            self._time_values = raw

    def _file_for_time(self, global_idx):
        """Return (path_index_in_self.paths, local_time_index)."""
        for start, end, fi in self._file_offsets:
            if start <= global_idx < end:
                return fi, global_idx - start
        raise IndexError(f"Time index {global_idx} out of range (0–{self._total_time - 1})")

    def _h5_read(self, file_idx, varname, sel_tuple):
        """Read a slice from a file. Uses h5py for HDF5 files, xarray otherwise."""
        if self._is_hdf5:
            import h5py
            with h5py.File(str(self.paths[file_idx]), "r") as h:
                return np.asarray(h[varname][sel_tuple], dtype=float)
        else:
            with xr.open_dataset(
                str(self.paths[file_idx]),
                decode_times=False, decode_timedelta=False,
            ) as ds:
                return np.asarray(ds[varname].values[sel_tuple], dtype=float)

    def close(self):
        self.ds.close()

    @property
    def filename(self):
        if len(self.paths) == 1:
            return self.paths[0].name
        common = os.path.commonprefix([p.name for p in self.paths])
        return f"{common}... ({len(self.paths)} files)"

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
        if self._multi and dim == self._time_dim:
            return self._total_time
        return self.ds[varname].sizes[dim]

    def dim_coord_values(self, dim):
        """Get coordinate values for a dimension, or None if no coords exist."""
        if self._multi and dim == self._time_dim:
            return self._time_values
        if dim in self.ds.coords:
            return self.ds.coords[dim].values
        return None

    def get_slice(self, varname, index_sel):
        """Get a 2D DataArray by selecting integer indices on non-spatial dims."""
        if not self._multi:
            return self.ds[varname].isel(index_sel)

        # Multi-file: map time index to the right file
        local_sel = dict(index_sel)
        if self._time_dim and self._time_dim in local_sel:
            fi, local_t = self._file_for_time(local_sel[self._time_dim])
            local_sel[self._time_dim] = local_t
        else:
            fi = 0

        # Build h5py index tuple in dimension order
        var = self.ds[varname]
        sel_tuple = tuple(local_sel.get(d, slice(None)) for d in var.dims)
        data = self._h5_read(fi, varname, sel_tuple)

        # Wrap in DataArray with reference coords for spatial dims
        spatial = self.spatial_dims(varname)
        coords = {}
        for d in spatial:
            cv = self.dim_coord_values(d)
            if cv is not None:
                coords[d] = cv
        remaining_dims = [d for d in var.dims if d not in index_sel]
        return xr.DataArray(data, dims=remaining_dims, coords=coords)

    def get_timeseries(self, varname, spatial_sel):
        """Get a DataArray with spatial dims indexed out."""
        if not self._multi:
            return self.ds[varname].isel(spatial_sel)

        # Multi-file: read the point from each file via h5py
        var = self.ds[varname]
        # Build per-dim selectors (spatial dims are fixed, time dim is full)
        dim_sels = {}
        for d in var.dims:
            if d in spatial_sel:
                dim_sels[d] = spatial_sel[d]
            elif d == self._time_dim:
                dim_sels[d] = "time"  # marker
            else:
                dim_sels[d] = slice(None)

        chunks = []
        for start, end, fi in self._file_offsets:
            n = end - start
            sel_tuple = []
            for d in var.dims:
                if d == self._time_dim:
                    sel_tuple.append(slice(None))  # all local timesteps
                elif d in spatial_sel:
                    sel_tuple.append(spatial_sel[d])
                else:
                    sel_tuple.append(slice(None))
            arr = self._h5_read(fi, varname, tuple(sel_tuple))
            chunks.append(arr)

        values = np.concatenate(chunks, axis=0) if len(chunks[0].shape) > 0 else np.array(chunks)
        # Find remaining dims (those not indexed by a scalar in spatial_sel)
        remaining_dims = []
        remaining_coords = {}
        for d in var.dims:
            if d in spatial_sel and np.ndim(spatial_sel[d]) == 0:
                continue
            remaining_dims.append(d)
            if d == self._time_dim:
                remaining_coords[d] = self._time_values
            else:
                cv = self.dim_coord_values(d)
                if cv is not None:
                    remaining_coords[d] = cv
        return xr.DataArray(values, dims=remaining_dims, coords=remaining_coords)

    def get_value(self, varname, index_sel):
        """Read a single scalar value at the given indices. Multi-file aware."""
        if not self._multi:
            return float(self.ds[varname].isel(index_sel).values)
        local_sel = dict(index_sel)
        fi = 0
        if self._time_dim and self._time_dim in local_sel:
            fi, local_t = self._file_for_time(local_sel[self._time_dim])
            local_sel[self._time_dim] = local_t
        var = self.ds[varname]
        sel_tuple = tuple(local_sel.get(d, slice(None)) for d in var.dims)
        return float(self._h5_read(fi, varname, sel_tuple))

    def profile_dim(self, varname):
        """Return the non-time scan dimension suitable for vertical profiles, or None.

        For a var with dims (time, levgrnd, ncol), scan_dims=[time, levgrnd],
        so the profile dim is levgrnd (the second scan dim).
        """
        scan = self.scan_dims(varname)
        roles = self.dim_roles(varname)
        for d in scan:
            if roles.get(d) != "time":
                return d
        return None

    def get_profile(self, varname, spatial_sel, time_sel):
        """Extract a 1D profile along the profile dim at a point.

        spatial_sel: {dim: index} for spatial dims.
        time_sel: {dim: index} for the time dim.
        Returns: (values_1d, levels_1d, dim_name, level_units)
        """
        pdim = self.profile_dim(varname)
        if pdim is None:
            return None

        if not self._multi:
            sel = {}
            sel.update(spatial_sel)
            sel.update(time_sel)
            data = self.ds[varname].isel(sel)
            values = data.values.astype(float)
        else:
            sel = {}
            sel.update(spatial_sel)
            sel.update(time_sel)
            fi = 0
            if self._time_dim and self._time_dim in sel:
                fi, local_t = self._file_for_time(sel[self._time_dim])
                sel[self._time_dim] = local_t
            var = self.ds[varname]
            sel_tuple = tuple(sel.get(d, slice(None)) for d in var.dims)
            values = self._h5_read(fi, varname, sel_tuple)

        levels = self.dim_coord_values(pdim)
        if levels is None:
            levels = np.arange(self.dim_size(varname, pdim), dtype=float)
        level_units = ""
        if pdim in self.ds.coords:
            level_units = self.ds.coords[pdim].attrs.get("units", "")
        return values, levels.astype(float), pdim, level_units

    def get_area_average_profile(self, varname, bbox, time_sel):
        """Extract an area-averaged 1D profile along the profile dim."""
        pdim = self.profile_dim(varname)
        if pdim is None:
            return None
        lon_min, lon_max, lat_min, lat_max = bbox

        # Map time to correct file for multi-file
        local_time_sel = dict(time_sel)
        fi = 0
        if self._multi and self._time_dim and self._time_dim in local_time_sel:
            fi, local_t = self._file_for_time(local_time_sel[self._time_dim])
            local_time_sel[self._time_dim] = local_t

        if self.is_unstructured(varname):
            (col_dim,) = self.spatial_dims(varname)
            lat, lon = self.get_unstructured_latlon(varname)
            if lat is None or lon is None:
                return None
            lon = (np.asarray(lon, dtype=float) + 180.0) % 360.0 - 180.0
            lat = np.asarray(lat, dtype=float)
            mask = (lat >= lat_min) & (lat <= lat_max) & (lon >= lon_min) & (lon <= lon_max)
            col_idx = np.where(mask)[0]
            if col_idx.size == 0:
                return None
            if col_idx.size > self.MAX_AREA_CELLS:
                rng = np.random.default_rng(0)
                col_idx = rng.choice(col_idx, self.MAX_AREA_CELLS, replace=False)
            weights = np.cos(np.deg2rad(lat[col_idx]))

            if self._multi:
                var = self.ds[varname]
                sel = dict(local_time_sel)
                sel[col_dim] = col_idx
                sel_tuple = tuple(sel.get(d, slice(None)) for d in var.dims)
                sub = self._h5_read(fi, varname, sel_tuple)
                # Average over column axis (last axis)
                values = (sub * weights).sum(axis=-1) / weights.sum()
            else:
                sel = {col_dim: col_idx}
                sel.update(local_time_sel)
                sub = self.ds[varname].isel(sel)
                values = (sub * weights).sum(dim=col_dim).values / weights.sum()
        else:
            y_dim, x_dim = self.spatial_dims(varname)
            lat_vals = self.dim_coord_values(y_dim)
            lon_vals = self.dim_coord_values(x_dim)
            if lat_vals is None or lon_vals is None:
                return None
            yi = np.where((lat_vals >= lat_min) & (lat_vals <= lat_max))[0]
            xi = np.where((lon_vals >= lon_min) & (lon_vals <= lon_max))[0]
            if yi.size == 0 or xi.size == 0:
                return None
            n_cells = yi.size * xi.size
            if n_cells > self.MAX_AREA_CELLS:
                rng = np.random.default_rng(0)
                target = max(1, int(np.sqrt(self.MAX_AREA_CELLS)))
                if yi.size > target:
                    yi = rng.choice(yi, target, replace=False); yi.sort()
                if xi.size > target:
                    xi = rng.choice(xi, target, replace=False); xi.sort()
            weights_2d = np.broadcast_to(
                np.cos(np.deg2rad(lat_vals[yi]))[:, np.newaxis], (len(yi), len(xi))
            )

            if self._multi:
                var = self.ds[varname]
                sel = dict(local_time_sel)
                sel[y_dim] = yi
                sel[x_dim] = xi
                sel_tuple = tuple(sel.get(d, slice(None)) for d in var.dims)
                sub = self._h5_read(fi, varname, sel_tuple)
                values = (sub * weights_2d).sum(axis=(-2, -1)) / weights_2d.sum()
            else:
                sel = {y_dim: yi, x_dim: xi}
                sel.update(local_time_sel)
                sub = self.ds[varname].isel(sel)
                weight_da = xr.DataArray(weights_2d, dims=[y_dim, x_dim])
                values = ((sub * weight_da).sum(dim=[y_dim, x_dim]) / weight_da.sum()).values

        levels = self.dim_coord_values(pdim)
        if levels is None:
            levels = np.arange(self.dim_size(varname, pdim), dtype=float)
        level_units = ""
        if pdim in self.ds.coords:
            level_units = self.ds.coords[pdim].attrs.get("units", "")
        return values.astype(float), levels.astype(float), pdim, level_units

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
        if n_cells > self.MAX_AREA_CELLS:
            rng = np.random.default_rng(0)
            target_per_axis = max(1, int(np.sqrt(self.MAX_AREA_CELLS)))
            if yi.size > target_per_axis:
                yi = rng.choice(yi, target_per_axis, replace=False)
                yi.sort()
            if xi.size > target_per_axis:
                xi = rng.choice(xi, target_per_axis, replace=False)
                xi.sort()
            n_cells = yi.size * xi.size

        weights = np.cos(np.deg2rad(lat_vals[yi]))
        weight_2d = np.broadcast_to(weights[:, np.newaxis], (len(yi), len(xi)))
        total_w = float(weight_2d.sum())

        if not self._multi:
            sel = {y_dim: yi, x_dim: xi}
            if extra_sel:
                sel.update(extra_sel)
            sub = self.ds[varname].isel(sel)
            weight_da = xr.DataArray(weight_2d, dims=[y_dim, x_dim])
            weighted = (sub * weight_da).sum(dim=[y_dim, x_dim])
            ts = weighted / weight_da.sum(dim=[y_dim, x_dim])
        else:
            var = self.ds[varname]
            chunks = []
            for start, end, fi in self._file_offsets:
                sel = {}
                sel[y_dim] = yi
                sel[x_dim] = xi
                if extra_sel:
                    sel.update(extra_sel)
                sel_tuple = tuple(sel.get(d, slice(None)) for d in var.dims)
                sub = self._h5_read(fi, varname, sel_tuple)
                # sub shape: (n_time_local, [n_levels,] n_yi, n_xi) — average over last two
                avg = (sub * weight_2d).sum(axis=(-2, -1)) / total_w
                chunks.append(avg)
            values = np.concatenate(chunks, axis=0)
            ts = xr.DataArray(values, dims=[self._time_dim],
                              coords={self._time_dim: self._time_values})

        return ts, n_cells

    def _area_avg_unstructured(self, varname, bbox, extra_sel):
        lon_min, lon_max, lat_min, lat_max = bbox
        (col_dim,) = self.spatial_dims(varname)
        lat, lon = self.get_unstructured_latlon(varname)
        if lat is None or lon is None:
            raise ValueError("Cannot determine lat/lon for unstructured grid")

        lon = (np.asarray(lon, dtype=float) + 180.0) % 360.0 - 180.0
        lat = np.asarray(lat, dtype=float)

        mask = (lat >= lat_min) & (lat <= lat_max) & (lon >= lon_min) & (lon <= lon_max)
        col_idx = np.where(mask)[0]
        if col_idx.size == 0:
            raise ValueError("No grid cells in selected area")

        if col_idx.size > self.MAX_AREA_CELLS:
            rng = np.random.default_rng(0)
            col_idx = rng.choice(col_idx, self.MAX_AREA_CELLS, replace=False)
            col_idx.sort()

        n_cells = col_idx.size
        weights = np.cos(np.deg2rad(lat[col_idx]))
        total_w = float(weights.sum())

        if not self._multi:
            sel = {col_dim: col_idx}
            if extra_sel:
                sel.update(extra_sel)
            sub = self.ds[varname].isel(sel)
            ts = (sub * weights).sum(dim=col_dim) / weights.sum()
        else:
            var = self.ds[varname]
            chunks = []
            for start, end, fi in self._file_offsets:
                sel = {col_dim: col_idx}
                if extra_sel:
                    sel.update(extra_sel)
                sel_tuple = tuple(sel.get(d, slice(None)) for d in var.dims)
                sub = self._h5_read(fi, varname, sel_tuple)
                avg = (sub * weights).sum(axis=-1) / total_w
                chunks.append(avg)
            values = np.concatenate(chunks, axis=0)
            ts = xr.DataArray(values, dims=[self._time_dim],
                              coords={self._time_dim: self._time_values})

        return ts, n_cells

    def get_global_range(self, varname):
        """Compute robust min/max using percentiles to ignore outliers/fill values."""
        if not self._multi:
            var = self.ds[varname]
            if var.size < 10_000_000:
                arr = var.values.ravel()
            else:
                scan = self.scan_dims(varname)
                if scan:
                    first_dim = scan[0]
                    n = self.dim_size(varname, first_dim)
                    indices = sorted(set([0, n // 2, n - 1]))
                    samples = [var.isel({first_dim: i}).values for i in indices]
                    arr = np.concatenate([s.ravel() for s in samples])
                else:
                    arr = var.values.ravel()
        else:
            # Multi-file: sample from first, middle, and last files
            import h5py
            sample_fis = sorted(set([
                self._file_offsets[0][2],
                self._file_offsets[len(self._file_offsets) // 2][2],
                self._file_offsets[-1][2],
            ]))
            samples = []
            for fi in sample_fis:
                try:
                    with h5py.File(str(self.paths[fi]), "r") as h:
                        data = np.asarray(h[varname][:], dtype=float)
                        # Replace fill values with NaN (h5py doesn't do this automatically)
                        fv = h[varname].attrs.get("_FillValue", None)
                        if fv is not None:
                            data[data == float(fv[0] if hasattr(fv, '__len__') else fv)] = np.nan
                        samples.append(data.ravel())
                except (OSError, KeyError):
                    continue
            arr = np.concatenate(samples) if samples else np.array([0.0])

        finite = arr[np.isfinite(arr)]
        if finite.size == 0:
            return 0.0, 1.0

        vmin = float(np.percentile(finite, 2))
        vmax = float(np.percentile(finite, 98))

        if np.isnan(vmin) or np.isnan(vmax):
            return 0.0, 1.0
        if vmin == vmax:
            return vmin - 1.0, vmax + 1.0
        return vmin, vmax
