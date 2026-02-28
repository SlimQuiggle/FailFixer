"""G-code parser for FailFixer.

Parses G-code files with layer detection priority:
  1. ;LAYER:<n> comment markers
  2. ;LAYER_CHANGE or similar patterns
  3. Fallback: Z increases via G0/G1 Z moves

Detects and preserves printer state: units, positioning mode,
extruder mode, bed temp, nozzle temp.

Handles files up to 50 MB efficiently (target: parse < 3 s).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO


# ---------------------------------------------------------------------------
# Compiled regexes — built once at module level for speed
# ---------------------------------------------------------------------------

_RE_LAYER_NUM = re.compile(r";\s*LAYER\s*:\s*(-?\d+)", re.IGNORECASE)
_RE_LAYER_CHANGE = re.compile(r";\s*LAYER_CHANGE", re.IGNORECASE)
_RE_Z_MOVE = re.compile(
    r"^G[01]\s.*Z\s*([+-]?\d+\.?\d*)", re.IGNORECASE
)
_RE_TEMP_BED = re.compile(
    r"^M(140|190)\b.*?[SR]\s*([+-]?\d+\.?\d*)", re.IGNORECASE
)
_RE_TEMP_NOZZLE = re.compile(
    r"^M(104|109)\b.*?[SR]\s*([+-]?\d+\.?\d*)", re.IGNORECASE
)
_RE_KLIPPER_SET_HEATER = re.compile(
    r"^SET_HEATER_TEMPERATURE\b.*?\bHEATER\s*=\s*([A-Z0-9_]+)\b.*?\bTARGET\s*=\s*([+-]?\d+\.?\d*)",
    re.IGNORECASE,
)
_RE_KLIPPER_TEMP_WAIT = re.compile(
    r"^TEMPERATURE_WAIT\b.*?\bSENSOR\s*=\s*([A-Z0-9_]+)\b.*?\b(?:MINIMUM|MAXIMUM|TARGET)\s*=\s*([+-]?\d+\.?\d*)",
    re.IGNORECASE,
)
# Klipper START_PRINT / PRINT_START macros that pass temps as params
_RE_KLIPPER_MACRO_EXTRUDER = re.compile(
    r"\b(?:EXTRUDER_TEMP|EXTRUDER|HOTEND|NOZZLE|NOZZLE_TEMP|HOTEND_TEMP)\s*=\s*([+-]?\d+\.?\d*)",
    re.IGNORECASE,
)
_RE_KLIPPER_MACRO_BED = re.compile(
    r"\b(?:BED_TEMP|BED|BED_TEMPERATURE)\s*=\s*([+-]?\d+\.?\d*)",
    re.IGNORECASE,
)
# Comment-embedded temp hints from slicer metadata
_RE_COMMENT_NOZZLE_TEMP = re.compile(
    r";\s*(?:nozzle_temperature|temperature_extruder|extruder_temperature|hotend_temp|nozzle_temp|first_layer_temperature)\s*=\s*(\d+\.?\d*)",
    re.IGNORECASE,
)
_RE_COMMENT_BED_TEMP = re.compile(
    r";\s*(?:bed_temperature|first_layer_bed_temperature|heated_bed_temperature)\s*=\s*(\d+\.?\d*)",
    re.IGNORECASE,
)
_RE_UNIT = re.compile(r"^G(20|21)\b", re.IGNORECASE)
_RE_POS_MODE = re.compile(r"^G(90|91)\b", re.IGNORECASE)
_RE_EXT_MODE = re.compile(r"^M(82|83)\b", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class PrinterState:
    """Detected printer state from the G-code preamble / body."""

    units: str = "G21"           # G20 = inches, G21 = mm
    positioning: str = "G90"     # G90 = absolute, G91 = relative
    extruder_mode: str = "M82"   # M82 = absolute, M83 = relative
    bed_temp: float = 0.0
    nozzle_temp: float = 0.0


@dataclass
class LayerInfo:
    """Describes a single detected layer."""

    number: int                   # 0-based layer index
    z_height: float               # Z height in mm
    start_line: int               # first line index (0-based) of layer
    end_line: int = -1            # last line index (inclusive, set during finalization)


@dataclass
class ParsedGCode:
    """Result of parsing a G-code file."""

    lines: list[str]                        # raw lines (no trailing newlines)
    layers: list[LayerInfo] = field(default_factory=list)
    state: PrinterState = field(default_factory=PrinterState)
    header_end_line: int = 0                # line index where header ends
    detection_method: str = "none"          # "comment_layer", "layer_change", "z_move"
    source_filename: str = "unknown"        # original filename (basename)
    preamble_lines: list[str] = field(default_factory=list)  # original pre-layer lines


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


class GCodeParser:
    """Streaming G-code parser optimised for large files."""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def parse_file(self, path: str | Path) -> ParsedGCode:
        """Parse a G-code file on disk and return *ParsedGCode*."""
        path = Path(path)
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            result = self._parse_stream(fh)
        result.source_filename = path.name
        return result

    def parse_string(self, text: str) -> ParsedGCode:
        """Parse G-code from a string (convenience for tests)."""
        import io
        return self._parse_stream(io.StringIO(text))

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _parse_stream(self, stream: IO[str]) -> ParsedGCode:
        lines: list[str] = []
        state = PrinterState()
        layer_markers: list[tuple[int, int, float | None]] = []  # (line_idx, layer_num, z)
        layer_change_markers: list[int] = []                      # line indices
        z_changes: list[tuple[int, float]] = []                   # (line_idx, z)
        current_z: float = 0.0
        header_end: int = 0
        first_move_seen: bool = False

        # Local references for hot-loop speed
        lines_append = lines.append
        re_layer_num_search = _RE_LAYER_NUM.search
        re_layer_change_search = _RE_LAYER_CHANGE.search
        re_z_move_match = _RE_Z_MOVE.match
        re_temp_bed_match = _RE_TEMP_BED.match
        re_temp_nozzle_match = _RE_TEMP_NOZZLE.match
        re_klipper_set_heater_match = _RE_KLIPPER_SET_HEATER.match
        re_klipper_temp_wait_match = _RE_KLIPPER_TEMP_WAIT.match
        re_klipper_macro_extruder_search = _RE_KLIPPER_MACRO_EXTRUDER.search
        re_klipper_macro_bed_search = _RE_KLIPPER_MACRO_BED.search
        re_unit_match = _RE_UNIT.match
        re_pos_mode_match = _RE_POS_MODE.match
        re_ext_mode_match = _RE_EXT_MODE.match

        for idx, raw in enumerate(stream):
            line = raw.rstrip("\n\r")
            lines_append(line)
            stripped = line.strip()

            if not stripped:
                continue

            first_char = stripped[0]

            # --- Comment-only lines (fast path) ---
            if first_char == ";":
                # Only check layer markers in comments that could match
                upper5 = stripped[1:7].upper()
                if "LAYER" in upper5:
                    m = re_layer_num_search(stripped)
                    if m:
                        layer_markers.append((idx, int(m.group(1)), None))
                    elif re_layer_change_search(stripped):
                        layer_change_markers.append(idx)
                # Slicer comment metadata for temps (fallback)
                if state.nozzle_temp == 0.0:
                    m_cn = _RE_COMMENT_NOZZLE_TEMP.search(stripped)
                    if m_cn:
                        temp = float(m_cn.group(1))
                        if temp > 0:
                            state.nozzle_temp = temp
                if state.bed_temp == 0.0:
                    m_cb = _RE_COMMENT_BED_TEMP.search(stripped)
                    if m_cb:
                        temp = float(m_cb.group(1))
                        if temp > 0:
                            state.bed_temp = temp
                continue

            # --- Command lines ---
            semi = stripped.find(";")
            cmd = stripped[:semi].rstrip() if semi >= 0 else stripped
            if not cmd:
                continue
            cmd_upper = cmd.upper()

            # Fast-classify by first character to skip regex on bulk G1 moves
            fc = first_char.upper()

            if fc == "G":

                # G0/G1 lines are ~95% of all commands
                if cmd_upper[1:2] in ("0", "1"):
                    # Only run Z regex if 'Z' appears in the line
                    if "Z" in cmd_upper or "z" in cmd:
                        m_z = re_z_move_match(cmd_upper)
                        if m_z:
                            new_z = float(m_z.group(1))
                            if new_z != current_z:
                                z_changes.append((idx, new_z))
                                current_z = new_z
                    # Header end heuristic
                    if not first_move_seen and ("E" in cmd_upper or "e" in cmd):
                        first_move_seen = True
                        header_end = idx
                else:
                    # Less common G-codes: G20/G21, G90/G91, G28, G92 …
                    m_unit = re_unit_match(cmd_upper)
                    if m_unit:
                        state.units = f"G{m_unit.group(1)}"
                    m_pos = re_pos_mode_match(cmd_upper)
                    if m_pos:
                        state.positioning = f"G{m_pos.group(1)}"

            elif fc == "M":
                # Quick prefix check to avoid regex on irrelevant M-codes
                prefix3 = cmd_upper[1:4]  # digits after 'M'
                if prefix3.startswith(("140", "190")):
                    m_bed = re_temp_bed_match(cmd_upper)
                    if m_bed:
                        temp = float(m_bed.group(2))
                        if temp > 0:
                            state.bed_temp = temp
                elif prefix3.startswith(("104", "109")):
                    m_noz = re_temp_nozzle_match(cmd_upper)
                    if m_noz:
                        temp = float(m_noz.group(2))
                        if temp > 0:
                            state.nozzle_temp = temp
                elif prefix3.startswith(("82", "83")):
                    m_ext = re_ext_mode_match(cmd_upper)
                    if m_ext:
                        state.extruder_mode = f"M{m_ext.group(1)}"

            elif cmd_upper.startswith("SET_HEATER_TEMPERATURE"):
                m_heat = re_klipper_set_heater_match(cmd_upper)
                if m_heat:
                    heater = m_heat.group(1).upper()
                    temp = float(m_heat.group(2))
                    if temp > 0:
                        if "BED" in heater:
                            state.bed_temp = temp
                        elif "EXTRUDER" in heater:
                            state.nozzle_temp = temp

            elif cmd_upper.startswith("TEMPERATURE_WAIT"):
                m_wait = re_klipper_temp_wait_match(cmd_upper)
                if m_wait:
                    sensor = m_wait.group(1).upper()
                    temp = float(m_wait.group(2))
                    if temp > 0:
                        if "BED" in sensor:
                            state.bed_temp = temp
                        elif "EXTRUDER" in sensor:
                            state.nozzle_temp = temp

            else:
                # Catch-all for Klipper macros like PRINT_START, START_PRINT, etc.
                # that pass temps as key=value parameters
                m_macro_ext = re_klipper_macro_extruder_search(cmd_upper)
                if m_macro_ext:
                    temp = float(m_macro_ext.group(1))
                    if temp > 0:
                        state.nozzle_temp = temp
                m_macro_bed = re_klipper_macro_bed_search(cmd_upper)
                if m_macro_bed:
                    temp = float(m_macro_bed.group(1))
                    if temp > 0:
                        state.bed_temp = temp

        # --- Build layer list from best available source ---
        result = ParsedGCode(lines=lines, state=state, header_end_line=header_end)
        # Capture preamble: everything before the first layer starts
        # Will be populated after layers are built

        if layer_markers:
            result.detection_method = "comment_layer"
            result.layers = self._layers_from_markers(layer_markers, len(lines))
            self._backfill_z(result.layers, z_changes)
        elif layer_change_markers:
            result.detection_method = "layer_change"
            result.layers = self._layers_from_change_markers(
                layer_change_markers, z_changes, len(lines)
            )
        elif z_changes:
            result.detection_method = "z_move"
            result.layers = self._layers_from_z_changes(z_changes, len(lines))
        # else: no layers detected (tiny / empty file)

        # Capture preamble (everything before first layer)
        if result.layers:
            first_layer_line = result.layers[0].start_line
            result.preamble_lines = lines[:first_layer_line]

        return result

    # ------------------------------------------------------------------
    # Layer building helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _layers_from_markers(
        markers: list[tuple[int, int, float | None]],
        total_lines: int,
    ) -> list[LayerInfo]:
        """Build layers from ;LAYER:<n> markers."""
        layers: list[LayerInfo] = []
        for i, (line_idx, num, z) in enumerate(markers):
            info = LayerInfo(number=num, z_height=z if z is not None else 0.0, start_line=line_idx)
            if layers:
                layers[-1].end_line = line_idx - 1
            layers.append(info)
        if layers:
            layers[-1].end_line = total_lines - 1
        return layers

    @staticmethod
    def _backfill_z(
        layers: list[LayerInfo],
        z_changes: list[tuple[int, float]],
    ) -> None:
        """Fill in z_height for layers that came from comment markers."""
        if not z_changes:
            return
        zi = 0
        for layer in layers:
            # Find the first Z change at or after the layer start
            while zi < len(z_changes) and z_changes[zi][0] < layer.start_line:
                zi += 1
            if zi < len(z_changes):
                layer.z_height = z_changes[zi][1]
            elif zi > 0:
                layer.z_height = z_changes[zi - 1][1]

    @staticmethod
    def _layers_from_change_markers(
        markers: list[int],
        z_changes: list[tuple[int, float]],
        total_lines: int,
    ) -> list[LayerInfo]:
        """Build layers from ;LAYER_CHANGE markers, pairing with Z changes."""
        layers: list[LayerInfo] = []
        zi = 0
        for i, line_idx in enumerate(markers):
            # Advance Z index to the nearest Z change at or after this marker
            while zi < len(z_changes) and z_changes[zi][0] < line_idx:
                zi += 1
            z = z_changes[zi][1] if zi < len(z_changes) else (
                z_changes[-1][1] if z_changes else 0.0
            )
            info = LayerInfo(number=i, z_height=z, start_line=line_idx)
            if layers:
                layers[-1].end_line = line_idx - 1
            layers.append(info)
        if layers:
            layers[-1].end_line = total_lines - 1
        return layers

    @staticmethod
    def _layers_from_z_changes(
        z_changes: list[tuple[int, float]],
        total_lines: int,
    ) -> list[LayerInfo]:
        """Fallback: each Z increase = new layer."""
        layers: list[LayerInfo] = []
        prev_z: float = -1.0
        layer_num = 0
        for line_idx, z in z_changes:
            if z > prev_z:
                info = LayerInfo(number=layer_num, z_height=z, start_line=line_idx)
                if layers:
                    layers[-1].end_line = line_idx - 1
                layers.append(info)
                layer_num += 1
                prev_z = z
        if layers:
            layers[-1].end_line = total_lines - 1
        return layers
