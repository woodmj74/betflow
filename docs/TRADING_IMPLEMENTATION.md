# Betflow Trading Implementation
Version: 0.1  
Status: Working Design Notes (matches current code baseline)

This document describes the step-by-step implementation flow Betflow uses to move from “markets on Betfair” to “one selected runner (or no selection)”. It is intentionally structural and auditable.

---

## 0. Inputs and Configuration

### 0.1 Configuration Source
- Config is loaded from `config/filters.yaml` via `load_filter_config()`.
- Config is treated as a single source of truth for thresholds and ranges.

### 0.2 Core Configuration Areas
- `global.horizon_hours` and `global.take`: control which markets are pulled.
- `global.defaults`: baseline runner count range and liquidity minimum.
- `regions`: per-region overrides (market countries, liquidity threshold, optional runner ranges).
- `structure_gates`: market structure rules (anchor / soup / tier).
- `selection`: runner selection rules (bands, spreads, rank exclusions).

---

# 1. Market Discovery

Goal: find candidate WIN markets worth inspecting further.

Implemented in:
- `services/market_discovery.py`
- `scripts/discover_markets.py`

---

## 1.1 Market Query (Time Window)

- Query Betfair for Horse Racing WIN markets.
- Restrict to configured countries / regions.
- Restrict to markets within `global.horizon_hours`.
- Typically take next `global.take` markets.

No runner logic occurs here.

---

## 1.2 Region Mapping

- Each market is mapped to a configured `region` via `event.countryCode`.
- If no region matches → market rejected.

---

## 1.3 Runner Count Gate (Hard Market Veto)

**Rule:** Reject if runner count not within configured range.

- Determine runner count from MarketCatalogue.
- Allowed range:
  - Region-specific override (if present)
  - Otherwise `global.defaults.runner_count`
- If `< min` or `> max` → MARKET REJECTED.

Purpose:
- Avoid very small fields.
- Avoid excessively large fields with unstable tails.

---

## 1.4 Liquidity Gate (Hard Market Veto)

**Rule:** Reject if traded volume below threshold.

- Determine liquidity threshold:
  - Region override if present
  - Otherwise `global.defaults.liquidity_min`
- If liquidity `< threshold` → MARKET REJECTED.

Purpose:
- Avoid thin markets.
- Avoid unreliable spreads and unstable ladders.

---

## 1.5 Discovery Output

Produces:
- Eligible markets.
- Rejected markets with explicit reasons.

At this stage no runner is considered.

---

# 2. Market Inspection (Stage 1 – Structural Gate)

Goal: determine if the market is structurally tradable.

Implemented in:
- `scripts/inspect_market_structure.py`
- `markets/structure_metrics.py`
- `markets/market_rules.py`

---

## 2.1 Load Market Data

For a given market ID:

- Load MarketCatalogue (metadata).
- Load MarketBook (best offers).

---

## 2.2 Build Runner Ladders

Convert raw prices into structured ladder objects containing:

- best back price
- best lay price
- spread in ticks
- runner name / runner number

This becomes the basis for structure metrics and selection.

---

## 2.3 Compute Market Structure Metrics

Examples:

- Top N implied probability sum
- Price compression / flatness indicators
- Tier separation indicators

Metrics describe the shape of the market without narrative interpretation.

---

## 2.4 Evaluate Structure Gates (Hard Market Veto)

### 2.4.1 Anchor Gate

**Rule:** Top N runners must hold minimum implied probability.

- Compute implied probability: `1 / best_back`
- Sort by best_back ascending
- Sum top `structure_gates.anchor.top_n`
- If sum `< min_top_implied` → FAIL

---

### 2.4.2 Soup Gate

**Rule:** Reject flat, compressed top clusters.

- Consider top `structure_gates.soup.top_k`
- Compute `max_price / min_price`
- If ratio `<= max_band_ratio` → FAIL

---

### 2.4.3 Tier Gate

**Rule:** Require visible tier breaks.

- Consider top `structure_gates.tier.top_region`
- Check adjacent price jump ratios
- If no jump ≥ `min_jump_ratio` → FAIL

---

## 2.5 Stage 1 Result

- If any gate fails → MARKET REJECTED
- If all pass → MARKET ACCEPTED

Only accepted markets proceed to runner selection.

---

# 3. Runner Selection (Stage 2 – Candidate Selection)

Goal: select one runner within an accepted market.

Selection is implemented as a pure function using ladders + metrics + config.

---

## 3.1 Hard Band (Strategy Identity Guardrail)

**Rule:** Never select outside `selection.hard_band`.

If `best_back` outside `[min, max]` → runner ineligible.

Purpose:
- Prevent strategy drift.
- Define operating identity.

---

## 3.2 Primary Band (Normal Range)

**Rule:** Prefer runners inside `selection.primary_band`.

This is the main harvesting zone.

---

## 3.3 Secondary Band (Conditional Range)

**Rule:** Only consider secondary band if anchoring is strong.

Condition:

`topN_implied_sum >= secondary_band.requires_top_n_implied_at_least`

If not satisfied → secondary runners rejected.

---

## 3.4 Spread Gate (Execution Quality)

**Rule:** Spread must be ≤ `selection.max_spread_ticks`.

If `spread_ticks > max` → runner rejected.

Purpose:
- Maintain tradeability.
- Avoid noisy pricing.

---

## 3.5 Rank Exclusion (Mid-Field Bias)

Rank exclusion may be static (fixed top_n/bottom_n) or dynamic (resolved via field-size rules). Only the resolved exclusion is applied and printed.

- Assign `price_rank` (1 = favourite).
- Exclude:
  - Top `rank_exclusion.top_n`
  - Bottom `rank_exclusion.bottom_n`

Purpose:
- Avoid favourites-adjacent runners.
- Avoid deep tail rags.
- Focus on structural mid-field.

---

## 3.6 Selection Ordering Logic (Scoring Model)

Betflow does not use predictive modelling.  
The selection “score” is simply a deterministic ordering mechanism between already-eligible runners.

### Design Intent

The ordering reflects two priorities:

1. Execution quality (tight spreads)
2. Structural fit within the preferred band (avoid edges)

No narrative or outcome-based inputs are used.

---

### Units of Measurement

All distance comparisons are performed in **Betfair ticks**, not raw price differences.

Reason:
- Tick size varies across price ranges.
- Spread is already measured in ticks.
- Using ticks keeps distance and spread comparable and interpretable.

---

### Primary Band Ordering

For runners in the Primary band:

1. Lowest `spread_ticks` wins.
2. If tied, lowest `distance_from_primary_centre_ticks` wins.
3. If still tied, lowest `best_back` wins (stable deterministic fallback).

Where:

- `primary_centre = (primary_band.min + primary_band.max) / 2`
- `distance_from_primary_centre_ticks` is the number of Betfair ladder ticks between `best_back` and `primary_centre`.

This ensures:
- Spread is treated as the dominant execution quality signal.
- Centrality only differentiates equally tradeable candidates.
- Behaviour is stable and explainable.

---

### Secondary Band Ordering

Secondary band runners are only considered if anchoring condition is met.

When allowed:

- Secondary runners are ordered using the same logic:
  1. Lowest spread ticks
  2. Lowest distance from secondary centre (in ticks)
  3. Deterministic fallback

However, Primary band candidates always take precedence over Secondary band candidates.

---

### No Numeric Prediction Model

Although a numeric score may be displayed for debugging purposes, it is derived directly from:

- spread_ticks
- distance_from_centre_ticks

It does not represent probability, confidence, or expected value.

It is purely a sorting mechanism.

---

## 3.7 Debug and Audit Output (Mandatory)

Selection must print:

- Config summary.
- One row per runner with PASS / FAIL and reason.
- Spread ticks.
- Distance from centre in ticks.
- Stable `selection_summary` line.

This ensures:
- Behaviour changes can be traced to price movement.
- Threshold effects (band boundaries, spread limits, anchoring) are visible.
- The system remains explainable and reproducible.


---

# 4. Non-Goals (Current Phase)

Not yet implemented:

- Bet placement (paper or live).
- Database persistence.
- Session P/L awareness.
- Multi-runner per market.
- Volatility or time-series stability scoring.

Future phases must preserve structural philosophy.

---

# 5. Commands (Reference)

Discovery:

```
python -m betflow.scripts.discover_markets
```

Inspect structure:

```
python -m betflow.scripts.inspect_market_structure <market_id>
```