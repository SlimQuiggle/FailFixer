"""Launch FailFixer GUI."""
import sys
from pathlib import Path

# Ensure the projects/ directory is on sys.path so 'failfixer' package resolves
project_root = Path(__file__).resolve().parent.parent  # projects/
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication
from failfixer.ui.main_window import MainWindow


def _runtime_root() -> Path:
    """Root folder for source and PyInstaller onefile runtime."""
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))


def _assets_dir() -> Path:
    root = _runtime_root()
    candidates = [
        root / "assets",
        root / "failfixer" / "assets",
        Path(__file__).resolve().parent / "assets",
    ]
    for p in candidates:
        if p.is_dir():
            return p
    return candidates[0]


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("FailFixer")

    # Set app-level icon (shows in Windows taskbar)
    icon_path = _assets_dir() / "logo.ico"
    if not icon_path.exists():
        icon_path = _assets_dir() / "logo.png"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
