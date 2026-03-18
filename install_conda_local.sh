#!/bin/bash
# Local conda installation script for ncview2

set -e  # Exit on error

echo "==> Creating conda environment 'ncview2'..."
conda create -y -n ncview2 python=3.11 pyside6 cartopy scipy xarray \
    netcdf4 matplotlib cftime cmocean nc-time-axis h5py

echo ""
echo "==> Activating environment..."
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate ncview2

echo ""
echo "==> Installing ncview2 in editable mode..."
pip install -e .

echo ""
read -p "Create wrapper script for easy access? (run from anywhere) [Y/n] " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Nn]$ ]]; then
    ncview2 --install
fi

echo ""
echo "============================================"
echo "Installation complete!"
echo ""
echo "To use ncview2:"
echo "  1. Activate environment: conda activate ncview2"
echo "  2. Run: ncview2 <file.nc>"
echo ""
if [[ ! $REPLY =~ ^[Nn]$ ]]; then
    echo "Wrapper installed - add ~/.local/bin to PATH to run from anywhere."
else
    echo "To create wrapper later: activate environment and run 'ncview2 --install'"
fi
echo "============================================"
