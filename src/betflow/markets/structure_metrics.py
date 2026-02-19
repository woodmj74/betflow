from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional


@dataclass(frozen=True)
class RunnerPrice:
    selection_id: int
    runner_number: Optional[int]  # may be None if we can't map
    name: str

    best_back: Optional[float]
    best_lay: Optional[float]

    @property
    def spread(self) -> Optional[float]:
        if self.best_back is None or self.best_lay is None:
            return None
        return self.best_lay - self.best_back

    @property
    def implied_from_back(self) -> Optional[float]:
        if self.best_back is None or self.best_back <= 1.0:
            return None
        return 1.0 / self.best_back


@dataclass(frozen=True)
class StructureMetrics:
    runner_count: int

    top_n: int
    top_n_implied_sum: float

    top_cluster_n: int
    top_cluster_implied_sum: float

    # simple tier-break measure between runner k and k+1 (by back price ordering)
    max_tier_jump_ratio_top: float  # e.g. 1.35 means +35% jump at best point in top region

    # soup detector: proportion of top K runners within a tight band
    soup_top_k: int
    soup_band_ratio: float  # max_price / min_price for top_k
    is_soup: bool


def _tier_jump_ratio(sorted_prices: list[float], region_k: int) -> float:
    """
    Compute the maximum adjacent ratio (p[i+1] / p[i]) within the first `region_k` runners.
    Prices assumed sorted ascending.
    """
    if len(sorted_prices) < 2:
        return 1.0
    region_k = max(2, min(region_k, len(sorted_prices)))
    max_ratio = 1.0
    for i in range(region_k - 1):
        a, b = sorted_prices[i], sorted_prices[i + 1]
        if a > 0:
            max_ratio = max(max_ratio, b / a)
    return max_ratio


def compute_structure_metrics(
    runners_sorted_by_back: list[RunnerPrice],
    *,
    top_cluster_n: int = 3,
    top_region_for_tier: int = 6,
    soup_top_k: int = 5,
    soup_band_ratio_threshold: float = 1.25,
) -> StructureMetrics:
    """
    runners_sorted_by_back: list ordered by best_back ascending (favourite first)

    - top_cluster implied sum uses best_back implied probabilities
    - tier jump ratio uses best_back prices in the top region
    - soup: top K runners are considered 'soup' if max/min <= threshold (very clustered)
    """
    runner_count = len(runners_sorted_by_back)

    # Extract usable back prices
    back_prices = [r.best_back for r in runners_sorted_by_back if r.best_back is not None]
    back_prices_sorted = [p for p in back_prices if p is not None]
    back_prices_sorted.sort()

    # Top-N implied sum (where N equals actual available or requested)
    top_n = min(10, runner_count)
    top_n_implied_sum = 0.0
    for r in runners_sorted_by_back[:top_n]:
        imp = r.implied_from_back
        if imp is not None:
            top_n_implied_sum += imp

    # Top cluster implied sum
    top_cluster_n_eff = min(top_cluster_n, runner_count)
    top_cluster_implied_sum = 0.0
    for r in runners_sorted_by_back[:top_cluster_n_eff]:
        imp = r.implied_from_back
        if imp is not None:
            top_cluster_implied_sum += imp

    # Tier break ratio in top region
    tier_region_prices = []
    for r in runners_sorted_by_back[: min(top_region_for_tier, runner_count)]:
        if r.best_back is not None:
            tier_region_prices.append(r.best_back)
    max_jump_ratio_top = _tier_jump_ratio(tier_region_prices, len(tier_region_prices))

    # Soup detector on top K
    k = min(soup_top_k, runner_count)
    top_k_prices = [r.best_back for r in runners_sorted_by_back[:k] if r.best_back is not None]
    if len(top_k_prices) >= 2:
        mn, mx = min(top_k_prices), max(top_k_prices)
        band_ratio = (mx / mn) if mn > 0 else 999.0
    else:
        band_ratio = 999.0
    is_soup = band_ratio <= soup_band_ratio_threshold

    return StructureMetrics(
        runner_count=runner_count,
        top_n=top_n,
        top_n_implied_sum=top_n_implied_sum,
        top_cluster_n=top_cluster_n_eff,
        top_cluster_implied_sum=top_cluster_implied_sum,
        max_tier_jump_ratio_top=max_jump_ratio_top,
        soup_top_k=k,
        soup_band_ratio=band_ratio,
        is_soup=is_soup,
    )


def market_gate_passes(
    m: StructureMetrics,
    *,
    min_top_cluster_implied: float = 0.65,
    max_soup_band_ratio: float = 1.20,
    min_tier_jump_ratio: float = 1.25,
) -> tuple[bool, list[str]]:
    """
    First-cut gate rules (we'll tune + move to YAML later).
    """
    reasons: list[str] = []

    if m.top_cluster_implied_sum < min_top_cluster_implied:
        reasons.append(
            f"FAIL anchor: top{m.top_cluster_n} implied={m.top_cluster_implied_sum:.3f} < {min_top_cluster_implied:.3f}"
        )
    else:
        reasons.append(
            f"PASS anchor: top{m.top_cluster_n} implied={m.top_cluster_implied_sum:.3f} >= {min_top_cluster_implied:.3f}"
        )

    # Soup veto: topK too tightly packed (ultra-flat favourites cluster)
    if m.soup_band_ratio <= max_soup_band_ratio:
        reasons.append(
            f"FAIL soup: top{m.soup_top_k} band ratio={m.soup_band_ratio:.3f} <= {max_soup_band_ratio:.3f}"
        )
    else:
        reasons.append(
            f"PASS soup: top{m.soup_top_k} band ratio={m.soup_band_ratio:.3f} > {max_soup_band_ratio:.3f}"
        )

    # Tier break: needs at least one meaningful jump in top region
    if m.max_tier_jump_ratio_top < min_tier_jump_ratio:
        reasons.append(
            f"FAIL tier: max jump={m.max_tier_jump_ratio_top:.3f} < {min_tier_jump_ratio:.3f}"
        )
    else:
        reasons.append(
            f"PASS tier: max jump={m.max_tier_jump_ratio_top:.3f} >= {min_tier_jump_ratio:.3f}"
        )

    passed = all(r.startswith("PASS") for r in reasons)
    return passed, reasons
