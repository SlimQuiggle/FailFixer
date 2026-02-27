"""Printer profile loader for FailFixer.

Loads printer profiles from JSON files. Falls back to built-in
defaults if no profile file is found.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class PrinterProfile:
    """A printer configuration profile."""

    firmware: str = "marlin"
    safe_lift_mm: float = 10.0
    park_x: float = 0.0
    park_y: float = 200.0
    tolerance_mm: float = 0.15
    bed_mesh_cmd: str = "M420 S1"

    @classmethod
    def from_dict(cls, data: dict) -> PrinterProfile:
        return cls(
            firmware=str(data.get("firmware", "marlin")),
            safe_lift_mm=float(data.get("safe_lift_mm", 10.0)),
            park_x=float(data.get("park_x", 0.0)),
            park_y=float(data.get("park_y", 200.0)),
            tolerance_mm=float(data.get("tolerance_mm", 0.15)),
            bed_mesh_cmd=str(data.get("bed_mesh_cmd", "M420 S1")),
        )


def _default_profiles_dir() -> Path:
    """Resolve profiles dir for source and PyInstaller runtimes."""
    candidates: list[Path] = []

    # PyInstaller onefile extraction root
    if hasattr(sys, "_MEIPASS"):
        root = Path(getattr(sys, "_MEIPASS"))
        candidates.extend([
            root / "profiles",
            root / "failfixer" / "profiles",
        ])

    # Source fallback
    candidates.append(Path(__file__).resolve().parent.parent / "profiles")

    for p in candidates:
        if p.is_dir():
            return p
    return candidates[0]


class ProfileLoader:
    """Loads *PrinterProfile* from JSON files."""

    # Default search paths (relative to project root)
    _DEFAULT_PROFILE_NAME = "default_marlin.json"

    def __init__(self, profiles_dir: str | Path | None = None) -> None:
        if profiles_dir is not None:
            self._dir = Path(profiles_dir)
        else:
            self._dir = _default_profiles_dir()

    @property
    def profiles_dir(self) -> Path:
        return self._dir

    def list_profiles(self) -> list[str]:
        """Return the names of available profile JSON files."""
        if not self._dir.is_dir():
            return []
        return sorted(p.name for p in self._dir.glob("*.json"))

    def load(self, name: str | None = None) -> PrinterProfile:
        """Load a profile by filename (within *profiles_dir*).

        Returns the built-in default if the file doesn't exist.
        """
        target = name or self._DEFAULT_PROFILE_NAME
        path = self._dir / target

        if not path.is_file():
            return PrinterProfile()  # built-in defaults

        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)

        return PrinterProfile.from_dict(data)

    def load_path(self, path: str | Path) -> PrinterProfile:
        """Load a profile from an arbitrary path."""
        path = Path(path)
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return PrinterProfile.from_dict(data)
