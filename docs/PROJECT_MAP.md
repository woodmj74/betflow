# Betflow – Project Map

This is the “how to think about the repo” document.

If `docs/STATE.md` is *what we have and how to run it*, this is *what each part means and how the pieces interact*.

## The big idea
Betflow is a research-oriented Betfair Exchange platform with paper trading first.

We build in small steps:
- add one capability
- add a proof script
- only then build the next layer

## Key layers

### 1) Scripts (entry points)
**Where you run things from the command line.**  
Scripts should be simple: load config, call services, print human-friendly output.

- `betflow.scripts.test_connection`
  - Proves login + one JSON-RPC call
- `betflow.scripts.test_session_retry`
  - Proves session expiry recovery (re-login + retry once)
- `betflow.scripts.discover_markets`
  - Finds the next N WIN markets and prints pass/fail reasons

### 2) Services (business logic you’ll reuse)
**Where the actual “logic” lives.**  
Services should return structured data, not print.

- `services/market_discovery.py`
  - Discovers markets (Horse Racing, WIN)
  - Applies Phase 1 eligibility gates:
    - runner count range
    - liquidity threshold (region-aware)
  - Returns decisions: eligible/rejected + reasons

Later services will include:
- `services/market_ladder.py`
  - Builds a ladder view from `listMarketBook` (best back/lay, spread ticks)
- `services/runner_selection.py`
  - Applies odds-band harvesting rules (~12–18), spread thresholds, guard rails
- `services/paper_trading.py`
  - Simulates orders, outcomes, P&L, and produces audit events

### 3) Betfair client (gateway)
**The only thing that talks to Betfair.**

- `betfair/client.py` (`BetfairClient`)
  - cert login
  - JSON-RPC calls
  - session retry once on `INVALID_SESSION_INFORMATION`

Rule: Services call the client. Scripts call services.  
No other file should “wing it” with raw HTTP requests.

### 4) Configuration
**No hard-coded thresholds in code.**

- `config/filters.yaml`
  - Global defaults (runner range, liquidity, horizon, take)
  - Region blocks that can override defaults

- `filter_config.py`
  - Loads YAML into typed config objects
  - Provides helper methods like:
    - “what’s liquidity_min for region X?”
    - “what runner range applies here?”

## Typical flow (today)

```mermaid
flowchart LR
  A[discover_markets.py] --> B[load_filter_config]
  A --> C[MarketDiscovery service]
  C --> D[BetfairClient.rpc]
  D --> E[Betfair API]
  C --> A


---

## 2️⃣ PROJECT_MAP.md Update

We keep this shorter — this is architecture view, not narrative.

Add under Phase 2:

```markdown
### Phase 2 – Market Structure

inspect_market_structure.py
  - Uses BetfairClient.rpc()
  - Loads filter_config
  - Produces diagnostic ladder view
  - Calculates basic structural metrics

No selection logic yet.
No persistence.
No staking.
