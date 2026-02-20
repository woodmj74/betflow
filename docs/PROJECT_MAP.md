Betflow Trading Implementation

Version: 0.2
Status: Working Design Notes (aligned to deterministic implementation)

This document describes the step-by-step implementation flow Betflow uses to move from “markets on Betfair” to “one selected runner (or no selection)”.

This is an implementation document.
It explains how configuration interacts with execution.

0. Inputs and Configuration
0.1 Configuration Source

Config is loaded from config/filters.yaml via load_filter_config().

Config is treated as the single source of truth.

No thresholds are hardcoded in scripts.

0.2 Core Configuration Areas
Global

global.horizon_hours

global.take

global.defaults.runner_count

global.defaults.liquidity_min

Regions

market_countries

optional runner count overrides

optional liquidity overrides

Structure Gates

anchor

soup

tier

Selection

hard_band

primary_band

secondary_band

max_spread_ticks

rank_exclusion.top_n

rank_exclusion.bottom_n

1. Market Discovery (Pre-Structure)

Goal: Identify candidate WIN markets for structural inspection.

Implemented in:

services/market_discovery.py

scripts/discover_markets.py

1.1 Time Window

Pull Horse Racing WIN markets.

Restrict by configured countries.

Restrict to global.horizon_hours.

Take next global.take markets by start time.

No runner logic occurs here.

1.2 Region Mapping

Each market is mapped to a configured region via:

market.event.countryCode

If no region matches → MARKET REJECTED.

1.3 Runner Count Gate

Reject if:

runner_count < min OR runner_count > max

Range resolution:

Region override if present

Else global default

Purpose:

Avoid very small fields.

Avoid excessively large, unstable markets.

1.4 Liquidity Gate

Reject if:

totalMatched < liquidity_min

Threshold resolution:

Region override if present

Else global default

Purpose:

Avoid thin markets.

Avoid unstable spreads.

2. Market Inspection (Stage 1 — Structural Gate)

Goal: Determine if the market is structurally tradable.

Implemented in:

markets.structure_metrics

markets.market_rules

scripts.inspect_market_structure

2.1 Ladder Construction

From:

MarketCatalogue (runner metadata)

MarketBook (best prices)

We build RunnerLadder objects containing:

best_back

best_lay

spread_ticks

runner name

runner number

Tick modelling follows Betfair ladder bands.

2.2 Structure Metrics

Computed metrics include:

top_n_implied_sum

soup_band_ratio

tier_max_adjacent_ratio

These describe shape only — no narrative interpretation.

2.3 Structure Gates

Gates are evaluated in fixed order:

Anchor gate

Soup gate

Tier gate

Any failure → MARKET REJECTED
All pass → MARKET ACCEPTED

Only accepted markets proceed to selection.

3. Runner Selection (Stage 2)

Selection is deterministic and purely structural.

Implemented in:

select_candidate_runner(...)

3.1 Gate Order (Intentional and Preserved)

For each runner (sorted by best_back ascending):

Missing back/lay

Hard band

Spread gate

Rank exclusion

Band classification (Primary / Secondary)

Gate order is intentional.

The first failing rule defines the primary rejection reason.
Rank exclusion may be appended as diagnostic context.

3.2 Hard Band

Reject if:

best_back outside selection.hard_band

Purpose:

Define strategy identity.

Prevent drift into unwanted odds regimes.

3.3 Spread Gate

Reject if:

spread_ticks > selection.max_spread_ticks

Purpose:

Maintain execution quality.

Avoid unstable price ladders.

3.4 Rank Exclusion

After spread passes:

Exclude:

Top rank_exclusion.top_n favourites

Bottom rank_exclusion.bottom_n outsiders

Price rank is assigned BEFORE exclusions.

Rank exclusion:

Removes runners from eligibility.

Does NOT alter structural ordering logic.

May be annotated in debug output.

Purpose:

Avoid favourites-adjacent runners.

Avoid deep tail rags.

Focus on structural mid-field.

3.5 Primary vs Secondary Band

Primary band:

selection.primary_band

Secondary band:

selection.secondary_band

Secondary eligibility requires:

top_n_implied_sum >= secondary.requires_top_n_implied_at_least

If anchoring condition fails → secondary rejected.

Primary candidates always take precedence over secondary.

3.6 Deterministic Ordering (No Scoring Model)

There is no scoring model.

Ordering rule for eligible candidates:

Lowest spread_ticks

Lowest distance_ticks

Lowest best_back

Distance is calculated as:

round(abs(price - band_midpoint) / tick_size(price))

Distance is rounded to nearest whole tick.

This avoids fractional tick debates and preserves explainability.

Exactly one runner is selected.
If none eligible → no selection.

3.7 Debug Output Contract

Selection output must show:

Band

Spread (ticks)

Distance (ticks)

Status (ELIGIBLE / REJECTED)

Explicit rejection reason

Final selection summary

No numeric predictive score is used.

Debug output must allow:

Reproducibility

Clear explanation of behaviour

Visibility into threshold interactions

4. Behavioural Guarantees

No session P/L awareness

No chasing logic

Fixed risk unit model (future phase)

One entry per market

Deterministic behaviour given identical prices

5. Non-Goals (Current Phase)

Not implemented:

Paper betting engine

Persistence layer

Live order placement

Volatility modelling

Multi-runner selection

Future phases must preserve structural integrity.

6. Commands

Discovery:

python -m betflow.scripts.discover_markets

Inspection + Selection:

python -m betflow.scripts.inspect_market_structure <market_id>

End of Document.