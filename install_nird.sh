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

echo "==> Creating module-loading wrapper..."
cat > ~/.local/bin/ncview2 << 'WRAPPER_EOF'
#!/bin/bash
# ncview2 wrapper that loads required modules

# Load required modules
module load Anaconda3/2023.07-2 2>/dev/null
module load GEOS/3.11.1-GCC-12.2.0 2>/dev/null
module load PROJ/9.2.0-GCCcore-12.3.0 2>/dev/null
module load X11/20221110-GCCcore-12.2.0 2>/dev/null

# Set DISPLAY if not set (for VS Code Remote)
if [ -z "$DISPLAY" ]; then
    export DISPLAY=:0
fi

# Force Qt to use PySide6 plugins (not Anaconda's Qt5 plugins)
export QT_PLUGIN_PATH="$HOME/.local/lib/python3.11/site-packages/PySide6/Qt/plugins"

# Run ncview2
exec /nird/services/software/nird/sw/software/Anaconda3/2023.07-2/bin/python -m ncview2 "$@"
WRAPPER_EOF
chmod +x ~/.local/bin/ncview2

echo ""
read -p "Add ~/.local/bin to PATH in ~/.bashrc? [Y/n] " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Nn]$ ]]; then
    # Check if already in bashrc
    if ! grep -q 'PATH.*\.local/bin' ~/.bashrc; then
        echo "" >> ~/.bashrc
        echo "# ncview2 - PATH only (wrapper auto-loads modules)" >> ~/.bashrc
        echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
        echo "==> Added PATH to ~/.bashrc"
        echo "==> Run 'source ~/.bashrc' or open a new terminal"
    else
        echo "==> PATH already in ~/.bashrc"
    fi
else
    echo ""
    echo "To use ncview2, add to PATH before each session:"
    echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
fi

echo ""
echo "Installation complete! Use: ncview2 <file.nc>"
echo "Note: The ncview2 wrapper automatically loads required modules."
echo "      For GUI, ensure X11 forwarding is enabled (ssh -X) or use VS Code Remote."
