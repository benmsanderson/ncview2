#!/bin/bash
# Olivia (Sigma2) installation script for ncview2 using hpc-container-wrapper

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
INSTALL_DIR="${NCVIEW2_OLIVIA_PREFIX:-$HOME/.local/ncview2-olivia}"

if ! command -v module >/dev/null 2>&1; then
    echo "ERROR: module command not found. This script is intended for Olivia." >&2
    exit 1
fi

echo "==> Preparing Olivia software stack..."
module load NRIS/CPU
module load hpc-container-wrapper

if ! command -v conda-containerize >/dev/null 2>&1; then
    echo "ERROR: conda-containerize not found after loading hpc-container-wrapper." >&2
    exit 1
fi

# Use the system CA bundle explicitly. This avoids TLS failures when curl is
# invoked by hpc-container-wrapper to fetch Miniforge.
if [[ -z "${CURL_CA_BUNDLE:-}" && -r /var/lib/ca-certificates/ca-bundle.pem ]]; then
    export CURL_CA_BUNDLE=/var/lib/ca-certificates/ca-bundle.pem
fi
if [[ -z "${SSL_CERT_FILE:-}" && -r /var/lib/ca-certificates/ca-bundle.pem ]]; then
    export SSL_CERT_FILE=/var/lib/ca-certificates/ca-bundle.pem
fi

# Sigma2 proxy defaults are typically needed on compute nodes. Keep existing
# user values if already set.
if [[ -n "${SLURM_JOB_ID:-}" ]]; then
    export http_proxy="${http_proxy:-http://10.63.2.48:3128/}"
    export https_proxy="${https_proxy:-http://10.63.2.48:3128/}"
fi

echo ""
echo "==> Building containerized conda environment..."
echo "    Prefix: $INSTALL_DIR"
conda-containerize new --mamba --prefix "$INSTALL_DIR" "$REPO_ROOT/environment.yml"

echo ""
echo "==> Installing ncview2 in editable mode inside wrapped environment..."
"$INSTALL_DIR/bin/pip" install -e "$REPO_ROOT"

echo ""
echo "==> Creating launcher in ~/.local/bin/ncview2 ..."
mkdir -p "$HOME/.local/bin"
cat > "$HOME/.local/bin/ncview2" <<LAUNCHER_EOF
#!/bin/bash
export PATH="$INSTALL_DIR/bin:\$PATH"
exec "$INSTALL_DIR/bin/python" -m ncview2 "\$@"
LAUNCHER_EOF
chmod +x "$HOME/.local/bin/ncview2"

echo ""
read -p "Add ~/.local/bin to PATH in ~/.bashrc? [Y/n] " -n 1 -r
echo
if [[ ! ${REPLY:-} =~ ^[Nn]$ ]]; then
    if ! grep -q 'PATH.*\.local/bin' "$HOME/.bashrc"; then
        echo "" >> "$HOME/.bashrc"
        echo "# ncview2 launcher" >> "$HOME/.bashrc"
        echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.bashrc"
        echo "==> Added ~/.local/bin to PATH in ~/.bashrc"
    else
        echo "==> ~/.local/bin is already configured in ~/.bashrc"
    fi
fi

echo ""
echo "============================================"
echo "Installation complete for Olivia."
echo "Run: ncview2 <file.nc>"
echo "If needed, activate in current shell: export PATH=\"$HOME/.local/bin:\$PATH\""
echo "============================================"
