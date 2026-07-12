"""
calibrate.py
============
Self-contained calibration script for the ethical-risk scoring pipeline.

What it does
------------
1. Loads labelled documents from calibration_docs/positive/ and
   calibration_docs/negative/ (or any folder you point it at via CLI).
2. Evaluates every document through the full pipeline.
3. Reports per-document scores, a confusion matrix, accuracy, precision,
   recall, and F1 score.
4. If accuracy is not 100 % it runs an automated grid-search over the
   key tunable parameters (threshold, governance sigmoid scale,
   governance weight, lr_noise multipliers) and applies the best-found
   combination directly to base_agent.py and parent_agent.py in-place.
5. Saves a before/after comparison to calibration_results.txt.

Usage
-----
    # use default calibration_docs/ folder
    python calibrate.py

    # point at a specific folder
    python calibrate.py "c:/path/to/labelled_docs"

Folder structure expected
-------------------------
    <folder>/
        positive/    <- docs that SHOULD be classified as Publish
            doc1.txt
            ...
        negative/    <- docs that SHOULD be classified as Do Not Publish
            doc2.txt
            ...

Supported file types: .txt  .md

IMPORTANT — only these two files are ever modified
---------------------------------------------------
    app/agents/base_agent.py
    app/orchestrator/parent_agent.py

No DKR files, prompts, configs, or other source files are touched.

How the scoring pipeline works (brief)
---------------------------------------
Every document passes through five domain agents (Bias, Privacy, Security,
Compliance, Transparency).  Each agent:

  Phase 1 – Relevance gate
      Only DKR fields whose field-name tokens appear in the document AND
      have at least 2 meaningful token matches are forwarded to scoring.
      Token length floor: > 3 characters.

  Phase 2 – Per-field score (max 1.0)
      Component A  field-name coverage      cap 0.45   weight: dominant
      Component B  broad token coverage     cap 0.20
      Component C  term density (log)       cap 0.25
      Component D  prominence bonus         cap 0.10

      Raw score is multiplied by a governance multiplier (0.15–1.0):
        • Counts governance-affirmation phrases in positive context
          (negation-aware: "human review" only counts if NOT preceded by
          "no/without" and NOT followed by "is unnecessary/optional").
        • Counts safeguard-dismissal phrases unconditionally.
        • net = dismissals - gov_hits * GOV_WEIGHT
        • multiplier = 0.15 + 0.85 * sigmoid(net / GOV_SIGMOID_SCALE)

  Phase 3 – Agent overall score (ceiling-pull)
      high_risk fields (score >= threshold) dominate via score³/score² weighting.
      low_risk  fields add LR_NOISE_AGENT * mean(low_risk scores) as noise.

  ParentAgent aggregation (ceiling-pull at domain level)
      Same logic: high-risk domains dominate, low-risk domains add
      LR_NOISE_DOMAIN * mean(low-risk domain scores) as noise.
      Decision: publish = overall_score < THRESHOLD

Tunable parameters (grid-searched when accuracy < 1.0)
--------------------------------------------------------
  THRESHOLD          Decision boundary.  Default 0.7.
  GOV_SIGMOID_SCALE  Controls sigmoid steepness.  Default 4.0.
  GOV_WEIGHT         Weight applied to governance hits.  Default 0.6.
  LR_NOISE_AGENT     Low-risk field noise multiplier in base_agent.  Default 0.15.
  LR_NOISE_DOMAIN    Low-risk domain noise multiplier in parent_agent.  Default 0.10.
"""

from __future__ import annotations

import re
import sys
from datetime import datetime
from pathlib import Path

# ── project root on sys.path ───────────────────────────────────────────
_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(_ROOT))

from app.orchestrator.parent_agent import ParentAgent
from app.services.document_payload import normalize_document_payload

# ── paths ──────────────────────────────────────────────────────────────
DEFAULT_CAL_DIR   = _ROOT / "calibration_docs"
BASE_AGENT_FILE   = _ROOT / "app" / "agents" / "base_agent.py"
PARENT_AGENT_FILE = _ROOT / "app" / "orchestrator" / "parent_agent.py"
RESULTS_FILE      = _ROOT / "calibration_results.txt"
SUPPORTED         = {".txt", ".md"}

# ── default parameter values (must match what is in the agent files) ───
DEFAULTS = {
    "THRESHOLD":         0.7,
    "GOV_SIGMOID_SCALE": 4.0,
    "GOV_WEIGHT":        0.6,
    "LR_NOISE_AGENT":    0.15,
    "LR_NOISE_DOMAIN":   0.10,
}

# ── grid-search search space ───────────────────────────────────────────
GRID = {
    "THRESHOLD":         [0.50, 0.55, 0.60, 0.65, 0.70, 0.75],
    "GOV_SIGMOID_SCALE": [3.0, 4.0, 5.0, 6.0],
    "GOV_WEIGHT":        [0.4, 0.5, 0.6, 0.7, 0.8],
    "LR_NOISE_AGENT":    [0.05, 0.10, 0.15, 0.20],
    "LR_NOISE_DOMAIN":   [0.05, 0.10, 0.15],
}

# ══════════════════════════════════════════════════════════════════════ #
#  Document loading                                                      #
# ══════════════════════════════════════════════════════════════════════ #

def load_docs(folder: Path) -> list[dict]:
    """Load all labelled docs from positive/ and negative/ subfolders."""
    docs = []
    for label, expected in [("positive", "Publish"), ("negative", "Do Not Publish")]:
        sub = folder / label
        if not sub.exists():
            print(f"  [warn] subfolder not found: {sub}")
            continue
        for f in sorted(sub.iterdir()):
            if f.suffix.lower() not in SUPPORTED:
                continue
            text = f.read_text(encoding="utf-8", errors="ignore").strip()
            if not text:
                print(f"  [warn] empty file skipped: {f.name}")
                continue
            docs.append({"tag": f"{label}/{f.name}", "text": text,
                          "expected": expected})
    return docs


# ══════════════════════════════════════════════════════════════════════ #
#  Metrics                                                               #
# ══════════════════════════════════════════════════════════════════════ #

def calc_metrics(tp, fp, fn, tn) -> dict:
    total     = tp + fp + fn + tn
    accuracy  = (tp + tn) / total if total else 0.0
    precision = tp / (tp + fp)    if (tp + fp) else 0.0
    recall    = tp / (tp + fn)    if (tp + fn) else 0.0
    f1        = (2 * precision * recall / (precision + recall)
                 if (precision + recall) else 0.0)
    return dict(accuracy=round(accuracy,3), precision=round(precision,3),
                recall=round(recall,3),    f1=round(f1,3),
                tp=tp, fp=fp, fn=fn, tn=tn, total=total)


# ══════════════════════════════════════════════════════════════════════ #
#  Pipeline evaluation                                                   #
# ══════════════════════════════════════════════════════════════════════ #

def evaluate_all(docs: list[dict]) -> tuple[dict, list[dict]]:
    """
    Run every doc through the pipeline (re-importing ParentAgent so that
    any in-place edits to agent files take effect).

    Returns (metrics_dict, per_doc_results).
    """
    # Force reload so patched constants are picked up
    import importlib
    import app.agents.base_agent as _ba
    import app.orchestrator.parent_agent as _pa
    importlib.reload(_ba)
    importlib.reload(_pa)
    from app.orchestrator.parent_agent import ParentAgent as _PA

    pa = _PA()
    tp = fp = fn = tn = 0
    results = []

    for doc in docs:
        tag, text, expected = doc["tag"], doc["text"], doc["expected"]
        r       = pa.evaluate_document(
                      normalize_document_payload({"document_text": text}), tag)
        actual  = r["decision"]
        score   = r["overall_score"]
        correct = (actual == expected)

        if   expected == "Do Not Publish" and actual == "Do Not Publish": tp += 1
        elif expected == "Publish"         and actual == "Do Not Publish": fp += 1
        elif expected == "Do Not Publish" and actual == "Publish":         fn += 1
        else:                                                               tn += 1

        results.append(dict(tag=tag, expected=expected, actual=actual,
                             score=score, correct=correct,
                             agent_scores={a["agent"]: a["overall_score"]
                                           for a in r.get("agent_outputs", [])}))

    return calc_metrics(tp, fp, fn, tn), results


# ══════════════════════════════════════════════════════════════════════ #
#  In-place patching of agent files                                      #
# ══════════════════════════════════════════════════════════════════════ #

def _patch(path: Path, pattern: str, replacement: str) -> bool:
    """Replace first occurrence of regex pattern in file.  Returns True on success."""
    src = path.read_text(encoding="utf-8")
    new_src, count = re.subn(pattern, replacement, src, count=1)
    if count == 0:
        return False
    path.write_text(new_src, encoding="utf-8")
    return True


def apply_params(params: dict) -> None:
    """
    Write the given parameter values into base_agent.py and parent_agent.py.

    Parameters touched
    ------------------
    base_agent.py:
      THRESHOLD        — passed as constructor default from app.config, but
                         also used as self.threshold; we patch the config import
                         by overriding the sigmoid scale and gov weight constants
                         inside _governance_multiplier, and the lr_noise multiplier
                         inside _analyze_fields.

      GOV_SIGMOID_SCALE — the divisor in sigmoid(net / SCALE)
      GOV_WEIGHT        — the coefficient on gov_hits in net = dismiss - gov*WEIGHT
      LR_NOISE_AGENT    — the 0.15 multiplier on low-risk field noise

    parent_agent.py:
      THRESHOLD        — THRESHOLD class constant
      LR_NOISE_DOMAIN  — the 0.10 multiplier on low-risk domain noise
    """
    t  = params["THRESHOLD"]
    gs = params["GOV_SIGMOID_SCALE"]
    gw = params["GOV_WEIGHT"]
    la = params["LR_NOISE_AGENT"]
    ld = params["LR_NOISE_DOMAIN"]

    # ── base_agent.py ──────────────────────────────────────────────────

    # 1. GOV_SIGMOID_SCALE  — appears as:  sig = 1.0 / (1.0 + math.exp(-net / 4.0))
    _patch(BASE_AGENT_FILE,
           r"math\.exp\(-net\s*/\s*[\d.]+\)",
           f"math.exp(-net / {gs})")

    # 2. GOV_WEIGHT  — appears as:  net = dismiss_hits - gov_hits * 0.6
    _patch(BASE_AGENT_FILE,
           r"net\s*=\s*dismiss_hits\s*-\s*gov_hits\s*\*\s*[\d.]+",
           f"net = dismiss_hits - gov_hits * {gw}")

    # 3. LR_NOISE_AGENT  — appears as:  / len(low_risk) * 0.15
    _patch(BASE_AGENT_FILE,
           r"sum\(f\[.score.\]\s+for\s+f\s+in\s+low_risk\)\s*/\s*len\(low_risk\)\s*\*\s*[\d.]+",
           f"sum(f['score'] for f in low_risk) / len(low_risk) * {la}")

    # ── parent_agent.py ────────────────────────────────────────────────

    # 4. THRESHOLD class constant  — appears as:  THRESHOLD: float = 0.7
    _patch(PARENT_AGENT_FILE,
           r"THRESHOLD:\s*float\s*=\s*[\d.]+",
           f"THRESHOLD: float = {t}")

    # 5. LR_NOISE_DOMAIN  — appears as:  / len(low_risk_domains_data) * 0.10
    _patch(PARENT_AGENT_FILE,
           r"sum\(d\[.overall_score.\]\s+for\s+d\s+in\s+low_risk_domains_data\)\s*/\s*"
           r"len\(low_risk_domains_data\)\s*\*\s*[\d.]+",
           f"sum(d['overall_score'] for d in low_risk_domains_data) / "
           f"len(low_risk_domains_data) * {ld}")


def restore_defaults() -> None:
    apply_params(DEFAULTS)


# ══════════════════════════════════════════════════════════════════════ #
#  Grid search                                                           #
# ══════════════════════════════════════════════════════════════════════ #

def grid_search(docs: list[dict]) -> dict:
    """
    Exhaustive grid search over GRID search space.

    Scoring priority (highest to lowest):
      1. recall == 1.0  (no false negatives — mandatory)
      2. accuracy
      3. precision
      4. f1

    Returns the best parameter dict found.
    """
    import itertools

    keys   = list(GRID.keys())
    values = list(GRID.values())
    total  = 1
    for v in values:
        total *= len(v)

    print(f"\n  Grid search: {total} combinations across "
          f"{len(keys)} parameters...")

    best_params  = None
    best_score   = (-1, -1, -1, -1)   # (recall, accuracy, precision, f1)

    for combo in itertools.product(*values):
        params = dict(zip(keys, combo))
        apply_params(params)
        m, _ = evaluate_all(docs)

        # Priority tuple: recall first, then accuracy, precision, f1
        score = (m["recall"], m["accuracy"], m["precision"], m["f1"])

        if score > best_score:
            best_score  = score
            best_params = params.copy()

        # Early exit if perfect
        if best_score == (1.0, 1.0, 1.0, 1.0):
            print("  Perfect score found — stopping early.")
            break

    # Restore best
    apply_params(best_params)
    return best_params


# ══════════════════════════════════════════════════════════════════════ #
#  Report formatting                                                     #
# ══════════════════════════════════════════════════════════════════════ #

def format_results(header: str, m: dict, results: list[dict],
                   params: dict) -> str:
    SEP  = "=" * 72
    lines = [f"\n{SEP}", header, SEP]

    col = 35
    lines.append(f"\n{'File':<{col}} {'Expected':<20} {'Actual':<20} "
                 f"{'Score':>6}  Status")
    lines.append("-" * (col + 52))

    for r in results:
        status = "OK" if r["correct"] else (
            "FALSE_NEG" if r["expected"] == "Do Not Publish" else "FALSE_POS")
        lines.append(f"{r['tag']:<{col}} {r['expected']:<20} "
                     f"{r['actual']:<20} {r['score']:>6.3f}  {status}")
        if not r["correct"]:
            ag = "  ".join(f"{a}={s:.3f}" for a, s in r["agent_scores"].items())
            lines.append(f"  └─ {ag}")

    lines += [
        f"\n{'─'*72}",
        f"  Accuracy          : {m['accuracy']:.3f}",
        f"  Precision (risky) : {m['precision']:.3f}",
        f"  Recall    (risky) : {m['recall']:.3f}  ← KEY METRIC",
        f"  F1 score          : {m['f1']:.3f}",
        f"  TP={m['tp']}  FP={m['fp']}  FN={m['fn']}  TN={m['tn']}",
        f"\n  Parameters in effect:",
    ]
    for k, v in params.items():
        lines.append(f"    {k:<22} = {v}")

    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════ #
#  Main                                                                  #
# ══════════════════════════════════════════════════════════════════════ #

def main() -> None:
    # ── resolve calibration folder ─────────────────────────────────────
    if len(sys.argv) > 1:
        cal_dir = Path(sys.argv[1])
    else:
        cal_dir = DEFAULT_CAL_DIR

    if not cal_dir.exists():
        print(f"Error: calibration folder not found: {cal_dir}")
        print("Create calibration_docs/positive/ and calibration_docs/negative/ "
              "with .txt files, or pass a folder path as an argument.")
        sys.exit(1)

    docs = load_docs(cal_dir)
    if not docs:
        print("No documents found. Check the folder has positive/ and "
              "negative/ subfolders with .txt files.")
        sys.exit(1)

    pos = sum(1 for d in docs if d["expected"] == "Publish")
    neg = sum(1 for d in docs if d["expected"] == "Do Not Publish")
    ts  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print(f"\nCalibration run — {ts}")
    print(f"Folder  : {cal_dir.resolve()}")
    print(f"Docs    : {len(docs)} total  ({pos} positive / {neg} negative)")

    # ── baseline (current params) ──────────────────────────────────────
    print("\nEvaluating baseline (current parameters)...")
    baseline_m, baseline_results = evaluate_all(docs)

    baseline_section = format_results(
        f"BASELINE — {ts}",
        baseline_m, baseline_results, DEFAULTS)

    print(f"\n  Accuracy  {baseline_m['accuracy']:.3f}  "
          f"Precision {baseline_m['precision']:.3f}  "
          f"Recall {baseline_m['recall']:.3f}  "
          f"F1 {baseline_m['f1']:.3f}")

    # ── decide if calibration needed ───────────────────────────────────
    if baseline_m["recall"] == 1.0 and baseline_m["accuracy"] == 1.0:
        print("\nPerfect recall and accuracy — no calibration needed.")
        output = baseline_section + "\n\nNo calibration required.\n"
        RESULTS_FILE.write_text(output, encoding="utf-8")
        print(f"Results saved to {RESULTS_FILE}")
        return

    if baseline_m["recall"] < 1.0:
        print(f"\n  !! Recall {baseline_m['recall']:.3f} — "
              f"{baseline_m['fn']} risky doc(s) slipping through. "
              f"Running grid search...")
    else:
        print(f"\n  Recall is perfect but accuracy is "
              f"{baseline_m['accuracy']:.3f}. Running grid search for "
              f"better overall accuracy...")

    # ── grid search ─────────────────────────────────────────────────────
    best_params = grid_search(docs)
    tuned_m, tuned_results = evaluate_all(docs)

    print(f"\n  Best params found:")
    for k, v in best_params.items():
        print(f"    {k:<22} = {v}")
    print(f"\n  After calibration:")
    print(f"  Accuracy  {tuned_m['accuracy']:.3f}  "
          f"Precision {tuned_m['precision']:.3f}  "
          f"Recall {tuned_m['recall']:.3f}  "
          f"F1 {tuned_m['f1']:.3f}")

    tuned_section = format_results(
        f"AFTER CALIBRATION — {ts}",
        tuned_m, tuned_results, best_params)

    # ── save results ────────────────────────────────────────────────────
    RESULTS_FILE.write_text(
        baseline_section + "\n\n" + tuned_section + "\n",
        encoding="utf-8")
    print(f"\nResults saved to {RESULTS_FILE}")

    # ── warn if recall still imperfect ─────────────────────────────────
    if tuned_m["recall"] < 1.0:
        print(f"\n  WARNING: recall is still {tuned_m['recall']:.3f} after "
              f"grid search.\n"
              f"  {tuned_m['fn']} risky doc(s) still passing.  "
              f"Consider reviewing dataset labels or expanding the\n"
              f"  governance/dismissal phrase lists in base_agent.py.")
    else:
        print("\n  Recall = 1.000 — all risky documents are blocked.")


if __name__ == "__main__":
    main()
