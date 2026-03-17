#!/bin/bash
# NIRD installation script for ncview2

set -e  # Exit on error

echo "==> Loading required modules..."
module load Anaconda3/2023.07-2
module load GEOS/3.11.1-GCC-12.2.0
module load PROJ/9.2.0-GCCcore-12.3.0
module load X11/20221110-GCCcore-12.2.0

echo "==> Installing ncview2..."
python -m pip install --user -e .

echo "==> Installing geo dependencies (cartopy, cmocean)..."
python -m pip install --user cartopy cmocean

echo ""
read -p "Add modules to ~/.bashrc for permanent setup? [Y/n] " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Nn]$ ]]; then
    # Check if already in bashrc
    if ! grep -q "module load Anaconda3/2023.07-2" ~/.bashrc; then
        echo "" >> ~/.bashrc
        echo "# ncview2 modules" >> ~/.bashrc
        echo 'module load Anaconda3/2023.07-2' >> ~/.bashrc
        echo 'module load GEOS/3.11.1-GCC-12.2.0' >> ~/.bashrc
        echo 'module load PROJ/9.2.0-GCCcore-12.3.0' >> ~/.bashrc
        echo 'module load X11/20221110-GCCcore-12.2.0' >> ~/.bashrc
        echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
        echo "==> Added to ~/.bashrc"
        echo "==> Run 'source ~/.bashrc' or open a new terminal"
    else
        echo "==> Modules already in ~/.bashrc"
    fi
else
    echo ""
    echo "To use ncview2, run these before each session:"
    echo "  module load Anaconda3/2023.07-2"
    echo "  module load GEOS/3.11.1-GCC-12.2.0"
    echo "  module load PROJ/9.2.0-GCCcore-12.3.0"
    echo "  module load X11/20221110-GCCcore-12.2.0"
    echo "  export PATH=\"\$HOME/.local/bin:\$PATH\"" 
fi

echo ""
echo "Installation complete! Use: ncview2 <file.nc>"
