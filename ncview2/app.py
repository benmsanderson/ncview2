"""Application entry point and CLI."""

import matplotlib

matplotlib.use("QtAgg")

import sys  # noqa: E402
import os  # noqa: E402
import stat  # noqa: E402
import glob  # noqa: E402
import argparse  # noqa: E402
from pathlib import Path  # noqa: E402
from PySide6.QtWidgets import QApplication, QFileDialog  # noqa: E402


def _install_wrapper():
    """Write a shell wrapper script so ncview2 works without activating the env."""
    python = sys.executable
    wrapper_dir = Path.home() / ".local" / "bin"
    wrapper_path = wrapper_dir / "ncview2"

    wrapper_dir.mkdir(parents=True, exist_ok=True)

    script = f"""#!/bin/sh
exec "{python}" -m ncview2 "$@"
"""
    wrapper_path.write_text(script)
    wrapper_path.chmod(wrapper_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    print(f"Installed wrapper to {wrapper_path}")
    print(f"  Python: {python}")

    # Check if wrapper dir is in PATH
    path_dirs = os.environ.get("PATH", "").split(os.pathsep)
    if str(wrapper_dir) not in path_dirs:
        print(f"\n  Add {wrapper_dir} to your PATH:")
        print(f'    export PATH="{wrapper_dir}:$PATH"')
        print(f"  (add this to your ~/.bashrc or ~/.zshrc)")

    # Warn if running inside a module environment
    if os.environ.get("LOADEDMODULES"):
        print("\n  Note: module environment detected. If ncview2 fails outside")
        print("  your module session, you may need to load the relevant")
        print("  modules in your shell profile.")


def main():
    # Handle --install before any Qt setup
    if "--install" in sys.argv:
        _install_wrapper()
        sys.exit(0)

    parser = argparse.ArgumentParser(
        prog="ncview2",
        description="ncview2 — a modern NetCDF visual browser",
    )
    parser.add_argument("files", nargs="*", help="NetCDF file(s) to open")
    args = parser.parse_args()

    app = QApplication(sys.argv)
    app.setApplicationName("ncview2")

    # Import main window after QApplication exists (required by some Qt setups)
    from ncview2.main_window import MainWindow

    window = MainWindow()
    window.show()

    # Expand any glob patterns the shell didn't expand (e.g. quoted wildcards)
    expanded = []
    for pattern in args.files:
        matches = sorted(glob.glob(pattern))
        expanded.extend(matches if matches else [pattern])

    if expanded:
        window.open_file(expanded if len(expanded) > 1 else expanded[0])
    else:
        path, _ = QFileDialog.getOpenFileName(
            window,
            "Open NetCDF File",
            "",
            "NetCDF Files (*.nc *.nc4 *.cdf *.hdf5 *.h5);;All Files (*)",
        )
        if path:
            window.open_file(path)
        else:
            sys.exit(0)

    sys.exit(app.exec())
