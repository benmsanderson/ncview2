# ncview2

A modern NetCDF visual browser — a Python reimplementation of the core
[ncview](http://meteora.ucsd.edu/~pierce/ncview_home_page.html) workflow.

## Features

- **Instant open**: `ncview2 file.nc` shows the first plottable variable immediately
- **Click for timeseries**: click any point on the spatial plot to extract a timeseries
- **Animate**: play/pause/step through time (or any scannable dimension)
- **Modern colormaps**: perceptually uniform (viridis, etc.) + ocean-specific (cmocean)
- **Auto-detect geography**: coastlines and land overlay when lat/lon are detected (cartopy)
- **Cross-platform**: macOS, Linux, Windows via Qt6

## Install

```bash
# Core install
pip install -e .

# With geographic features (coastlines, projections, ocean colormaps)
pip install -e ".[geo]"
```

## Usage

```bash
# Open a file directly
ncview2 file.nc

# Or via python -m
python -m ncview2 file.nc

# No arguments → file dialog
ncview2
```

## Quick test

Generate test data and open it:

```bash
python tests/make_test_data.py
ncview2 test_data.nc
```

## Controls

| Action | How |
|---|---|
| Change variable | Dropdown at top |
| Change timestep | Drag the time slider, or use ⏮ ◀ ▶ ⏭ buttons |
| Animate | Press ▶ (forward) or ◀ (backward); ⏸ to pause |
| Extract timeseries | Click anywhere on the spatial plot |
| Change colormap | Dropdown in the control panel |
| Change animation speed | Spin box (ms between frames) |
| Open another file | "Open..." button |

## Dependencies

| Package | Required | Purpose |
|---|---|---|
| xarray | ✅ | NetCDF reading, CF conventions, lazy slicing |
| netCDF4 | ✅ | NetCDF4/HDF5 backend for xarray |
| numpy | ✅ | Array operations |
| matplotlib | ✅ | Spatial plots, timeseries, colorbars |
| PySide6 | ✅ | Qt6 GUI framework |
| cartopy | optional | Map projections, coastlines |
| cmocean | optional | Ocean-specific colormaps |

## Architecture

```
ncview2/
├── app.py               # CLI entry point, QApplication setup
├── main_window.py       # Main window — orchestrates all components
├── data_model.py        # xarray-based data loading and slicing
├── spatial_canvas.py    # Matplotlib canvas for 2D spatial plots
├── timeseries_canvas.py # Matplotlib canvas for 1D timeseries
├── controls.py          # Animation buttons, dimension sliders, options
└── colormaps.py         # Colormap registry and auto-selection
```

## License

MIT
