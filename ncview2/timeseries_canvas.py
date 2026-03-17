"""Matplotlib canvas for 1D timeseries line plots, embedded in Qt."""

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from matplotlib.widgets import SpanSelector
from matplotlib.dates import AutoDateLocator, ConciseDateFormatter
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QFileDialog
from PySide6.QtCore import Signal

try:
    import nc_time_axis  # noqa: F401 — registers cftime support with matplotlib
except ImportError:
    pass


class TimeseriesCanvas(QWidget):
    """Widget containing a timeseries plot with x-span zoom and click-to-jump."""

    # Emitted when user clicks on the timeseries: (nearest_time_index,)
    time_clicked = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.fig = Figure(constrained_layout=True)
        self.canvas = FigureCanvasQTAgg(self.fig)

        # Simple button bar
        self._btn_bar = QWidget()
        self._btn_bar.setVisible(False)
        btn_layout = QHBoxLayout(self._btn_bar)
        btn_layout.setContentsMargins(4, 2, 4, 2)
        btn_layout.setSpacing(4)
        self._home_btn = QPushButton("Reset zoom")
        self._home_btn.clicked.connect(self._reset_zoom)
        self._save_btn = QPushButton("Save…")
        self._save_btn.clicked.connect(self._save_figure)
        btn_layout.addWidget(self._home_btn)
        btn_layout.addWidget(self._save_btn)
        btn_layout.addStretch()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._btn_bar)
        layout.addWidget(self.canvas, stretch=1)

        self.ax = self.fig.add_subplot(111)
        self.line = None
        self.time_marker = None
        self._has_data = False
        self._n_points = 0
        self._y_data = None
        self._x_numeric = None
        self._full_xlim = None
        self._span = None
        self.ax.set_visible(False)
        self.canvas.draw()

        self.canvas.mpl_connect("button_press_event", self._on_click)

    # ── Span zoom ────────────────────────────────────────────────

    def _init_span_selector(self):
        """Create the SpanSelector for x-range zooming with shaded preview."""
        if self._span is not None:
            self._span.disconnect_events()
        self._span = SpanSelector(
            self.ax,
            self._on_span_selected,
            "horizontal",
            useblit=True,
            props=dict(facecolor="#1f77b4", alpha=0.2),
            interactive=False,
            button=[1],
        )

    def _on_span_selected(self, xmin, xmax):
        """Zoom to the selected x-range and auto-fit y."""
        if abs(xmax - xmin) < 1e-10:
            return  # click, not drag
        self.ax.set_xlim(xmin, xmax)
        self._fit_ylim()
        self.canvas.draw_idle()

    def _fit_ylim(self):
        """Set y-limits to match the data visible in the current x-range."""
        if self._y_data is None or self._x_numeric is None:
            return
        xlo, xhi = self.ax.get_xlim()
        mask = (self._x_numeric >= xlo) & (self._x_numeric <= xhi)
        if not mask.any():
            return
        visible_y = self._y_data[mask]
        finite = visible_y[np.isfinite(visible_y)]
        if finite.size == 0:
            return
        ymin, ymax = float(finite.min()), float(finite.max())
        margin = (ymax - ymin) * 0.05 if ymax != ymin else abs(ymin) * 0.1 or 1.0
        self.ax.set_ylim(ymin - margin, ymax + margin)

    def _reset_zoom(self):
        """Reset to the full data range."""
        if self._full_xlim is not None:
            self.ax.set_xlim(self._full_xlim)
            self._fit_ylim()
            self.canvas.draw_idle()

    def _save_figure(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save timeseries plot", "", "PNG (*.png);;PDF (*.pdf);;SVG (*.svg)"
        )
        if path:
            self.fig.savefig(path, dpi=150)

    # ── Plot / update ────────────────────────────────────────────

    def plot(self, da, point_label=""):
        """Plot a 1D DataArray as a timeseries."""
        self.ax.set_visible(True)
        self.ax.clear()
        self._btn_bar.setVisible(True)

        dim = da.dims[0]
        if dim in da.coords:
            x = da.coords[dim].values
        else:
            x = np.arange(da.sizes[dim])

        self._n_points = len(x)
        y = da.values.astype(float)
        self._y_data = y
        (self.line,) = self.ax.plot(x, y, "-", linewidth=1, color="#1f77b4")

        # Nice datetime formatting
        x_arr = np.asarray(x)
        if x_arr.size > 0 and np.issubdtype(x_arr.dtype, np.datetime64):
            loc = AutoDateLocator()
            self.ax.xaxis.set_major_locator(loc)
            self.ax.xaxis.set_major_formatter(ConciseDateFormatter(loc))

        # Rotate tick labels if they're long (dates, etc.)
        self.fig.autofmt_xdate(rotation=30, ha="right")

        self.ax.set_xlabel(dim)
        units = da.attrs.get("units", "")
        name = da.attrs.get("long_name", da.name or "")
        ylabel = f"{name} [{units}]" if units else name
        self.ax.set_ylabel(ylabel, fontsize=9)

        if point_label:
            self.ax.set_title(point_label, fontsize=9)

        self.ax.grid(True, alpha=0.3)
        self.time_marker = None
        self._has_data = True

        # Cache numeric x-values for y-rescaling and click lookup
        try:
            self._x_numeric = np.asarray(
                self.ax.convert_xunits(self.line.get_xdata()), dtype=float
            )
        except (TypeError, ValueError):
            self._x_numeric = np.arange(self._n_points, dtype=float)

        # Store full range, fit y, set up span selector
        self._full_xlim = self.ax.get_xlim()
        self._fit_ylim()
        self._init_span_selector()
        self.canvas.draw()

    def mark_time(self, index):
        """Show the current scan position as a vertical line."""
        if not self._has_data or self.line is None:
            return
        x_data = self.line.get_xdata()
        if index < 0 or index >= len(x_data):
            return
        if self.time_marker:
            self.time_marker.remove()
        self.time_marker = self.ax.axvline(x_data[index], color="red", linewidth=1, alpha=0.7)
        self.canvas.draw()

    def clear_plot(self):
        self.ax.clear()
        self.ax.set_visible(False)
        self._btn_bar.setVisible(False)
        self.line = None
        self.time_marker = None
        self._has_data = False
        self._n_points = 0
        self._y_data = None
        self._x_numeric = None
        self._full_xlim = None
        if self._span is not None:
            self._span.disconnect_events()
            self._span = None
        self.canvas.draw()

    # ── Click → jump to timestep ─────────────────────────────────

    def _on_click(self, event):
        """Single click on timeseries → jump the spatial view to that timestep.

        Drag events are handled by SpanSelector; only non-drag clicks arrive here.
        """
        if not self._has_data or self.line is None:
            return
        if event.inaxes != self.ax or event.button != 1:
            return
        x_data = self.line.get_xdata()
        if len(x_data) == 0:
            return
        xd = event.xdata
        try:
            x_num = self.ax.convert_xunits(x_data)
            idx = int(np.argmin(np.abs(np.asarray(x_num, dtype=float) - float(xd))))
        except (TypeError, ValueError):
            xlim = self.ax.get_xlim()
            frac = (xd - xlim[0]) / (xlim[1] - xlim[0]) if xlim[1] != xlim[0] else 0
            idx = int(round(frac * (self._n_points - 1)))
            idx = max(0, min(idx, self._n_points - 1))
        self.time_clicked.emit(idx)
