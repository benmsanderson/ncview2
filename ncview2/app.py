"""Application entry point and CLI."""

import matplotlib

matplotlib.use("QtAgg")

import sys  # noqa: E402
import argparse  # noqa: E402
from PySide6.QtWidgets import QApplication, QFileDialog  # noqa: E402


def main():
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

    if args.files:
        window.open_file(args.files[0])
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
