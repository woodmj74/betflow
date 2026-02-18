# Betflow – Current State

## Purpose
Research-oriented Betfair Exchange platform (paper trading first).
Odds-band harvesting strategy (12–18), structured filters, strong guardrails.

## Current Phase
Clean-slate structural tidy on branch: chore/clean-slate

## What Currently Works
- Betfair cert login works
- listEventTypes works
- listMarketCatalogue works
- listMarketBook works (but ladder currently showing back/lay = None in main logic)

## Known Issue
Ladder candidates show:
  back=None lay=None lpt=...

Need to verify:
- listMarketBook projection includes EX_BEST_OFFERS
- Parsing of runner.ex.availableToBack / availableToLay
- No data lost in refactor

## Key Parameters
- Odds band: 12–18
- Runner count filter: 7–16
- Spread constraint: (ticks – confirm)
- Liquidity profile: (confirm)

## Next Steps
1. Clean folder structure
2. Create single smoke test script
3. Confirm best back/lay visible
4. Reattach ladder logic

## Last Good Commit (from main)
Run: git log -1 --oneline main
