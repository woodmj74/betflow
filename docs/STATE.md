# Betflow — STATE

Last updated: 2026-02-19 (Europe/London)

---

## Current Phase

Phase 2 — Market structure inspection + market-level gating.

We are currently in **Mode B (Architecture cleanup)** but very close to returning to Mode A.

---

## Green Baseline (What Works)

### Connectivity
- Betfair login working via `BetfairClient()`
- RPC calls returning valid MarketCatalogue + MarketBook

### Canonical Modules

#### `betflow.markets.structure_metrics`
- `build_runner_ladders(market_catalogue, market_book)`
- `compute_market_structure_metrics(ladders, ...)`
- `MarketStructureMetrics`
- Pure module (no BetfairClient, no CLI logic)

#### `betflow.markets.market_rules`
- `evaluate_market_rules(...)`
- Country → region mapping via `market_countries`
- Region overrides for:
  - runner count
  - liquidity minimum
- Structure gates:
  - Anchor (top N implied sum)
  - Soup (top K band ratio)
  - Tier (max adjacent jump)

#### `betflow.scripts.inspect_market_structure`
- Prints:
  - `[MARKET]`
  - `[VALIDATION]`
  - `[LADDER]` (always, regardless of acceptance)
  - `[DECISION]`
- Ladder includes:
  - cloth number (if available)
  - best back
  - best lay
  - spread ticks

---

## Proof Commands (Baseline)

Run from repo root:

```bash
# Import sanity
python -c "from betflow.markets.structure_metrics import build_runner_ladders, compute_market_structure_metrics, MarketStructureMetrics; from betflow.markets.market_rules import evaluate_market_rules; print('imports ok')"

# Connection smoke test
python -m betflow.scripts.test_connection

# Structure inspect
python -m betflow.scripts.inspect_market_structure <market_id>



### OLD VERSIONS BELOW HERE ###

# Betflow – STATE

## What this repo is
Betflow is a research-oriented Betfair Exchange platform (paper trading first). This repo is being rebuilt deliberately from a clean slate with an emphasis on correctness, auditability, and incremental proof points.

## Clean-slate decision (2026-02-18)
We intentionally reset `main` to a minimal, purpose-built baseline to remove confusion and rebuild with a clear structure and repeatable workflow.
The previous working implementation has been preserved in branch: `firstbuild`.

## Current baseline (as of 2026-02-19)
A minimal skeleton has been implemented under `src/` with:

- `settings.py` — loads environment config via `.env` (local only, not tracked) and exports a singleton `settings`
- `logging.py` — structured logging via `structlog` (pretty console in dev)
- `betfair/client.py` — thin Betfair gateway supporting cert login + JSON-RPC + session retry
- `filter_config.py` — YAML-driven market filtering config loader
- `services/market_discovery.py` — reusable market discovery + eligibility logic (Phase 1: region + runners + liquidity)
- `scripts/test_connection.py` — smoke test proving auth + API call
- `scripts/test_session_retry.py` — proof of automatic re-login on invalid session
- `scripts/discover_markets.py` — prints next markets by time with verbose eligibility reasons

### Proof points (work)
Run from repo root:

0) Import sanity check:
`python -c "import betflow; print('imports ok')"`

1) Connection smoke test:
`python -m betflow.scripts.test_connection`

Expected:
- Successful Betfair cert login
- Successful JSON-RPC call to `listEventTypes`
- Prints the first ~10 event types and "✅ Connection looks good."

2) Session retry proof:
`python -m betflow.scripts.test_session_retry`

Expected:
- Login succeeds
- Script deliberately breaks the session token
- First RPC attempt fails with `INVALID_SESSION_INFORMATION`
- Client re-logins once and retries once
- Call succeeds and script prints "✅ Session retry proof passed."

3) Market discovery (Phase 1):
`python -m betflow.scripts.discover_markets`

Expected:
- Discovers upcoming Horse Racing WIN markets across configured countries
- Takes the next N races by start time (config: `global.take`)
- Applies eligibility gates:
  - runner count min/max (global default with optional region override)
  - liquidity min (global default with optional region override)
- Prints pass/fail reasons per market + Eligible/Rejected summary

## How to resume (always start here)
1) `git pull`
2) Read this file top-to-bottom
3) Ensure `.env` exists locally (NOT committed)
4) Run import sanity check: `python -c "import betflow; print('imports ok')"`
5) Run smoke test: `python -m betflow.scripts.test_connection`
6) If smoke test fails: check `Known gotchas` below

## Branches
- `main`       = clean-slate rebuild (authoritative going forward)
- `firstbuild`  = frozen snapshot of the initial build (kept for reference)
- other branches may exist for experiments

## Non-negotiables
- No secrets committed:
  - `.env` must be gitignored and not tracked
  - certs/keys stay local; `secrets/` remains gitignored
- Every capability has a proof command before we build on it
- Small commits, clear messages, one concern per commit
- Prefer runnable scripts via `python -m betflow.scripts.<name>` over ad-hoc snippets

## Target structure (current and intended)
- `src/betflow/` application package
- `src/betflow/betfair/` Betfair API client(s)
- `src/betflow/scripts/` runnable utilities / smoke tests
- `src/betflow/services/` reusable logic (discovery, ladder, selection, etc.)
- `docs/` project documentation (this file + project map)
- `config/` configuration (YAML profiles etc.)

## Environment variables (current)
Local `.env` contains:
- `BETFAIR_APP_KEY`
- `BETFAIR_USERNAME`
- `BETFAIR_PASSWORD`
- `BETFLOW_ENV` (recommended: `dev`)

Optional (defaults to `/opt/betflow/secrets/...` if not set):
- `BETFAIR_CERT_CRT`
- `BETFAIR_CERT_KEY`

## Known gotchas
- **Cert login response format**: Betfair cert login may return JSON (not key=value lines).
  We parse JSON first, then fall back to key=value parsing.
- Betfair session tokens expire; do not treat session tokens as persistent state.
  We now handle expiry by re-login once and retry once.
- Best back/lay prices require `listMarketBook` with `priceProjection` including `EX_BEST_OFFERS`.
- Keep `.env` out of Git. If it was ever committed to a public repo, rotate credentials/keys.

## Next steps (immediate)
1) Phase 2: Get runners/prices for eligible markets:
   - `listMarketCatalogue` (runner metadata) + `listMarketBook` (prices, totalMatched, status)
2) Implement ladder output for eligible markets (best back/lay, spread in ticks)
3) Add compression rules (price-based) and integrate into eligibility:
   - e.g. count of runners under odds threshold, per market
4) Runner selection rules (odds-band harvesting ~12–18, spread thresholds)
5) Paper bet object model + audit logging (no live orders yet)


## Phase 2 – Market Structure Inspection (2026-02-19)

### What was added

- `inspect_market_structure.py` script
- Config loader aligned (`load_filter_config`)
- Dataclass config handling via `asdict`
- MarketCatalogue + MarketBook RPC integration
- Human-readable ladder output:
  - Runner number (leading zero)
  - Best back / lay
  - Spread (ticks)
- Basic structure metrics:
  - Runner count
  - Count of runners < 10.0
- Logging confirms stable Betfair RPC flow

### What this script currently does

- Pulls live market data
- Displays ladder and structural shape
- Displays config parameters (read-only context)

### What it does NOT yet do

- Apply structural gating rules
- Accept/reject market
- Perform anchor / candidate selection
- Score runners
- Persist output

### Technical Notes

- Tick calculation currently approximate (acceptable for diagnostics phase)
- `structure_metrics.py` remains pure
- `filter_config.py` still contains legacy stub (`load_filters_config`) — to be cleaned next

### Next Planned Step

- Add config-driven market-level rule evaluation
- Print ✓ / ✗ per rule
- Emit MARKET ACCEPTED / REJECTED decision

### Sanity Check

```bash
python -c "import betflow; print('imports ok')"


2026-02-20
### Minor Fixes (Mode A)
- Fixed dataclass config conversion in market_rules (now using asdict) so YAML thresholds are respected.
- Market printout now includes Venue (event.venue).
- Region line repositioned for clarity.
