# Betflow Trading Philosophy
Version: 1.0  
Status: Active Design Baseline  

---

## 1. Core Thesis

Betflow targets structural inefficiencies in mid-priced runners within probability-anchored WIN markets.

The strategy does **not** attempt to predict race outcomes.  
It exploits market shape, price distribution, and probability concentration.

The edge is derived from:

- Concentrated implied probability at the top of the market
- Clear tier separation between price clusters
- Stable pricing (tight lay/back spreads)
- Avoidance of flat, evenly distributed “handicap soup” markets
- Controlled exposure within a defined odds band

---

## 2. Market Regimes

Markets are classified structurally before any runner is considered.

### 2.1 Anchored (Preferred)

Characteristics:
- Top 2–3 runners hold significant implied probability
- Clear price tier breaks exist
- Probability mass is concentrated rather than evenly distributed

These markets are eligible for trading.

---

### 2.2 Semi-Anchored (Conditional)

Characteristics:
- Competitive top cluster but still meaningful concentration
- Some tier clarity
- No smooth gradient across top 5 runners

May be eligible depending on thresholds.

---

### 2.3 Flat / Smeared (Rejected)

Characteristics:
- Top 5 runners tightly grouped
- Smooth pricing gradient (no tier breaks)
- Even probability distribution
- “Handicap soup” structure

These markets are hard vetoed.

---

## 3. Runner Selection Bias

Once a market passes structural gating, runner selection occurs within a defined working band.

### 3.1 Preferred Odds Band

Primary band:
- 14.0 – 17.0

Secondary band (when top strongly anchored):
- 12.0 – 14.0

Rarely selected:
- < 12.0
- > 18.0

---

### 3.2 Selection Preferences

Within eligible markets:

- Avoid band edges (e.g. 11.8 or 18.2 boundary touches)
- Avoid dense micro-clusters of similarly priced runners
- Prefer runners slightly isolated from tight price groupings
- Prefer tighter lay/back spreads
- Slight downward adjustment when top of market is strongly anchored

The strategy does **not** rely on narrative factors (form, jockey, etc.).

---

## 4. Architecture Decision

Betflow uses a **Hybrid Model**:

### Stage 1 — Hard Market Gate
Binary pass/fail structural validation:
- Anchor strength
- Tier separation
- Flat-market veto
- Spread sanity
- Liquidity

If the market fails, no runner is considered.

### Stage 2 — Scored Runner Selection
Within valid markets:
- Candidates are scored based on structural fit
- Highest scoring runner is selected
- Only one selection per market

---

## 5. Behavioural Discipline

The system must remain independent of session state.

Non-negotiable constraints:

- No session P/L awareness
- No chasing logic
- Fixed risk unit staking
- One entry per market
- No emotional override layer

This strategy is structural, not reactive.

---

## 6. Strategic Intent

Betflow is designed to:

- Trade only in preferred structural regimes
- Reduce variance from flat handicap chaos
- Remove human narrative bias
- Operate with explainable decision logic
- Be fully auditable and reproducible

The system is intentionally selective rather than high-frequency.

---

## 7. Evolution Policy

Any future change to thresholds or selection logic must:

1. Be measurable.
2. Be backtested.
3. Be documented here.
4. Preserve the core thesis of structural anchoring and mid-band harvesting.

If changes drift away from these principles, the strategy should be reconsidered.

---

End of Document.
