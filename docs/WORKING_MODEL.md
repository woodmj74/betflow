# Betflow Working Model

This document defines how we work on Betflow together so every session is consistent, low-friction, and incremental.

## The non-negotiables

1. **One developer, one truth**
   - No duplicate implementations of the same concept.
   - `src/betflow/markets/` is canonical for market logic.
   - `src/betflow/scripts/` orchestrates and prints; it does not “own” logic.

2. **No hidden coupling**
   - Library code returns structured results.
   - Scripts render output and handle CLI args.

3. **Stabilise first**
   - When something is broken, we restore a green baseline before adding features.

4. **Checkpoint discipline**
   - After each meaningful step that runs cleanly, we commit and update `docs/STATE.md`.

---

## Operating modes

Every session MUST declare a mode at the top. If not declared, default is **Mode A**.

### Mode A — Incremental (default)
Goal: make progress with minimal change.

Rules:
- No structural refactors.
- No file moves/renames.
- Fix only what blocks the current objective.
- Keep behaviour the same unless the objective explicitly changes it.
- End with a **green run** of the current proof command(s).

Use Mode A when:
- Implementing runner selection.
- Adjusting gating thresholds/outputs.
- Enhancing printing or adding small features.

### Mode B — Architecture cleanup
Goal: improve structure without adding new features.

Rules:
- Structural changes are allowed (moves/renames/extractions).
- No new features until we regain a green baseline.
- End with:
  - all imports stable
  - no duplicate modules
  - scripts still run

Use Mode B when:
- There are duplicate modules (e.g., `analysis/` vs `markets/`).
- A module is “script-like” but lives in the library path.
- Imports and responsibilities are unclear.

---

## Session header template (paste at the start of every chat)

### Mode A header
