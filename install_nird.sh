#!/bin/bash
# NIRD installation script for ncview2
# Auto-detects whether Anaconda3 or Miniforge3 modules are available.

set -e  # Exit on error

# ── Detect available software stack ──────────────────────────────
detect_stack() {
    if module avail Miniforge3 2>&1 | grep -q Miniforge3; then
        echo "miniforge"
    elif module avail Anaconda3 2>&1 | grep -q Anaconda3; then
        echo "anaconda"
     elif module avail NRIS/Login 2>&1 | grep -q NRIS/Login; then
        echo "nris"
    else
        echo ""
    fi
}

STACK=$(detect_stack)

if [[ "$STACK" == "miniforge" ]]; then
    echo "==> Detected Miniforge3 stack"
    MOD_PYTHON="Miniforge3/24.1.2-0"
    MOD_GEOS="GEOS/3.12.1-GCC-13.2.0"
    MOD_PROJ="PROJ/9.3.1-GCCcore-13.2.0"
    MOD_X11="X11/20240607-GCCcore-13.3.0"
elif [[ "$STACK" == "anaconda" ]]; then
    echo "==> Detected Anaconda3 stack"
    MOD_PYTHON="Anaconda3/2023.07-2"
    MOD_GEOS="GEOS/3.11.1-GCC-12.2.0"
    MOD_PROJ="PROJ/9.2.0-GCCcore-12.3.0"
    MOD_X11="X11/20221110-GCCcore-12.2.0"
elif [[ "$STACK" == "nris" ]]; then
    echo "==> Detected NRIS (Olivia) stack"
    MOD_PYTHON="Anaconda/1.0"
    MOD_GEOS="GEOS/3.13.1-GCC-14.2.0"
    MOD_PROJ="PROJ/9.6.2-GCCcore-14.2.0"
    MOD_X11="X11/20250521-GCCcore-14.2.0"
    echo "==> Load top-level NRIS/Login module to get access to other modules"
    module load NRIS/Login
else
    echo "ERROR: Neither Miniforge3 nor Anaconda3 modules found."
    echo "Run 'module avail' to see available modules."
    exit 1
fi

echo "==> Loading required modules..."
module load "$MOD_PYTHON"
module load "$MOD_GEOS"
module load "$MOD_PROJ"
module load "$MOD_X11"

echo "==> Installing ncview2..."
python -m pip install --user -e .

echo "==> Installing geo dependencies (cartopy, cmocean)..."
python -m pip install --user cartopy cmocean

echo "==> Creating module-loading wrapper..."
mkdir -p ~/.local/bin
cat > ~/.local/bin/ncview2 << WRAPPER_EOF
#!/bin/bash
# ncview2 wrapper that loads required modules

# Load required modules
module load $MOD_PYTHON 2>/dev/null
module load $MOD_GEOS 2>/dev/null
module load $MOD_PROJ 2>/dev/null
module load $MOD_X11 2>/dev/null

# Set DISPLAY if not set (for VS Code Remote)
if [ -z "\$DISPLAY" ]; then
    export DISPLAY=:0
fi

# Force Qt to use PySide6 plugins (not system Qt5 plugins)
export QT_PLUGIN_PATH="\$HOME/.local/lib/python3.11/site-packages/PySide6/Qt/plugins"

# Run ncview2
exec python -m ncview2 "\$@"
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
