# Betflow Trading Philosophy
Version: 1.1  
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

Betflow is structural, not predictive.

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

### 3.1 Preferred Odds Bands

Primary band:
- 14.0 – 17.0

Secondary band (when top strongly anchored):
- 12.0 – 14.0

Rarely selected:
- < 12.0
- > 18.0

The hard band defines the strategic operating identity.  
Primary band is the normal harvesting zone.  
Secondary band is conditional on strong anchoring.

---

### 3.2 Selection Principles (Deterministic, Not Predictive)

Within eligible markets:

- Prefer runners with **tight lay/back spreads**
- Avoid band edges
- Avoid favourites-adjacent runners (rank exclusion)
- Avoid extreme rags (rank exclusion)
- Prefer structurally central runners within the working band

Selection is deterministic and explainable.

No numeric scoring model is used.

---

## 4. Architecture Decision

Betflow uses a **Hybrid Model**:

### Stage 1 — Hard Market Gate

Binary pass/fail structural validation:

- Anchor strength
- Tier separation
- Flat-market veto
- Liquidity threshold
- Runner count range

If the market fails, no runner is considered.

---

### Stage 2 — Deterministic Runner Selection

Within valid markets:

1. Apply hard band guardrail.
2. Apply spread threshold.
3. Apply rank exclusion (top_n / bottom_n).
4. Classify into Primary or Secondary band.
5. Order candidates deterministically:

   - Lowest spread (execution quality first)
   - Closest to band midpoint (structural centrality)
   - Lowest price fallback (stable tie-break)

Only one runner is selected per market.

If no runner satisfies constraints, no trade is taken.

There is no probabilistic scoring layer.

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

Selection decisions must always be explainable in plain language.

If a decision cannot be explained simply, the logic must be simplified.

---

## 7. Evolution Policy

Any future change to thresholds or selection logic must:

1. Be measurable.
2. Be backtested.
3. Be documented here.
4. Preserve the core thesis of structural anchoring and mid-band harvesting.
5. Maintain deterministic and explainable behaviour.

If changes drift toward predictive modelling or opaque scoring, the strategy should be reconsidered.

---

End of Document.