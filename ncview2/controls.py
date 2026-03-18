"""Animation transport controls, dimension sliders, and option widgets."""

from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QPushButton,
    QSlider,
    QLabel,
    QComboBox,
    QSpinBox,
)
from PySide6.QtCore import Signal, Qt


class AnimationControls(QWidget):
    """Row of transport buttons + speed control."""

    play_forward = Signal()
    play_backward = Signal()
    pause = Signal()
    step_forward = Signal()
    step_backward = Signal()
    go_to_start = Signal()
    go_to_end = Signal()
    speed_changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        buttons = [
            ("|◀", self.go_to_start),
            ("◀◀", self.step_backward),
            ("◀", self.play_backward),
            ("||", self.pause),
            ("▶", self.play_forward),
            ("▶▶", self.step_forward),
            ("▶|", self.go_to_end),
        ]
        for label, signal in buttons:
            btn = QPushButton(label)
            btn.setFixedWidth(40)
            btn.clicked.connect(signal)
            layout.addWidget(btn)

        layout.addSpacing(10)
        layout.addWidget(QLabel("Speed:"))
        self.speed_spin = QSpinBox()
        self.speed_spin.setRange(10, 2000)
        self.speed_spin.setValue(200)
        self.speed_spin.setSuffix(" ms")
        self.speed_spin.setSingleStep(50)
        layout.addWidget(self.speed_spin)
        layout.addStretch()

        self.speed_spin.valueChanged.connect(self.speed_changed)


class DimSlider(QWidget):
    """Labelled slider for one dimension, showing coordinate values."""

    value_changed = Signal(str, int)  # dim_name, index

    def __init__(self, dim_name, size, coord_labels=None, parent=None):
        super().__init__(parent)
        self.dim_name = dim_name
        self.coord_labels = coord_labels

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)

        self.name_label = QLabel(f"{dim_name}:")
        self.name_label.setFixedWidth(80)
        layout.addWidget(self.name_label)

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, max(size - 1, 0))
        self.slider.setValue(0)
        layout.addWidget(self.slider, stretch=1)

        self.value_label = QLabel()
        self.value_label.setMinimumWidth(120)
        layout.addWidget(self.value_label)

        self.index_label = QLabel(f"/ {size - 1}")
        self.index_label.setFixedWidth(60)
        layout.addWidget(self.index_label)

        # Show initial value without emitting signal
        self._update_label(0)
        # Connect AFTER initial value set to avoid spurious signals
        self.slider.valueChanged.connect(self._on_change)

    def _update_label(self, idx):
        if self.coord_labels and idx < len(self.coord_labels):
            self.value_label.setText(str(self.coord_labels[idx]))
        else:
            self.value_label.setText(f"[{idx}]")

    def _on_change(self, idx):
        self._update_label(idx)
        self.value_changed.emit(self.dim_name, idx)

    def set_value(self, idx):
        self.slider.setValue(idx)

    def value(self):
        return self.slider.value()

    def maximum(self):
        return self.slider.maximum()


class ControlPanel(QWidget):
    """Combined panel: animation controls + dimension sliders + options."""

    dim_index_changed = Signal(str, int)
    colormap_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(4, 4, 4, 4)

        # Animation row
        self.anim = AnimationControls()
        self._layout.addWidget(self.anim)

        # Dimension sliders (populated dynamically)
        self._dim_container = QWidget()
        self._dim_layout = QVBoxLayout(self._dim_container)
        self._dim_layout.setContentsMargins(0, 0, 0, 0)
        self._layout.addWidget(self._dim_container)

        # Options row
        opts = QHBoxLayout()
        opts.addWidget(QLabel("Colormap:"))
        self.cmap_combo = QComboBox()
        self.cmap_combo.setMinimumWidth(140)
        opts.addWidget(self.cmap_combo)
        opts.addStretch()
        self._layout.addLayout(opts)

        self.cmap_combo.currentTextChanged.connect(self._on_cmap)
        self.dim_sliders: dict[str, DimSlider] = {}

    def setup_dims(self, scan_dims, dim_sizes, dim_coord_labels):
        """Create sliders for all scannable dimensions.

        dim_coord_labels: {dim_name: list[str]} — display labels per index.
        """
        for slider in self.dim_sliders.values():
            slider.setParent(None)
            slider.deleteLater()
        self.dim_sliders.clear()

        for dim in scan_dims:
            size = dim_sizes[dim]
            labels = dim_coord_labels.get(dim)
            slider = DimSlider(dim, size, labels)
            slider.value_changed.connect(self.dim_index_changed)
            self._dim_layout.addWidget(slider)
            self.dim_sliders[dim] = slider

    def setup_colormaps(self, cmap_dict, default=None):
        """Populate the colormap dropdown from {category: [names]}."""
        self.cmap_combo.blockSignals(True)
        self.cmap_combo.clear()
        for category, names in cmap_dict.items():
            # Non-selectable category header
            self.cmap_combo.addItem(f"── {category} ──")
            idx = self.cmap_combo.count() - 1
            self.cmap_combo.model().item(idx).setEnabled(False)
            for name in names:
                self.cmap_combo.addItem(name)
        if default:
            idx = self.cmap_combo.findText(default)
            if idx >= 0:
                self.cmap_combo.setCurrentIndex(idx)
        self.cmap_combo.blockSignals(False)

    def get_dim_index(self, dim):
        if dim in self.dim_sliders:
            return self.dim_sliders[dim].value()
        return 0

    def get_dim_indices(self):
        return {dim: s.value() for dim, s in self.dim_sliders.items()}

    def set_dim_index(self, dim, idx):
        if dim in self.dim_sliders:
            self.dim_sliders[dim].set_value(idx)

    def _on_cmap(self, text):
        if text and not text.startswith("──"):
            self.colormap_changed.emit(text)
