# ncview2

A modern NetCDF visual browser — a Python reimplementation of the core
[ncview](https://cirrus.ucsd.edu/ncview/) workflow.

## Features

- **Instant open**: `ncview2 file.nc` shows the first plottable variable immediately
- **Click for timeseries**: click any point on the spatial plot to extract a timeseries
- **Area Average**: click and drag to calculate an area average for the line plot
- **Vertical profiles**: 3D variables with a vertical cooordinate will display an additional vertical profile
- **Support non-uniform grids**: Delauney traingulation map plot
- **Multi-file wildcard support**: fast loading of multiple history files using h5py
- **Animate**: play/pause/step through time (or any scannable dimension)
- **Multiple colormaps**: large library of Python colormaps
- **Auto-detect geography**: coastlines and land overlay when lat/lon are detected (cartopy)
- **Cross-platform**: macOS, Linux, Windows via Qt6

## Install

### Option A: Conda (recommended)

Conda handles the Qt6, cartopy, and HDF5 dependencies cleanly on all
platforms. This is the most reliable route, especially on Linux/HPC.

```bash
# Create and activate the environment
conda create -n ncview2 python=3.11 pyside6 cartopy scipy xarray \
    netcdf4 matplotlib cftime cmocean nc-time-axis h5py
conda activate ncview2

# Install ncview2 itself
pip install /path/to/ncview2
```

### Option B: pip only

pip can install everything, but cartopy requires system libraries
(GEOS, PROJ) that pip cannot provide. On macOS you can get these via
Homebrew (`brew install geos proj`); on Linux via your package manager.
Without them, `pip install cartopy` will fail and you'll run without
coastlines and map projections.

```bash
# Core install (no coastlines/projections)
pip install -e .

# With geographic features (requires GEOS + PROJ on your system)
pip install -e ".[geo]"
```

### Install the wrapper script to use anywhere (optional)

This lets you run `ncview2` from any terminal without activating the
environment first — just like the original ncview:

```bash
# Run this once, while the environment is active:
ncview2 --install
```

This writes a small shell wrapper to `~/.local/bin/ncview2` that calls
the environment's Python directly. Make sure `~/.local/bin` is in your
`PATH` (the command will tell you if it isn't).

After this, `ncview2 file.nc` works from anywhere — no activation needed.

## Usage

```bash
# Open a file directly
ncview2 file.nc

# Or via python -m
python -m ncview2 file.nc

# Open multiple sequential files (concatenated along time)
ncview2 run.cam.h0.*.nc

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
| xarray | yes | NetCDF reading, CF conventions, lazy slicing |
| netCDF4 | yes | NetCDF4/HDF5 backend for xarray |
| numpy | yes | Array operations |
| matplotlib | yes | Spatial plots, timeseries, colorbars |
| PySide6 | yes | Qt6 GUI framework |
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

## How multi-file loading works

When you pass multiple files (e.g. `ncview2 run.cam.h0.084*.nc`), ncview2
avoids the slow `xr.open_mfdataset` path. Instead:

1. **First file only** is opened with xarray to get variable metadata,
   coordinates, attributes, and grid structure (~1 s).
2. **All files** are scanned with h5py to read just the time coordinate
   and build a global time index — mapping each global timestep to a
   (file, local index) pair (~0.5 s for 60 files).
3. **Data reads** go through h5py directly to the correct file, so
   fetching a spatial slice or a point timeseries across 60 files takes
   well under a second.

Corrupt or truncated files are silently skipped during the scan.
Fill values (`_FillValue`) are converted to NaN for color-range
calculations so outliers don't blow out the color scale.


