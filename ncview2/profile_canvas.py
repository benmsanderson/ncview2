"""Matplotlib canvas for vertical profile plots, embedded in Qt."""

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PySide6.QtWidgets import QWidget, QVBoxLayout


class ProfileCanvas(QWidget):
    """Widget showing a vertical cross-section (e.g. depth vs temperature)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.fig = Figure(constrained_layout=True)
        self.canvas = FigureCanvasQTAgg(self.fig)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.canvas, stretch=1)

        self.ax = self.fig.add_subplot(111)
        self.line = None
        self._has_data = False
        self.ax.set_visible(False)
        self.canvas.draw()

    def plot(self, values, levels, level_name="", var_name="", var_units="",
             level_units="", point_label=""):
        """Plot a vertical profile.

        Parameters
        ----------
        values : 1D array — variable values along the vertical dim.
        levels : 1D array — coordinate values for the vertical dim.
        level_name : str — name of the vertical dimension (e.g. 'levgrnd').
        var_name : str — variable long_name or short name.
        var_units : str — variable units.
        level_units : str — level coordinate units.
        point_label : str — label describing the selected location.
        """
        self.ax.set_visible(True)
        self.ax.clear()

        y = np.asarray(levels, dtype=float)
        x = np.asarray(values, dtype=float)

        (self.line,) = self.ax.plot(x, y, "o-", markersize=3, linewidth=1, color="#1f77b4")

        xlabel = f"{var_name} [{var_units}]" if var_units else var_name
        ylabel = f"{level_name} [{level_units}]" if level_units else level_name
        self.ax.set_xlabel(xlabel, fontsize=9)
        self.ax.set_ylabel(ylabel, fontsize=9)

        if point_label:
            self.ax.set_title(point_label, fontsize=8)

        # Invert y-axis if levels are increasing (e.g. depth in meters)
        if len(y) > 1 and y[0] < y[-1]:
            self.ax.invert_yaxis()

        self.ax.grid(True, alpha=0.3)
        self._has_data = True
        self.canvas.draw()

    def update_values(self, values):
        """Update profile values without rebuilding the plot."""
        if not self._has_data or self.line is None:
            return
        self.line.set_xdata(np.asarray(values, dtype=float))
        # Refit x-limits
        finite = values[np.isfinite(values)]
        if finite.size > 0:
            xmin, xmax = float(finite.min()), float(finite.max())
            margin = (xmax - xmin) * 0.05 if xmax != xmin else abs(xmin) * 0.1 or 1.0
            self.ax.set_xlim(xmin - margin, xmax + margin)
        self.canvas.draw()

    def clear_plot(self):
        self.ax.clear()
        self.ax.set_visible(False)
        self.line = None
        self._has_data = False
        self.canvas.draw()
