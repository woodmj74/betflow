from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

import yaml


def _repo_root() -> Path:
    # /opt/betflow/src/betflow/filter_config.py -> /opt/betflow
    return Path(__file__).resolve().parents[2]


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


@dataclass(frozen=True)
class FilterConfig:
    global_cfg: GlobalConfig
    regions: Dict[str, RegionConfig]

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
        # preserve order but de-dupe
        seen = set()
        out = []
        for c in countries:
            if c not in seen:
                seen.add(c)
                out.append(c)
        return out


def load_filter_config(path: Optional[Path] = None) -> FilterConfig:
    if path is None:
        path = _repo_root() / "config" / "filters.yaml"

    data = _load_yaml(path)

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

    regions_raw = data.get("regions", {}) or {}
    regions: Dict[str, RegionConfig] = {}

    for code, r in regions_raw.items():
        if not isinstance(r, dict):
            raise ValueError(f"Region '{code}' must be a mapping")

        rc = r.get("runner_count")
        runner_range = None
        if isinstance(rc, dict):
            runner_range = RunnerCountRange(min=int(rc.get("min", 7)), max=int(rc.get("max", 16)))

        regions[code] = RegionConfig(
            code=str(code),
            name=str(r.get("name", code)),
            market_countries=list(r.get("market_countries", [])),
            liquidity_min=(float(r["liquidity_min"]) if "liquidity_min" in r and r["liquidity_min"] is not None else None),
            runner_count=runner_range,
        )

    if not regions:
        raise ValueError("No regions configured in filters.yaml")

    # basic validation
    for code, region in regions.items():
        if not region.market_countries:
            raise ValueError(f"Region '{code}' has no market_countries configured")

    return FilterConfig(global_cfg=global_cfg, regions=regions)


def _load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Filter config not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}
