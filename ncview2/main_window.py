"""Main application window — orchestrates data, plots, and controls."""

import numpy as np
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QComboBox,
    QLabel,
    QSplitter,
    QStatusBar,
    QFileDialog,
    QPushButton,
    QMessageBox,
)
from PySide6.QtCore import Qt, QTimer

from ncview2.data_model import DataModel
from ncview2.spatial_canvas import SpatialCanvas
from ncview2.timeseries_canvas import TimeseriesCanvas
from ncview2.controls import ControlPanel
from ncview2.colormaps import all_colormaps, default_colormap


def _format_coord_labels(vals):
    """Convert coordinate values to concise display strings."""
    if vals is None or len(vals) == 0:
        return None
    arr = np.asarray(vals)
    if np.issubdtype(arr.dtype, np.datetime64):
        return [str(v)[:19].replace("T", " ") for v in arr]
    if np.issubdtype(arr.dtype, np.floating):
        return [f"{v:.4g}" for v in arr]
    return [str(v) for v in arr]


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ncview2")
        self.resize(1000, 800)

        self.model: DataModel | None = None
        self.current_var: str | None = None
        self.scan_dims: list[str] = []
        self.spatial_dims: tuple = ()
        self._clicked_point: tuple[int, int] | None = None
        self._area_bbox: tuple[float, float, float, float] | None = None
        self._vmin: float | None = None
        self._vmax: float | None = None
        self._is_unstructured: bool = False
        self._playing = False
        self._play_direction = 1
        self._playing = False
        self._play_direction = 1

        self._build_ui()
        self._setup_timer()
        self._connect_signals()

    # ── UI construction ──────────────────────────────────────────

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(4, 4, 4, 4)

        # Top bar: variable selector + open button + info
        top = QHBoxLayout()
        top.addWidget(QLabel("Variable:"))
        self.var_combo = QComboBox()
        self.var_combo.setMinimumWidth(200)
        top.addWidget(self.var_combo)
        self.open_btn = QPushButton("Open…")
        top.addWidget(self.open_btn)
        top.addStretch()
        self.info_label = QLabel()
        top.addWidget(self.info_label)
        root.addLayout(top)

        # Vertical splitter: spatial plot on top, timeseries below
        self.splitter = QSplitter(Qt.Vertical)
        self.spatial = SpatialCanvas()
        self.timeseries = TimeseriesCanvas()
        self.splitter.addWidget(self.spatial)
        self.splitter.addWidget(self.timeseries)
        self.splitter.setSizes([500, 300])
        root.addWidget(self.splitter, stretch=1)

        # Control panel at bottom
        self.controls = ControlPanel()
        root.addWidget(self.controls)

        self.status = QStatusBar()
        self.setStatusBar(self.status)

    def _setup_timer(self):
        self.timer = QTimer()
        self.timer.timeout.connect(self._animation_tick)

    def _connect_signals(self):
        self.var_combo.currentTextChanged.connect(self._on_variable_changed)
        self.open_btn.clicked.connect(self._on_open_clicked)
        self.spatial.point_clicked.connect(self._on_point_clicked)
        self.spatial.area_selected.connect(self._on_area_selected)
        self.timeseries.time_clicked.connect(self._on_timeseries_clicked)
        self.controls.dim_index_changed.connect(self._on_dim_changed)
        self.controls.colormap_changed.connect(self._on_colormap_changed)

        anim = self.controls.anim
        anim.play_forward.connect(lambda: self._start_playing(1))
        anim.play_backward.connect(lambda: self._start_playing(-1))
        anim.pause.connect(self._stop_playing)
        anim.step_forward.connect(lambda: self._step(1))
        anim.step_backward.connect(lambda: self._step(-1))
        anim.go_to_start.connect(self._go_to_start)
        anim.go_to_end.connect(self._go_to_end)
        anim.speed_changed.connect(self._on_speed_changed)

    # ── File operations ──────────────────────────────────────────

    def _on_open_clicked(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open NetCDF",
            "",
            "NetCDF Files (*.nc *.nc4 *.cdf *.hdf5 *.h5);;All Files (*)",
        )
        if path:
            self.open_file(path)

    def open_file(self, path):
        try:
            new_model = DataModel(path)
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Failed to open file:\n{exc}")
            return

        if self.model:
            self.model.close()
        self.model = new_model
        self.setWindowTitle(f"ncview2 — {self.model.filename}")

        variables = self.model.plottable_variables
        self.var_combo.blockSignals(True)
        self.var_combo.clear()
        self.var_combo.addItems(variables)
        self.var_combo.blockSignals(False)

        self.controls.setup_colormaps(all_colormaps(), "viridis")

        if variables:
            self.var_combo.setCurrentIndex(0)
            self._on_variable_changed(variables[0])
        else:
            self.status.showMessage("No plottable variables found in this file.")

        self.status.showMessage(
            f"Opened {path} — {len(variables)} plottable variable(s)", 5000
        )

    # ── Variable selection ───────────────────────────────────────

    def _on_variable_changed(self, varname):
        if not varname or not self.model:
            return

        self.current_var = varname
        self._stop_playing()
        self._clicked_point = None
        self._area_bbox = None
        self.timeseries.clear_plot()

        self._is_unstructured = self.model.is_unstructured(varname)

        # Identify dimensions
        self.spatial_dims = self.model.spatial_dims(varname)
        self.scan_dims = self.model.scan_dims(varname)
        roles = self.model.dim_roles(varname)

        # Build slider metadata
        dim_sizes = {d: self.model.dim_size(varname, d) for d in self.scan_dims}
        dim_labels = {}
        for d in self.scan_dims:
            vals = self.model.dim_coord_values(d)
            dim_labels[d] = _format_coord_labels(vals)

        self.controls.setup_dims(self.scan_dims, dim_sizes, dim_labels)

        # Compute global color range
        self._vmin, self._vmax = self.model.get_global_range(varname)

        # Auto-select colormap
        cmap = default_colormap(self._vmin, self._vmax)
        idx = self.controls.cmap_combo.findText(cmap)
        if idx >= 0:
            self.controls.cmap_combo.blockSignals(True)
            self.controls.cmap_combo.setCurrentIndex(idx)
            self.controls.cmap_combo.blockSignals(False)

        # Draw initial frame
        sel = {d: 0 for d in self.scan_dims}
        da = self.model.get_slice(varname, sel)

        var_meta = self.model.ds[varname]
        units = var_meta.attrs.get("units", "")
        long_name = var_meta.attrs.get("long_name", varname)

        if self._is_unstructured:
            lat, lon = self.model.get_unstructured_latlon(varname)
            self.spatial.setup_unstructured(
                da.values, lon, lat,
                cmap=cmap, vmin=self._vmin, vmax=self._vmax,
                title=long_name, units=units,
            )
        else:
            y_dim, x_dim = self.spatial_dims
            is_geo = roles.get(y_dim) == "lat" and roles.get(x_dim) == "lon"
            self.spatial.setup(da, cmap=cmap, vmin=self._vmin, vmax=self._vmax, geo=is_geo)

        # Info label
        shape = ", ".join(f"{d}={s}" for d, s in zip(var_meta.dims, var_meta.shape))
        self.info_label.setText(f"{varname} ({shape})")

    # ── Dimension slider changes ─────────────────────────────────

    def _on_dim_changed(self, _dim_name, _index):
        self._update_spatial()
        if self._clicked_point or self._area_bbox:
            self._update_timeseries_marker()

    def _update_spatial(self):
        if not self.current_var or not self.model:
            return
        sel = self.controls.get_dim_indices()
        da = self.model.get_slice(self.current_var, sel)

        # Build title suffix showing current scan position
        parts = []
        for dim in self.scan_dims:
            idx = sel.get(dim, 0)
            vals = self.model.dim_coord_values(dim)
            if vals is not None and idx < len(vals):
                v = vals[idx]
                if np.issubdtype(np.asarray([v]).dtype, np.datetime64):
                    parts.append(str(v)[:19].replace("T", " "))
                elif isinstance(v, (float, np.floating)):
                    parts.append(f"{dim}={v:.4g}")
                else:
                    parts.append(f"{dim}={v}")
            else:
                parts.append(f"{dim}=[{idx}]")
        suffix = "   ".join(parts)

        if self._is_unstructured:
            var_meta = self.model.ds[self.current_var]
            long_name = var_meta.attrs.get("long_name", self.current_var)
            title = f"{long_name}  {suffix}".strip() if suffix else long_name
            self.spatial.update_data(da.values, title_suffix=title)
        else:
            self.spatial.update_data(da, title_suffix=suffix)

    # ── Click → timeseries ───────────────────────────────────────

    def _on_point_clicked(self, yi, xi):
        if not self.current_var or not self.model:
            return
        self._area_bbox = None

        if self._is_unstructured:
            self._on_point_clicked_unstructured(xi)
        else:
            self._on_point_clicked_regular(yi, xi)

    def _on_point_clicked_regular(self, yi, xi):
        y_dim, x_dim = self.spatial_dims

        sel = dict(self.controls.get_dim_indices())
        sel[y_dim] = yi
        sel[x_dim] = xi
        try:
            val = float(self.model.ds[self.current_var].isel(sel).values)
            y_coords = self.model.dim_coord_values(y_dim)
            x_coords = self.model.dim_coord_values(x_dim)
            y_val = f"{y_coords[yi]:.4g}" if y_coords is not None else str(yi)
            x_val = f"{x_coords[xi]:.4g}" if x_coords is not None else str(xi)
            self.status.showMessage(f"{y_dim}={y_val}, {x_dim}={x_val} → {val:.6g}")
        except Exception:
            pass

        self._clicked_point = (yi, xi)
        self.spatial.mark_point(yi, xi)

        if not self.scan_dims:
            return

        spatial_sel = {y_dim: yi, x_dim: xi}
        for dim in self.scan_dims[1:]:
            spatial_sel[dim] = self.controls.get_dim_index(dim)

        try:
            ts = self.model.get_timeseries(self.current_var, spatial_sel)
            y_coords = self.model.dim_coord_values(y_dim)
            x_coords = self.model.dim_coord_values(x_dim)
            y_str = f"{y_coords[yi]:.4g}" if y_coords is not None else str(yi)
            x_str = f"{x_coords[xi]:.4g}" if x_coords is not None else str(xi)
            label = f"{y_dim}={y_str}, {x_dim}={x_str}"
            self.timeseries.plot(ts, point_label=label)
            self._update_timeseries_marker()
        except Exception as exc:
            self.status.showMessage(f"Timeseries error: {exc}", 5000)

    def _on_point_clicked_unstructured(self, col_idx):
        (col_dim,) = self.spatial_dims
        lat, lon = self.model.get_unstructured_latlon(self.current_var)

        sel = dict(self.controls.get_dim_indices())
        sel[col_dim] = col_idx
        try:
            val = float(self.model.ds[self.current_var].isel(sel).values)
            lat_v = f"{lat[col_idx]:.2f}" if lat is not None else "?"
            lon_v = f"{lon[col_idx]:.2f}" if lon is not None else "?"
            self.status.showMessage(f"lat={lat_v}, lon={lon_v} (col {col_idx}) → {val:.6g}")
        except Exception:
            pass

        self._clicked_point = (-1, col_idx)
        self.spatial.mark_point(-1, col_idx)

        if not self.scan_dims:
            return

        spatial_sel = {col_dim: col_idx}
        for dim in self.scan_dims[1:]:
            spatial_sel[dim] = self.controls.get_dim_index(dim)

        try:
            ts = self.model.get_timeseries(self.current_var, spatial_sel)
            lat_s = f"{lat[col_idx]:.2f}" if lat is not None else str(col_idx)
            lon_s = f"{lon[col_idx]:.2f}" if lon is not None else str(col_idx)
            label = f"lat={lat_s}, lon={lon_s}"
            self.timeseries.plot(ts, point_label=label)
            self._update_timeseries_marker()
        except Exception as exc:
            self.status.showMessage(f"Timeseries error: {exc}", 5000)

    def _update_timeseries_marker(self):
        if self.scan_dims:
            idx = self.controls.get_dim_index(self.scan_dims[0])
            self.timeseries.mark_time(idx)

    # ── Area-average timeseries ──────────────────────────────────

    def _on_area_selected(self, lon_min, lon_max, lat_min, lat_max):
        if not self.current_var or not self.model:
            return
        if not self.scan_dims:
            self.status.showMessage("Area average requires a scan dimension (e.g. time)", 5000)
            return

        self._clicked_point = None
        bbox = (lon_min, lon_max, lat_min, lat_max)

        # Extra sel: fix non-time scan dims to current slider position
        extra_sel = {}
        for dim in self.scan_dims[1:]:
            extra_sel[dim] = self.controls.get_dim_index(dim)

        try:
            ts, n_cells = self.model.get_area_average_timeseries(
                self.current_var, bbox, extra_sel=extra_sel or None,
            )
        except ValueError as exc:
            self.status.showMessage(str(exc), 5000)
            return

        self._area_bbox = bbox
        self.spatial.mark_area(lon_min, lon_max, lat_min, lat_max)

        sampled = n_cells >= self.model.MAX_AREA_CELLS
        label = (
            f"Area avg [{lat_min:.1f}\u2013{lat_max:.1f}, {lon_min:.1f}\u2013{lon_max:.1f}]  "
            f"({n_cells} cells{', ~sampled' if sampled else ''})"
        )
        self.timeseries.plot(ts, point_label=label)
        self._update_timeseries_marker()
        self.status.showMessage(label, 5000)

    def _on_timeseries_clicked(self, index):
        """Jump the time slider to the clicked position on the timeseries."""
        if self.scan_dims:
            self.controls.set_dim_index(self.scan_dims[0], index)

    # ── Animation ────────────────────────────────────────────────

    def _start_playing(self, direction):
        if not self.scan_dims:
            return
        self._play_direction = direction
        self._playing = True
        self.timer.start(self.controls.anim.speed_spin.value())

    def _stop_playing(self):
        self._playing = False
        self.timer.stop()

    def _step(self, direction):
        if not self.scan_dims:
            return
        dim = self.scan_dims[0]
        slider = self.controls.dim_sliders.get(dim)
        if slider:
            new = slider.value() + direction
            if 0 <= new <= slider.maximum():
                slider.set_value(new)

    def _go_to_start(self):
        if self.scan_dims:
            self.controls.set_dim_index(self.scan_dims[0], 0)

    def _go_to_end(self):
        if self.scan_dims:
            dim = self.scan_dims[0]
            slider = self.controls.dim_sliders.get(dim)
            if slider:
                self.controls.set_dim_index(dim, slider.maximum())

    def _animation_tick(self):
        if not self.scan_dims:
            self._stop_playing()
            return
        dim = self.scan_dims[0]
        slider = self.controls.dim_sliders.get(dim)
        if not slider:
            self._stop_playing()
            return
        new = slider.value() + self._play_direction
        if new > slider.maximum():
            new = 0
        elif new < 0:
            new = slider.maximum()
        slider.set_value(new)

    def _on_speed_changed(self, ms):
        if self._playing:
            self.timer.setInterval(ms)

    # ── Colormap ─────────────────────────────────────────────────

    def _on_colormap_changed(self, cmap):
        self.spatial.set_colormap(cmap)

    # ── Cleanup ──────────────────────────────────────────────────

    def closeEvent(self, event):
        self._stop_playing()
        if self.model:
            self.model.close()
        super().closeEvent(event)
