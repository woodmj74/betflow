from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List
import yaml


@dataclass(frozen=True)
class Profile:
    name: str
    countries: List[str]
    min_total_matched: float


@dataclass(frozen=True)
class Defaults:
    min_runners: int
    max_runners: int
    fav_min: float
    fav_max: float


@dataclass(frozen=True)
class RunnerTargeting:
    max_odds: float
    field_threshold: int
    large_field_rank: int
    smaller_field_rank: int
    target_odds_min: float
    target_odds_max: float
    max_back_lay_spread_ticks: int


@dataclass(frozen=True)
class SanityChecks:
    max_runners_under_10: int
    prefer_cluster_under: float


@dataclass(frozen=True)
class FilterConfig:
    profiles: Dict[str, Profile]
    defaults: Defaults
    runner_targeting: RunnerTargeting
    sanity_checks: SanityChecks


def load_filter_config(path: str = "config/filters.yaml") -> FilterConfig:
    p = Path(path)
    data: Dict[str, Any] = yaml.safe_load(p.read_text())

    profiles = {
        name: Profile(
            name=name,
            countries=cfg["countries"],
            min_total_matched=float(cfg["min_total_matched"]),
        )
        for name, cfg in data["profiles"].items()
    }

    d = data["defaults"]
    rt = data["runner_targeting"]
    sc = data["sanity_checks"]

    return FilterConfig(
        profiles=profiles,
        defaults=Defaults(
            min_runners=int(d["min_runners"]),
            max_runners=int(d["max_runners"]),
            fav_min=float(d["fav_min"]),
            fav_max=float(d["fav_max"]),
        ),
        runner_targeting=RunnerTargeting(
            max_odds=float(rt["max_odds"]),
            field_threshold=int(rt["field_threshold"]),
            large_field_rank=int(rt["large_field_rank"]),
            smaller_field_rank=int(rt["smaller_field_rank"]),
            target_odds_min=float(rt["target_odds_min"]),
            target_odds_max=float(rt["target_odds_max"]),
            max_back_lay_spread_ticks=int(rt["max_back_lay_spread_ticks"]),
        ),
        sanity_checks=SanityChecks(
            max_runners_under_10=int(sc["max_runners_under_10"]),
            prefer_cluster_under=float(sc["prefer_cluster_under"]),
        ),
    )
