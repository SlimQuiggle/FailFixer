"""Layer mapper for FailFixer.

Maps between layer numbers and Z heights.  Supports lookup by:
  - layer number (int)
  - measured Z height (float)

Warns when a measured Z is within ±tolerance of a layer boundary
but not an exact match.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .gcode_parser import LayerInfo


@dataclass
class LayerMatch:
    """Result of a layer lookup."""

    layer: LayerInfo
    exact: bool = True
    delta_mm: float = 0.0       # signed distance from nearest layer Z
    warning: str | None = None  # human-readable warning if fuzzy match


class LayerMapper:
    """Bidirectional layer ↔ Z mapper."""

    def __init__(
        self,
        layers: Sequence[LayerInfo],
        tolerance_mm: float = 0.15,
    ) -> None:
        if not layers:
            raise ValueError("Layer list is empty — cannot build mapper.")
        self._layers = list(layers)
        self._tolerance = tolerance_mm
        # Build quick-lookup indices
        self._by_number: dict[int, LayerInfo] = {l.number: l for l in self._layers}
        # Z sorted for binary-search style lookup
        self._z_sorted: list[LayerInfo] = sorted(self._layers, key=lambda l: l.z_height)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def layer_count(self) -> int:
        return len(self._layers)

    @property
    def min_layer(self) -> int:
        return self._layers[0].number

    @property
    def max_layer(self) -> int:
        return self._layers[-1].number

    @property
    def min_z(self) -> float:
        return self._z_sorted[0].z_height

    @property
    def max_z(self) -> float:
        return self._z_sorted[-1].z_height

    def by_layer_number(self, number: int) -> LayerMatch:
        """Look up a layer by its number.

        Raises *KeyError* if the layer number doesn't exist.
        """
        layer = self._by_number.get(number)
        if layer is None:
            raise KeyError(
                f"Layer {number} not found. "
                f"Valid range: {self.min_layer}–{self.max_layer}"
            )
        return LayerMatch(layer=layer, exact=True, delta_mm=0.0)

    def by_z_height(self, z_mm: float) -> LayerMatch:
        """Find the layer closest to *z_mm*.

        Raises *ValueError* if *z_mm* is further than *tolerance_mm*
        from every known layer.
        """
        best: LayerInfo | None = None
        best_delta: float = float("inf")

        # Linear scan is fine for typical layer counts (< 5 000).
        for layer in self._z_sorted:
            delta = z_mm - layer.z_height
            if abs(delta) < abs(best_delta):
                best_delta = delta
                best = layer

        assert best is not None  # guaranteed because __init__ rejects empty list

        if best_delta == 0.0:
            return LayerMatch(layer=best, exact=True, delta_mm=0.0)

        if abs(best_delta) <= self._tolerance:
            warning = (
                f"Measured Z {z_mm:.3f} mm is {best_delta:+.3f} mm from "
                f"layer {best.number} (Z {best.z_height:.3f} mm). "
                f"Within tolerance (±{self._tolerance} mm) — using layer {best.number}."
            )
            return LayerMatch(
                layer=best,
                exact=False,
                delta_mm=best_delta,
                warning=warning,
            )

        raise ValueError(
            f"Measured Z {z_mm:.3f} mm is {abs(best_delta):.3f} mm away from "
            f"the nearest layer (layer {best.number} @ Z {best.z_height:.3f} mm). "
            f"This exceeds the tolerance of ±{self._tolerance} mm."
        )

    def all_layers(self) -> list[LayerInfo]:
        """Return all layers sorted by number."""
        return list(self._layers)
