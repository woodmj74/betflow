# Betflow – STATE

## What this repo is
Betflow is a research-oriented Betfair Exchange platform (paper trading first). This repo is being rebuilt deliberately from a clean slate with an emphasis on correctness, auditability, and incremental proof points.

## Clean-slate decision (2026-02-18)
We intentionally reset `main` to a minimal, purpose-built baseline to remove confusion and rebuild with a clear structure and repeatable workflow.
The previous working implementation has been preserved in branch: `firstbuild`.

## Current baseline (as of 2026-02-18)
A minimal skeleton has been implemented under `src/` with:
- `settings.py` — loads environment config via `.env` (local only, not tracked)
- `logging.py` — structured logging via `structlog` (pretty console in dev)
- `betfair/client.py` — thin Betfair gateway supporting cert login + JSON-RPC
- `scripts/test_connection.py` — smoke test proving auth + API calls

### Proof point (works)
Run from repo root:

`python -m betflow.scripts.test_connection`

Expected:
- Successful Betfair cert login
- Successful JSON-RPC call to `listEventTypes`
- Prints the first ~10 event types and "✅ Connection looks good."

## How to resume (always start here)
1) `git pull`
2) Read this file top-to-bottom
3) Ensure `.env` exists locally (NOT committed)
4) Run smoke test: `python -m betflow.scripts.test_connection`
5) If smoke test fails: check `Known gotchas` below

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
- `docs/` project documentation (this file)
- (planned) `config/` configuration (YAML profiles etc.)
- (planned) `services/` reusable logic once we reintroduce market selection/ladders

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
  We now parse JSON first, then fall back to key=value parsing.
- Betfair session tokens expire; do not treat session tokens as persistent state.
- Best back/lay prices require `listMarketBook` with `priceProjection` including `EX_BEST_OFFERS`.
- Keep `.env` out of Git. If it was ever committed to a public repo, rotate credentials/keys.

## Next steps (immediate)
1) Commit the clean skeleton + working smoke test as the new baseline checkpoint
2) Add session retry logic in `BetfairClient`:
   - on `INVALID_SESSION_INFORMATION`, re-login once and retry the request once
3) Reintroduce market discovery (Horse Racing WIN, region filtering) as a script with verbose pass/fail reasons
4) Reintroduce market ladder + market shape services (incremental, with proof scripts)

## Next milestone (near-term)
- Market eligibility rules (field size, liquidity, compression, spreads)
- Runner selection rules (odds-band harvesting ~12–18, spread thresholds)
- Paper bet object model + audit logging (no live orders yet)
