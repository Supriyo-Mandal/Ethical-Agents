# Ethical Agents - Semantic Risk Analyzer

Multi-agent AI system for analyzing documents for ethical risks across Bias, Privacy, Security, Compliance, and Transparency dimensions.

## 🎯 Overview

This system uses 5 specialized AI agents to evaluate documents and make publish/don't-publish decisions based on risk scores across multiple ethical dimensions.

**Architecture**: Frontend (React) → Backend (FastAPI) → Agent Orchestrator → 5 Domain Agents

## 🚀 Quick Start

### Option 1: Unified Starter (Recommended)
```bash
cd Ethical-Agents
python start_services.py
```

Then open: http://localhost:5173

### Option 2: Manual Start
```bash
# Terminal 1: Backend API
python -m uvicorn backend.app.main:app --reload --port 8000

# Terminal 2: Frontend
cd frontend
npm run dev
```

## 📊 System Architecture

```
┌─────────────────┐
│  Frontend       │  User uploads document
│  React + Vite   │  
│  Port: 5173     │
└────────┬────────┘
         │ POST /upload
         │ (multipart/form-data)
         ▼
┌─────────────────┐
│  Backend API    │  Receives file, calls agents
│  FastAPI        │  
│  Port: 8000     │
└────────┬────────┘
         │ analyze_document()
         ▼
┌─────────────────┐
│  Orchestrator   │  Routes to ParentAgent
│  Schema Trans.  │  Transforms output
└────────┬────────┘
         │ evaluate_document()
         ▼
┌─────────────────┐
│  ParentAgent    │  Coordinates 5 agents
│  Aggregates     │  Makes final decision
└────────┬────────┘
         │ agent.evaluate() ×5
         ▼
┌─────────────────────────────────────────┐
│            Domain Agents                │
│  ┌──────────┐  ┌──────────┐           │
│  │  Bias    │  │ Privacy  │           │
│  └──────────┘  └──────────┘           │
│  ┌──────────┐  ┌──────────┐           │
│  │ Security │  │Compliance│           │
│  └──────────┘  └──────────┘           │
│  ┌──────────┐                          │
│  │Transprncy│                          │
│  └──────────┘                          │
└─────────────────────────────────────────┘
         │
         │ Load knowledge repositories
         ▼
┌─────────────────┐
│  Knowledge Base │  Risk field definitions
│  JSON + TXT     │  AI prompts
└─────────────────┘
```

## 🎯 How It Works

1. **User uploads document** via React frontend
2. **Backend receives file** and calls agent orchestrator
3. **ParentAgent** coordinates 5 domain-specific agents
4. **Each agent** evaluates document against its knowledge repository
5. **Agents score risks** (0.0 = safe, 1.0 = high risk)
6. **ParentAgent aggregates** scores (takes maximum)
7. **Decision made**: If score < 0.7 → Publish, else Don't Publish
8. **Results displayed** to user with detailed breakdowns

## 📁 Project Structure

```
Ethical-Agents/
├── frontend/               # React frontend (Vite)
│   ├── src/
│   │   ├── App.jsx        # Main UI component
│   │   └── main.jsx
│   ├── .env               # API URL configuration
│   └── package.json
│
├── backend/               # FastAPI backend wrapper
│   ├── app/
│   │   ├── api/
│   │   │   └── routes.py  # API endpoints
│   │   ├── analysis.py    # Calls agent system
│   │   ├── storage.py     # JSON storage
│   │   └── main.py        # FastAPI app
│   └── reports/           # Analysis results (JSON)
│
├── app/                   # Agent system
│   ├── orchestrator/
│   │   ├── parent_agent.py        # Main orchestrator
│   │   └── __init__.py            # Entry point + schema transform
│   ├── agents/
│   │   ├── base_agent.py          # Base agent class
│   │   ├── bias/agent.py
│   │   ├── privacy/agent.py
│   │   ├── security/agent.py
│   │   ├── compliance/agent.py
│   │   └── transparency/agent.py
│   ├── knowledge/         # Risk field definitions
│   │   ├── bias/
│   │   │   ├── repository.json
│   │   │   └── prompt.txt
│   │   ├── privacy/
│   │   ├── security/
│   │   ├── compliance/
│   │   └── transparency/
│   └── core/              # Utilities
│
├── connection_flow_audit.py       # System audit tool ⭐
├── fix_connections.py             # Integration fixer ⭐
├── start_services.py              # Unified starter ⭐
├── connection_audit_report.json   # Latest audit results
│
├── CONNECTION_GUIDE.md            # Detailed integration guide 📚
├── SYSTEM_FLOW_DIAGRAM.md         # Visual architecture 📚
├── INTEGRATION_SUMMARY.md         # Complete summary 📚
├── QUICK_REFERENCE.md             # Quick lookup 📚
│
└── requirements.txt
```

## 🔧 Configuration

### Frontend Environment
Create `frontend/.env`:
```env
VITE_API_URL=http://localhost:8000
```

### Backend Environment
```bash
export OPENAI_API_KEY=your_key_here
export BACKEND_URL=http://127.0.0.1:8000
```

### Fireworks AI
Set API key in `config.json`:
```json
{
  "api_key": "fw_xxx..."
}
```

## 🔍 System Health Check

```bash
# Run comprehensive audit
python connection_flow_audit.py

# Check backend
curl http://localhost:8000/health

# View audit results
cat connection_audit_report.json
```

## 📡 API Endpoints

### Backend API (Port 8000)
- `GET /health` - Health check
- `POST /upload` - Upload and analyze document
- `POST /analyze` - Analyze document
- `GET /history` - Get all analyses
- `GET /report/{id}` - Get specific report

### Response Format
```json
{
  "publish": true,
  "overall_score": 0.45,
  "summary": "The document presents a manageable risk profile...",
  "metadata": {
    "fields": [
      {
        "agent": "Bias",
        "field": "Automated Decision Making",
        "score": 0.88,
        "reason": "The document discusses automated decisions..."
      }
    ],
    "description": "...",
    "paragraph": "...",
    "fields_used": ["Automated Decision Making"],
    "agent_count": 5,
    "decision": "Publish"
  },
  "previous_documents": [...]
}
```

## 🎯 Decision Logic

```python
# Each agent scores document (0.0 - 1.0)
agent_score = average(field_scores)

# ParentAgent takes maximum score
overall_score = max(all_agent_scores)

# Decision threshold
THRESHOLD = 0.7

if overall_score < 0.7:
    decision = "Publish"        # Safe
else:
    decision = "Do Not Publish" # Too risky
```

## 🧪 Testing

### Manual Test
1. Start services: `python start_services.py`
2. Open frontend: http://localhost:5173
3. Click "Upload" or "New Review"
4. Select a document
5. Click "Submit for review"
6. View results and dashboard

### Automated Audit
```bash
python connection_flow_audit.py
```

Checks:
- ✓ Service availability
- ✓ JSON schema validation
- ✓ Data flow integrity
- ✓ Integration points
- ✓ Issue detection

## 📚 Documentation

| File | Purpose |
|------|---------|
| **QUICK_REFERENCE.md** | Quick lookup and commands |
| **CONNECTION_GUIDE.md** | Step-by-step connection details |
| **SYSTEM_FLOW_DIAGRAM.md** | Visual flow with ASCII diagrams |
| **INTEGRATION_SUMMARY.md** | Complete integration summary |
| **connection_audit_report.json** | Latest system audit results |

## 🛠️ Tools Included

### 1. Connection Audit Tool
```bash
python connection_flow_audit.py
```
- Checks service availability
- Validates JSON schemas
- Documents data flow
- Identifies integration issues
- Generates recommendations
- Saves detailed report

### 2. Unified Service Starter
```bash
python start_services.py
```
- Starts both backend and frontend
- Monitors service health
- Single command deployment

### 3. Connection Fixer
```bash
python fix_connections.py
```
- Fixes integration issues
- Connects real agents (was stub)
- Adds schema transformation
- Configures environment

## 🐛 Troubleshooting

### Frontend can't connect to backend
```bash
# Check backend is running
curl http://localhost:8000/health

# Verify .env configuration
cat frontend/.env

# Check CORS settings
# File: backend/app/main.py
```

### Agents not working
```bash
# Verify orchestrator connection
# File: app/orchestrator/__init__.py

# Check ParentAgent instantiation
# Should call: ParentAgent().evaluate_document()
```

### Schema errors
```bash
# Run audit to identify
python connection_flow_audit.py

# Check transformation layer
# File: app/orchestrator/__init__.py
# Function: transform_to_backend_schema()
```

## 🔄 Development Workflow

1. Make code changes
2. Run audit: `python connection_flow_audit.py`
3. Check for issues in report
4. Fix issues if needed
5. Restart services: `python start_services.py`
6. Test upload flow
7. Verify results

## 📊 Knowledge Repository Format

Each agent has a knowledge repository (`app/knowledge/{domain}/repository.json`):

```json
[
  {
    "field_id": "unique-id",
    "field_name": "Risk Field Name",
    "description": "What this field represents",
    "reason": "Why it's a concern",
    "examples": ["example1", "example2"]
  }
]
```

## 🎨 Frontend Features

- **Upload Page**: Drag-and-drop file upload
- **Dashboard**: View all analyzed documents
- **Result Cards**: Detailed risk breakdown
- **Status Badges**: YES (green) / NO (yellow)
- **History**: LocalStorage persistence
- **Responsive**: Mobile-friendly design

## 🔐 Security Notes

- File uploads validated by type and size
- Backend stores reports as JSON (not executable)
- CORS configured for localhost development
- Production: Update CORS origins in `backend/app/main.py`

## 📈 Extending the System

### Add a New Agent
1. Create `app/agents/newdomain/agent.py`:
   ```python
   from app.agents.base_agent import BaseAgent
   
   class NewDomainAgent(BaseAgent):
       def __init__(self):
           super().__init__(name="NewDomain")
   ```

2. Create knowledge repository:
   - `app/knowledge/newdomain/repository.json`
   - `app/knowledge/newdomain/prompt.txt`

3. Add to ParentAgent (`app/orchestrator/parent_agent.py`):
   ```python
   from app.agents.newdomain.agent import NewDomainAgent
   
   agent_classes = [..., NewDomainAgent]
   ```

### Update Knowledge Base
1. Edit `app/knowledge/{domain}/repository.json`
2. Add/modify field definitions
3. Agents auto-load on next evaluation

### Change Risk Threshold
Edit `app/orchestrator/parent_agent.py`:
```python
self.threshold = 0.7  # Change to desired value (0.0-1.0)
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make changes
4. Run audit: `python connection_flow_audit.py`
5. Submit pull request

## 📄 License

[Your License Here]

## 🙏 Acknowledgments

- Fireworks AI for LLM capabilities
- FastAPI for backend framework
- React + Vite for frontend

## 📞 Support

For issues or questions:
1. Check documentation files (see 📚 Documentation section)
2. Run audit tool: `python connection_flow_audit.py`
3. Review troubleshooting section
4. Check audit report: `connection_audit_report.json`

---

**Quick Links:**
- 📖 [Quick Reference](QUICK_REFERENCE.md)
- 🔗 [Connection Guide](CONNECTION_GUIDE.md)
- 📊 [System Flow Diagram](SYSTEM_FLOW_DIAGRAM.md)
- 📝 [Integration Summary](INTEGRATION_SUMMARY.md)

**Status**: ✅ All systems integrated and tested
