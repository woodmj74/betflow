from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import yaml


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


PathLike = Union[str, Path]


# -----------------
# Existing config
# -----------------

@dataclass(frozen=True)
class RunnerCountRange:
    min: int
    max: int


@dataclass(frozen=True)
class GlobalDefaults:
    runner_count: RunnerCountRange
    liquidity_min: float


@dataclass(frozen=True)
class GlobalConfig:
    horizon_hours: int
    take: int
    defaults: GlobalDefaults


@dataclass(frozen=True)
class RegionConfig:
    code: str
    name: str
    market_countries: List[str]
    liquidity_min: Optional[float] = None
    runner_count: Optional[RunnerCountRange] = None


# -----------------
# NEW: Structure gates
# -----------------

@dataclass(frozen=True)
class AnchorGate:
    top_n: int
    min_top_implied: float


@dataclass(frozen=True)
class SoupGate:
    top_k: int
    max_band_ratio: float  # if max/min <= ratio => FAIL


@dataclass(frozen=True)
class TierGate:
    top_region: int
    min_jump_ratio: float  # max adjacent ratio in top_region must be >= this


@dataclass(frozen=True)
class StructureGates:
    anchor: AnchorGate
    soup: SoupGate
    tier: TierGate


@dataclass(frozen=True)
class HorseSelectionFilters:
    min_odds: float
    max_odds: float
    max_spread: float


@dataclass(frozen=True)
class FilterConfig:
    global_cfg: GlobalConfig
    regions: Dict[str, RegionConfig]
    structure_gates: StructureGates
    horse_selection: HorseSelectionFilters

    def resolve_liquidity_min(self, region_code: str) -> float:
        region = self.regions[region_code]
        return float(region.liquidity_min if region.liquidity_min is not None else self.global_cfg.defaults.liquidity_min)

    def resolve_runner_range(self, region_code: str) -> RunnerCountRange:
        region = self.regions[region_code]
        return region.runner_count if region.runner_count is not None else self.global_cfg.defaults.runner_count

    def all_market_countries(self) -> List[str]:
        countries: List[str] = []
        for r in self.regions.values():
            countries.extend(r.market_countries)
        seen = set()
        out: List[str] = []
        for c in countries:
            if c not in seen:
                seen.add(c)
                out.append(c)
        return out


def load_filter_config(path: Optional[PathLike] = None) -> FilterConfig:
    if path is None:
        path_obj = _repo_root() / "config" / "filters.yaml"
    else:
        path_obj = path if isinstance(path, Path) else Path(path)
        if not path_obj.is_absolute():
            path_obj = _repo_root() / path_obj

    data = _load_yaml(path_obj)

    # ---- global
    g = data.get("global", {})
    defaults = g.get("defaults", {})

    runner_count = defaults.get("runner_count", {})
    global_defaults = GlobalDefaults(
        runner_count=RunnerCountRange(
            min=int(runner_count.get("min", 7)),
            max=int(runner_count.get("max", 16)),
        ),
        liquidity_min=float(defaults.get("liquidity_min", 2000)),
    )

    global_cfg = GlobalConfig(
        horizon_hours=int(g.get("horizon_hours", 48)),
        take=int(g.get("take", 10)),
        defaults=global_defaults,
    )

    # ---- regions
    regions_raw = data.get("regions", {}) or {}
    regions: Dict[str, RegionConfig] = {}

    for code, r in regions_raw.items():
        if not isinstance(r, dict):
            raise ValueError(f"Region '{code}' must be a mapping")

        rc = r.get("runner_count")
        runner_range = None
        if isinstance(rc, dict):
            runner_range = RunnerCountRange(min=int(rc.get("min", 7)), max=int(rc.get("max", 16)))

        regions[str(code)] = RegionConfig(
            code=str(code),
            name=str(r.get("name", code)),
            market_countries=list(r.get("market_countries", [])),
            liquidity_min=(float(r["liquidity_min"]) if "liquidity_min" in r and r["liquidity_min"] is not None else None),
            runner_count=runner_range,
        )

    if not regions:
        raise ValueError("No regions configured in filters.yaml")

    for code, region in regions.items():
        if not region.market_countries:
            raise ValueError(f"Region '{code}' has no market_countries configured")

    # ---- NEW: structure_gates (with defaults so old configs still work)
    sg = data.get("structure_gates", {}) or {}
    anchor_raw = sg.get("anchor", {}) or {}
    soup_raw = sg.get("soup", {}) or {}
    tier_raw = sg.get("tier", {}) or {}

    structure_gates = StructureGates(
        anchor=AnchorGate(
            top_n=int(anchor_raw.get("top_n", 3)),
            min_top_implied=float(anchor_raw.get("min_top_implied", 0.65)),
        ),
        soup=SoupGate(
            top_k=int(soup_raw.get("top_k", 5)),
            max_band_ratio=float(soup_raw.get("max_band_ratio", 1.20)),
        ),
        tier=TierGate(
            top_region=int(tier_raw.get("top_region", 6)),
            min_jump_ratio=float(tier_raw.get("min_jump_ratio", 1.25)),
        ),
    )

    horse_selection_raw = data.get("horse_selection", {}) or {}
    horse_selection = HorseSelectionFilters(
        min_odds=float(horse_selection_raw.get("min_odds", 12.0)),
        max_odds=float(horse_selection_raw.get("max_odds", 18.0)),
        max_spread=float(horse_selection_raw.get("max_spread", 2.0)),
    )

    return FilterConfig(
        global_cfg=global_cfg,
        regions=regions,
        structure_gates=structure_gates,
        horse_selection=horse_selection,
    )


def _load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Filter config not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}
