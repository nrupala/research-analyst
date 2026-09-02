"""Mental-model lens registry (Phase 5).

Runs every registered lens over the same typed LensInput and returns typed
LensResults. Adding a lens = drop a module in this package + register it here.
"""
# Module: research_analyst/engines/lenses/__init__.py | Version: 1.0 | Updated: 2026-09-02

from __future__ import annotations

from . import graham, greenblatt, lynch
from .base import ATTRIBUTION, LensInput, LensResult, LensSignal

LENSES: dict[str, object] = {
    "graham": graham.run,
    "greenblatt": greenblatt.run,
    "lynch": lynch.run,
}

LENS_ORDER = ["graham", "greenblatt", "lynch"]


def run_all(data: LensInput) -> list[LensResult]:
    """Run every registered lens over the input. Never raises: a failing lens
    yields an empty educational LensResult with the gap noted."""
    results: list[LensResult] = []
    for key in LENS_ORDER:
        fn = LENSES.get(key)
        if fn is None:
            continue
        try:
            result = fn(data)
        except Exception as e:  # lens isolation: one bad lens must not kill the report
            result = LensResult(
                lens=key,
                name=key.capitalize(),
                summary="Lens could not be computed for this security.",
                signals=[LensSignal(
                    label="Computation", value="error", read="neutral",
                    note=f"{type(e).__name__}: {e}"[:200],
                )],
                attribution=ATTRIBUTION.format(name=key.capitalize()),
            )
        results.append(result)
    return results


__all__ = ["ATTRIBUTION", "LensInput", "LensResult", "LensSignal", "LENSES", "run_all"]
