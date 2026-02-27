"""FailFixer – Main application window (PyQt6)."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, QMimeData
from PyQt6.QtGui import QDragEnterEvent, QDropEvent, QDoubleValidator, QIcon, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSpinBox,
    QStatusBar,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from failfixer.app.controller import FailFixerController


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _assets_dir() -> Path:
    """Return the assets/ directory relative to the project root."""
    return Path(__file__).resolve().parent.parent / "assets"


def _profiles_dir() -> Path:
    """Return the profiles/ directory relative to the project root."""
    return Path(__file__).resolve().parent.parent / "profiles"


def _load_profile_names() -> list[str]:
    """Scan profiles/ for .json files and return their stem names."""
    d = _profiles_dir()
    if not d.is_dir():
        return ["default_marlin"]
    names = sorted(p.stem for p in d.glob("*.json"))
    return names if names else ["default_marlin"]


# ---------------------------------------------------------------------------
# Drag-and-drop file picker widget
# ---------------------------------------------------------------------------

class GCodeFilePicker(QWidget):
    """A line-edit + browse button that also accepts drag-and-drop."""

    _NORMAL_STYLE = (
        "GCodeFilePicker { border: 2px dashed #2a2a4a; border-radius: 8px;"
        " padding: 4px; background: #16213e; }"
    )
    _HOVER_STYLE = (
        "GCodeFilePicker { border: 2px dashed #00d4aa; border-radius: 8px;"
        " padding: 4px; background: #1a2a4e; }"
    )

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setStyleSheet(self._NORMAL_STYLE)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)

        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("Drop a .gcode file here or click Browse…")
        self.path_edit.setReadOnly(True)
        layout.addWidget(self.path_edit, stretch=1)

        self.browse_btn = QPushButton("Browse…")
        self.browse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.browse_btn.clicked.connect(self._browse)
        layout.addWidget(self.browse_btn)

    # -- public API --

    def file_path(self) -> str:
        return self.path_edit.text().strip()

    def set_file_path(self, path: str) -> None:
        self.path_edit.setText(path)

    # -- drag & drop --

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # type: ignore[override]
        if event.mimeData() and event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.toLocalFile().lower().endswith(".gcode"):
                    self.setStyleSheet(self._HOVER_STYLE)
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dragLeaveEvent(self, event) -> None:  # type: ignore[override]
        self.setStyleSheet(self._NORMAL_STYLE)
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:  # type: ignore[override]
        self.setStyleSheet(self._NORMAL_STYLE)
        if event.mimeData():
            for url in event.mimeData().urls():
                path = url.toLocalFile()
                if path.lower().endswith(".gcode"):
                    self.set_file_path(path)
                    event.acceptProposedAction()
                    return
        event.ignore()

    # -- browse dialog --

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select G-code File",
            "",
            "G-code Files (*.gcode *.gco *.g);;All Files (*)",
        )
        if path:
            self.set_file_path(path)


# ---------------------------------------------------------------------------
# Collapsible group box
# ---------------------------------------------------------------------------

class CollapsibleGroupBox(QGroupBox):
    """A QGroupBox with a checkable title that shows/hides its contents."""

    def __init__(self, title: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(title, parent)
        self.setCheckable(True)
        self.setChecked(False)
        self.toggled.connect(self._on_toggled)
        # start collapsed
        self._content_visible = False

    def _on_toggled(self, checked: bool) -> None:
        self._content_visible = checked
        for i in range(self.layout().count()) if self.layout() else []:
            item = self.layout().itemAt(i)
            widget = item.widget() if item else None
            if widget:
                widget.setVisible(checked)
            layout = item.layout() if item else None
            if layout:
                for j in range(layout.count()):
                    w = layout.itemAt(j).widget() if layout.itemAt(j) else None
                    if w:
                        w.setVisible(checked)

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        # enforce initial collapsed state
        self._on_toggled(self.isChecked())


# ---------------------------------------------------------------------------
# FAQ Dialog
# ---------------------------------------------------------------------------

class FAQDialog(QDialog):
    """Modal dialog showing frequently asked questions."""

    FAQ_CONTENT = """
<h2 style="color:#00d4aa;">Frequently Asked Questions</h2>

<h3 style="color:#ff6b35;">⚠️ Do I need to leave my print on the bed?</h3>
<p><b>YES!</b> The partial print must remain exactly where it is on the build plate.
Do not move it, bump the bed, or adjust anything. FailFixer generates G-code that
continues from where the print failed — if the object has shifted even slightly,
the layers won't align and the resume will fail.</p>

<h3 style="color:#00d4aa;">How do I find the layer number where my print failed?</h3>
<p>Open your original G-code in a slicer preview (Cura, PrusaSlicer, etc.) and scrub
through the layers to find the height where the print stopped. You can also measure
the height of the failed print with calipers and use the "Z Height" option instead
of layer number.</p>

<h3 style="color:#00d4aa;">What if I don't know the exact layer?</h3>
<p>Measure the height of your failed print with calipers. Enter that measurement
using the "Z Height (mm)" option. FailFixer will find the closest layer. It's better
to go <b>one layer lower</b> than too high — overlapping a layer is much better than
leaving a gap.</p>

<h3 style="color:#00d4aa;">Will the nozzle crash into my print when it homes?</h3>
<p>No. FailFixer only homes X and Y axes (which move to the corner of the bed, away
from your print). It <b>never</b> homes Z, which would drive the nozzle downward.
Instead, it uses G92 to set the Z position without moving.</p>

<h3 style="color:#00d4aa;">What does Z Offset do?</h3>
<p>Z Offset adds a small adjustment to the resume height. Use a positive value
(+0.1 to +0.3mm) if you want a tiny gap for better adhesion to the existing layers,
or a negative value if the first resumed layer isn't sticking. Most users can leave
this at 0.00.</p>

<h3 style="color:#00d4aa;">Why is there a seam/line where the print resumed?</h3>
<p>This is normal. The resumed layers may not perfectly bond with the failed layers
below. You can minimize this by:</p>
<ul>
<li>Using a slightly negative Z offset (-0.05 to -0.1mm) to squish the first layer</li>
<li>Ensuring the nozzle and bed are fully heated before the resume starts</li>
<li>Going one layer lower than where you think it failed</li>
</ul>

<h3 style="color:#00d4aa;">Which printers / firmware does this work with?</h3>
<p>FailFixer supports:</p>
<ul>
<li><b>Marlin</b> — Ender 3, CR-10, Prusa MK3/MK4, most common printers</li>
<li><b>Klipper</b> — Voron, custom builds, Sonic Pad setups</li>
<li><b>RepRapFirmware</b> — Duet boards</li>
</ul>
<p>Select your firmware profile in Advanced Options. When in doubt, use "default_marlin"
— it uses standard G-code that works on most printers.</p>

<h3 style="color:#00d4aa;">Can I resume a print that failed hours/days ago?</h3>
<p>Yes, as long as the print hasn't been moved or removed from the bed. The printer
doesn't need to stay powered on. FailFixer generates a fresh G-code file that heats
everything back up and starts from the resume layer.</p>

<h3 style="color:#00d4aa;">What if my print failed due to a clog or filament issue?</h3>
<p>Fix the underlying problem first (clear the clog, load new filament, etc.), then
use FailFixer to resume. The resume file will prime the nozzle before starting, but
it can't fix mechanical issues.</p>

<h3 style="color:#00d4aa;">Can I edit the output G-code?</h3>
<p>Yes! The output is a standard .gcode text file. You can open it in any text editor
to verify or adjust settings before printing.</p>
"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("FailFixer — FAQ")
        self.setMinimumSize(500, 500)
        self.resize(540, 600)

        if parent:
            self.setStyleSheet(parent.styleSheet())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: #1a1a2e; }")

        content = QLabel(self.FAQ_CONTENT)
        content.setWordWrap(True)
        content.setTextFormat(Qt.TextFormat.RichText)
        content.setAlignment(Qt.AlignmentFlag.AlignTop)
        content.setStyleSheet("QLabel { background: #1a1a2e; color: #e0e0e0; padding: 8px; }")
        scroll.setWidget(content)

        layout.addWidget(scroll)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)


# ---------------------------------------------------------------------------
# Main Window
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    """Primary FailFixer UI."""

    WINDOW_TITLE = "FailFixer — Resume Failed Print"

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(self.WINDOW_TITLE)
        self.setMinimumSize(520, 540)
        self.resize(560, 700)

        # Set window icon
        logo_path = Path(__file__).resolve().parent.parent / "assets" / "logo.png"
        if logo_path.exists():
            self.setWindowIcon(QIcon(str(logo_path)))

        self.controller = FailFixerController()

        self._apply_theme()
        self._build_ui()

    # ------------------------------------------------------------------
    # Theme
    # ------------------------------------------------------------------

    def _apply_theme(self) -> None:
        """Apply a modern dark theme with neon accent colors."""
        self.setStyleSheet("""
            /* ── Base ─────────────────────────────────────── */
            QMainWindow, QWidget {
                background-color: #1a1a2e;
                color: #e0e0e0;
                font-family: "Segoe UI", "Inter", "Roboto", sans-serif;
                font-size: 13px;
            }

            /* ── Labels ───────────────────────────────────── */
            QLabel {
                color: #e0e0e0;
            }
            QLabel[class="section-title"] {
                color: #00d4aa;
                font-size: 14px;
                font-weight: 600;
            }
            QLabel#headerTitle {
                color: #ffffff;
                font-size: 22px;
                font-weight: 700;
                background: transparent;
            }
            QLabel#headerSubtitle {
                color: #8a8aa0;
                font-size: 12px;
                background: transparent;
            }
            QLabel#headerAccent {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #00d4aa, stop:1 #0f3460);
                min-height: 2px;
                max-height: 2px;
            }

            /* ── Inputs (line edits, spin boxes) ──────────── */
            QLineEdit, QSpinBox, QDoubleSpinBox {
                background-color: #16213e;
                color: #e0e0e0;
                border: 1px solid #333;
                border-radius: 5px;
                padding: 4px 8px;
                selection-background-color: #00d4aa;
                selection-color: #1a1a2e;
            }
            QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {
                border: 1px solid #00d4aa;
            }
            QLineEdit:read-only {
                background-color: #16213e;
                color: #b0b0c0;
            }

            /* spin box arrows */
            QSpinBox::up-button, QDoubleSpinBox::up-button,
            QSpinBox::down-button, QDoubleSpinBox::down-button {
                background-color: #0f3460;
                border: none;
                width: 18px;
            }
            QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
            QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {
                background-color: #00d4aa;
            }
            QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-bottom: 5px solid #e0e0e0;
                width: 0; height: 0;
            }
            QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 5px solid #e0e0e0;
                width: 0; height: 0;
            }

            /* ── ComboBox ─────────────────────────────────── */
            QComboBox {
                background-color: #16213e;
                color: #e0e0e0;
                border: 1px solid #333;
                border-radius: 5px;
                padding: 4px 8px;
                min-height: 22px;
            }
            QComboBox:focus {
                border: 1px solid #00d4aa;
            }
            QComboBox::drop-down {
                border: none;
                background: #0f3460;
                width: 24px;
                border-top-right-radius: 5px;
                border-bottom-right-radius: 5px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 6px solid #e0e0e0;
                width: 0; height: 0;
            }
            QComboBox QAbstractItemView {
                background-color: #16213e;
                color: #e0e0e0;
                border: 1px solid #333;
                selection-background-color: #00d4aa;
                selection-color: #1a1a2e;
                outline: none;
            }

            /* ── Group Boxes ──────────────────────────────── */
            QGroupBox {
                background-color: #16213e;
                border: 1px solid #2a2a4a;
                border-radius: 8px;
                margin-top: 14px;
                padding-top: 18px;
                font-weight: 600;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 12px;
                padding: 0 6px;
                color: #00d4aa;
                font-size: 13px;
            }
            QGroupBox::indicator {
                width: 14px;
                height: 14px;
                border-radius: 3px;
                border: 1px solid #555;
                background: #1a1a2e;
            }
            QGroupBox::indicator:checked {
                background-color: #00d4aa;
                border: 1px solid #00d4aa;
            }

            /* ── Radio Buttons ────────────────────────────── */
            QRadioButton {
                spacing: 6px;
                color: #e0e0e0;
            }
            QRadioButton::indicator {
                width: 14px;
                height: 14px;
                border-radius: 8px;
                border: 2px solid #555;
                background: #1a1a2e;
            }
            QRadioButton::indicator:checked {
                background-color: #00d4aa;
                border: 2px solid #00d4aa;
            }

            /* ── Buttons (general) ────────────────────────── */
            QPushButton {
                background-color: #0f3460;
                color: #e0e0e0;
                border: 1px solid #2a2a4a;
                border-radius: 6px;
                padding: 6px 16px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #1a4a7a;
                border: 1px solid #00d4aa;
            }
            QPushButton:pressed {
                background-color: #0a2540;
            }

            /* Generate button (special) */
            QPushButton#generateBtn {
                background-color: #ff6b35;
                color: #ffffff;
                font-weight: 700;
                font-size: 14px;
                border: none;
                border-radius: 8px;
                padding: 8px 20px;
            }
            QPushButton#generateBtn:hover {
                background-color: #ff8855;
                border: 1px solid #ffaa77;
            }
            QPushButton#generateBtn:pressed {
                background-color: #e05520;
            }

            /* ── Status text ──────────────────────────────── */
            QTextEdit {
                background-color: #111128;
                color: #c8c8dc;
                border: 1px solid #2a2a4a;
                border-radius: 6px;
                padding: 6px;
                font-family: "Cascadia Code", "Consolas", "Fira Code", monospace;
                font-size: 12px;
                selection-background-color: #00d4aa;
                selection-color: #1a1a2e;
            }

            /* ── Status Bar ───────────────────────────────── */
            QStatusBar {
                background-color: #111128;
                color: #8a8aa0;
                border-top: 1px solid #2a2a4a;
                font-size: 12px;
            }

            /* ── Scrollbars ───────────────────────────────── */
            QScrollBar:vertical {
                background: #1a1a2e;
                width: 8px;
                border: none;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background: #333355;
                min-height: 30px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical:hover {
                background: #00d4aa;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
                border: none;
                height: 0;
            }
            QScrollBar:horizontal {
                background: #1a1a2e;
                height: 8px;
                border: none;
                border-radius: 4px;
            }
            QScrollBar::handle:horizontal {
                background: #333355;
                min-width: 30px;
                border-radius: 4px;
            }
            QScrollBar::handle:horizontal:hover {
                background: #00d4aa;
            }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal,
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
                background: none;
                border: none;
                width: 0;
            }

            /* ── Tooltips ─────────────────────────────────── */
            QToolTip {
                background-color: #0f3460;
                color: #e0e0e0;
                border: 1px solid #00d4aa;
                border-radius: 4px;
                padding: 4px;
            }

            /* ── Message Box ──────────────────────────────── */
            QMessageBox {
                background-color: #1a1a2e;
            }
            QMessageBox QLabel {
                color: #e0e0e0;
            }
            QMessageBox QPushButton {
                min-width: 80px;
            }
        """)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setSpacing(10)
        root.setContentsMargins(16, 12, 16, 12)

        # --- Header banner with logo ---
        header_row = QHBoxLayout()
        header_row.setSpacing(10)

        logo_path = _assets_dir() / "logo.png"
        if logo_path.exists():
            logo_label = QLabel()
            pixmap = QPixmap(str(logo_path)).scaled(
                42, 42, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            logo_label.setPixmap(pixmap)
            logo_label.setFixedSize(42, 42)
            logo_label.setStyleSheet("background: transparent;")
            header_row.addWidget(logo_label)

        header_text_col = QVBoxLayout()
        header_text_col.setSpacing(0)
        header_title = QLabel("FailFixer")
        header_title.setObjectName("headerTitle")
        header_text_col.addWidget(header_title)
        header_subtitle = QLabel("Resume Failed 3D Prints")
        header_subtitle.setObjectName("headerSubtitle")
        header_text_col.addWidget(header_subtitle)
        header_row.addLayout(header_text_col, stretch=1)

        root.addLayout(header_row)

        header_accent = QLabel()
        header_accent.setObjectName("headerAccent")
        header_accent.setFixedHeight(2)
        root.addWidget(header_accent)

        root.addSpacing(4)

        # --- File picker ---
        lbl_gcode = QLabel("G-code File")
        lbl_gcode.setProperty("class", "section-title")
        root.addWidget(lbl_gcode)
        self.file_picker = GCodeFilePicker()
        root.addWidget(self.file_picker)

        # --- Resume selector ---
        resume_group = QGroupBox("Resume Point")
        resume_layout = QVBoxLayout(resume_group)

        self.radio_layer = QRadioButton("Layer Number")
        self.radio_z = QRadioButton("Z Height (mm)")
        self.radio_layer.setChecked(True)

        self.btn_group = QButtonGroup(self)
        self.btn_group.addButton(self.radio_layer)
        self.btn_group.addButton(self.radio_z)

        # Layer spinbox
        layer_row = QHBoxLayout()
        layer_row.addWidget(self.radio_layer)
        self.layer_spin = QSpinBox()
        self.layer_spin.setRange(1, 999999)
        self.layer_spin.setValue(1)
        layer_row.addWidget(self.layer_spin, stretch=1)
        resume_layout.addLayout(layer_row)

        # Z height input
        z_row = QHBoxLayout()
        z_row.addWidget(self.radio_z)
        self.z_height_input = QDoubleSpinBox()
        self.z_height_input.setRange(0.01, 9999.99)
        self.z_height_input.setDecimals(2)
        self.z_height_input.setSuffix(" mm")
        self.z_height_input.setValue(0.20)
        self.z_height_input.setEnabled(False)
        z_row.addWidget(self.z_height_input, stretch=1)
        resume_layout.addLayout(z_row)

        # Toggle enable/disable based on radio
        self.radio_layer.toggled.connect(lambda on: self.layer_spin.setEnabled(on))
        self.radio_z.toggled.connect(lambda on: self.z_height_input.setEnabled(on))

        root.addWidget(resume_group)

        # --- Firmware selector (top-level, not hidden) ---
        fw_row = QHBoxLayout()
        fw_label = QLabel("Firmware")
        fw_label.setProperty("class", "section-title")
        fw_row.addWidget(fw_label)
        self.profile_combo = QComboBox()
        profiles = _load_profile_names()
        # Show friendly names
        friendly_names = {
            "default_marlin": "Marlin (default)",
            "klipper": "Klipper",
            "reprapfirmware": "RepRapFirmware (Duet)",
        }
        for p in profiles:
            self.profile_combo.addItem(friendly_names.get(p, p), p)
        # Default to Marlin
        marlin_idx = next((i for i, p in enumerate(profiles) if "marlin" in p), 0)
        self.profile_combo.setCurrentIndex(marlin_idx)
        fw_row.addWidget(self.profile_combo, stretch=1)
        root.addLayout(fw_row)

        # --- Advanced / optional fields (collapsible) ---
        adv = CollapsibleGroupBox("Advanced Options")
        adv_layout = QVBoxLayout(adv)

        # Z offset
        zo_row = QHBoxLayout()
        zo_row.addWidget(QLabel("Z Offset:"))
        self.z_offset_spin = QDoubleSpinBox()
        self.z_offset_spin.setRange(-10.0, 10.0)
        self.z_offset_spin.setDecimals(2)
        self.z_offset_spin.setSuffix(" mm")
        self.z_offset_spin.setValue(0.00)
        zo_row.addWidget(self.z_offset_spin, stretch=1)
        adv_layout.addLayout(zo_row)

        # Park X
        px_row = QHBoxLayout()
        px_row.addWidget(QLabel("Park X:"))
        self.park_x_spin = QDoubleSpinBox()
        self.park_x_spin.setRange(0, 500)
        self.park_x_spin.setDecimals(1)
        self.park_x_spin.setSuffix(" mm")
        self.park_x_spin.setSpecialValueText("(default)")
        self.park_x_spin.setValue(0)
        px_row.addWidget(self.park_x_spin, stretch=1)
        adv_layout.addLayout(px_row)

        # Park Y
        py_row = QHBoxLayout()
        py_row.addWidget(QLabel("Park Y:"))
        self.park_y_spin = QDoubleSpinBox()
        self.park_y_spin.setRange(0, 500)
        self.park_y_spin.setDecimals(1)
        self.park_y_spin.setSuffix(" mm")
        self.park_y_spin.setSpecialValueText("(default)")
        self.park_y_spin.setValue(0)
        py_row.addWidget(self.park_y_spin, stretch=1)
        adv_layout.addLayout(py_row)

        root.addWidget(adv)

        # --- Generate button ---
        self.generate_btn = QPushButton("⚡  Generate Resume File")
        self.generate_btn.setObjectName("generateBtn")
        self.generate_btn.setMinimumHeight(40)
        self.generate_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.generate_btn.clicked.connect(self._on_generate)
        root.addWidget(self.generate_btn)

        # --- Status / log area ---
        lbl_status = QLabel("Status")
        lbl_status.setProperty("class", "section-title")
        root.addWidget(lbl_status)
        self.status_text = QTextEdit()
        self.status_text.setReadOnly(True)
        self.status_text.setMaximumHeight(140)
        self.status_text.setPlaceholderText("Parse results and status messages will appear here…")
        root.addWidget(self.status_text)

        # --- Warning banner ---
        warning_label = QLabel("⚠️  PRINT MUST REMAIN IN SAME LOCATION ON BED!")
        warning_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        warning_label.setStyleSheet(
            "QLabel { background-color: #3d1a00; color: #ff6b35; "
            "font-weight: 700; font-size: 12px; padding: 6px; "
            "border: 1px solid #ff6b35; border-radius: 6px; }"
        )
        root.addWidget(warning_label)

        # --- FAQ button ---
        faq_btn = QPushButton("❓  FAQ — Common Questions")
        faq_btn.setStyleSheet(
            "QPushButton { background-color: #0f3460; color: #00d4aa; "
            "font-weight: 600; border: 1px solid #00d4aa; border-radius: 6px; "
            "padding: 6px 16px; }"
            "QPushButton:hover { background-color: #1a4a7a; }"
        )
        faq_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        faq_btn.clicked.connect(self._show_faq)
        root.addWidget(faq_btn)

        # --- Credit ---
        credit_label = QLabel("Developed by FleX3Designs")
        credit_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        credit_label.setStyleSheet(
            "QLabel { color: #555570; font-size: 11px; padding: 4px 0; }"
        )
        root.addWidget(credit_label)

        # Status bar
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("Ready")

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _gather_params(self) -> dict:
        """Collect current UI state into a kwargs dict for the controller."""
        params: dict = {
            "gcode_path": self.file_picker.file_path(),
            "z_offset": self.z_offset_spin.value(),
            "profile": self.profile_combo.currentData() or "default_marlin",
        }

        if self.radio_layer.isChecked():
            params["layer_num"] = self.layer_spin.value()
        else:
            params["z_height"] = self.z_height_input.value()

        # Park coordinates — only include if advanced section is expanded
        # and values are non-zero (i.e., user intentionally set them)
        if self.park_x_spin.value() > 0:
            params["park_x"] = self.park_x_spin.value()
        if self.park_y_spin.value() > 0:
            params["park_y"] = self.park_y_spin.value()

        return params

    def _validate_inputs(self) -> Optional[str]:
        """Return an error message string if inputs are invalid, else None."""
        path = self.file_picker.file_path()
        if not path:
            return "Please select a G-code file."
        if not os.path.isfile(path):
            return f"File not found:\n{path}"
        return None

    def _build_summary(self, params: dict) -> str:
        """Build a human-readable summary for the confirmation dialog."""
        lines: list[str] = []
        lines.append(f"File: {Path(params['gcode_path']).name}")

        if "layer_num" in params:
            lines.append(f"Resume at layer: {params['layer_num']}")
        else:
            lines.append(f"Resume at Z height: {params['z_height']:.2f} mm")

        if params.get("z_offset", 0.0) != 0.0:
            lines.append(f"Z offset: {params['z_offset']:+.2f} mm")

        if "park_x" in params or "park_y" in params:
            px = params.get("park_x", "default")
            py = params.get("park_y", "default")
            lines.append(f"Park position: X={px}  Y={py}")

        lines.append(f"Profile: {params['profile']}")
        return "\n".join(lines)

    def _default_output_name(self, params: dict) -> str:
        """Generate the default output filename."""
        src = Path(params["gcode_path"])
        if "layer_num" in params:
            tag = f"resume_layer{params['layer_num']:04d}"
        else:
            tag = f"resume_z{params['z_height']:.2f}".replace(".", "_")
        return f"{src.stem}_{tag}.gcode"

    def _log(self, text: str) -> None:
        self.status_text.append(text)

    def _show_faq(self) -> None:
        """Show the FAQ dialog."""
        dialog = FAQDialog(self)
        dialog.exec()

    # ------------------------------------------------------------------
    # Generate handler
    # ------------------------------------------------------------------

    def _on_generate(self) -> None:
        # 1. Validate inputs
        err = self._validate_inputs()
        if err:
            QMessageBox.warning(self, "Input Error", err)
            return

        params = self._gather_params()

        # 2. Confirmation dialog
        summary = self._build_summary(params)
        reply = QMessageBox.question(
            self,
            "Confirm Generation",
            f"Generate resume G-code with these settings?\n\n{summary}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        # 3. Save-as dialog
        default_name = self._default_output_name(params)
        default_dir = str(Path(params["gcode_path"]).parent / default_name)
        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Resume G-code",
            default_dir,
            "G-code Files (*.gcode);;All Files (*)",
        )
        if not save_path:
            return

        # 4. Run controller
        self.statusBar().showMessage("Generating…")
        self._log("---")
        self._log(f"Processing: {params['gcode_path']}")
        QApplication.processEvents()

        try:
            result = self.controller.process(
                gcode_path=params["gcode_path"],
                layer_num=params.get("layer_num"),
                z_height=params.get("z_height"),
                z_offset=params.get("z_offset", 0.0),
                park_x=params.get("park_x"),
                park_y=params.get("park_y"),
                profile=params.get("profile", "default_marlin"),
                output_path=save_path,
            )
        except Exception as exc:
            self._log(f"❌ Error: {exc}")
            QMessageBox.critical(self, "Generation Failed", str(exc))
            self.statusBar().showMessage("Failed")
            return

        # 5. Report results
        self._log(f"✅ Resume file saved: {result.output_path}")
        if hasattr(result, "total_layers"):
            self._log(f"   Total layers detected: {result.total_layers}")
        if hasattr(result, "bed_temp") and result.bed_temp:
            self._log(f"   Bed temp: {result.bed_temp}°C")
        if hasattr(result, "nozzle_temp") and result.nozzle_temp:
            self._log(f"   Nozzle temp: {result.nozzle_temp}°C")

        if hasattr(result, "warnings") and result.warnings:
            for w in result.warnings:
                self._log(f"   ⚠️  {w}")

        self.statusBar().showMessage("Done — file saved")
        QMessageBox.information(
            self,
            "Success",
            f"Resume G-code saved to:\n{result.output_path}",
        )
