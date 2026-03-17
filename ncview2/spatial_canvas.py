"""Matplotlib canvas for 2D spatial plots, embedded in Qt."""

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle
from matplotlib.tri import Triangulation
from PySide6.QtCore import Signal
from scipy.spatial import cKDTree

try:
    import cartopy.crs as ccrs
    import cartopy.feature as cfeature

    HAS_CARTOPY = True
except ImportError:
    HAS_CARTOPY = False


class SpatialCanvas(FigureCanvasQTAgg):
    """Canvas displaying a 2D field with optional coastlines and colorbar."""

    # Emitted when the user clicks on the plot: (y_index, x_index)
    #   For unstructured grids x_index is the column index, y_index is -1.
    point_clicked = Signal(int, int)
    # Emitted when user Shift-drags a rectangle: (lon_min, lon_max, lat_min, lat_max)
    area_selected = Signal(float, float, float, float)

    def __init__(self, parent=None):
        self.fig = Figure(constrained_layout=True)
        super().__init__(self.fig)
        self.ax = None
        self.mesh = None
        self.cbar = None
        self.marker = None
        self._x_coords = None
        self._x_coords_orig = None
        self._y_coords = None
        self._use_geo = False
        self._cmap = "viridis"
        self._vmin = None
        self._vmax = None
        self._lon_sort_idx = None  # reorder index for non-monotonic longitudes
        self._lon_unsort_idx = None  # inverse mapping for click → original index
        # Unstructured grid state
        self._unstructured = False
        self._tri = None
        self._col_lons = None
        self._col_lats = None
        self._kdtree = None
        # Rectangle drag state
        self._drag_origin = None
        self._drag_rect = None
        self._area_rect = None  # persistent rectangle showing selection
        self.mpl_connect("button_press_event", self._on_press)
        self.mpl_connect("button_release_event", self._on_release)
        self.mpl_connect("motion_notify_event", self._on_motion)

    # ── Regular grid setup ───────────────────────────────────────

    def setup(self, da, cmap=None, vmin=None, vmax=None, geo=False):
        """Full plot setup for a new variable on a regular grid."""
        self.fig.clear()
        self._unstructured = False
        self._tri = None
        self._col_lons = None
        self._col_lats = None
        self._kdtree = None
        self._lon_sort_idx = None
        self._lon_unsort_idx = None
        self._use_geo = geo and HAS_CARTOPY
        if cmap:
            self._cmap = cmap

        if self._use_geo:
            self.ax = self.fig.add_subplot(111, projection=ccrs.PlateCarree())
            self.ax.coastlines(linewidth=0.5, color="0.3")
            self.ax.add_feature(cfeature.LAND, facecolor="0.92", zorder=0)
        else:
            self.ax = self.fig.add_subplot(111)

        y_dim, x_dim = da.dims[-2], da.dims[-1]
        self._x_coords = (
            da.coords[x_dim].values if x_dim in da.coords else np.arange(da.sizes[x_dim])
        )
        self._x_coords_orig = self._x_coords.copy()
        self._y_coords = (
            da.coords[y_dim].values if y_dim in da.coords else np.arange(da.sizes[y_dim])
        )

        # Ensure longitudes are monotonically increasing for pcolormesh
        if not np.all(np.diff(self._x_coords) > 0):
            self._lon_sort_idx = np.argsort(self._x_coords)
            self._lon_unsort_idx = np.argsort(self._lon_sort_idx)
            self._x_coords = self._x_coords[self._lon_sort_idx]
        else:
            self._lon_sort_idx = None
            self._lon_unsort_idx = None

        data = np.asarray(da.values, dtype=float)
        if self._lon_sort_idx is not None:
            data = data[..., self._lon_sort_idx]
        masked_data = np.ma.masked_invalid(data)
        if vmin is None:
            vmin = float(np.nanmin(data))
        if vmax is None:
            vmax = float(np.nanmax(data))
        self._vmin, self._vmax = vmin, vmax

        kw = dict(cmap=self._cmap, vmin=vmin, vmax=vmax, shading="auto")
        if self._use_geo:
            kw["transform"] = ccrs.PlateCarree()

        self.mesh = self.ax.pcolormesh(self._x_coords, self._y_coords, masked_data, **kw)
        self.cbar = self.fig.colorbar(self.mesh, ax=self.ax, shrink=0.85, pad=0.02)

        units = da.attrs.get("units", "")
        long_name = da.attrs.get("long_name", da.name or "")
        if units:
            self.cbar.set_label(units)
        self.ax.set_title(long_name, fontsize=10)
        if not self._use_geo:
            self.ax.set_xlabel(x_dim)
            self.ax.set_ylabel(y_dim)

        self.marker = None
        self.draw()

    # ── Unstructured grid setup ──────────────────────────────────

    def setup_unstructured(self, data_1d, lon, lat, cmap=None, vmin=None, vmax=None,
                           title="", units=""):
        """Full plot setup for an unstructured (column-indexed) grid using tripcolor."""
        self.fig.clear()
        self._unstructured = True
        self._x_coords = None
        self._y_coords = None
        self._use_geo = HAS_CARTOPY
        if cmap:
            self._cmap = cmap

        self._col_lons = np.asarray(lon, dtype=float)
        self._col_lats = np.asarray(lat, dtype=float)

        # Normalize lon to -180..180 so triangulation wraps at the dateline
        # instead of at the prime meridian, matching cartopy PlateCarree output.
        self._col_lons = (self._col_lons + 180.0) % 360.0 - 180.0

        # Build triangulation, masking dateline-crossing triangles
        self._tri = self._build_triangulation(self._col_lons, self._col_lats)

        # KD-tree for nearest-point click lookup (in -180..180 lon/lat space)
        self._kdtree = cKDTree(np.column_stack([self._col_lons, self._col_lats]))

        data = np.asarray(data_1d, dtype=float)
        if vmin is None:
            vmin = float(np.nanmin(data))
        if vmax is None:
            vmax = float(np.nanmax(data))
        self._vmin, self._vmax = vmin, vmax

        if self._use_geo:
            self.ax = self.fig.add_subplot(111, projection=ccrs.PlateCarree())
            self.ax.set_global()
            self.ax.coastlines(linewidth=0.5, color="0.3")
        else:
            self.ax = self.fig.add_subplot(111)

        kw = dict(cmap=self._cmap, vmin=vmin, vmax=vmax)
        if self._use_geo:
            kw["transform"] = ccrs.PlateCarree()

        self.mesh = self.ax.tripcolor(self._tri, data, **kw)
        self.cbar = self.fig.colorbar(self.mesh, ax=self.ax, shrink=0.85, pad=0.02)

        if units:
            self.cbar.set_label(units)
        self.ax.set_title(title, fontsize=10)

        self.marker = None
        self.draw()

    @staticmethod
    def _build_triangulation(lon, lat):
        """Delaunay triangulation with dateline-crossing triangles masked."""
        tri = Triangulation(lon, lat)
        # Mask triangles whose vertices span > 180° in longitude
        triangles = tri.triangles
        lon_tri = lon[triangles]
        max_span = np.max(lon_tri, axis=1) - np.min(lon_tri, axis=1)
        tri.set_mask(max_span > 180.0)
        return tri

    # ── Data update (animation fast path) ────────────────────────

    def update_data(self, da_or_1d, title_suffix=""):
        """Update the plot data without rebuilding axes."""
        if self.mesh is None:
            return

        if self._unstructured:
            data = np.asarray(da_or_1d, dtype=float)
        else:
            data = np.asarray(da_or_1d.values, dtype=float)
            if self._lon_sort_idx is not None:
                data = data[..., self._lon_sort_idx]
        self.mesh.set_array(np.ma.masked_invalid(data).ravel())

        if self._vmin is not None:
            self.mesh.set_clim(self._vmin, self._vmax)

        if self._unstructured:
            title = title_suffix or ""
        else:
            long_name = da_or_1d.attrs.get("long_name", da_or_1d.name or "")
            title = f"{long_name}  {title_suffix}".strip() if title_suffix else long_name
        self.ax.set_title(title, fontsize=10)
        self.draw()

    # ── Color controls ───────────────────────────────────────────

    def set_clim(self, vmin, vmax):
        self._vmin, self._vmax = vmin, vmax
        if self.mesh:
            self.mesh.set_clim(vmin, vmax)
            self.draw()

    def set_colormap(self, cmap):
        self._cmap = cmap
        if self.mesh:
            self.mesh.set_cmap(cmap)
            self.draw()

    # ── Marker / click ───────────────────────────────────────────

    def mark_point(self, yi, xi):
        """Draw a crosshair on the selected grid point."""
        if self.marker:
            self.marker.remove()
            self.marker = None
        self.clear_area_rect()

        if self._unstructured:
            col = xi  # for unstructured, xi is the column index
            if self._col_lons is None:
                return
            x = float(self._col_lons[col])
            y = float(self._col_lats[col])
        else:
            if self._x_coords_orig is None or self._y_coords is None:
                return
            x = float(self._x_coords_orig[xi])
            y = float(self._y_coords[yi])

        kw = {}
        if self._use_geo:
            kw["transform"] = ccrs.PlateCarree()
        (self.marker,) = self.ax.plot(
            x, y, "kx", markersize=10, markeredgewidth=2, zorder=10, **kw
        )
        self.draw()

    def mark_area(self, lon_min, lon_max, lat_min, lat_max):
        """Draw a persistent rectangle showing the area selection."""
        self.clear_area_rect()
        if self.marker:
            self.marker.remove()
            self.marker = None
        kw = {}
        if self._use_geo:
            kw["transform"] = ccrs.PlateCarree()
        self._area_rect = Rectangle(
            (lon_min, lat_min), lon_max - lon_min, lat_max - lat_min,
            linewidth=2, edgecolor="red", facecolor="red", alpha=0.15, zorder=9, **kw,
        )
        self.ax.add_patch(self._area_rect)
        self.draw()

    def clear_area_rect(self):
        """Remove the persistent area rectangle."""
        if self._area_rect is not None:
            self._area_rect.remove()
            self._area_rect = None

    # ── Mouse events: click vs drag ─────────────────────────────

    def _on_press(self, event):
        """Record press location; drag vs click is decided on release."""
        if event.inaxes != self.ax or event.button != 1:
            return
        if event.xdata is None or event.ydata is None:
            return
        self._drag_origin = (event.xdata, event.ydata)

    def _on_motion(self, event):
        """Draw rubber-band rectangle while dragging."""
        if self._drag_origin is None or event.xdata is None:
            return
        if event.inaxes != self.ax:
            return

        x0, y0 = self._drag_origin
        x1, y1 = event.xdata, event.ydata
        # Update rubber-band rectangle
        if self._drag_rect is not None:
            self._drag_rect.remove()
        kw = {}
        if self._use_geo:
            kw["transform"] = ccrs.PlateCarree()
        self._drag_rect = Rectangle(
            (min(x0, x1), min(y0, y1)), abs(x1 - x0), abs(y1 - y0),
            linewidth=1.5, edgecolor="red", facecolor="red", alpha=0.1,
            linestyle="--", zorder=10, **kw,
        )
        self.ax.add_patch(self._drag_rect)
        self.draw_idle()

    def _on_release(self, event):
        """Finish rectangle drag (area avg) or handle plain click (point)."""
        if event.inaxes != self.ax or event.button != 1:
            self._drag_origin = None
            return
        if event.xdata is None or event.ydata is None:
            self._drag_origin = None
            return

        # Clean up rubber-band
        if self._drag_rect is not None:
            self._drag_rect.remove()
            self._drag_rect = None
            self.draw_idle()

        if self._drag_origin is not None:
            x0, y0 = self._drag_origin
            x1, y1 = event.xdata, event.ydata
            self._drag_origin = None
            # Drag: emit area if rectangle is non-trivial
            if abs(x1 - x0) > 0.5 or abs(y1 - y0) > 0.5:
                lon_min, lon_max = sorted([x0, x1])
                lat_min, lat_max = sorted([y0, y1])
                self.area_selected.emit(lon_min, lon_max, lat_min, lat_max)
                return

        # Click (no drag or tiny drag) → point selection
        self._drag_origin = None
        xd, yd = event.xdata, event.ydata
        if self._unstructured:
            if self._kdtree is None:
                return
            _, col_idx = self._kdtree.query([xd, yd])
            self.point_clicked.emit(-1, int(col_idx))
        else:
            if self._x_coords is None or self._y_coords is None:
                return
            xi = int(np.argmin(np.abs(self._x_coords - xd)))
            yi = int(np.argmin(np.abs(self._y_coords - yd)))
            # Map sorted lon index back to original dataset index
            if self._lon_unsort_idx is not None:
                xi = int(self._lon_unsort_idx[xi])
            self.point_clicked.emit(yi, xi)
