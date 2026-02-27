"""FailFixer – Step-by-step wizard flow (PyQt6).

A minimal alternative to the main window that guides the user through:
  1. Pick file
  2. Set resume point
  3. Confirm & save
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication,
    QDoubleSpinBox,
    QFileDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
    QWizard,
    QWizardPage,
)

from failfixer.app.controller import FailFixerController


# ---------------------------------------------------------------------------
# Page 1 – Pick G-code file
# ---------------------------------------------------------------------------

class FilePickerPage(QWizardPage):
    """Wizard page: select the source .gcode file."""

    def __init__(self, parent: Optional[QWizard] = None) -> None:
        super().__init__(parent)
        self.setTitle("Select G-code File")
        self.setSubTitle("Choose the original .gcode file from your failed print.")

        layout = QVBoxLayout(self)

        self.path_label = QLabel("No file selected")
        self.path_label.setWordWrap(True)
        layout.addWidget(self.path_label)

        btn = QPushButton("Browse…")
        btn.clicked.connect(self._browse)
        layout.addWidget(btn)

        self._file_path: str = ""

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select G-code File",
            "",
            "G-code Files (*.gcode *.gco *.g);;All Files (*)",
        )
        if path:
            self._file_path = path
            self.path_label.setText(path)
            self.completeChanged.emit()

    def isComplete(self) -> bool:  # type: ignore[override]
        return bool(self._file_path) and os.path.isfile(self._file_path)

    def file_path(self) -> str:
        return self._file_path


# ---------------------------------------------------------------------------
# Page 2 – Set resume point
# ---------------------------------------------------------------------------

class ResumePointPage(QWizardPage):
    """Wizard page: choose layer number or Z height."""

    def __init__(self, parent: Optional[QWizard] = None) -> None:
        super().__init__(parent)
        self.setTitle("Set Resume Point")
        self.setSubTitle("Enter the layer number or measured Z height where the print failed.")

        layout = QVBoxLayout(self)

        self.radio_layer = QRadioButton("Layer Number")
        self.radio_layer.setChecked(True)
        layout.addWidget(self.radio_layer)

        self.layer_spin = QSpinBox()
        self.layer_spin.setRange(1, 999999)
        self.layer_spin.setValue(1)
        layout.addWidget(self.layer_spin)

        self.radio_z = QRadioButton("Z Height (mm)")
        layout.addWidget(self.radio_z)

        self.z_spin = QDoubleSpinBox()
        self.z_spin.setRange(0.01, 9999.99)
        self.z_spin.setDecimals(2)
        self.z_spin.setSuffix(" mm")
        self.z_spin.setValue(0.20)
        self.z_spin.setEnabled(False)
        layout.addWidget(self.z_spin)

        self.radio_layer.toggled.connect(lambda on: self.layer_spin.setEnabled(on))
        self.radio_z.toggled.connect(lambda on: self.z_spin.setEnabled(on))

    def use_layer(self) -> bool:
        return self.radio_layer.isChecked()

    def layer_num(self) -> int:
        return self.layer_spin.value()

    def z_height(self) -> float:
        return self.z_spin.value()


# ---------------------------------------------------------------------------
# Page 3 – Confirm
# ---------------------------------------------------------------------------

class ConfirmPage(QWizardPage):
    """Wizard page: show summary and confirm generation."""

    def __init__(self, parent: Optional[QWizard] = None) -> None:
        super().__init__(parent)
        self.setTitle("Confirm")
        self.setSubTitle("Review the settings below. Click Finish to generate the resume file.")

        layout = QVBoxLayout(self)
        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)

    def initializePage(self) -> None:  # type: ignore[override]
        wizard: ResumeWizard = self.wizard()  # type: ignore[assignment]
        lines: list[str] = []
        lines.append(f"<b>File:</b> {Path(wizard.gcode_path()).name}")

        if wizard.resume_page.use_layer():
            lines.append(f"<b>Resume at layer:</b> {wizard.resume_page.layer_num()}")
        else:
            lines.append(f"<b>Resume at Z:</b> {wizard.resume_page.z_height():.2f} mm")

        lines.append(f"<b>Profile:</b> default_marlin")
        self.summary_label.setText("<br>".join(lines))


# ---------------------------------------------------------------------------
# Wizard
# ---------------------------------------------------------------------------

class ResumeWizard(QWizard):
    """Step-by-step wizard for resume G-code generation."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("FailFixer Wizard")
        self.setMinimumSize(440, 340)

        self.file_page = FilePickerPage()
        self.resume_page = ResumePointPage()
        self.confirm_page = ConfirmPage()

        self.addPage(self.file_page)
        self.addPage(self.resume_page)
        self.addPage(self.confirm_page)

        self.controller = FailFixerController()

    def gcode_path(self) -> str:
        return self.file_page.file_path()

    def accept(self) -> None:  # type: ignore[override]
        """Called when user clicks Finish — generate the file."""
        params: dict = {
            "gcode_path": self.gcode_path(),
            "profile": "default_marlin",
        }
        if self.resume_page.use_layer():
            params["layer_num"] = self.resume_page.layer_num()
            tag = f"resume_layer{params['layer_num']:04d}"
        else:
            params["z_height"] = self.resume_page.z_height()
            tag = f"resume_z{params['z_height']:.2f}".replace(".", "_")

        src = Path(params["gcode_path"])
        default_name = f"{src.stem}_{tag}.gcode"
        default_dir = str(src.parent / default_name)

        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Resume G-code",
            default_dir,
            "G-code Files (*.gcode);;All Files (*)",
        )
        if not save_path:
            return  # user cancelled — stay in wizard

        try:
            result = self.controller.process(
                gcode_path=params["gcode_path"],
                layer_num=params.get("layer_num"),
                z_height=params.get("z_height"),
                z_offset=0.0,
                profile=params.get("profile", "default_marlin"),
                output_path=save_path,
            )
            QMessageBox.information(
                self,
                "Success",
                f"Resume G-code saved to:\n{result.output_path}",
            )
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))
            return  # stay in wizard on error

        super().accept()
