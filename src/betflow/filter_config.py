from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml


# -----------------------------
# Dataclasses representing filters.yaml
# -----------------------------

@dataclass(frozen=True)
class RegionConfig:
    name: str
    country_codes: List[str]
    liquidity_min: float


@dataclass(frozen=True)
class ScopeConfig:
    regions: Dict[str, RegionConfig]
    reject_out_of_scope: bool

    def region_for_country(self, country_code: Optional[str]) -> Optional[RegionConfig]:
        if not country_code:
            return None
        cc = country_code.upper()
        for r in self.regions.values():
            if cc in (c.upper() for c in r.country_codes):
                return r
        return None

    def in_scope(self, country_code: Optional[str]) -> bool:
        region = self.region_for_country(country_code)
        if region:
            return True
        return not self.reject_out_of_scope

    def liquidity_min_for_country(self, country_code: Optional[str]) -> Optional[float]:
        region = self.region_for_country(country_code)
        return region.liquidity_min if region else None


@dataclass(frozen=True)
class MarketFieldSizeConfig:
    min: int
    max: int


@dataclass(frozen=True)
class MarketCompressionConfig:
    under_odds: float
    max_count: int


@dataclass(frozen=True)
class MarketConfig:
    field_size: MarketFieldSizeConfig
    compression: MarketCompressionConfig


@dataclass(frozen=True)
class RunnerOddsBandConfig:
    min: float
    max: float


@dataclass(frozen=True)
class RunnerSpreadConfig:
    max_ticks: int


@dataclass(frozen=True)
class RunnerRankBufferConfig:
    min_rank: int
    max_rank: int


@dataclass(frozen=True)
class RunnerConfig:
    odds_band: RunnerOddsBandConfig
    preferred_odds: float
    spread: RunnerSpreadConfig
    rank_buffer: RunnerRankBufferConfig


@dataclass(frozen=True)
class ProbabilityTopClusterConfig:
    count: int
    min_total_implied: float
    max_total_implied: float


@dataclass(frozen=True)
class ProbabilityUniformCheckConfig:
    multiplier: float


@dataclass(frozen=True)
class ProbabilityConfig:
    top_cluster: ProbabilityTopClusterConfig
    uniform_check: ProbabilityUniformCheckConfig


@dataclass(frozen=True)
class RiskConfig:
    min_stake: float
    max_liability: float


@dataclass(frozen=True)
class StrategyConfig:
    version: str
    scope: ScopeConfig
    market: MarketConfig
    runner: RunnerConfig
    probability: ProbabilityConfig
    risk: RiskConfig
    source_path: str

    # ---- convenience helpers we’ll use in scripts ----

    def is_market_in_scope(self, country_code: Optional[str]) -> bool:
        return self.scope.in_scope(country_code)

    def market_liquidity_min(self, country_code: Optional[str]) -> Optional[float]:
        return self.scope.liquidity_min_for_country(country_code)

    def field_size_ok(self, runner_count: int) -> Tuple[bool, str]:
        lo = self.market.field_size.min
        hi = self.market.field_size.max
        if runner_count < lo or runner_count > hi:
            return False, f"Field size {runner_count} outside [{lo}–{hi}]"
        return True, f"Field size {runner_count} within [{lo}–{hi}]"

    def odds_band_ok(self, odds: float) -> Tuple[bool, str]:
        lo = self.runner.odds_band.min
        hi = self.runner.odds_band.max
        if odds < lo or odds > hi:
            return False, f"Odds {odds:.2f} outside band [{lo}–{hi}]"
        return True, f"Odds {odds:.2f} within band [{lo}–{hi}]"

    def spread_ok(self, ticks: int) -> Tuple[bool, str]:
        mx = self.runner.spread.max_ticks
        if ticks > mx:
            return False, f"Spread {ticks} ticks > max {mx}"
        return True, f"Spread {ticks} ticks <= max {mx}"


# -----------------------------
# Loader + validation
# -----------------------------

class ConfigError(RuntimeError):
    pass


def _require(d: Dict[str, Any], key: str, ctx: str) -> Any:
    if key not in d:
        raise ConfigError(f"Missing required key '{key}' under {ctx}")
    return d[key]


def _as_float(v: Any, ctx: str) -> float:
    try:
        return float(v)
    except Exception as e:
        raise ConfigError(f"Expected number at {ctx}, got {v!r}") from e


def _as_int(v: Any, ctx: str) -> int:
    try:
        return int(v)
    except Exception as e:
        raise ConfigError(f"Expected int at {ctx}, got {v!r}") from e


def _as_str(v: Any, ctx: str) -> str:
    if not isinstance(v, str):
        raise ConfigError(f"Expected string at {ctx}, got {type(v).__name__}: {v!r}")
    return v


def _as_version(v: Any, ctx: str) -> str:
    """
    Accept version as string or number (YAML often parses 1.0 as float).
    Normalise to a string.
    """
    if isinstance(v, (int, float)):
        # Keep human-friendly formatting: 1.0 -> "1.0"
        return str(v)
    if isinstance(v, str):
        return v
    raise ConfigError(f"Expected version as string/number at {ctx}, got {type(v).__name__}: {v!r}")


def load_filter_config(path: str | Path, verbose: bool = False) -> StrategyConfig:
    p = Path(path)
    if not p.exists():
        raise ConfigError(f"Filters file not found: {p}")

    try:
        raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    except Exception as e:
        raise ConfigError(f"Failed to parse YAML: {p} ({e})") from e

    if not isinstance(raw, dict):
        raise ConfigError(f"Top-level YAML must be a mapping/dict: {p}")

    version = _as_version(_require(raw, "version", "root"), "root.version")

    # ---- scope.regions ----
    scope_raw = _require(raw, "scope", "root")
    if not isinstance(scope_raw, dict):
        raise ConfigError("root.scope must be a mapping/dict")

    regions_raw = _require(scope_raw, "regions", "root.scope")
    if not isinstance(regions_raw, dict) or not regions_raw:
        raise ConfigError("root.scope.regions must be a non-empty mapping/dict")

    regions: Dict[str, RegionConfig] = {}
    for region_name, region_val in regions_raw.items():
        if not isinstance(region_val, dict):
            raise ConfigError(f"root.scope.regions.{region_name} must be a mapping/dict")

        cc = _require(region_val, "country_codes", f"root.scope.regions.{region_name}")
        if not isinstance(cc, list) or not cc:
            raise ConfigError(f"root.scope.regions.{region_name}.country_codes must be a non-empty list")

        liquidity_min = _as_float(
            _require(region_val, "liquidity_min", f"root.scope.regions.{region_name}"),
            f"root.scope.regions.{region_name}.liquidity_min",
        )

        regions[region_name] = RegionConfig(
            name=str(region_name),
            country_codes=[str(x).upper() for x in cc],
            liquidity_min=liquidity_min,
        )

    reject_out = scope_raw.get("reject_out_of_scope", True)
    reject_out_of_scope = bool(reject_out)

    scope = ScopeConfig(regions=regions, reject_out_of_scope=reject_out_of_scope)

    # ---- market ----
    market_raw = _require(raw, "market", "root")
    if not isinstance(market_raw, dict):
        raise ConfigError("root.market must be a mapping/dict")

    field_size_raw = _require(market_raw, "field_size", "root.market")
    if not isinstance(field_size_raw, dict):
        raise ConfigError("root.market.field_size must be a mapping/dict")
    field_size = MarketFieldSizeConfig(
        min=_as_int(_require(field_size_raw, "min", "root.market.field_size"), "root.market.field_size.min"),
        max=_as_int(_require(field_size_raw, "max", "root.market.field_size"), "root.market.field_size.max"),
    )
    if field_size.min <= 0 or field_size.max < field_size.min:
        raise ConfigError("root.market.field_size must have 0 < min <= max")

    compression_raw = _require(market_raw, "compression", "root.market")
    if not isinstance(compression_raw, dict):
        raise ConfigError("root.market.compression must be a mapping/dict")
    compression = MarketCompressionConfig(
        under_odds=_as_float(_require(compression_raw, "under_odds", "root.market.compression"),
                            "root.market.compression.under_odds"),
        max_count=_as_int(_require(compression_raw, "max_count", "root.market.compression"),
                         "root.market.compression.max_count"),
    )
    if compression.under_odds <= 1.0 or compression.max_count < 0:
        raise ConfigError("root.market.compression under_odds must be > 1.0 and max_count >= 0")

    market = MarketConfig(field_size=field_size, compression=compression)

    # ---- runner ----
    runner_raw = _require(raw, "runner", "root")
    if not isinstance(runner_raw, dict):
        raise ConfigError("root.runner must be a mapping/dict")

    odds_band_raw = _require(runner_raw, "odds_band", "root.runner")
    if not isinstance(odds_band_raw, dict):
        raise ConfigError("root.runner.odds_band must be a mapping/dict")
    odds_band = RunnerOddsBandConfig(
        min=_as_float(_require(odds_band_raw, "min", "root.runner.odds_band"), "root.runner.odds_band.min"),
        max=_as_float(_require(odds_band_raw, "max", "root.runner.odds_band"), "root.runner.odds_band.max"),
    )
    if odds_band.min <= 1.0 or odds_band.max < odds_band.min:
        raise ConfigError("root.runner.odds_band must have 1.0 < min <= max")

    preferred_odds = _as_float(_require(runner_raw, "preferred_odds", "root.runner"), "root.runner.preferred_odds")

    spread_raw = _require(runner_raw, "spread", "root.runner")
    if not isinstance(spread_raw, dict):
        raise ConfigError("root.runner.spread must be a mapping/dict")
    spread = RunnerSpreadConfig(
        max_ticks=_as_int(_require(spread_raw, "max_ticks", "root.runner.spread"), "root.runner.spread.max_ticks")
    )
    if spread.max_ticks < 0:
        raise ConfigError("root.runner.spread.max_ticks must be >= 0")

    rank_raw = _require(runner_raw, "rank_buffer", "root.runner")
    if not isinstance(rank_raw, dict):
        raise ConfigError("root.runner.rank_buffer must be a mapping/dict")
    rank_buffer = RunnerRankBufferConfig(
        min_rank=_as_int(_require(rank_raw, "min_rank", "root.runner.rank_buffer"), "root.runner.rank_buffer.min_rank"),
        max_rank=_as_int(_require(rank_raw, "max_rank", "root.runner.rank_buffer"), "root.runner.rank_buffer.max_rank"),
    )
    if rank_buffer.min_rank <= 0 or rank_buffer.max_rank < rank_buffer.min_rank:
        raise ConfigError("root.runner.rank_buffer must have 0 < min_rank <= max_rank")

    runner = RunnerConfig(
        odds_band=odds_band,
        preferred_odds=preferred_odds,
        spread=spread,
        rank_buffer=rank_buffer,
    )

    # ---- probability ----
    prob_raw = _require(raw, "probability", "root")
    if not isinstance(prob_raw, dict):
        raise ConfigError("root.probability must be a mapping/dict")

    top_cluster_raw = _require(prob_raw, "top_cluster", "root.probability")
    if not isinstance(top_cluster_raw, dict):
        raise ConfigError("root.probability.top_cluster must be a mapping/dict")
    top_cluster = ProbabilityTopClusterConfig(
        count=_as_int(_require(top_cluster_raw, "count", "root.probability.top_cluster"),
                      "root.probability.top_cluster.count"),
        min_total_implied=_as_float(_require(top_cluster_raw, "min_total_implied", "root.probability.top_cluster"),
                                    "root.probability.top_cluster.min_total_implied"),
        max_total_implied=_as_float(_require(top_cluster_raw, "max_total_implied", "root.probability.top_cluster"),
                                    "root.probability.top_cluster.max_total_implied"),
    )
    if top_cluster.count <= 0:
        raise ConfigError("root.probability.top_cluster.count must be > 0")
    if not (0.0 < top_cluster.min_total_implied <= top_cluster.max_total_implied <= 1.5):
        raise ConfigError("root.probability.top_cluster min/max_total_implied must be sensible (0..1.5)")

    uniform_raw = _require(prob_raw, "uniform_check", "root.probability")
    if not isinstance(uniform_raw, dict):
        raise ConfigError("root.probability.uniform_check must be a mapping/dict")
    uniform_check = ProbabilityUniformCheckConfig(
        multiplier=_as_float(_require(uniform_raw, "multiplier", "root.probability.uniform_check"),
                             "root.probability.uniform_check.multiplier")
    )
    if uniform_check.multiplier <= 0.0:
        raise ConfigError("root.probability.uniform_check.multiplier must be > 0")

    probability = ProbabilityConfig(top_cluster=top_cluster, uniform_check=uniform_check)

    # ---- risk ----
    risk_raw = _require(raw, "risk", "root")
    if not isinstance(risk_raw, dict):
        raise ConfigError("root.risk must be a mapping/dict")

    risk = RiskConfig(
        min_stake=_as_float(_require(risk_raw, "min_stake", "root.risk"), "root.risk.min_stake"),
        max_liability=_as_float(_require(risk_raw, "max_liability", "root.risk"), "root.risk.max_liability"),
    )
    if risk.min_stake <= 0.0 or risk.max_liability <= 0.0:
        raise ConfigError("root.risk min_stake and max_liability must be > 0")

    cfg = StrategyConfig(
        version=version,
        scope=scope,
        market=market,
        runner=runner,
        probability=probability,
        risk=risk,
        source_path=str(p),
    )

    if verbose:
        print("\n[CONFIG LOADED]")
        print(f"  source: {cfg.source_path}")
        print(f"  version: {cfg.version}")
        print(f"  reject_out_of_scope: {cfg.scope.reject_out_of_scope}")
        print("  regions:")
        for r in cfg.scope.regions.values():
            print(f"    - {r.name}: countries={r.country_codes} liquidity_min={r.liquidity_min}")
        print(f"  market.field_size: {cfg.market.field_size.min}–{cfg.market.field_size.max}")
        print(f"  market.compression: under_odds<{cfg.market.compression.under_odds} max_count={cfg.market.compression.max_count}")
        print(f"  runner.odds_band: {cfg.runner.odds_band.min}–{cfg.runner.odds_band.max} preferred={cfg.runner.preferred_odds}")
        print(f"  runner.spread.max_ticks: {cfg.runner.spread.max_ticks}")
        print(f"  runner.rank_buffer: {cfg.runner.rank_buffer.min_rank}–{cfg.runner.rank_buffer.max_rank}")
        print(f"  probability.top_cluster: count={cfg.probability.top_cluster.count} "
              f"min={cfg.probability.top_cluster.min_total_implied} max={cfg.probability.top_cluster.max_total_implied}")
        print(f"  probability.uniform_check.multiplier: {cfg.probability.uniform_check.multiplier}")
        print(f"  risk: min_stake={cfg.risk.min_stake} max_liability={cfg.risk.max_liability}")

    return cfg
