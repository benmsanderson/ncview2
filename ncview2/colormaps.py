"""Colormap registry and auto-selection logic."""

SEQUENTIAL = [
    "viridis", "plasma", "inferno", "magma", "cividis",
    "YlOrRd", "YlGnBu", "Spectral",
]

DIVERGING = ["RdBu_r", "BrBG", "coolwarm", "seismic", "PiYG"]

CYCLIC = ["twilight", "twilight_shifted", "hsv"]

try:
    import cmocean  # noqa: F401

    OCEAN = [
        f"cmo.{name}"
        for name in [
            "thermal", "haline", "solar", "ice", "gray",
            "oxy", "deep", "dense", "algae", "matter",
            "turbid", "speed", "amp", "tempo", "rain",
            "phase", "topo", "balance", "delta", "curl",
        ]
    ]
except ImportError:
    OCEAN = []


def all_colormaps():
    """Return dict of category → list of colormap names."""
    cmaps = {
        "Sequential": SEQUENTIAL,
        "Diverging": DIVERGING,
        "Cyclic": CYCLIC,
    }
    if OCEAN:
        cmaps["Ocean (cmocean)"] = OCEAN
    return cmaps


def default_colormap(vmin, vmax):
    """Pick a sensible default colormap based on data range."""
    if vmin < 0 and vmax > 0:
        return "RdBu_r"
    return "viridis"
