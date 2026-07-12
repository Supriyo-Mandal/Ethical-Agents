# Ethical Agents — Semantic Risk Analyzer

A multi-agent AI system that evaluates documents for ethical risk across five domains — **Bias, Privacy, Security, Compliance, and Transparency** — and returns a clear publish / do-not-publish decision with per-domain scores, high-risk field breakdowns, and actionable recommendations.

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Scoring Pipeline](#scoring-pipeline)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
- [Configuration](#configuration)
- [API Reference](#api-reference)
- [Calibration](#calibration)
- [Extending the System](#extending-the-system)
- [Tech Stack](#tech-stack)

---

## Overview

Ethical Agents accepts any document (PDF, DOCX, TXT, MD) and runs it through a pipeline of five specialist agents. Each agent scores the document against a curated **Domain Knowledge Repository (DKR)** of risk fields. A parent orchestrator aggregates the domain scores using a ceiling-pull model and produces a final decision.

The frontend displays the full result in real time: overall score, domain score bars, high-risk fields with reasons, and remediation recommendations. All past analyses are persisted in the backend and loaded automatically on startup.

---

## Architecture

```
Browser (React + Vite)
        │
        │  POST /upload  ·  GET /history  ·  GET /report/{id}
        ▼
Backend API  (FastAPI · port 8000)
        │  extract text from PDF / DOCX / TXT / MD
        │  build document payload
        ▼
Orchestrator  (app/orchestrator)
        │  ParentAgent.evaluate_document()
        ▼
┌────────────────────────────────────┐
│          Five Domain Agents         │
│  Bias · Privacy · Security         │
│  Compliance · Transparency         │
└───────────────┬────────────────────┘
                │  load DKR + prompt
                ▼
       Knowledge Repositories
       app/knowledge/{domain}/
         repository.json  ←  risk field definitions
         prompt.txt        ←  LLM learning prompt
                │
                │  Phase 3: LLM (Fireworks AI)
                ▼
       New fields proposed → written back to DKR
```

---

## Scoring Pipeline

Every document passes through three phases inside each agent.

### Phase 1 — Relevance Gate
Only DKR fields whose name tokens appear in the document **and** have at least two meaningful keyword matches are forwarded to scoring. Short tokens (≤ 3 chars) are ignored to reduce noise.

### Phase 2 — Per-field Scoring (max 1.0)

| Component | Cap | Description |
|-----------|-----|-------------|
| A — Field-name coverage | 0.45 | Fraction of curated field-name tokens found in the document |
| B — Broad coverage | 0.20 | Fraction of all DKR entry tokens matched |
| C — Term density | 0.25 | Log-scaled reward for repeated term mentions |
| D — Prominence bonus | 0.10 | Field-name tokens appearing in the first 20% of the document |

The raw score is multiplied by a **governance multiplier** (0.15 – 1.0):

- Documents with explicit safeguards ("human review", "audit trail", "informed consent", "bias mitigation" …) get a multiplier near **0.15**, collapsing risk scores significantly.
- Documents that dismiss safeguards ("no human oversight", "validation is unnecessary", "fully automated decision" …) get a multiplier near **1.0**, preserving the full risk signal.

The multiplier is computed via a negation-aware phrase scan followed by a sigmoid function:

```
net        = dismissal_hits − governance_hits × 0.6
multiplier = 0.15 + 0.85 × sigmoid(net / 4.0)
```

### Phase 3 — Learning
If a Fireworks AI key is configured and the DKR has fewer than 60 fields, the agent asks the LLM whether the document introduces a genuinely novel risk concept. Candidates pass a Jaccard-style saturation check (≥ 60% overlap with an existing field → rejected). Accepted fields are written back to `repository.json`.

### Parent Orchestrator Aggregation

High-risk domains (score ≥ 0.70) dominate via score³/score² weighting. Clean domains add only 10% noise.

```
if any domain ≥ threshold:
    overall = Σ(score³) / Σ(score²)  +  mean(clean domains) × 0.10
else:
    overall = max(domain scores)

publish = overall_score < 0.70
```

---

## Project Structure

```
Ethical-Agents/
│
├── app/                            # AI agent framework
│   ├── agents/
│   │   ├── base_agent.py          # Scoring engine + governance multiplier
│   │   ├── bias/agent.py
│   │   ├── compliance/agent.py
│   │   ├── privacy/agent.py
│   │   ├── security/agent.py
│   │   └── transparency/agent.py
│   ├── knowledge/                 # Domain Knowledge Repositories
│   │   ├── bias/
│   │   │   ├── repository.json    # Risk field definitions (editable)
│   │   │   └── prompt.txt         # LLM learning prompt
│   │   ├── compliance/
│   │   ├── privacy/
│   │   ├── security/
│   │   └── transparency/
│   ├── orchestrator/
│   │   ├── parent_agent.py        # Aggregation + decision logic
│   │   └── __init__.py            # Entry point + schema bridge
│   ├── services/
│   │   ├── fireworks_client.py    # LLM API client
│   │   ├── knowledge_repository.py
│   │   └── document_payload.py
│   └── config.py                  # THRESHOLD, paths, allowed extensions
│
├── backend/                        # FastAPI wrapper
│   ├── app/
│   │   ├── api/routes.py          # /upload  /history  /report/{id}
│   │   ├── analysis.py            # File ingestion → orchestrator call
│   │   ├── storage.py             # JSON report persistence
│   │   ├── schemas.py             # Pydantic response models
│   │   └── main.py                # FastAPI app + CORS
│   └── reports/                   # Persisted analysis JSON files
│
├── frontend/                       # React + Vite UI
│   ├── src/
│   │   ├── App.jsx                # All views + API integration
│   │   ├── index.css              # Dark theme styles
│   │   └── main.jsx               # Entry point
│   ├── index.html
│   └── package.json
│
├── calibration_docs/               # Labelled test documents
│   ├── positive/                  # Documents that should be published
│   └── negative/                  # Documents that should be blocked
│
├── calibrate.py                    # Auto-calibration + grid search
├── test_eval.py                    # Evaluation script for test sets
├── start_services.py               # One-command service launcher
├── requirements.txt                # Python dependencies
└── .env.example                    # Environment variable template
```

---

## Getting Started

### Prerequisites

| Requirement | Version |
|-------------|---------|
| Python | 3.10+ |
| Node.js | 18+ |
| npm | 9+ |

### 1. Clone and install

```bash
git clone <repo-url>
cd Ethical-Agents

# Python dependencies
pip install -r requirements.txt

# Frontend dependencies
cd frontend && npm install && cd ..
```

### 2. Configure environment

```bash
# Copy and fill in your keys
cp .env.example .env
```

Edit `.env`:
```env
FIREWORKS_API_KEY=fw_your_key_here
OPENAI_API_KEY=sk_your_key_here      # optional fallback
```

Or set the Fireworks key in `config.json`:
```json
{ "api_key": "fw_your_key_here" }
```

### 3. Start all services

```bash
python start_services.py
```

This starts:
- **Backend API** → http://localhost:8000
- **Frontend** → http://localhost:3000

### Manual start (alternative)

```bash
# Terminal 1 — backend
python -m uvicorn backend.app.main:app --reload --port 8000

# Terminal 2 — frontend
cd frontend
npm run dev
```

### 4. Use it

1. Open http://localhost:3000
2. Go to **Upload** and select a PDF, DOCX, TXT, or MD file
3. Click **Submit for review**
4. View the decision, domain scores, high-risk fields, and recommendations
5. Visit **Dashboard** to browse all past analyses

---

## Configuration

| File | Key | Default | Description |
|------|-----|---------|-------------|
| `app/config.py` | `THRESHOLD` | `0.7` | Risk score above which publication is blocked |
| `app/config.py` | `MAX_FILE_SIZE_MB` | `10` | Maximum upload size |
| `app/config.py` | `ALLOWED_EXTENSIONS` | `.txt .md .pdf .docx` | Accepted file types |
| `app/orchestrator/parent_agent.py` | `THRESHOLD` | `0.7` | Orchestrator decision boundary |
| `config.json` | `api_key` | — | Fireworks AI API key |

---

## API Reference

All endpoints are on **port 8000**.

### `GET /health`
Returns `{"status": "ok"}`.

### `POST /upload` · `POST /analyze`
Upload a document for analysis.

**Request:** `multipart/form-data` with field `file`.

**Response:**
```json
{
  "publish": false,
  "overall_score": 0.862,
  "summary": "Publication is withheld due to elevated risk in Transparency, Privacy...",
  "metadata": {
    "decision": "Do Not Publish",
    "domain_scores": {
      "Bias": 0.354,
      "Privacy": 0.840,
      "Security": 0.819,
      "Compliance": 0.785,
      "Transparency": 0.855
    },
    "high_risk_fields": [
      {
        "agent": "Transparency",
        "field_name": "Self-Improving Model Opacity",
        "score": 0.851,
        "reason": "..."
      }
    ],
    "recommendations": [
      "[Privacy] Review and remediate 'Universal data collection without consent' (score 0.80): ..."
    ],
    "fields": [ ... ],
    "newly_learned_fields": [ ... ]
  },
  "previous_documents": [ ... ]
}
```

### `GET /history`
Returns all previously analysed documents.

```json
{ "analyses": [ { "id": "...", "document_name": "...", ... } ] }
```

### `GET /report/{analysis_id}`
Returns the full JSON report for a single analysis.

---

## Calibration

The `calibrate.py` script measures pipeline accuracy on labelled documents and auto-tunes scoring parameters.

```bash
python calibrate.py
```

Place labelled documents in:
```
calibration_docs/
  positive/   ← documents that SHOULD be published
  negative/   ← documents that SHOULD be blocked
```

The script:
1. Runs every document through the full pipeline
2. Computes accuracy, precision, recall, and F1
3. If accuracy < 100%, runs a grid search over `THRESHOLD`, `GOV_SIGMOID_SCALE`, `GOV_WEIGHT`, `LR_NOISE_AGENT`, `LR_NOISE_DOMAIN`
4. Patches `base_agent.py` and `parent_agent.py` in-place with the best parameters
5. Saves a before/after report to `calibration_results.txt`

To evaluate against a custom folder:
```bash
python calibrate.py "path/to/your/docs"
```

---

## Extending the System

### Add a new risk domain

**1. Create the agent:**
```python
# app/agents/fairness/agent.py
from app.agents.base_agent import BaseAgent

class FairnessAgent(BaseAgent):
    def __init__(self):
        super().__init__(name="Fairness")
```

**2. Create the knowledge repository:**
```
app/knowledge/fairness/repository.json   # list of risk field objects
app/knowledge/fairness/prompt.txt        # LLM learning prompt
```

**3. Register in the orchestrator:**
```python
# app/orchestrator/parent_agent.py
from app.agents.fairness.agent import FairnessAgent

agents = [BiasAgent, PrivacyAgent, SecurityAgent, ComplianceAgent, TransparencyAgent, FairnessAgent]
```

### Knowledge repository format

```json
[
  {
    "field_id": "FAIR_001",
    "field_name": "Disparate Impact",
    "description": "When an algorithm produces outcomes that disproportionately disadvantage a protected group.",
    "reason": "Disparate impact can violate anti-discrimination law even without discriminatory intent.",
    "examples": ["loan rejection rates differ by race", "hiring algorithm filters out women"]
  }
]
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18, React Router 6, Vite 5 |
| Backend API | FastAPI, Uvicorn, Pydantic v2 |
| Document parsing | pypdf, pdfminer.six, python-docx |
| LLM (Phase 3) | Fireworks AI (`accounts/fireworks/models/gpt-oss-120b`) |
| Storage | JSON files (no database required) |
| Styling | Custom CSS — dark theme with radial gradients |

---

## License

[Your License Here]
