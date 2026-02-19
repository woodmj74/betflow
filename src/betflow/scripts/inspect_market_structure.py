from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import asdict, is_dataclass


from betflow.betfair.client import BetfairClient
from betflow.filter_config import load_filter_config


# ----------------------------
# Helpers
# ----------------------------

def _cfg_to_dict(cfg_obj: Any) -> Dict[str, Any]:
    """
    Convert FilterConfig (dataclass), pydantic v1/v2 model, or plain dict into a plain dict.
    """
    if cfg_obj is None:
        return {}
    if isinstance(cfg_obj, dict):
        return cfg_obj

    # Dataclasses (your FilterConfig is one)
    if is_dataclass(cfg_obj):
        return asdict(cfg_obj)

    # Pydantic v2
    if hasattr(cfg_obj, "model_dump"):
        return cfg_obj.model_dump()

    # Pydantic v1
    if hasattr(cfg_obj, "dict"):
        return cfg_obj.dict()

    # Fallback
    if hasattr(cfg_obj, "__dict__"):
        return dict(vars(cfg_obj))

    raise TypeError(f"Unsupported config object type: {type(cfg_obj)}")



def _get(d: Dict[str, Any], path: str, default: Any = None) -> Any:
    cur: Any = d
    for key in path.split("."):
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur


def _print_kv(k: str, v: Any) -> None:
    print(f"{k:<28} {v}")


def _fmt_runner_no(n: int) -> str:
    # Leading zero for single digits
    return f"{n:02d}"


def _parse_betfair_dt(s: str) -> str:
    # Keep it simple: normalise Z -> +00:00 then show UTC
    if not s:
        return "(unknown)"
    txt = str(s).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(txt)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%MZ")
    except Exception:
        return str(s)


def _best_price(offers: Any) -> float:
    """
    offers is typically a list like [{"price": 12.0, "size": 3.45}, ...]
    """
    if not isinstance(offers, list) or not offers:
        return 0.0
    top = offers[0]
    if isinstance(top, dict):
        return float(top.get("price") or 0.0)
    return 0.0


def _tick_size(odds: float) -> float:
    """
    Betfair tick ladder (simplified, standard increments).
    """
    if odds < 2:
        return 0.01
    if odds < 3:
        return 0.02
    if odds < 4:
        return 0.05
    if odds < 6:
        return 0.1
    if odds < 10:
        return 0.2
    if odds < 20:
        return 0.5
    if odds < 30:
        return 1.0
    if odds < 50:
        return 2.0
    if odds < 100:
        return 5.0
    return 10.0


def _spread_ticks(best_back: float, best_lay: float) -> int:
    if best_back <= 0 or best_lay <= 0 or best_lay < best_back:
        return 0
    # Approx ticks using tick size at back price (good enough for diagnostics)
    step = _tick_size(best_back)
    return int(round((best_lay - best_back) / step))


# ----------------------------
# RPC fetchers
# ----------------------------

def fetch_market_catalogue(client: BetfairClient, market_id: str) -> Dict[str, Any]:
    params = {
        "filter": {"marketIds": [market_id]},
        "maxResults": 1,
        "marketProjection": ["EVENT", "MARKET_START_TIME", "RUNNER_DESCRIPTION"],
    }
    rows = client.rpc("listMarketCatalogue", params)
    if isinstance(rows, list) and rows:
        return rows[0] if isinstance(rows[0], dict) else {}
    return {}


def fetch_market_book(client: BetfairClient, market_id: str) -> Dict[str, Any]:
    params = {
        "marketIds": [market_id],
        "priceProjection": {"priceData": ["EX_BEST_OFFERS"]},
    }
    rows = client.rpc("listMarketBook", params)
    if isinstance(rows, list) and rows:
        return rows[0] if isinstance(rows[0], dict) else {}
    return {}


# ----------------------------
# Main
# ----------------------------

@dataclass(frozen=True)
class Inputs:
    market_id: str
    config_path: Optional[Path]


def parse_args() -> Inputs:
    p = argparse.ArgumentParser(
        prog="inspect_market_structure",
        description="Inspect one market: catalogue + book + basic ladder and structure diagnostics.",
    )
    p.add_argument("market_id", help="Betfair marketId, e.g. 1.254186158")
    p.add_argument("--config", dest="config_path", default=None, help="Optional path to config/filters.yaml")
    a = p.parse_args()
    return Inputs(
        market_id=a.market_id,
        config_path=Path(a.config_path) if a.config_path else None,
    )


def main() -> int:
    inp = parse_args()

    cfg_obj = load_filter_config(inp.config_path)
    cfg = _cfg_to_dict(cfg_obj)

    print("====================================================")
    print("[INSPECT] Market Structure")
    print("====================================================")
    _print_kv("Market ID:", inp.market_id)
    _print_kv("Config:", str(inp.config_path) if inp.config_path else "(default loader path)")
    print("----------------------------------------------------")

    client = BetfairClient()
    client.login()

    cat = fetch_market_catalogue(client, inp.market_id)
    book = fetch_market_book(client, inp.market_id)

    market_name = str(cat.get("marketName") or "(unknown)")
    start_time = _parse_betfair_dt(str(cat.get("marketStartTime") or ""))
    event = cat.get("event") if isinstance(cat.get("event"), dict) else {}
    country = str((event or {}).get("countryCode") or "")

    _print_kv("Market name:", market_name)
    _print_kv("Start time:", start_time)
    _print_kv("Country:", country)
    _print_kv("Status:", book.get("status", "(unknown)"))
    _print_kv("In-play:", book.get("inplay", "(unknown)"))
    _print_kv("Total matched:", float(book.get("totalMatched") or 0.0))
    print("----------------------------------------------------")

    # Config snippets (read-only, just for context)
    odds_min = _get(cfg, "runner_target.odds.min", 12.0)
    odds_max = _get(cfg, "runner_target.odds.max", 18.0)
    max_spread_ticks = _get(cfg, "runner_target.spread.max_ticks", 3)

    print("[CONFIG]")
    _print_kv("Target odds band:", f"{odds_min}–{odds_max}")
    _print_kv("Max spread ticks:", max_spread_ticks)
    print("----------------------------------------------------")

    # Build selectionId -> (runnerName, sortPriority)
    runners_cat = cat.get("runners") if isinstance(cat.get("runners"), list) else []
    cat_map: Dict[int, Tuple[str, int]] = {}
    for r in runners_cat:
        if not isinstance(r, dict):
            continue
        sid = int(r.get("selectionId") or 0)
        name = str(r.get("runnerName") or "")
        sp = int(r.get("sortPriority") or 0)
        if sid:
            cat_map[sid] = (name, sp)

    runners_book = book.get("runners") if isinstance(book.get("runners"), list) else []
    if not runners_book:
        print("[LADDER] No runners in marketBook (maybe suspended / API returned empty).")
        print("====================================================")
        return 0

    # Sort by sortPriority if available; fall back to selectionId
    def sort_key(rb: Any) -> Tuple[int, int]:
        sid = int(rb.get("selectionId") or 0) if isinstance(rb, dict) else 0
        sp = cat_map.get(sid, ("", 9999))[1]
        return (sp if sp else 9999, sid)

    runners_book_sorted = sorted([r for r in runners_book if isinstance(r, dict)], key=sort_key)

    # Basic structure metrics: how many runners are "compressed" under 10.0 (using best back if available else LTP)
    under_10 = 0

    print("[LADDER] (best available back/lay)")
    print(f"{'No':>2}  {'Runner':<28}  {'Back':>8}  {'Lay':>8}  {'Spr(t)':>6}")
    print("-" * 62)

    for rb in runners_book_sorted:
        sid = int(rb.get("selectionId") or 0)
        name, sp = cat_map.get(sid, (f"selectionId {sid}", 0))

        ex = rb.get("ex") if isinstance(rb.get("ex"), dict) else {}
        atb = ex.get("availableToBack")
        atl = ex.get("availableToLay")

        best_back = _best_price(atb)
        best_lay = _best_price(atl)
        ltp = float(rb.get("lastPriceTraded") or 0.0)

        # Use back if we have it, else LTP
        ref_price = best_back if best_back > 0 else ltp
        if ref_price and ref_price < 10.0:
            under_10 += 1

        ticks = _spread_ticks(best_back, best_lay)

        runner_no = sp if sp else 0
        rn = _fmt_runner_no(runner_no) if runner_no else "--"

        print(
            f"{rn:>2}  "
            f"{name[:28]:<28}  "
            f"{best_back:>8.2f}  "
            f"{best_lay:>8.2f}  "
            f"{ticks:>6}"
        )

    print("----------------------------------------------------")
    print("[STRUCTURE]")
    _print_kv("Runner count:", len(runners_book_sorted))
    _print_kv("Runners < 10.0:", under_10)
    print("====================================================")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
