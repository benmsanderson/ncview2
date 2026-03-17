#!/bin/bash
# Source this file to set up the environment for ncview2
# Usage: source setup_env.sh

module load Anaconda3/2023.07-2
module load GEOS/3.11.1-GCC-12.2.0
module load PROJ/9.2.0-GCCcore-12.3.0

# Add local bin to PATH
export PATH="$HOME/.local/bin:$PATH"

echo "Environment set up for ncview2"
echo "You can now run: ncview2 <netcdf_file>"
