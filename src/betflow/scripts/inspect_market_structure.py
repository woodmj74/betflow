# src/betflow/scripts/inspect_market_structure.py

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from betflow.filter_config import load_filter_config

# NOTE:
# Keep structure_metrics.py PURE (no config imports).
# This script can import both config + metrics and glue them together.

# These imports should already exist in your repo, but names may differ slightly.
# If your client lives somewhere else, adjust THESE imports only.
from betflow.betfair.client import BetfairClient  # type: ignore
from betflow.betfair.types import MarketBook, MarketCatalogue  # type: ignore
from betflow.market.structure_metrics import compute_structure_metrics  # type: ignore


def _cfg_to_dict(cfg_obj: Any) -> Dict[str, Any]:
    """
    Convert FilterConfig (pydantic v1/v2) or plain dict into a plain dict.
    """
    if cfg_obj is None:
        return {}
    if isinstance(cfg_obj, dict):
        return cfg_obj
    # Pydantic v2
    if hasattr(cfg_obj, "model_dump"):
        return cfg_obj.model_dump()
    # Pydantic v1
    if hasattr(cfg_obj, "dict"):
        return cfg_obj.dict()
    # Fallback (best effort)
    return dict(cfg_obj)


def _get(d: Dict[str, Any], path: str, default: Any = None) -> Any:
    """
    Simple dotted-path getter, e.g. _get(cfg, "runner_target.odds.min", 12.0)
    """
    cur: Any = d
    for key in path.split("."):
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur


def _print_kv(title: str, value: Any) -> None:
    print(f"{title:<30} {value}")


def _fmt_runner_no(i: int) -> str:
    # 1 -> 01, 9 -> 09, 10 -> 10
    return f"{i:02d}"


@dataclass(frozen=True)
class InspectInputs:
    market_id: str
    config_path: Optional[Path]


def parse_args() -> InspectInputs:
    p = argparse.ArgumentParser(
        prog="inspect_market_structure",
        description="Inspect a market's structure metrics and config-driven checks.",
    )
    p.add_argument("market_id", help="Betfair marketId, e.g. 1.254188322")
    p.add_argument(
        "--config",
        dest="config_path",
        default=None,
        help="Optional path to filters.yaml (defaults to repo config/filters.yaml via loader default).",
    )
    args = p.parse_args()
    return InspectInputs(
        market_id=args.market_id,
        config_path=Path(args.config_path) if args.config_path else None,
    )


def main() -> None:
    inp = parse_args()

    # --- Load config (FIXED FUNCTION NAME) ---
    cfg_obj = load_filter_config(inp.config_path)
    cfg = _cfg_to_dict(cfg_obj)

    print("====================================================")
    print("[INSPECT] Market Structure")
    print("====================================================")
    _print_kv("Market ID:", inp.market_id)
    _print_kv("Config path:", str(inp.config_path) if inp.config_path else "(default loader path)")
    print("----------------------------------------------------")

    # --- Connect client ---
    client = BetfairClient.from_env()  # this matches the pattern you used elsewhere
    client.login()

    # --- Fetch market data ---
    # You likely already have helpers for this in your other scripts.
    # Keep it simple here: catalogue (names/runners/start), book (prices).
    cat: MarketCatalogue = client.get_market_catalogue(inp.market_id)
    book: MarketBook = client.get_market_book(inp.market_id)

    # --- Print market header ---
    _print_kv("Market name:", getattr(cat, "market_name", getattr(cat, "marketName", "(unknown)")))
    _print_kv("Start time:", getattr(cat, "market_start_time", getattr(cat, "marketStartTime", "(unknown)")))
    _print_kv("Event:", getattr(getattr(cat, "event", None), "name", "(unknown)"))
    print("----------------------------------------------------")

    # --- Compute metrics (structure_metrics remains pure) ---
    metrics = compute_structure_metrics(cat, book)

    # --- Display metrics summary ---
    print("[METRICS]")
    for k in sorted(metrics.keys()):
        _print_kv(f"- {k}:", metrics[k])
    print("----------------------------------------------------")

    # --- Example config-driven checks (read-only) ---
    # These assume your YAML shape from our filters.yaml discussions.
    # Adjust dotted paths if your schema differs.
    min_runners = _get(cfg, "market_eligibility.runners.min", 7)
    max_runners = _get(cfg, "market_eligibility.runners.max", 16)

    odds_min = _get(cfg, "runner_target.odds.min", 12.0)
    odds_max = _get(cfg, "runner_target.odds.max", 18.0)

    spread_max_ticks = _get(cfg, "runner_target.spread.max_ticks", 3)

    print("[CONFIG CHECKS]")
    _print_kv("Runner bounds:", f"{min_runners}–{max_runners}")
    _print_kv("Target odds band:", f"{odds_min}–{odds_max}")
    _print_kv("Max spread ticks:", spread_max_ticks)
    print("----------------------------------------------------")

    # --- Ladder view (human-friendly; with leading-zero runner numbers) ---
    # We’re intentionally “business readable” here.
    runners = getattr(book, "runners", [])
    if not runners:
        print("[LADDER] No runners found in marketBook.")
        return

    print("[LADDER] (best available back/lay)")
    print(f"{'No':>2}  {'Runner':<26}  {'Back':>8}  {'Lay':>8}  {'Spread':>8}")
    print("-" * 60)

    # Attempt to map selectionId -> runner name from catalogue
    name_by_sel: Dict[int, str] = {}
    cat_runners = getattr(cat, "runners", getattr(cat, "runners", [])) or []
    for r in cat_runners:
        sel_id = int(getattr(r, "selection_id", getattr(r, "selectionId", 0)) or 0)
        nm = str(getattr(r, "runner_name", getattr(r, "runnerName", "")) or "")
        if sel_id:
            name_by_sel[sel_id] = nm

    # Sort by last traded price if present; fallback selectionId
    def _runner_sort_key(r: Any) -> Any:
        ltp = getattr(r, "last_price_traded", getattr(r, "lastPriceTraded", None))
        sel = getattr(r, "selection_id", getattr(r, "selectionId", 0))
        return (ltp is None, ltp if ltp is not None else 9999.0, int(sel or 0))

    runners_sorted = sorted(runners, key=_runner_sort_key)

    for idx, r in enumerate(runners_sorted, start=1):
        sel = int(getattr(r, "selection_id", getattr(r, "selectionId", 0)) or 0)
        nm = name_by_sel.get(sel, f"selectionId {sel}")

        ex = getattr(r, "ex", None)
        backs = getattr(ex, "available_to_back", getattr(ex, "availableToBack", [])) if ex else []
        lays = getattr(ex, "available_to_lay", getattr(ex, "availableToLay", [])) if ex else []

        best_back = float(getattr(backs[0], "price", getattr(backs[0], "price", 0.0))) if backs else 0.0
        best_lay = float(getattr(lays[0], "price", getattr(lays[0], "price", 0.0))) if lays else 0.0

        spread = best_lay - best_back if best_back and best_lay else 0.0

        print(
            f"{_fmt_runner_no(idx):>2}  "
            f"{nm[:26]:<26}  "
            f"{best_back:>8.2f}  "
            f"{best_lay:>8.2f}  "
            f"{spread:>8.2f}"
        )

    print("====================================================")


if __name__ == "__main__":
    main()
