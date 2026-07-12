# Calibration README

## What is calibration?

Calibration is the process of tuning the scoring weights and decision
threshold so that the pipeline correctly classifies every document —
blocking all risky ones while publishing all safe ones.

The goal is:
- **Recall = 1.000** — no risky document ever passes (mandatory)
- **Precision ≥ 0.98** — very few safe documents are wrongly blocked
- **Accuracy as high as possible** without overfitting

---

## Files involved

| File | Role |
|------|------|
| `calibrate.py` | The calibration script — run this |
| `calibration_docs/positive/` | Safe documents (expected: Publish) |
| `calibration_docs/negative/` | Risky documents (expected: Do Not Publish) |
| `calibration_results.txt` | Output — baseline vs tuned metrics |
| `train_eval_results.txt` | Output — epoch-by-epoch training metrics |
| `test_eval.py` | Standalone test script for unseen labelled documents |
| `app/agents/base_agent.py` | **Only agent file modified during calibration** |
| `app/orchestrator/parent_agent.py` | **Only orchestrator file modified during calibration** |
| `app/knowledge/<domain>/repository.json` | DKR files — **never modified by calibration** |
| `app/knowledge/<domain>/prompt.txt` | LLM prompts — **never modified by calibration** |

No other files are ever touched by the calibration script.

---

## How to run

```bash
# Default — uses calibration_docs/ in the project root
python calibrate.py

# Custom folder
python calibrate.py "c:/path/to/your/labelled_docs"
```

The folder must have this structure:

```
your_folder/
    positive/       ← docs that SHOULD be classified as Publish
        doc1.txt
        doc2.txt
    negative/       ← docs that SHOULD be classified as Do Not Publish
        doc3.txt
        doc4.txt
```

Supported formats: `.txt` and `.md`

---

## What the script does, step by step

### Step 1 — Load documents

Reads all `.txt` / `.md` files from `positive/` and `negative/`
subfolders. Each file gets a label: `Publish` or `Do Not Publish`.

### Step 2 — Baseline evaluation

Runs every document through the full pipeline using the **current
parameter values** in `base_agent.py` and `parent_agent.py`.

Computes:
- **Accuracy** — fraction of docs correctly classified
- **Precision** — of all docs blocked, how many were truly risky
- **Recall** — of all risky docs, how many were blocked ← most important
- **F1** — harmonic mean of precision and recall

Prints a per-document table showing score and classification status.

### Step 3 — Decide if calibration is needed

- If recall = 1.0 and accuracy = 1.0 → done, no changes made.
- If recall < 1.0 → grid search triggered (risky docs slipping through).
- If recall = 1.0 but accuracy < 1.0 → grid search to reduce false positives.

### Step 4 — Grid search (if needed)

Tries every combination of the five tunable parameters (720 total):

| Parameter | What it controls | Search space |
|-----------|-----------------|--------------|
| `THRESHOLD` | Decision boundary (publish vs block) | 0.50 – 0.75 |
| `GOV_SIGMOID_SCALE` | Steepness of governance multiplier sigmoid | 3.0 – 6.0 |
| `GOV_WEIGHT` | How much each governance hit reduces the multiplier | 0.4 – 0.8 |
| `LR_NOISE_AGENT` | Influence of low-risk fields on agent score | 0.05 – 0.20 |
| `LR_NOISE_DOMAIN` | Influence of low-risk domains on final score | 0.05 – 0.15 |

Best combination is selected by this priority order:

1. **Recall = 1.0** (no false negatives — mandatory)
2. Accuracy
3. Precision
4. F1

The search stops early if a perfect combination (all 1.0) is found.

### Step 5 — Apply best parameters in-place

The winning values are written directly into:
- `app/agents/base_agent.py` — patches sigmoid scale, gov weight, lr_noise multiplier
- `app/orchestrator/parent_agent.py` — patches THRESHOLD class constant and domain lr_noise

Done via targeted regex substitution — only the specific numeric literals
change, all code structure and comments are preserved exactly.

### Step 6 — Save results

`calibration_results.txt` is written with:
- Baseline per-document table and metrics
- Post-calibration per-document table and metrics
- Final parameter values applied

---

## How the full scoring pipeline works

Each document passes through **five domain agents** in parallel:
Bias, Privacy, Security, Compliance, Transparency.

Each agent runs three phases:

---

### Phase 1 — Reasoning: Relevance gate (`_is_relevant`)

Before any scoring, every DKR field is checked for relevance against
the document. A field only proceeds to scoring if it passes both gates:

**Gate 1** — At least one **field-name token** (length > 3) must appear
in the document. A field whose curated risk label has no match in the
document simply is not relevant — description/example matches alone are
too noisy.

**Gate 2** — At least **2 meaningful tokens** (length > 3) from the
combined entry (name + description + examples) must match the document.
This prevents a single coincidental word from triggering scoring.

---

### Phase 2 — Analysis: Per-field scoring (`_risk_score`)

Each relevant field is scored against the document across four components:

```
Component A  field-name coverage     cap 0.45
             Fraction of DKR field-name tokens found in doc.
             Uses a power curve: score_a = 0.45 * (coverage ** 0.65)
             50% name coverage → 0.33 | 100% coverage → 0.45
             Returns 0 immediately if no field-name token matches at all.

Component B  broad coverage bonus    cap 0.20
             Fraction of ALL DKR entry tokens (name + desc + reason +
             examples) that match the document.
             score_b = 0.20 * (broad_coverage ** 0.70)

Component C  term density (log)      cap 0.25
             Rewards repeated mentions of matched terms.
             Field-name hits are weighted 2× over other hits.
             score_c = min(0.25, 0.10 * log1p(fn_hits*2 + other_hits))
             2 hits → 0.11 | 10 hits → 0.18 | 40 hits → 0.23

Component D  prominence bonus        cap 0.10
             Bonus if field-name tokens appear in the first 20% of doc.
             score_d = min(0.10, prominence_hits * 0.06)
```

**Raw score = A + B + C + D (max 1.0)**

The raw score is then multiplied by the **governance multiplier** (see below)
to produce the final field score.

---

### Governance multiplier (`_governance_multiplier`)

This is the core differentiator between responsible and irresponsible docs.
It is computed once per document and applied to every field score.

**Output range:** 0.15 (very responsible) → 1.0 (very irresponsible)

**How it works:**

1. Scan the full document text for **governance-affirmation phrases** —
   phrases like `"human review"`, `"audit trail"`, `"explainable ai"`,
   `"phased deployment"`, `"model validation"`, `"data governance"`, etc.
   (~60 phrases total in `_GOVERNANCE_PHRASES`).

   These are counted **only in positive context** using negation-aware
   matching:
   - NOT preceded (within 50 chars of the phrase) by: `no`, `without`,
     `lacking`, `not`, `never`
   - NOT followed (within 60 chars) by: `is unnecessary`, `is optional`,
     `is not required`, `are unnecessary`, `is generally unnecessary`, etc.

   So `"human review is unnecessary"` → **0 governance hits**
   And `"human review is mandatory"` → **1 governance hit**

2. Scan for **safeguard-dismissal phrases** — phrases like `"is unnecessary"`,
   `"are unnecessary"`, `"not required"`, `"perfect accuracy"`,
   `"unlimited scalability"`, `"one universal ai"`, `"replace all"`,
   `"no validation"`, `"model evaluation is optional"`, etc.
   (~90 phrases total in `_DISMISSAL_PHRASES`). Counted without negation
   checking — if the phrase appears, it counts.

3. Compute:
   ```
   gov_hits     = min(20, count of governance phrase positive hits)
   dismiss_hits = min(20, count of dismissal phrase hits)
   net          = dismiss_hits - gov_hits * GOV_WEIGHT   (default 0.6)
   sig          = sigmoid(net / GOV_SIGMOID_SCALE)        (default 4.0)
   multiplier   = 0.15 + 0.85 * sig
   ```

**Effect in practice:**
- Responsible docs (many gov hits, zero dismissals): net ≈ -6, multiplier ≈ 0.25–0.45 → scores collapse below threshold → **Publish**
- Irresponsible docs (many dismissals, few real gov hits): net ≈ +12, multiplier ≈ 0.90–0.99 → scores stay high → **Do Not Publish**

---

### Agent overall score — ceiling-pull model (`_analyze_fields`)

After all fields are scored and sorted descending, the agent overall
score is computed:

```python
high_risk = [f for f in evaluated if f["score"] >= threshold]
low_risk  = [f for f in evaluated if f["score"] <  threshold]

if high_risk:
    # score³/score² weighted mean — most dangerous field dominates
    hr_pull  = Σ(score³) / Σ(score²)
    lr_noise = mean(low_risk scores) * LR_NOISE_AGENT   (default 0.15)
    overall  = min(1.0, hr_pull + lr_noise)
else:
    # no high-risk fields — plain mean keeps clean docs low
    overall  = mean(all field scores)
```

**Effect:** One field scoring 0.84 drives the agent overall to ~0.87.
Ten fields all scoring 0.20 average to 0.20. Low-risk fields cannot
inflate a clean result.

---

### Final score — ParentAgent ceiling-pull (`_decide`)

Same model applied at the domain level across the five agents:

```python
high_risk_domains = [d for d in domain_summaries if d["overall_score"] >= threshold]
low_risk_domains  = [d for d in domain_summaries if d["overall_score"] <  threshold]

if high_risk_domains:
    hr_pull       = Σ(score³) / Σ(score²)
    lr_noise      = mean(low-risk domain scores) * LR_NOISE_DOMAIN  (default 0.10)
    overall_score = min(1.0, hr_pull + lr_noise)
else:
    overall_score = max(domain scores)

publish = overall_score < THRESHOLD
```

**Decision:** `"Publish"` if `overall_score < THRESHOLD`, else `"Do Not Publish"`.

---

### Phase 3 — Learning: Dynamic DKR field addition (`_learn_new_fields`)

After scoring is complete, each agent **optionally proposes new DKR fields**
by calling the Fireworks LLM. This is the self-improving mechanism that
allows the system's knowledge repositories to grow over time.

**Guard conditions** (all must be true before calling the LLM):

1. The document text is non-empty
2. The domain's DKR currently has fewer than 60 fields (hard cap — prevents
   unbounded growth regardless of anything else)

If both pass, the agent sends the full document payload and the domain
prompt to the LLM and receives back candidate fields.

**Validation in `_extract_proposed_fields`** — each candidate must pass
all of the following checks in order:

| Check | Rule |
|-------|------|
| Has field_name | Non-empty string |
| Not a duplicate | Case-insensitive match against all existing DKR names |
| Name length | ≤ 6 words (longer = a sentence, not a concept) |
| Has description | Non-empty string |
| Has reason | Non-empty string |
| **Topic-saturation** | Jaccard overlap vs best-matching existing field < 0.60 |

The last check is the **Topic-Saturated Learning (TSL)** filter, described below.

#### Topic-Saturated Learning (`_is_saturated`)

**Problem it solves:** Without this, the DKR can accumulate many
near-duplicate fields in the same conceptual area (e.g., `bias_severity`,
`bias_impact_severity`, `bias_impact_metric` — all describing roughly the
same thing). The hard cap of 60 still allows this up to the limit, and a
full DKR stops learning globally even if some areas are under-covered.

**How it works:**

For each candidate field, compute the Jaccard token overlap between the
candidate's `(name + description)` tokens and every existing DKR field's
`(name + description)` tokens. Take the **maximum overlap** across all
existing fields:

```
cand_tokens  = meaningful tokens (len > 2) from candidate name + description
entry_tokens = meaningful tokens (len > 2) from existing field name + description

overlap = |cand_tokens ∩ entry_tokens| / |cand_tokens ∪ entry_tokens|

if max(overlap over all existing fields) >= 0.60 → REJECT (already covered)
else → ACCEPT (genuinely novel)
```

**Effect as the DKR grows:**

- **Sparse DKR (few fields):** Almost every candidate clears the threshold
  → learning is fast, permissive
- **Mature DKR (many fields):** Conceptual areas that are already
  well-represented become progressively harder to add to → the agent
  naturally slows down in saturated areas while still accepting genuinely
  new concepts elsewhere
- **Hard cap:** The 60-field global limit remains as a final safety net

**Worked examples at threshold = 0.60:**

| Candidate | Best-matching existing field | Overlap | Decision |
|-----------|------------------------------|---------|----------|
| `bias_impact_severity` | `bias_severity` (already exists) | ~0.72 | Rejected — too similar |
| `bias_impact_severity` | `bias_type` | ~0.18 | (this field would pass) |
| `quantum_entanglement_bias` | any existing bias field | < 0.15 | Accepted — novel |
| `consent_management_workflow` | `consent_management_process` | ~0.65 | Rejected — already covered |

Fields that pass all checks are appended to the domain's
`app/knowledge/<domain>/repository.json` file via `append_new_fields()`.

The newly learned fields are returned in the API response under
`newly_learned_fields` so callers can inspect what was added.

---

## Symptom → fix reference

| Symptom | Likely cause | What grid search will try |
|---------|-------------|--------------------------|
| Risky doc passes (recall < 1.0) | Multiplier too low / threshold too high | Lower THRESHOLD, raise GOV_WEIGHT |
| Safe doc blocked (false positive) | Threshold too low or noise too high | Raise THRESHOLD, lower LR_NOISE values |
| Everything blocked | Threshold too aggressive | Raise THRESHOLD |
| Everything published | Governance multiplier not working | Lower GOV_SIGMOID_SCALE, raise GOV_WEIGHT |
| Borderline doc misclassified despite grid search | Governance phrase list incomplete | Add relevant phrases to `_GOVERNANCE_PHRASES` or `_DISMISSAL_PHRASES` in `base_agent.py` |

---

## Current trained state

See `calibration_results.txt` for calibration run output.
See `train_eval_results.txt` for the full 12-epoch training evaluation.

Final verified metrics (19 positive + 19 negative docs, 12 epochs):

| Metric | Score |
|--------|-------|
| Accuracy | 1.000 |
| Precision | 1.000 |
| Recall | 1.000 |
| F1 | 1.000 |
| False negatives | 0 |
| False positives | 0 |
| Epochs with perfect recall | 12 / 12 |

Active parameters:

| Parameter | Value |
|-----------|-------|
| THRESHOLD | 0.7 |
| GOV_SIGMOID_SCALE | 4.0 |
| GOV_WEIGHT | 0.6 |
| LR_NOISE_AGENT | 0.15 |
| LR_NOISE_DOMAIN | 0.10 |

---

## Adding new calibration documents

1. Add `.txt` files to `calibration_docs/positive/` or `calibration_docs/negative/`
2. Run `python calibrate.py`
3. If metrics drop, the script automatically re-tunes the parameters

If a document is consistently misclassified despite grid search, the
governance/dismissal phrase lists in `base_agent.py` likely need extending.
Add specific phrases from the problematic document to `_GOVERNANCE_PHRASES`
(if it's a responsible doc being wrongly blocked) or `_DISMISSAL_PHRASES`
(if it's an irresponsible doc slipping through), then re-run calibration.

## Running tests on unseen documents

```bash
python test_eval.py "c:/path/to/test_folder"
```

The test folder must have the same `positive/` and `negative/` subfolder
structure. Results are saved to both `test_results.txt` and appended to
`train_eval_results.txt`.
