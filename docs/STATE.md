# Betflow — STATE

Last updated: 2026-02-20 (Europe/London)

---

# Current Phase

**Phase 2 — Market Structure + Deterministic Runner Selection**

We have returned to **Mode A (Single-Developer Incremental Build)**.

Architecture cleanup is complete.  
Selection logic is now deterministic and explainable.  
No numeric “scoring” model remains.

---

# System Status — Green Baseline

## Connectivity

- Betfair certificate login via `BetfairClient()` working.
- JSON-RPC calls returning valid `MarketCatalogue` + `MarketBook`.
- Automatic session retry implemented (re-login once, retry once).
- Connection smoke tests pass.

---

# Canonical Modules

## `betflow.markets.structure_metrics`

Pure module. No RPC, no CLI.

Provides:

- `build_runner_ladders(market_catalogue, market_book)`
- `compute_market_structure_metrics(ladders, ...)`
- `select_candidate_runner(...)`
- `RunnerLadder`
- `MarketStructureMetrics`
- `RunnerSelectionRow`

Features:

- Betfair tick ladder modelling
- Spread in ticks
- Distance-from-band-centre (in ticks, rounded)
- Deterministic runner ordering:
  - Lowest spread
  - Then closest to band centre
  - Then lowest price fallback
- Primary takes precedence over Secondary
- Secondary only allowed if anchoring condition satisfied

No numeric scoring is used for decision making.

---

## `betflow.markets.market_rules`

Provides:

- `evaluate_market_rules(...)`

Features:

- Region mapping via `market_countries`
- Region overrides:
  - runner count range
  - liquidity minimum
- Structure gates:
  - Anchor (top N implied probability sum)
  - Soup (top K band compression ratio)
  - Tier (max adjacent jump ratio)

Returns:

- ACCEPT / REJECT
- Region code
- Per-rule pass/fail diagnostics

---

## `betflow.scripts.inspect_market_structure`

Displays:

- `[MARKET]`
- `[VALIDATION]`
- `[LADDER]` (always printed)
- `[SELECTION]`
- `[DECISION]`

Selection table columns:

- No (two-digit cloth number)
- Runner (truncated)
- Back
- Lay
- Sprd (spread ticks)
- Dist (distance ticks from band midpoint)
- Band (PRIMARY / SECONDARY / HARD / -)
- Status (ELIGIBLE / REJECTED)
- Reason (explicit rejection cause)

Rank exclusion diagnostics now appended even if runner failed earlier gates:
e.g.
- `outside hard band; excluded: top 2`

Formatting supports prices up to 1000.00.

---

# Trading Model (As Implemented)

## Stage 1 — Hard Market Gate

Market must pass:

- Region eligibility
- Runner count range
- Liquidity threshold
- Anchor gate
- Soup gate
- Tier gate

If any fail → MARKET REJECTED.

---

## Stage 2 — Deterministic Runner Selection

Applied only if market accepted.

Gates (in order):

1. Missing back/lay
2. Hard band
3. Spread threshold
4. Rank exclusion (top_n / bottom_n)
5. Primary / Secondary band classification

Ordering rule (no scoring):

- Primary candidates sorted by:
  - spread_ticks (ascending)
  - distance_ticks (ascending)
  - best_back (ascending)

- If no Primary candidates:
  - Secondary candidates (if anchoring allows) sorted the same way.

One runner selected per market.
If none eligible → no selection.

---

# Philosophy Alignment

System now fully reflects:

- Structural, not predictive trading
- Explainable selection logic
- Deterministic ordering
- No P/L awareness
- No session-based adaptation
- No narrative factors

Numeric “score” model removed.
Selection now mirrors human explanation logic.

---

# Proof Commands

Run from repo root:

```bash
# Import sanity
python -c "import betflow; print('imports ok')"

# Connection smoke test
python -m betflow.scripts.test_connection

# Market inspection + selection
python -m betflow.scripts.inspect_market_structure <market_id>

Expected:
- Market printed
- Validation gates shown
- Ladder always printed
- Selection table shown
- Selected runner (if any)
- MARKET ACCEPTED / REJECTED


---

# Repo Structure (Current)

- `src/betflow/betfair/` — API client
- `src/betflow/markets/` — structure + rules + selection (pure logic)
- `src/betflow/services/` — discovery
- `src/betflow/scripts/` — runnable utilities
- `config/` — YAML config
- `docs/` — documentation

---

# Environment Variables

Required (local `.env`, not committed):

- `BETFAIR_APP_KEY`
- `BETFAIR_USERNAME`
- `BETFAIR_PASSWORD`

Optional:

- `BETFAIR_CERT_CRT`
- `BETFAIR_CERT_KEY`
- `BETFLOW_ENV`

---

# Non-Negotiables

- No secrets committed.
- Every capability has a proof command.
- Small commits.
- One concern per commit.
- No architectural shifts without checkpointing.
- No duplicate config sources.
- Markets logic remains pure and testable.

---

# Known Gotchas

- Betfair cert login may return JSON.
- Session tokens expire — retry logic handles this.
- Tick ladder is approximate but correct for structural use.
- MarketBook must request `EX_BEST_OFFERS` for spread calculation.

---

# Immediate Next Steps (Mode A)

1. Clean selection output further (remove legacy score usage entirely).
2. Stabilise selection behaviour across multiple live markets.
3. Capture structured selection output for persistence layer.
4. Design paper-bet object model (no live orders yet).
5. Define audit logging format (selection + structure snapshot).

---

# Development Discipline

We are operating as:

- One developer
- One direction
- Incremental capability
- Deterministic behaviour
- Fully explainable logic

No parallel experiments.
No silent refactors.
No architecture drift.

---

2026-02-21 – Selection Engine Refinement

  Rank exclusion now supports dynamic rules based on ACTIVE runner count
  Only the resolved exclusion is printed (Top X / Bottom Y (dynamic|static))
  ACTIVE runners (status == ACTIVE) are the sole source of truth for:
  Field size
  Structure metrics
  Rank exclusion
  Selection ordering
  _print_selection_debug() cleaned to remove duplicate helpers
  No architectural change. Single-path evolution maintained.

End of STATE.