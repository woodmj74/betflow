from __future__ import annotations

import sys
from datetime import datetime, timezone
from typing import Any

from betflow.betfair.client import BetfairClient


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


def _get(d: dict, path: list[str], default: Any = None) -> Any:
    cur: Any = d
    for p in path:
        if not isinstance(cur, dict) or p not in cur:
            return default
        cur = cur[p]
    return cur


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python -m betflow.scripts.inspect_market_structure <marketId>")
        return 2

    market_id = sys.argv[1].strip()

    
    # Pull structure gate config
    anchor_top_n = int(_get(cfg, ["structure_gates", "anchor", "top_n"], 3))
    min_top_implied = float(_get(cfg, ["structure_gates", "anchor", "min_top_implied"], 0.65))

    soup_top_k = int(_get(cfg, ["structure_gates", "soup", "top_k"], 5))
    soup_threshold = float(_get(cfg, ["structure_gates", "soup", "max_band_ratio"], 1.20))

    tier_top_region = int(_get(cfg, ["structure_gates", "tier", "top_region"], 6))
    tier_min_jump = float(_get(cfg, ["structure_gates", "tier", "min_jump_ratio"], 1.25))

    bf = BetfairClient()

    # --- MarketCatalogue ---
    cat_params = {
        "filter": {"marketIds": [market_id]},
        "maxResults": 1,
        "marketProjection": [
            "RUNNER_DESCRIPTION",
            "RUNNER_METADATA",
            "MARKET_START_TIME",
            "EVENT",
            "MARKET_DESCRIPTION",
        ],
    }

    cats = bf.rpc("listMarketCatalogue", cat_params)
    if not cats:
        print(f"No market found for {market_id}")
        return 1

    cat = cats[0]
    market_name = cat.get("marketName", "?")
    start_time = cat.get("marketStartTime", "?")
    event_name = (cat.get("event") or {}).get("name", "?")

    sel_to_name: dict[int, str] = {}
    sel_to_num: dict[int, int | None] = {}
    for r in (cat.get("runners") or []):
        sid = int(r.get("selectionId"))
        sel_to_name[sid] = r.get("runnerName", f"sel:{sid}")
        sel_to_num[sid] = _cloth_number_from_metadata(r.get("metadata") or {})

    # --- MarketBook ---
    book_params = {
        "marketIds": [market_id],
        "priceProjection": {
            "priceData": ["EX_BEST_OFFERS"],
            "exBestOffersOverrides": {"bestPricesDepth": 1},
        },
        "orderProjection": "ALL",
        "matchProjection": "NO_ROLLUP",
    }

    books = bf.rpc("listMarketBook", book_params)
    if not books:
        print(f"No market book returned for {market_id}")
        return 1

    book = books[0]
    runners_book = book.get("runners") or []

    rp: list[RunnerPrice] = []
    for rb in runners_book:
        sid = int(rb.get("selectionId"))
        ex = rb.get("ex") or {}
        best_back = _best_price(ex, "availableToBack")
        best_lay = _best_price(ex, "availableToLay")
        rp.append(
            RunnerPrice(
                selection_id=sid,
                runner_number=sel_to_num.get(sid),
                name=sel_to_name.get(sid, f"sel:{sid}"),
                best_back=best_back,
                best_lay=best_lay,
            )
        )

    rp.sort(key=lambda r: (r.best_back is None, r.best_back or 9999.0))

    # --- Metrics + gate using config thresholds ---
    metrics = compute_structure_metrics(
        rp,
        anchor_top_n=anchor_top_n,
        tier_top_region=tier_top_region,
        soup_top_k=soup_top_k,
        soup_band_ratio_threshold=soup_threshold,
    )

    passed, reasons = market_gate_passes(
        metrics,
        min_top_cluster_implied=min_top_implied,
        max_soup_band_ratio=soup_threshold,
        min_tier_jump_ratio=tier_min_jump,
    )

    # --- Print report ---
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    print()
    print(f"[STRUCTURE] {now}")
    print(f"Market: {market_id}  |  {event_name}  |  {market_name}")
    print(f"Start:  {start_time}")
    print()

    print("Gate thresholds (from config):")
    print(f"  Anchor: top_n={anchor_top_n}  min_top_implied={min_top_implied:.3f}")
    print(f"  Soup:   top_k={soup_top_k}    max_band_ratio={soup_threshold:.3f}")
    print(f"  Tier:   top_region={tier_top_region}  min_jump_ratio={tier_min_jump:.3f}")
    print()

    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"Gate: {status}")
    for line in reasons:
        print(f"  - {line}")
    print()

    print(
        f"Stats: runners={metrics.runner_count}  "
        f"top{metrics.top_cluster_n}_implied={metrics.top_cluster_implied_sum:.3f}  "
        f"tier_jump(max top)={metrics.max_tier_jump_ratio_top:.3f}  "
        f"soup_ratio(top{metrics.soup_top_k})={metrics.soup_band_ratio:.3f}"
    )
    print()

    print("Runners (sorted by best BACK):")
    print("No  Back    Lay     Sprd   Impl%   Name")
    print("--  ------  ------  -----  ------  ------------------------------")
    for r in rp[: min(20, len(rp))]:
        num = f"{r.runner_number:02d}" if isinstance(r.runner_number, int) else "--"
        back = f"{r.best_back:>6.2f}" if r.best_back is not None else "  None"
        lay = f"{r.best_lay:>6.2f}" if r.best_lay is not None else "  None"
        sprd = f"{r.spread:>5.2f}" if r.spread is not None else " None"
        impl = f"{(r.implied_from_back * 100):>5.1f}%" if r.implied_from_back is not None else "  N/A"
        print(f"{num}  {back}  {lay}  {sprd}  {impl:>6}  {r.name[:30]}")

    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
