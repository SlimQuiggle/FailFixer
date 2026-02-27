"""G-code validator for FailFixer.

Validates output G-code to ensure:
  - No syntax errors on critical commands
  - Temperature commands are present
  - No Z collisions (Z doesn't go below resume Z unexpectedly)
  - Safe movement order (Z lift before XY travel)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum


class Severity(Enum):
    WARNING = "warning"
    ERROR = "error"


@dataclass
class ValidationIssue:
    """A single validation finding."""

    severity: Severity
    line_number: int      # 1-based for human display
    message: str
    code: str             # machine-readable short code


@dataclass
class ValidationResult:
    """Aggregate validation result."""

    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(i.severity == Severity.ERROR for i in self.issues)

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == Severity.WARNING]

    @property
    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == Severity.ERROR]

    def summary(self) -> str:
        if self.ok and not self.warnings:
            return "Validation passed with no issues."
        parts: list[str] = []
        if self.errors:
            parts.append(f"{len(self.errors)} error(s)")
        if self.warnings:
            parts.append(f"{len(self.warnings)} warning(s)")
        return "Validation: " + ", ".join(parts) + "."


# Compiled patterns
_RE_G_COMMAND = re.compile(r"^G(\d+)", re.IGNORECASE)
_RE_M_COMMAND = re.compile(r"^M(\d+)", re.IGNORECASE)
_RE_Z_PARAM = re.compile(r"Z\s*([+-]?\d+\.?\d*)", re.IGNORECASE)
_RE_X_PARAM = re.compile(r"X\s*([+-]?\d+\.?\d*)", re.IGNORECASE)
_RE_Y_PARAM = re.compile(r"Y\s*([+-]?\d+\.?\d*)", re.IGNORECASE)
_RE_S_PARAM = re.compile(r"S\s*(\d+\.?\d*)", re.IGNORECASE)

# Known G/M codes we consider valid
_VALID_G = {0, 1, 4, 10, 11, 20, 21, 28, 29, 80, 90, 91, 92}
_VALID_M = {
    0, 1, 17, 18, 19, 20, 21, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33,
    42, 73, 75, 76, 77, 78, 80, 81, 82, 83, 84, 85,
    92, 104, 105, 106, 107, 108, 109, 110, 111, 112,
    114, 115, 116, 117, 118, 119, 120, 121, 122,
    140, 141, 143, 149, 150, 155, 163, 164, 190, 191,
    200, 201, 202, 203, 204, 205, 206, 207, 208, 209,
    210, 211, 212, 218, 220, 221, 226,
    240, 250, 251, 260, 261, 280, 281, 290, 291,
    300, 301, 302, 303, 304, 305,
    400, 401, 402, 403, 404, 405, 406, 407, 408,
    420, 421, 422, 423, 425,
    500, 501, 502, 503, 504, 505, 510, 511, 512,
    524, 540, 552, 569, 575, 593,
    600, 601, 602, 603, 605, 665,
    701, 702, 703, 704, 710, 851, 852, 860, 861, 862,
    900, 906, 907, 908, 910, 911, 912, 913, 914, 915,
    997, 998, 999,
}


class Validator:
    """Validate a list of G-code output lines."""

    def validate(
        self,
        lines: list[str],
        resume_z: float = 0.0,
        safe_lift_z: float = 10.0,
    ) -> ValidationResult:
        result = ValidationResult()

        has_bed_temp = False
        has_nozzle_temp = False
        has_z_lift = False
        has_xy_move = False
        first_xy_line: int | None = None
        first_z_line: int | None = None
        current_z: float = 0.0
        in_header = True

        for idx, raw_line in enumerate(lines):
            line_num = idx + 1
            stripped = raw_line.strip()

            # Skip blanks / pure comments
            if not stripped or stripped.startswith(";"):
                if stripped == "; --- End Resume Header ---":
                    in_header = False
                elif stripped.startswith("; === Resume Print from Layer"):
                    in_header = False
                continue

            cmd = stripped.split(";", 1)[0].strip()
            if not cmd:
                continue

            cmd_upper = cmd.upper()

            # --- Syntax check: known G/M codes ---
            gm = _RE_G_COMMAND.match(cmd_upper)
            if gm:
                code = int(gm.group(1))
                if code not in _VALID_G:
                    # Not necessarily an error — just a warning for unusual codes
                    result.issues.append(ValidationIssue(
                        severity=Severity.WARNING,
                        line_number=line_num,
                        message=f"Unusual G-code: G{code}",
                        code="UNUSUAL_G",
                    ))

            mm = _RE_M_COMMAND.match(cmd_upper)
            if mm:
                code = int(mm.group(1))
                if code not in _VALID_M:
                    result.issues.append(ValidationIssue(
                        severity=Severity.WARNING,
                        line_number=line_num,
                        message=f"Unusual M-code: M{code}",
                        code="UNUSUAL_M",
                    ))

            # --- Temperature detection ---
            if cmd_upper.startswith(("M140", "M190")):
                s = _RE_S_PARAM.search(cmd_upper)
                if s and float(s.group(1)) > 0:
                    has_bed_temp = True
            if cmd_upper.startswith(("M104", "M109")):
                s = _RE_S_PARAM.search(cmd_upper)
                if s and float(s.group(1)) > 0:
                    has_nozzle_temp = True

            # --- Movement safety ---
            z_match = _RE_Z_PARAM.search(cmd_upper)
            x_match = _RE_X_PARAM.search(cmd_upper)
            y_match = _RE_Y_PARAM.search(cmd_upper)

            if z_match and cmd_upper.startswith(("G0", "G1")):
                new_z = float(z_match.group(1))
                current_z = new_z
                if not has_z_lift:
                    has_z_lift = True
                    first_z_line = line_num

            if (x_match or y_match) and cmd_upper.startswith(("G0", "G1")):
                if not has_xy_move:
                    has_xy_move = True
                    first_xy_line = line_num

            # --- Z collision: only check after header ---
            if not in_header and z_match and cmd_upper.startswith(("G0", "G1")):
                new_z = float(z_match.group(1))
                # Warn if Z goes below resume_z minus a small tolerance
                if new_z < resume_z - 0.5:
                    result.issues.append(ValidationIssue(
                        severity=Severity.WARNING,
                        line_number=line_num,
                        message=(
                            f"Z moves to {new_z:.3f} mm, which is below "
                            f"resume Z {resume_z:.3f} mm. Possible collision."
                        ),
                        code="Z_COLLISION",
                    ))

            # --- Detect G28 Z (forbidden) ---
            if cmd_upper.startswith("G28"):
                if "Z" in cmd_upper:
                    result.issues.append(ValidationIssue(
                        severity=Severity.ERROR,
                        line_number=line_num,
                        message="G28 Z detected — auto-homing Z is forbidden in resume files.",
                        code="Z_HOME",
                    ))

        # --- Post-scan checks ---
        if not has_bed_temp:
            result.issues.append(ValidationIssue(
                severity=Severity.ERROR,
                line_number=0,
                message="No bed temperature command found.",
                code="MISSING_BED_TEMP",
            ))

        if not has_nozzle_temp:
            result.issues.append(ValidationIssue(
                severity=Severity.ERROR,
                line_number=0,
                message="No nozzle temperature command found.",
                code="MISSING_NOZZLE_TEMP",
            ))

        # Z must be lifted before first XY move
        if has_xy_move and first_xy_line is not None:
            if first_z_line is None or first_z_line > first_xy_line:
                result.issues.append(ValidationIssue(
                    severity=Severity.ERROR,
                    line_number=first_xy_line,
                    message="XY movement before Z lift — risk of collision.",
                    code="XY_BEFORE_Z",
                ))

        return result
