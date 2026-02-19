# Betflow – Project Map

This document explains what each part of the repo does and how the pieces interact.

## Architecture layers

### 1) Scripts (entry points)
Scripts are lightweight CLIs that call services.

- `betflow.scripts.test_connection`
  - Proves cert login + JSON-RPC call
- `betflow.scripts.test_session_retry`
  - Proves expired-session recovery (re-login + retry)
- `betflow.scripts.discover_markets`
  - Discovers upcoming WIN markets and prints market eligibility
- `betflow.scripts.inspect_market_structure`
  - Evaluates structure gates and applies horse selection filters to runner ladders

### 2) Services (reusable business logic)
- `services/market_discovery.py`
  - Region mapping
  - Runner count + liquidity gates
- `services/horse_selection.py`
  - Applies config-driven runner filters (odds band + spread cap)

### 3) Analysis (pure decision logic)
- `analysis/structure_metrics.py`
  - Builds runner ladders from MarketCatalogue + MarketBook
  - Computes market-level structure metrics
- `analysis/market_rules.py`
  - Applies market-level rules (country/region, field size, liquidity, anchor/soup/tier gates)

### 4) Betfair gateway
- `betfair/client.py`
  - Cert login
  - JSON-RPC
  - Automatic retry on `INVALID_SESSION_INFORMATION`

### 5) Configuration
- `config/filters.yaml`
  - Global defaults, per-region overrides, structure gates, and horse selection filters
- `filter_config.py`
  - Typed loader + helpers for resolving region-aware thresholds

## Flow overview

`inspect_market_structure` does:
1. Load config
2. Fetch MarketCatalogue + MarketBook
3. Build ladders + structure metrics
4. Apply market rules
5. If market accepted, apply horse selection filters and print candidate count
