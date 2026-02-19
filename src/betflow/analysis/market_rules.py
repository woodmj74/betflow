from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from betflow.analysis.structure_metrics import MarketStructureMetrics
from betflow.filter_config import FilterConfig


@dataclass(frozen=True)
class RuleResult:
    ok: bool
    label: str
    detail: str


def evaluate_market_rules(
    *,
    market_catalogue: Dict[str, Any],
    market_book: Dict[str, Any],
    metrics: MarketStructureMetrics,
    cfg: FilterConfig,
) -> Tuple[bool, Optional[str], List[RuleResult]]:
    results: List[RuleResult] = []

    country = (market_catalogue.get("event", {}) or {}).get("countryCode")
    region_code = _region_for_country(cfg, country)

    # --- Country / region mapping
    if not country:
        results.append(RuleResult(False, "Country", "missing event.countryCode"))
    elif not region_code:
        results.append(RuleResult(False, "Country", f"{country} not in any configured region"))
    else:
        region_name = cfg.regions[region_code].name
        results.append(RuleResult(True, "Country", f"{country} -> {region_code} ({region_name})"))

    # --- Runner count & liquidity
    if region_code:
        rr = cfg.resolve_runner_range(region_code)
        ok_rc = rr.min <= metrics.runner_count <= rr.max
        results.append(RuleResult(ok_rc, "Field size", f"{metrics.runner_count} in [{rr.min}–{rr.max}]"))

        liquidity_min = cfg.resolve_liquidity_min(region_code)
        total_matched = float(market_book.get("totalMatched") or 0.0)
        ok_lq = total_matched >= float(liquidity_min)
        results.append(RuleResult(ok_lq, "Liquidity", f"{total_matched:,.0f} ≥ {float(liquidity_min):,.0f}"))
    else:
        results.append(RuleResult(False, "Field size", "skipped (no region resolved)"))
        results.append(RuleResult(False, "Liquidity", "skipped (no region resolved)"))

    # --- Structure gates (anchor/soup/tier)
    prices = metrics.best_back_prices_sorted  # ascending (fav first)
    results.extend(_eval_structure_gates(prices, cfg))

    accepted = all(r.ok for r in results)
    return accepted, region_code, results


def _eval_structure_gates(prices_asc: List[float], cfg: FilterConfig) -> List[RuleResult]:
    out: List[RuleResult] = []
    sg = cfg.structure_gates

    # If we don't have enough priced runners, fail the structure gates (conservative)
    if not prices_asc:
        return [
            RuleResult(False, "Anchor", "no priced runners"),
            RuleResult(False, "Soup", "no priced runners"),
            RuleResult(False, "Tier", "no priced runners"),
        ]

    # ---- Anchor gate
    n = max(1, sg.anchor.top_n)
    if len(prices_asc) < n:
        out.append(RuleResult(False, "Anchor", f"need top_n={n} priced runners, have {len(prices_asc)}"))
    else:
        top_prices = prices_asc[:n]
        top_implied = sum(1.0 / p for p in top_prices if p and p > 1.0)
        ok = top_implied >= float(sg.anchor.min_top_implied)
        out.append(
            RuleResult(
                ok,
                "Anchor",
                f"top{n} implied={top_implied:.3f} ≥ {float(sg.anchor.min_top_implied):.3f}",
            )
        )

    # ---- Soup gate
    k = max(2, sg.soup.top_k)
    if len(prices_asc) < k:
        out.append(RuleResult(False, "Soup", f"need top_k={k} priced runners, have {len(prices_asc)}"))
    else:
        band = prices_asc[:k]
        min_p = min(band)
        max_p = max(band)
        ratio = (max_p / min_p) if min_p > 0 else float("inf")
        # if topK max/min <= ratio => FAIL soup (too tight / too many plausible winners)
        ok = ratio > float(sg.soup.max_band_ratio)
        out.append(
            RuleResult(
                ok,
                "Soup",
                f"top{k} band ratio={ratio:.3f} must be > {float(sg.soup.max_band_ratio):.3f}",
            )
        )

    # ---- Tier gate
    m = max(2, sg.tier.top_region)
    if len(prices_asc) < m:
        out.append(RuleResult(False, "Tier", f"need top_region={m} priced runners, have {len(prices_asc)}"))
    else:
        region = prices_asc[:m]
        # Adjacent jump ratio (later price / earlier price)
        jumps = [(region[i + 1] / region[i]) for i in range(len(region) - 1) if region[i] > 0]
        max_jump = max(jumps) if jumps else 1.0
        ok = max_jump >= float(sg.tier.min_jump_ratio)
        out.append(
            RuleResult(
                ok,
                "Tier",
                f"max adjacent jump={max_jump:.3f} ≥ {float(sg.tier.min_jump_ratio):.3f} (top{m})",
            )
        )

    return out


def _region_for_country(cfg: FilterConfig, country_code: Optional[str]) -> Optional[str]:
    if not country_code:
        return None
    cc = country_code.upper()
    for code, region in cfg.regions.items():
        if cc in [c.upper() for c in region.market_countries]:
            return code
    return None
