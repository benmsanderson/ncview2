#!/bin/bash
# Local pip installation script for ncview2
# Requires: Python 3.10+, GEOS, PROJ libraries on your system

set -e  # Exit on error

echo "==> Checking for Python 3.10+..."
python_version=$(python3 --version 2>&1 | awk '{print $2}' | cut -d. -f1,2)
if ! python3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" 2>/dev/null; then
    echo "ERROR: Python 3.10 or higher required"
    exit 1
fi
echo "    Found Python $python_version"

echo ""
echo "==> Creating virtual environment..."
python3 -m venv venv
source venv/bin/activate

echo ""
echo "==> Upgrading pip..."
pip install --upgrade pip

echo ""
echo "==> Installing ncview2 with all dependencies..."
pip install -e ".[geo]"

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
echo "  1. Activate environment: source venv/bin/activate"
echo "  2. Run: ncview2 <file.nc>"
echo ""
if [[ ! $REPLY =~ ^[Nn]$ ]]; then
    echo "Wrapper installed - add ~/.local/bin to PATH to run from anywhere."
else
    echo "To create wrapper later: activate venv and run 'ncview2 --install'"
fi
echo ""
echo "Note: If cartopy failed to install, you may need"
echo "      GEOS and PROJ system libraries."
echo "      macOS: brew install geos proj"
echo "      Ubuntu: sudo apt install libgeos-dev libproj-dev"
echo "============================================"
