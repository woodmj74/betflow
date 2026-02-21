from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


# ----------------------------
# Tick helpers (Betfair ticks)
# ----------------------------

# Bands: (inclusive lower bound, inclusive upper bound, tick size)
_TICK_BANDS: list[tuple[float, float, float]] = [
    (1.01, 2.00, 0.01),
    (2.00, 3.00, 0.02),
    (3.00, 4.00, 0.05),
    (4.00, 6.00, 0.10),
    (6.00, 10.00, 0.20),
    (10.00, 20.00, 0.50),
    (20.00, 30.00, 1.00),
    (30.00, 50.00, 2.00),
    (50.00, 100.00, 5.00),
    (100.00, 1000.00, 10.00),
]

def _in_band(price: float | None, band) -> bool:
    if price is None:
        return False
    return band.min <= price <= band.max

def tick_size(price: float) -> float:
    p = float(price)
    for lo, hi, t in _TICK_BANDS:
        if lo <= p <= hi:
            return t
    # Fallback (shouldn't happen in normal markets)
    return 0.01


def ticks_between(back: float, lay: float) -> int:
    """
    Approximate tick distance between two prices using Betfair bands.
    Assumes back <= lay and both valid prices.
    """
    b = float(back)
    l = float(lay)
    if l <= b:
        return 0

    ticks = 0
    cur = b
    # Step in ticks until we reach or exceed lay
    # Guard against infinite loops on bad input.
    for _ in range(10000):
        t = tick_size(cur)
        nxt = round(cur + t, 10)
        ticks += 1
        if nxt >= l - 1e-12:
            return ticks
        cur = nxt
    return ticks


def _distance_ticks(price: float, centre: float) -> int:
    """
    Approx tick distance between price and centre.
    We round to nearest whole tick so we avoid fractional tick debates in logs.
    """
    if price <= 0 or centre <= 0:
        return 9999

    # Use tick size at the price point (consistent, simple).
    t = tick_size(price)
    return int(round(abs(price - centre) / t))


# ----------------------------
# Data models
# ----------------------------

@dataclass(frozen=True)
class RunnerLadder:
    selection_id: int
    runner_number: int | None
    name: str
    best_back: float | None
    best_lay: float | None

    @property
    def spread_ticks(self) -> int | None:
        if self.best_back is None or self.best_lay is None:
            return None
        return ticks_between(self.best_back, self.best_lay)

    @property
    def implied_prob(self) -> float | None:
        if self.best_back is None or self.best_back <= 0:
            return None
        return 1.0 / self.best_back


@dataclass(frozen=True)
class MarketStructureMetrics:
    runner_count: int
    priced_runner_count: int
    top_n_implied_sum: float
    soup_band_ratio: float
    tier_max_adjacent_ratio: float


@dataclass(frozen=True)
class RunnerSelectionRow:
    runner: RunnerLadder
    price_rank: int  # 1 = favourite by price
    band: str        # "PRIMARY" | "SECONDARY" | "HARD" | "-"
    spread_ticks: int | None
    distance_ticks: int | None
    score: float     # kept for compatibility with existing debug printing (not used for ordering)
    reason: str


# ----------------------------
# Selection (Stage 2)
# ----------------------------

def select_candidate_runner(
    ladders: Iterable[RunnerLadder],
    metrics: MarketStructureMetrics,
    cfg: Any,  # FilterConfig (Any here avoids import cycles)
) -> tuple[RunnerLadder | None, list[RunnerSelectionRow]]:
    """
    Deterministic selection (explainable):
      - Apply hard gates (hard band, spread, rank exclusion)
      - Classify as PRIMARY / SECONDARY (secondary only if anchored_ok)
      - Choose ONE runner:
          Primary candidates ordered by (spread_ticks, distance_ticks, best_back)
          If no primary candidates, use secondary candidates with same ordering.
    Returns: (selected_runner_or_None, debug_rows)
    """

    rows = [r for r in ladders if r.best_back is not None and r.best_back > 0]
    rows.sort(key=lambda r: r.best_back or 9999.0)  # price rank basis

    # Anchor condition to allow secondary band
    top_n = max(int(getattr(cfg.structure_gates.anchor, "top_n", 3)), 0)
    anchored_ok = metrics.top_n_implied_sum >= float(cfg.selection.secondary_band.requires_top_n_implied_at_least)

    hard = cfg.selection.hard_band
    primary = cfg.selection.primary_band
    secondary = cfg.selection.secondary_band
    max_spread = int(cfg.selection.max_spread_ticks)

    top_excl = int(cfg.selection.rank_exclusion.top_n)
    bot_excl = int(cfg.selection.rank_exclusion.bottom_n)

    debug: list[RunnerSelectionRow] = []
    eligible_primary: list[RunnerSelectionRow] = []
    eligible_secondary: list[RunnerSelectionRow] = []

    total = len(rows)

    primary_target = getattr(primary, "target_price", None)
    if primary_target is None:
        primary_target = (primary.min + primary.max) / 2.0

    secondary_target = getattr(secondary, "target_price", None)
    if secondary_target is None:
        secondary_target = (secondary.min + secondary.max) / 2.0

    for idx, r in enumerate(rows, start=1):
        st = r.spread_ticks
        # Pre-compute rank exclusion tag for diagnostics (even if runner fails earlier gates)
        rank_tag: str | None = None
        if top_excl > 0 and idx <= top_excl:
            rank_tag = f"excluded: top {top_excl}"
        elif bot_excl > 0 and (total - idx) < bot_excl:
            rank_tag = f"excluded: bottom {bot_excl}"

        # Must have both back and lay to be considered tradable
        if r.best_back is None or r.best_lay is None:
            reason = "missing back/lay"
            if rank_tag:
                reason = f"{reason}; {rank_tag}"
            debug.append(RunnerSelectionRow(r, idx, "-", st, None, -9999.0, reason))
            continue

        # Hard band gate (identity guardrail)
        if not (hard.min <= r.best_back <= hard.max):
            reason = "outside hard band"
            if rank_tag:
                reason = f"{reason}; {rank_tag}"
            debug.append(RunnerSelectionRow(r, idx, "-", st, None, -9999.0, reason))
            continue

        # Hard band guardrail must also apply to LAY (execution boundary)
        if not (hard.min <= r.best_lay <= hard.max):
            reason = f"outside hard band (lay {r.best_lay:.2f} not in [{hard.min:g}–{hard.max:g}])"
            if rank_tag:
                reason = f"{reason}; {rank_tag}"
            debug.append(RunnerSelectionRow(r, idx, "-", st, None, -9999.0, reason))
            continue

        # Determine structural band first (based on BACK only)
        in_primary = primary.min <= r.best_back <= primary.max
        in_secondary = secondary.min <= r.best_back <= secondary.max

        if in_primary:
            structural_band = "PRIMARY"
        elif in_secondary and anchored_ok:
            structural_band = "SECONDARY"
        else:
            structural_band = "HARD"

        # Spread gate
        if st is None or st > max_spread:
            reason = f"spread {st} > {max_spread}"
            if rank_tag:
                reason = f"{reason}; {rank_tag}"
            debug.append(RunnerSelectionRow(r, idx, structural_band, st, None, -9999.0, reason))
            continue

        # Rank exclusion
        if top_excl > 0 and idx <= top_excl:
            debug.append(RunnerSelectionRow(r, idx, "HARD", st, None, -9999.0, f"excluded: top {top_excl}"))
            continue
        if bot_excl > 0 and (total - idx) < bot_excl:
            debug.append(RunnerSelectionRow(r, idx, "HARD", st, None, -9999.0, f"excluded: bottom {bot_excl}"))
            continue

        in_primary = primary.min <= r.best_back <= primary.max
        in_secondary = secondary.min <= r.best_back <= secondary.max

        if in_primary:
            dt = _distance_ticks(r.best_back, primary_target)
            row = RunnerSelectionRow(r, idx, "PRIMARY", st, dt, 0.0, "in primary band")
            eligible_primary.append(row)
            debug.append(row)
            continue

        if anchored_ok and in_secondary:
            dt = _distance_ticks(r.best_back, secondary_target)
            row = RunnerSelectionRow(r, idx, "SECONDARY", st, dt, 0.0, "secondary allowed (anchored)")
            eligible_secondary.append(row)
            debug.append(row)
            continue

        # In hard band, but not in an allowed selection band
        if in_secondary and not anchored_ok:
            debug.append(RunnerSelectionRow(r, idx, "HARD", st, None, -9999.0, "secondary not allowed (anchoring)"))
        else:
            debug.append(RunnerSelectionRow(r, idx, "HARD", st, None, -9999.0, "not in allowed band"))

    def _order_key(row: RunnerSelectionRow) -> tuple[int, int, float]:
        sprd = row.spread_ticks if row.spread_ticks is not None else 9999
        dist = row.distance_ticks if row.distance_ticks is not None else 9999
        back = row.runner.best_back if row.runner.best_back is not None else 9999.0
        return (sprd, dist, back)

    # Choose from primary first, then secondary
    if eligible_primary:
        eligible_primary.sort(key=_order_key)
        return eligible_primary[0].runner, debug

    if eligible_secondary:
        eligible_secondary.sort(key=_order_key)
        return eligible_secondary[0].runner, debug

    return None, debug


# ----------------------------
# Extraction helpers
# ----------------------------

def _best_price(ex: dict, side: str) -> float | None:
    if not ex:
        return None
    ladder = ex.get(side) or []
    if not ladder:
        return None
    p = ladder[0].get("price")
    return float(p) if p is not None else None


def _cloth_number_from_metadata(md: dict) -> int | None:
    if not isinstance(md, dict):
        return None
    for k in ("CLOTH_NUMBER", "CLOTH_NUMBER_ALPHA"):
        v = md.get(k)
        if v is None:
            continue
        try:
            return int(v)
        except Exception:
            continue
    return None


def build_runner_ladders(market_catalogue: dict, market_book: dict) -> list[RunnerLadder]:
    """
    Build best-back/best-lay ladder rows for each runner in a market.
    Uses catalogue runners for names + cloth numbers, book runners for prices.
    """
    sel_to_name: dict[int, str] = {}
    sel_to_num: dict[int, int | None] = {}

    for r in (market_catalogue.get("runners") or []):
        sid = int(r.get("selectionId"))
        sel_to_name[sid] = r.get("runnerName", f"sel:{sid}")
        sel_to_num[sid] = _cloth_number_from_metadata(r.get("metadata") or {})

    out: list[RunnerLadder] = []
    for rb in (market_book.get("runners") or []):
        # ACTIVE only: exclude non-runners (REMOVED, etc.) from ladders and
        # downstream field-size logic.
        if rb.get("status") != "ACTIVE":
            continue

        sid = int(rb.get("selectionId"))
        ex = rb.get("ex") or {}
        best_back = _best_price(ex, "availableToBack")
        best_lay = _best_price(ex, "availableToLay")

        out.append(
            RunnerLadder(
                selection_id=sid,
                runner_number=sel_to_num.get(sid),
                name=sel_to_name.get(sid, f"sel:{sid}"),
                best_back=best_back,
                best_lay=best_lay,
            )
        )

    # Sort by best_back (None last)
    out.sort(key=lambda r: (r.best_back is None, r.best_back or 9999.0))
    return out


# ----------------------------
# Metrics
# ----------------------------

def compute_market_structure_metrics(
    ladders: Iterable[RunnerLadder],
    *,
    anchor_top_n: int = 3,
    soup_top_k: int = 5,
    tier_top_region: int = 6,
) -> MarketStructureMetrics:
    rows = list(ladders)
    runner_count = len(rows)

    priced = [r for r in rows if r.best_back is not None and r.best_back > 0]
    priced_runner_count = len(priced)

    # Anchor: sum implied probs of top_n favourites (lowest prices)
    top = priced[: max(anchor_top_n, 0)]
    top_n_implied_sum = sum((r.implied_prob or 0.0) for r in top)

    # Soup: top_k band ratio = max_price / min_price within top_k
    soup_rows = priced[: max(soup_top_k, 0)]
    if len(soup_rows) >= 2:
        prices = [r.best_back for r in soup_rows if r.best_back is not None]
        mn = min(prices)
        mx = max(prices)
        soup_band_ratio = (mx / mn) if mn > 0 else 999.0
    else:
        soup_band_ratio = 999.0

    # Tier: max adjacent ratio within top_region
    tier_rows = priced[: max(tier_top_region, 0)]
    tier_max_adjacent_ratio = 0.0
    for a, b in zip(tier_rows, tier_rows[1:]):
        if a.best_back and b.best_back and a.best_back > 0:
            tier_max_adjacent_ratio = max(tier_max_adjacent_ratio, b.best_back / a.best_back)

    return MarketStructureMetrics(
        runner_count=runner_count,
        priced_runner_count=priced_runner_count,
        top_n_implied_sum=top_n_implied_sum,
        soup_band_ratio=soup_band_ratio,
        tier_max_adjacent_ratio=tier_max_adjacent_ratio,
    )