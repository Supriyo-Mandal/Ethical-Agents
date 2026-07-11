"""
calibrate.py — Accuracy measurement for the ethical-risk scoring pipeline.

Usage
-----
1. Place labelled documents under:
       calibration_docs/positive/   ← should be classified as Publish
       calibration_docs/negative/   ← should be classified as Do Not Publish

2. Run from the project root:
       python calibrate.py

3. The script prints per-document results and a final accuracy summary.
   Adjust weights in base_agent.py / parent_agent.py, then re-run.

Supported file types: .txt  .md
(PDF/DOCX require the full backend stack — use plain text for calibration.)
"""

from __future__ import annotations

import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.orchestrator.parent_agent import ParentAgent
from app.services.document_payload import normalize_document_payload

# ── Configuration ──────────────────────────────────────────────────────
CALIBRATION_DIR = Path("calibration_docs")
POSITIVE_DIR    = CALIBRATION_DIR / "positive"   # expected: Publish
NEGATIVE_DIR    = CALIBRATION_DIR / "negative"   # expected: Do Not Publish
SUPPORTED_EXTS  = {".txt", ".md"}

# ── Helpers ────────────────────────────────────────────────────────────

def load_docs(folder: Path, label: str) -> list[tuple[str, str, str]]:
    """Return list of (filename, text, expected_decision)."""
    if not folder.exists():
        print(f"  [warn] folder not found: {folder}")
        return []
    docs = []
    for f in sorted(folder.iterdir()):
        if f.suffix.lower() not in SUPPORTED_EXTS:
            continue
        text = f.read_text(encoding="utf-8", errors="ignore").strip()
        if not text:
            print(f"  [warn] empty file skipped: {f.name}")
            continue
        docs.append((f.name, text, label))
    return docs


def run(docs: list[tuple[str, str, str]]) -> list[dict]:
    pa = ParentAgent()
    results = []
    for filename, text, expected in docs:
        payload = normalize_document_payload({"document_text": text})
        r = pa.evaluate_document(payload, filename)
        actual    = r["decision"]          # "Publish" or "Do Not Publish"
        score     = r["overall_score"]
        correct   = (actual == expected)
        results.append({
            "file":     filename,
            "expected": expected,
            "actual":   actual,
            "score":    score,
            "correct":  correct,
            "agent_scores": {
                a["agent"]: a["overall_score"]
                for a in r.get("agent_outputs", [])
            },
        })
    return results


def print_results(results: list[dict]) -> None:
    # Per-document table
    col = 42
    print(f"\n{'File':<{col}} {'Expected':<20} {'Actual':<20} {'Score':>6}  {'OK'}")
    print("-" * (col + 52))
    for r in results:
        tick = "✅" if r["correct"] else "❌"
        print(
            f"{r['file']:<{col}} "
            f"{r['expected']:<20} "
            f"{r['actual']:<20} "
            f"{r['score']:>6.3f}  {tick}"
        )
        # Show per-agent breakdown for misclassified docs
        if not r["correct"]:
            for agent, s in r["agent_scores"].items():
                print(f"    {agent}: {s:.3f}")

    # Summary
    total   = len(results)
    correct = sum(1 for r in results if r["correct"])
    fp      = sum(1 for r in results if not r["correct"] and r["expected"] == "Publish")
    fn      = sum(1 for r in results if not r["correct"] and r["expected"] == "Do Not Publish")

    print()
    print(f"Accuracy : {correct}/{total}  ({100*correct/total:.1f}%)" if total else "No documents found.")
    if fp:
        print(f"False positives (blocked but should publish)  : {fp}")
    if fn:
        print(f"False negatives (published but should block)  : {fn}")
    if correct == total and total > 0:
        print("🎯 Perfect accuracy — all documents classified correctly.")
    print()


# ── Main ───────────────────────────────────────────────────────────────

def main() -> None:
    print(f"\nCalibration root : {CALIBRATION_DIR.resolve()}")

    positive_docs = load_docs(POSITIVE_DIR, "Publish")
    negative_docs = load_docs(NEGATIVE_DIR, "Do Not Publish")
    all_docs      = positive_docs + negative_docs

    if not all_docs:
        print(
            "\nNo documents found. Create the following folders and add .txt files:\n"
            f"  {POSITIVE_DIR}\n"
            f"  {NEGATIVE_DIR}\n"
        )
        sys.exit(1)

    print(f"Positive (expect Publish)       : {len(positive_docs)} doc(s)")
    print(f"Negative (expect Do Not Publish): {len(negative_docs)} doc(s)")
    print("\nRunning pipeline...\n")

    results = run(all_docs)
    print_results(results)


if __name__ == "__main__":
    main()
