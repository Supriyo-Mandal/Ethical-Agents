# Connectivity test: backend analysis.py -> app/orchestrator -> agents
# Run from project root with the full python path
from __future__ import annotations

import sys
import traceback
import types

PASS = "\033[92m[PASS]\033[0m"
FAIL = "\033[91m[FAIL]\033[0m"
INFO = "\033[94m[INFO]\033[0m"

results: list[tuple[str, bool, str]] = []


def check(label: str, fn):
    try:
        detail = fn()
        results.append((label, True, detail or ""))
        print(f"{PASS} {label}" + (f"  ->  {detail}" if detail else ""))
        return True
    except Exception as exc:
        results.append((label, False, str(exc)))
        print(f"{FAIL} {label}")
        print(f"       {exc}")
        traceback.print_exc()
        return False


# ── 1. Import app.orchestrator ────────────────────────────────────────────────
def _import_orchestrator():
    import app.orchestrator as orch
    assert hasattr(orch, "analyze_document"), "analyze_document not found in app.orchestrator"
    return "app.orchestrator imported OK"

check("Import app.orchestrator", _import_orchestrator)


# ── 2. Import backend.app.analysis ────────────────────────────────────────────
def _import_analysis():
    from backend.app.analysis import analyze
    return "backend.app.analysis imported OK"

check("Import backend.app.analysis", _import_analysis)


# ── 3. Import all five agents ─────────────────────────────────────────────────
def _import_agents():
    from app.agents.bias.agent import BiasAgent
    from app.agents.compliance.agent import ComplianceAgent
    from app.agents.privacy.agent import PrivacyAgent
    from app.agents.security.agent import SecurityAgent
    from app.agents.transparency.agent import TransparencyAgent
    agents = [BiasAgent(), ComplianceAgent(), PrivacyAgent(), SecurityAgent(), TransparencyAgent()]
    names = [a.name for a in agents]
    return f"Agents loaded: {names}"

check("Import all five agents", _import_agents)


# ── 4. BaseAgent.evaluate() returns expected shape ───────────────────────────
def _base_agent_evaluate():
    from app.agents.base_agent import BaseAgent
    agent = BaseAgent(name="Test")
    result = agent.evaluate("sample text", "sample.txt")
    assert "agent" in result
    assert "overall_score" in result
    return f"evaluate() keys: {list(result.keys())}"

check("BaseAgent.evaluate() returns expected shape", _base_agent_evaluate)


# ── 5. ParentAgent.decide() aggregates scores correctly ──────────────────────
def _parent_agent_decide():
    from app.orchestrator.parent_agent import ParentAgent
    agent = ParentAgent()
    outputs = [
        {"overall_score": 0.4},
        {"overall_score": 0.6},
        {"overall_score": 0.55},
    ]
    result = agent.decide(outputs)
    assert "publish" in result
    assert "overall_score" in result
    assert result["overall_score"] == 0.6   # max of the three
    assert result["publish"] is True         # 0.6 < threshold 0.7
    return f"publish={result['publish']}, overall_score={result['overall_score']}"

check("ParentAgent.decide() aggregates correctly", _parent_agent_decide)


# ── 6. Simulate a minimal UploadFile-like payload through analyze_document ───
def _orchestrator_call():
    from app.orchestrator import analyze_document

    # Minimal stand-in for UploadFile
    fake_file = types.SimpleNamespace(
        filename="test_document.txt",
        content_type="text/plain",
        content=b"This is a test document.",
    )
    payload = {
        "document_name": fake_file.filename,
        "document_type": fake_file.content_type,
        "document": fake_file,
    }

    result = analyze_document(payload)
    assert isinstance(result, dict), "Result must be a dict"
    for key in ("publish", "overall_score", "summary", "metadata"):
        assert key in result, f"Missing key: {key}"
    assert "fields" in result["metadata"], "metadata.fields missing"
    return (
        f"publish={result['publish']}, "
        f"overall_score={result['overall_score']}, "
        f"fields={len(result['metadata']['fields'])}"
    )

check("analyze_document(payload) returns correct shape", _orchestrator_call)


# ── 7. Full call through backend analysis.analyze() ──────────────────────────
def _backend_analyze():
    from backend.app.analysis import analyze

    fake_file = types.SimpleNamespace(
        filename="test_document.pdf",
        content_type="application/pdf",
        content=b"%PDF test content",
    )

    result = analyze(fake_file)
    assert isinstance(result, dict)
    for key in ("publish", "overall_score", "summary", "metadata"):
        assert key in result, f"Missing key in backend result: {key}"
    return f"Backend analyze() OK — publish={result['publish']}, score={result['overall_score']}"

check("backend.app.analysis.analyze() full call", _backend_analyze)


# ── 8. storage.save_analysis / load_analysis round-trip ──────────────────────
def _storage_roundtrip():
    from backend.app.storage import save_analysis, load_analysis

    dummy_result = {
        "publish": True,
        "overall_score": 0.55,
        "summary": "Connectivity test entry",
        "metadata": {"fields": []},
    }
    saved = save_analysis("connectivity_test.txt", dummy_result)
    analysis_id = saved["id"]

    loaded = load_analysis(analysis_id)
    assert loaded is not None
    assert loaded["id"] == analysis_id
    assert loaded["document_name"] == "connectivity_test.txt"

    # Clean up the test report
    from backend.app.storage import delete_analysis
    delete_analysis(analysis_id)

    return f"save→load round-trip OK (id={analysis_id[:8]}…)"

check("storage save/load round-trip", _storage_roundtrip)


# ── Summary ───────────────────────────────────────────────────────────────────
print()
print("=" * 55)
passed = sum(1 for _, ok, _ in results if ok)
total  = len(results)
print(f"  Results: {passed}/{total} passed")
if passed == total:
    print("  \033[92mAll connectivity checks passed.\033[0m")
else:
    print("  \033[91mSome checks failed — see details above.\033[0m")
    for label, ok, detail in results:
        if not ok:
            print(f"    FAIL: {label} — {detail}")
print("=" * 55)

sys.exit(0 if passed == total else 1)
