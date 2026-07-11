# Scoring Calibration — Session Context

## What This Task Is

You have a set of labelled documents (positive = safe to publish, negative = should be blocked).
Your job is to run them through the scoring pipeline, measure accuracy, and adjust weights/thresholds
until every document is classified correctly. You must **only touch the two files listed below** —
nothing else in the codebase should be modified.

---

## Files You Are Allowed to Touch

| File | What to change |
|------|----------------|
| `app/agents/base_agent.py` | Scoring weights inside `_risk_score()` and `_analyze_fields()` |
| `app/orchestrator/parent_agent.py` | Aggregation weights and `THRESHOLD` inside `_decide()` |

**Do not touch any other file.** In particular:
- `app/knowledge/*/repository.json` — DKR field data, must stay unchanged
- `app/knowledge/*/prompt.txt` — LLM prompts, must stay unchanged
- `app/config.py` — application config, must stay unchanged
- `backend/` — backend API layer, must stay unchanged
- `frontend/` — UI, must stay unchanged
- Any `__pycache__` or test file

---

## Current Scoring Architecture (as of this session)

### Threshold

```
THRESHOLD = 0.7   # defined in app/config.py, read by BaseAgent and ParentAgent
```

`ParentAgent` also has its own hardcoded copy:
```python
# app/orchestrator/parent_agent.py  line ~21
THRESHOLD: float = 0.7
```
When adjusting the decision boundary, change **both** values consistently,
or better: make `ParentAgent.THRESHOLD` import from `app.config.THRESHOLD`.

---

### Per-field score: `BaseAgent._risk_score()`  →  `app/agents/base_agent.py`

Four components, max 1.0:

| Component | Cap | Parameter to tune | Current value |
|-----------|-----|-------------------|---------------|
| A — field-name coverage | 0.45 | `score_a = min(0.45, 0.45 * (fn_coverage ** 0.65))` | cap=0.45, exponent=0.65 |
| B — broad coverage bonus | 0.20 | `score_b = min(0.20, 0.20 * (broad_coverage ** 0.70))` | cap=0.20, exponent=0.70 |
| C — term density (log-scaled) | 0.25 | `score_c = min(0.25, 0.10 * math.log1p(weighted_hits))` | cap=0.25, log_scale=0.10 |
| D — prominence bonus | 0.10 | `score_d = min(0.10, prominence_hits * 0.06)` | cap=0.10, per_hit=0.06 |

Field-name hits are weighted **2×** over description/example hits in Component C:
```python
weighted_hits = fn_hits * 2.0 + other_hits
```

**Relevance gate** (controls which fields even reach scoring):
```python
# _is_relevant() in base_agent.py
min_token_length  = 4    # tokens shorter than this are ignored (hardcoded >3 check)
min_total_matches = 2    # Gate 2: total meaningful token matches required
```

---

### Per-agent overall score: `BaseAgent._analyze_fields()`  →  `app/agents/base_agent.py`

Ceiling-pull model — high-risk fields dominate, low-risk fields add noise only:

```python
# High-risk fields (score >= threshold) — score³/score² weighted mean
hr_pull = Σ(score³) / Σ(score²)

# Low-risk fields — plain mean × noise_weight
lr_noise = mean(low_risk scores) * 0.15     # ← tune this multiplier
```

**Parameters to tune:**
- `0.15` — low-risk noise multiplier (lower = less inflation from borderline fields)

---

### Final overall score: `ParentAgent._decide()`  →  `app/orchestrator/parent_agent.py`

Same ceiling-pull structure at the domain level:

```python
# High-risk domains (overall_score >= threshold)
hr_pull = Σ(score³) / Σ(score²)

# Low-risk domains — plain mean × noise_weight
lr_noise = mean(low_risk domain scores) * 0.10    # ← tune this multiplier

# If NO domain is high-risk → overall = max(domain scores)
```

**Parameters to tune:**
- `0.10` — low-risk domain noise multiplier

---

## How to Run the Calibration

### 1. Place your documents

Put all test documents in a folder called `calibration_docs/` at the project root.
Name them so their label is clear, e.g.:

```
calibration_docs/
  positive/
    book_club_agenda.txt
    internal_memo.txt
    ...
  negative/
    loan_rejection_no_consent.txt
    biometric_data_no_policy.txt
    ...
```

### 2. Run the calibration script

A ready-to-use script is at `calibrate.py` in the project root (see below).
Run it from the project root:

```bash
python calibrate.py
```

It will print per-document scores and a summary accuracy table.

### 3. Tune — iterate

Based on the output, adjust **only** the parameters listed in the tables above.
After each change, re-run `calibrate.py` and compare results.

**Common fixes:**

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| Positive doc blocked (false positive) | Score too high for clean doc | Lower Component A cap (0.45→0.40) or raise `min_total_matches` (2→3) in `_is_relevant()` |
| Negative doc passes (false negative) | High-risk fields not reaching threshold | Lower `THRESHOLD` (0.7→0.65) or raise Component C log scale (0.10→0.12) |
| Too many fields matched on clean docs | Relevance gate too loose | Raise `min_total_matches` to 3, or raise token length floor to 5 |
| High-risk doc score barely above threshold | Low-risk noise dragging hr_pull down | Lower `lr_noise` multiplier in `_analyze_fields()` (0.15→0.05) |

---

## Calibration Script (`calibrate.py`)

This script is already written — see `calibrate.py` in the project root.
It reads from `calibration_docs/positive/` and `calibration_docs/negative/`,
runs each doc through the full pipeline, and reports accuracy.

---

## Safety Rules for the Agent

1. **Only edit** `app/agents/base_agent.py` and `app/orchestrator/parent_agent.py`.
2. **Never edit** DKR files (`app/knowledge/*/repository.json`) — those are ground-truth risk definitions.
3. **Never edit** `app/config.py` — change `THRESHOLD` in `parent_agent.py` directly if needed.
4. **Never rename or move** any file.
5. After every parameter change, run `python calibrate.py` and record the accuracy before making the next change.
6. Change **one parameter at a time** so you can isolate the effect.
7. If accuracy regresses, revert the last change before trying something else.
8. Target: 100% accuracy on all labelled documents. Stop when achieved.

---

## Current Baseline (smoke test, pre-calibration)

| Document | Expected | Score | Decision | Correct? |
|----------|----------|-------|----------|----------|
| Book club agenda (clean) | Publish | 0.0 | Publish | ✅ |
| AI hiring with human review (mixed) | Publish | 0.441 | Publish | ✅ |
| Loan rejection, no consent, no controls (risky) | Do Not Publish | 0.934 | Do Not Publish | ✅ |

---

## Quick Smoke Test

After any change, verify the baseline hasn't broken:

```python
# paste into a file and run: python _smoke.py
import sys; sys.path.insert(0, ".")
from app.orchestrator.parent_agent import ParentAgent
from app.services.document_payload import normalize_document_payload

CLEAN = "Meeting agenda for the quarterly book club. Tea and biscuits provided."
RISKY = """
This AI system automatically rejects loan applications from certain ethnic groups
without any human review. Sensitive personal data including biometric identifiers
and health records is collected without explicit consent or lawful basis.
No GDPR compliance. No data retention policy. Fully automated decisions with no
explainability, no audit trail, no encryption, no access control.
"""
pa = ParentAgent()
for label, doc in [("CLEAN", CLEAN), ("RISKY", RISKY)]:
    r = pa.evaluate_document(normalize_document_payload({"document_text": doc}), label)
    print(f"{label}: score={r['overall_score']}  decision={r['decision']}")
# Expected: CLEAN → Publish, RISKY → Do Not Publish
```
