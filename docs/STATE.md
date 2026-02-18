# Betflow – STATE

## What this repo is
Betflow is a research-oriented Betfair Exchange platform (paper trading first). This repo is being rebuilt deliberately from a clean slate.

## Clean-slate decision (2026-02-18)
We are intentionally resetting `main` to a minimal, purpose-built baseline to reduce confusion and rebuild with clear structure.
The previous working implementation has been preserved in branch: `firstbuild`.

## How to resume (always start here)
1) `git pull`
2) Read this file top-to-bottom
3) Run the current smoke test (when added): `python -m betflow.scripts.smoke_test`
4) If smoke test fails: check `Known gotchas` below

## Branches
- `main`      = clean-slate rebuild (authoritative going forward)
- `firstbuild` = frozen snapshot of the initial build (kept for reference)
- other branches may exist for experiments

## Non-negotiables
- No secrets committed (certs/keys stay local; `secrets/` remains gitignored)
- Every capability has a proof command (smoke test) before we build on it
- Small commits, clear messages, one concern per commit

## Target structure (goal)
- `src/betflow/` application package
- `scripts/` or `src/betflow/scripts/` runnable utilities
- `config/` configuration (yaml)
- `docs/` project documentation (this file)

## Known gotchas
- Betfair session tokens expire; do not treat session tokens as persistent state.
- Best back/lay prices require listMarketBook priceProjection with EX_BEST_OFFERS.

## Next steps (immediate)
1) Reset `main` content to minimal baseline (clean slate)
2) Add a single smoke test that proves Betfair connectivity and best offers
3) Rebuild market selection + ladder services step-by-step
