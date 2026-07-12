"""
test_eval.py
------------
Test evaluation script.  Takes a labelled test folder and evaluates every
document through the full pipeline, reporting accuracy, precision, recall,
and F1 score.

Expected folder structure:

    <test_folder>/
        positive/     ← documents that should be classified as Publish
            doc1.txt
            doc2.txt
            ...
        negative/     ← documents that should be classified as Do Not Publish
            doc3.txt
            doc4.txt
            ...

Supported file types: .txt  .md

Usage:
    python test_eval.py <test_folder>

    # example
    python test_eval.py "c:/Users/SARTHAK/OneDrive/Desktop/Doc"

Results are printed to stdout and appended to train_eval_results.txt.

Notes:
    - Documents are fed to the pipeline one at a time in random order
      (simulating real-world unseen arrival).
    - Each document is evaluated independently — no batching.
    - Misclassified documents are reported with their per-agent scores
      so you can trace which domain drove the wrong decision.
"""

from __future__ import annotations
import random
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.orchestrator.parent_agent import ParentAgent
from app.services.document_payload import normalize_document_payload

SUPPORTED    = {".txt", ".md"}
# Always write to the project root regardless of working directory
_PROJECT_ROOT = Path(__file__).resolve().parent
RESULTS_FILE  = _PROJECT_ROOT / "train_eval_results.txt"
TEST_RESULTS_FILE = _PROJECT_ROOT / "test_results.txt"

# ── Helpers ────────────────────────────────────────────────────────────

def load_folder(test_folder: Path):
    """Load all labelled docs from positive/ and negative/ subfolders."""
    docs = []
    for label, expected in [("positive", "Publish"), ("negative", "Do Not Publish")]:
        folder = test_folder / label
        if not folder.exists():
            print(f"  [warn] subfolder not found: {folder}")
            continue
        for f in sorted(folder.iterdir()):
            if f.suffix.lower() not in SUPPORTED:
                continue
            text = f.read_text(encoding="utf-8", errors="ignore").strip()
            if not text:
                print(f"  [warn] empty file skipped: {f.name}")
                continue
            docs.append({
                "tag":      f"{label}/{f.name}",
                "text":     text,
                "expected": expected,
            })
    return docs


def calc_metrics(tp, fp, fn, tn):
    total     = tp + fp + fn + tn
    accuracy  = (tp + tn) / total if total else 0.0
    precision = tp / (tp + fp)    if (tp + fp) else 0.0
    recall    = tp / (tp + fn)    if (tp + fn) else 0.0
    f1        = (2 * precision * recall / (precision + recall)
                 if (precision + recall) else 0.0)
    return dict(accuracy=round(accuracy, 3), precision=round(precision, 3),
                recall=round(recall, 3),    f1=round(f1, 3),
                tp=tp, fp=fp, fn=fn, tn=tn, total=total)


# ── Main ───────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print("Usage: python test_eval.py <test_folder>")
        print("  e.g. python test_eval.py \"c:/path/to/test_docs\"")
        sys.exit(1)

    test_folder = Path(sys.argv[1])
    if not test_folder.exists():
        print(f"Error: folder not found: {test_folder}")
        sys.exit(1)

    docs = load_folder(test_folder)
    if not docs:
        print("No documents found. Check the folder has positive/ and negative/ subfolders with .txt files.")
        sys.exit(1)

    # Shuffle to simulate random arrival order
    random.shuffle(docs)

    pos_count = sum(1 for d in docs if d["expected"] == "Publish")
    neg_count = sum(1 for d in docs if d["expected"] == "Do Not Publish")

    SEP  = "=" * 72
    HSEP = "#" * 72
    lines = []
    run_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines.append(f"\n{HSEP}")
    lines.append(f"TEST EVAL RUN  —  {run_ts}")
    lines.append(f"Folder : {test_folder.resolve()}")
    lines.append(f"Docs   : {len(docs)} total  ({pos_count} positive / {neg_count} negative)")
    lines.append(HSEP)

    pa = ParentAgent()
    tp = fp = fn = tn = 0
    result_rows  = []
    misclassified = []

    print(f"\nEvaluating {len(docs)} documents...\n")

    col = 30
    header = f"{'File':<{col}} {'Expected':<20} {'Actual':<20} {'Score':>6}  Status"
    print(header)
    print("-" * len(header))
    lines.append(f"\n{'File':<{col}} {'Expected':<20} {'Actual':<20} {'Score':>6}  Status")
    lines.append("-" * len(header))

    for doc in docs:
        tag      = doc["tag"]
        text     = doc["text"]
        expected = doc["expected"]

        payload = normalize_document_payload({"document_text": text})
        r       = pa.evaluate_document(payload, tag)
        actual  = r["decision"]
        score   = r["overall_score"]
        correct = (actual == expected)

        # Confusion matrix
        if expected == "Do Not Publish" and actual == "Do Not Publish":
            tp += 1
        elif expected == "Publish" and actual == "Do Not Publish":
            fp += 1
        elif expected == "Do Not Publish" and actual == "Publish":
            fn += 1
        else:
            tn += 1

        status = "OK" if correct else ("FALSE_NEG" if expected == "Do Not Publish" else "FALSE_POS")
        row    = f"{tag:<{col}} {expected:<20} {actual:<20} {score:>6.3f}  {status}"
        result_rows.append(row)
        print(row)
        lines.append(row)

        if not correct:
            agent_detail = "  ".join(
                f"{a['agent']}={a['overall_score']:.3f}"
                for a in r.get("agent_outputs", [])
            )
            detail = f"  └─ agents: {agent_detail}"
            misclassified.append({"tag": tag, "expected": expected,
                                   "actual": actual, "score": score,
                                   "detail": detail})
            print(detail)
            lines.append(detail)

    # ── Summary ────────────────────────────────────────────────────────
    m = calc_metrics(tp, fp, fn, tn)

    summary_lines = [
        f"\n{SEP}",
        "RESULTS SUMMARY",
        SEP,
        f"  Total documents   : {m['total']}",
        f"  Correct           : {tp + tn}  /  {m['total']}",
        f"",
        f"  Accuracy          : {m['accuracy']:.3f}",
        f"  Precision (risky) : {m['precision']:.3f}",
        f"  Recall    (risky) : {m['recall']:.3f}  ← KEY METRIC",
        f"  F1 score          : {m['f1']:.3f}",
        f"",
        f"  Confusion matrix  :",
        f"    TP (risky caught)      = {tp}",
        f"    FP (safe doc blocked)  = {fp}",
        f"    FN (risky doc passed)  = {fn}  ← must be 0",
        f"    TN (safe doc passed)   = {tn}",
    ]

    if misclassified:
        summary_lines.append(f"\n  Misclassified documents ({len(misclassified)}):")
        for mc in misclassified:
            summary_lines.append(f"    [{mc['expected']} → {mc['actual']}]  "
                                  f"{mc['tag']}  score={mc['score']:.3f}")
            summary_lines.append(f"    {mc['detail']}")
    else:
        summary_lines.append("\n  All documents classified correctly.")

    recall_status = "PERFECT" if m["recall"] == 1.0 else f"FAIL — {fn} risky doc(s) passed"
    summary_lines.append(f"\n  Recall status     : {recall_status}")

    for line in summary_lines:
        print(line)
    lines.extend(summary_lines)

    # Write to both test_results.txt (dedicated) and train_eval_results.txt (shared log)
    output = "\n".join(lines)
    with open(TEST_RESULTS_FILE, "a", encoding="utf-8") as fh:
        fh.write(output + "\n")
    with open(RESULTS_FILE, "a", encoding="utf-8") as fh:
        fh.write(output + "\n")
    print(f"\nResults saved to   : {TEST_RESULTS_FILE}")
    print(f"Also appended to   : {RESULTS_FILE}")


if __name__ == "__main__":
    main()
