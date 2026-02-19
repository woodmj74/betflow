from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import structlog

from betflow.betfair.client import BetfairClient
from betflow.filter_config import FilterConfig, RunnerCountRange


log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class MarketCandidate:
    market_id: str
    market_name: str
    start_time: datetime
    country_code: str
    total_matched: float
    runner_count: int


@dataclass(frozen=True)
class MarketDecision:
    market: MarketCandidate
    eligible: bool
    reasons: List[str]  # human-readable lines, already prefixed ✓/✗


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def find_horse_racing_event_type_id(client: BetfairClient) -> str:
    result = client.rpc("listEventTypes", {"filter": {}})
    for row in result:
        et = (row or {}).get("eventType", {})
        if isinstance(et, dict) and et.get("name") == "Horse Racing":
            return str(et.get("id"))
    # fallback: common id is 7, but we only use it if lookup fails
    log.warning("eventType.Horse Racing not found via API, falling back to id=7")
    return "7"


def discover_next_markets(
    client: BetfairClient,
    cfg: FilterConfig,
    take: Optional[int] = None,
) -> Tuple[List[MarketDecision], List[MarketDecision]]:
    """
    Returns (eligible, rejected) for the next N races by time, filtered to configured countries,
    applying runner_count + liquidity rules (region-aware).
    """
    horizon_hours = cfg.global_cfg.horizon_hours
    take_n = int(take if take is not None else cfg.global_cfg.take)

    event_type_id = find_horse_racing_event_type_id(client)

    now = _utcnow()
    to = now + timedelta(hours=horizon_hours)

    market_filter = {
        "eventTypeIds": [event_type_id],
        "marketTypeCodes": ["WIN"],
        "marketCountries": cfg.all_market_countries(),
        "marketStartTime": {"from": now.isoformat(), "to": to.isoformat()},
    }

    # We fetch more than we need, then apply our own filtering and take the first N by time.
    # Betfair maxResults is stringy in some examples; API accepts int too, but we'll pass int and keep it clean.
    params = {
        "filter": market_filter,
        "maxResults": 50,
        "marketProjection": ["EVENT", "MARKET_START_TIME", "RUNNER_DESCRIPTION"],
        "sort": "FIRST_TO_START",
    }

    log.info("markets.discover.start", take=take_n, horizon_hours=horizon_hours, countries=cfg.all_market_countries())

    rows = client.rpc("listMarketCatalogue", params)

    candidates: List[MarketCandidate] = []
    for r in rows:
        if not isinstance(r, dict):
            continue

        market_id = str(r.get("marketId", ""))
        market_name = str(r.get("marketName", ""))
        start_time_raw = r.get("marketStartTime")
        runners = r.get("runners") or []
        runner_count = len(runners) if isinstance(runners, list) else 0
        total_matched = float(r.get("totalMatched") or 0.0)

        event = r.get("event") if isinstance(r.get("event"), dict) else {}
        country_code = str((event or {}).get("countryCode") or "")

        if not market_id or not start_time_raw:
            continue

        start_time = _parse_betfair_datetime(start_time_raw)
        candidates.append(
            MarketCandidate(
                market_id=market_id,
                market_name=market_name,
                start_time=start_time,
                country_code=country_code,
                total_matched=total_matched,
                runner_count=runner_count,
            )
        )

    # Sort by time and take the next N
    candidates.sort(key=lambda x: x.start_time)
    candidates = candidates[:take_n]

    eligible: List[MarketDecision] = []
    rejected: List[MarketDecision] = []

    for m in candidates:
        decision = _evaluate_market(cfg, m)
        (eligible if decision.eligible else rejected).append(decision)

    return eligible, rejected


def _evaluate_market(cfg: FilterConfig, m: MarketCandidate) -> MarketDecision:
    # Determine region by country code mapping
    region_code = _region_for_country(cfg, m.country_code)
    runner_range = cfg.resolve_runner_range(region_code)
    liq_min = cfg.resolve_liquidity_min(region_code)

    reasons: List[str] = []

    # Runner count gate
    if runner_range.min <= m.runner_count <= runner_range.max:
        reasons.append(f"✓ Field size {m.runner_count} within [{runner_range.min}–{runner_range.max}] (region {region_code})")
        ok_runners = True
    else:
        reasons.append(f"✗ Field size {m.runner_count} outside [{runner_range.min}–{runner_range.max}] (region {region_code})")
        ok_runners = False

    # Liquidity gate
    if m.total_matched >= liq_min:
        reasons.append(f"✓ Liquidity {m.total_matched:,.0f} >= {liq_min:,.0f} (region {region_code})")
        ok_liq = True
    else:
        reasons.append(f"✗ Liquidity {m.total_matched:,.0f} < {liq_min:,.0f} (region {region_code})")
        ok_liq = False

    eligible = ok_runners and ok_liq
    reasons.append("→ MARKET ELIGIBLE" if eligible else "→ MARKET REJECTED")

    return MarketDecision(market=m, eligible=eligible, reasons=reasons)


def _region_for_country(cfg: FilterConfig, country_code: str) -> str:
    cc = (country_code or "").upper().strip()
    for code, region in cfg.regions.items():
        if cc in [c.upper() for c in region.market_countries]:
            return code
    # if something slips through, treat it as a "default" bucket by picking first region
    return next(iter(cfg.regions.keys()))


def _parse_betfair_datetime(s: str) -> datetime:
    # Betfair often returns ISO with Z, e.g. 2026-02-19T10:00:00.000Z
    # Python fromisoformat doesn't like 'Z' in older versions, so normalise.
    txt = str(s).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(txt)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return _utcnow()
