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


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("FailFixer")

    # Set app-level icon (shows in Windows taskbar)
    logo_path = Path(__file__).resolve().parent / "assets" / "logo.png"
    if logo_path.exists():
        app.setWindowIcon(QIcon(str(logo_path)))

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
