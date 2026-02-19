from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from betflow.analysis.structure_metrics import RunnerLadder
from betflow.filter_config import HorseSelectionFilters


@dataclass(frozen=True)
class SelectionDecision:
    runner: RunnerLadder
    eligible: bool
    reasons: List[str]


def evaluate_horse_selections(
    ladders: List[RunnerLadder],
    filters: HorseSelectionFilters,
) -> List[SelectionDecision]:
    decisions: List[SelectionDecision] = []

    for runner in ladders:
        reasons: List[str] = []
        odds = runner.best_back
        lay = runner.best_lay

        if odds is None:
            reasons.append("✗ missing back price")
            decisions.append(SelectionDecision(runner=runner, eligible=False, reasons=reasons))
            continue

        if filters.min_odds <= odds <= filters.max_odds:
            reasons.append(f"✓ odds {odds:.2f} in [{filters.min_odds:.2f}–{filters.max_odds:.2f}]")
            odds_ok = True
        else:
            reasons.append(f"✗ odds {odds:.2f} outside [{filters.min_odds:.2f}–{filters.max_odds:.2f}]")
            odds_ok = False

        spread: Optional[float] = None
        if lay is not None and lay >= odds:
            spread = lay - odds

        if spread is None:
            reasons.append("✗ spread unavailable")
            spread_ok = False
        elif spread <= filters.max_spread:
            reasons.append(f"✓ spread {spread:.2f} <= {filters.max_spread:.2f}")
            spread_ok = True
        else:
            reasons.append(f"✗ spread {spread:.2f} > {filters.max_spread:.2f}")
            spread_ok = False

        decisions.append(SelectionDecision(runner=runner, eligible=odds_ok and spread_ok, reasons=reasons))

    return decisions
