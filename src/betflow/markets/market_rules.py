from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from betflow.filter_config import FilterConfig
from betflow.markets.structure_metrics import MarketStructureMetrics


# ----------------------------
# Helper models
# ----------------------------

@dataclass(frozen=True)
class RuleResult:
    ok: bool
    label: str
    detail: str


# ----------------------------
# Small helpers
# ----------------------------

def _get(d: dict, path: list[str], default: Any = None) -> Any:
    cur: Any = d
    for p in path:
        if not isinstance(cur, dict) or p not in cur:
            return default
        cur = cur[p]
    return cur


def _region_for_country(cfg: FilterConfig, country: str | None) -> Optional[str]:
    if not country:
        return None

    cc = country.strip().upper()

    # cfg.regions is a dict keyed by region code (e.g. "GB", "IE")
    # RegionConfig also contains market_countries which should include cc.
    region = (cfg.regions or {}).get(cc)
    if region is not None:
        return cc

    # Fallback: scan by market_countries if keys ever diverge
    for region_code, region in (cfg.regions or {}).items():
        mc = getattr(region, "market_countries", None) or []
        if cc in [str(x).upper() for x in mc]:
            return str(region_code)

    return None



# ----------------------------
# Rule evaluation
# ----------------------------

def evaluate_market_rules(
    *,
    market_catalogue: Dict[str, Any],
    market_book: Dict[str, Any],
    metrics: MarketStructureMetrics,
    cfg: FilterConfig,
) -> Tuple[bool, Optional[str], List[RuleResult]]:
    """
    Evaluate market-level eligibility.
    Returns:
      accepted: bool
      region_code: Optional[str]
      results: list of RuleResult with pass/fail + human details
    """
    results: List[RuleResult] = []

    # Support both dataclass and pydantic-ish configs
    cfg_dict = cfg.dict() if hasattr(cfg, "dict") else cfg.__dict__

    country = (market_catalogue.get("event", {}) or {}).get("countryCode")
    region_code = _region_for_country(cfg, country)

    # --- structure gate parameters (from config)
    anchor_top_n = int(_get(cfg_dict, ["structure_gates", "anchor", "top_n"], 3))
    anchor_min_top_implied = float(_get(cfg_dict, ["structure_gates", "anchor", "min_top_implied"], 0.65))

    soup_top_k = int(_get(cfg_dict, ["structure_gates", "soup", "top_k"], 5))
    soup_max_band_ratio = float(_get(cfg_dict, ["structure_gates", "soup", "max_band_ratio"], 1.20))

    tier_top_region = int(_get(cfg_dict, ["structure_gates", "tier", "top_region"], 6))
    tier_min_jump_ratio = float(_get(cfg_dict, ["structure_gates", "tier", "min_jump_ratio"], 1.25))

    # --- Country / region mapping
    country_ok = False
    if not country:
        results.append(RuleResult(False, "Country", "missing event.countryCode"))
    elif not region_code:
        results.append(RuleResult(False, "Country", f"{country} not in any configured region"))
    else:
        region_name = cfg.regions[region_code].name
        results.append(RuleResult(True, "Country", f"{country} -> {region_code} ({region_name})"))
        country_ok = True

    # --- Runner count & liquidity (region driven)
    runner_ok = False
    liquidity_ok = False
    if region_code:
        rr = cfg.resolve_runner_range(region_code)
        runner_ok = rr.min <= metrics.runner_count <= rr.max
        results.append(RuleResult(runner_ok, "Field size", f"{metrics.runner_count} in [{rr.min}–{rr.max}]"))

        liquidity_min = cfg.resolve_liquidity_min(region_code)
        total_matched = float(market_book.get("totalMatched") or 0.0)
        liquidity_ok = total_matched >= float(liquidity_min)
        results.append(RuleResult(liquidity_ok, "Liquidity", f"{total_matched:,.0f} ≥ {float(liquidity_min):,.0f}"))
    else:
        results.append(RuleResult(False, "Field size", "skipped (no region resolved)"))
        results.append(RuleResult(False, "Liquidity", "skipped (no region resolved)"))

    # --- Structure gates (computed in metrics)
    # Anchor: sum implied probs of topN favourites
    anchor_ok = metrics.top_n_implied_sum >= anchor_min_top_implied
    results.append(
        RuleResult(
            ok=anchor_ok,
            label=f"Anchor (top{anchor_top_n} implied)",
            detail=f"{metrics.top_n_implied_sum:.3f} ≥ {anchor_min_top_implied:.3f}",
        )
    )

    # Soup: FAIL if max/min within topK <= threshold (too many plausible winners)
    # So PASS if ratio > threshold.
    soup_ok = metrics.soup_band_ratio > soup_max_band_ratio
    results.append(
        RuleResult(
            ok=soup_ok,
            label=f"Soup (top{soup_top_k} band ratio)",
            detail=f"{metrics.soup_band_ratio:.3f} > {soup_max_band_ratio:.3f}",
        )
    )

    # Tier: require some jump between adjacent prices in the top region
    tier_ok = metrics.tier_max_adjacent_ratio >= tier_min_jump_ratio
    results.append(
        RuleResult(
            ok=tier_ok,
            label=f"Tier (max adjacent jump top{tier_top_region})",
            detail=f"{metrics.tier_max_adjacent_ratio:.3f} ≥ {tier_min_jump_ratio:.3f}",
        )
    )

    accepted = country_ok and runner_ok and liquidity_ok and anchor_ok and soup_ok and tier_ok
    return accepted, region_code, results
