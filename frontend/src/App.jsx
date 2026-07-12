import { useEffect, useMemo, useState } from 'react';
import { Link, NavLink, Route, Routes, useLocation } from 'react-router-dom';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

const NAV = [
  { to: '/',          label: 'Home',      icon: '⬡' },
  { to: '/upload',    label: 'Upload',    icon: '⬆' },
  { to: '/dashboard', label: 'Dashboard', icon: '▤' },
];

/* ─── Score helpers ──────────────────────────────────────────────── */
function scoreColor(score) {
  if (score >= 0.75) return 'danger';
  if (score >= 0.5)  return 'caution';
  return 'safe';
}

function ScoreBar({ score }) {
  const pct   = Math.round(score * 100);
  const color = scoreColor(score);
  return (
    <div className="score-bar-wrap">
      <div className="score-bar-track">
        <div className={`score-bar-fill ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className={`score-label ${color}`}>{pct}</span>
    </div>
  );
}

/* ─── Root App ───────────────────────────────────────────────────── */
export default function App() {
  const location = useLocation();
  const [sidebarOpen, setSidebarOpen]   = useState(false);
  const [documents,   setDocuments]     = useState(() => {
    try {
      const raw = window.localStorage.getItem('ea-docs');
      if (raw) {
        const parsed = JSON.parse(raw);
        if (Array.isArray(parsed)) return parsed;
      }
    } catch { /* ignore */ }
    return [];
  });
  const [uploadState, setUploadState]   = useState({ loading: false, result: null });
  const [selectedFile, setSelectedFile] = useState(null);

  useEffect(() => {
    window.localStorage.setItem('ea-docs', JSON.stringify(documents));
  }, [documents]);

  // Load existing reports from the backend on mount
  useEffect(() => {
    fetch(`${API_URL}/history`)
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (!data?.analyses?.length) return;
        const fromBackend = data.analyses.map(r => ({
          id:            r.id,
          name:          r.document_name ?? 'Unknown',
          type:          'text/plain',
          submittedAt:   r.id,   // no timestamp in stored report; use id as stable key
          publish:       Boolean(r.publish),
          overall_score: r.overall_score ?? 0,
          summary:       r.summary ?? '',
          decision:      r.metadata?.decision ?? (r.publish ? 'Publish' : 'Do Not Publish'),
          domain_scores:     r.metadata?.domain_scores      ?? {},
          high_risk_fields:  r.metadata?.high_risk_fields   ?? [],
          recommendations:   r.metadata?.recommendations    ?? [],
          fields:            r.metadata?.fields             ?? [],
        }));
        // Merge: backend is source of truth; keep any local-only entries not yet in backend
        setDocuments(prev => {
          const backendIds = new Set(fromBackend.map(d => d.id));
          const localOnly  = prev.filter(d => !backendIds.has(d.id));
          return [...fromBackend, ...localOnly].slice(0, 50);
        });
      })
      .catch(() => { /* backend offline — keep localStorage */ });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const summary = useMemo(() => ({
    total:    documents.length,
    publish:  documents.filter(d => d.publish).length,
    blocked:  documents.filter(d => !d.publish).length,
  }), [documents]);

  const handleUpload = async (e) => {
    e.preventDefault();
    const file = selectedFile || e.target.elements.file?.files?.[0];
    if (!file) return;

    setUploadState({ loading: true, result: null });

    try {
      const fd = new FormData();
      fd.append('file', file);

      const res = await fetch(`${API_URL}/upload`, { method: 'POST', body: fd });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || 'Upload failed');
      }

      const data = await res.json();
      const meta = data.metadata ?? {};

      const entry = {
        id:          String(Date.now()),
        name:        file.name,
        type:        file.type || 'unknown',
        submittedAt: new Date().toLocaleString(),
        publish:     Boolean(data.publish),
        overall_score: data.overall_score ?? 0,
        summary:     data.summary ?? '',
        decision:    meta.decision ?? (data.publish ? 'Publish' : 'Do Not Publish'),
        domain_scores:      meta.domain_scores      ?? {},
        high_risk_fields:   meta.high_risk_fields   ?? [],
        recommendations:    meta.recommendations    ?? [],
        fields:             meta.fields             ?? [],
      };

      setDocuments(prev => [entry, ...prev].slice(0, 20));
      setUploadState({ loading: false, result: entry });
    } catch (err) {
      setUploadState({ loading: false, result: { error: err.message } });
    }

    setSelectedFile(null);
    e.target.reset();
  };

  const pageName = location.pathname === '/'
    ? 'Home'
    : location.pathname.replace('/', '').replace(/^\w/, c => c.toUpperCase());

  return (
    <div className="shell">
      {/* Mobile toggle */}
      <button className="drawer-btn" onClick={() => setSidebarOpen(o => !o)} aria-label="Menu">
        <span />
        <span />
        <span />
      </button>

      {/* Sidebar */}
      <aside className={`sidebar${sidebarOpen ? ' open' : ''}`}>
        <div className="brand">
          <div className="brand-logo">EA</div>
          <div>
            <p className="kicker">Ethical Agent</p>
            <p className="brand-sub">Review Hub</p>
          </div>
        </div>

        <nav className="nav-list">
          {NAV.map(({ to, label, icon }) => (
            <NavLink
              key={to} to={to}
              className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}
              onClick={() => setSidebarOpen(false)}
            >
              <span className="nav-icon">{icon}</span>
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-stat">
          <div className="stat-row">
            <span>Reviewed</span><strong>{summary.total}</strong>
          </div>
          <div className="stat-row">
            <span>Published</span><strong className="c-safe">{summary.publish}</strong>
          </div>
          <div className="stat-row">
            <span>Blocked</span><strong className="c-danger">{summary.blocked}</strong>
          </div>
        </div>
      </aside>

      {sidebarOpen && (
        <div className="backdrop" onClick={() => setSidebarOpen(false)} />
      )}

      {/* Main */}
      <main className="main">
        <header className="topbar">
          <div>
            <p className="kicker">workspace</p>
            <h1 className="topbar-title">{pageName}</h1>
          </div>
          <Link to="/upload" className="btn-primary">+ New Review</Link>
        </header>

        <Routes>
          <Route path="/"          element={<HomeView summary={summary} />} />
          <Route path="/upload"    element={
            <UploadView
              onUpload={handleUpload}
              selectedFile={selectedFile}
              setSelectedFile={setSelectedFile}
              uploadState={uploadState}
            />}
          />
          <Route path="/dashboard" element={<DashboardView documents={documents} summary={summary} />} />
        </Routes>
      </main>
    </div>
  );
}

/* ─── Home ───────────────────────────────────────────────────────── */
function HomeView({ summary }) {
  return (
    <section className="page">

      {/* Hero */}
      <div className="hero">
        <div className="hero-copy">
          <p className="kicker">Intelligent document review</p>
          <h2 className="hero-h2">
            Evaluate every document for ethical risk, compliance, and bias — automatically.
          </h2>
          <p className="hero-sub">
            Upload a PDF, DOCX, or TXT file and the agent pipeline scores it across
            five domains: Bias, Privacy, Security, Compliance, and Transparency.
          </p>
          <div className="hero-actions">
            <Link to="/upload"    className="btn-primary">Start Upload</Link>
            <Link to="/dashboard" className="btn-ghost">View Dashboard</Link>
          </div>
        </div>

        <div className="hero-visual" aria-hidden="true">
          <div className="orb orb-a" />
          <div className="orb orb-b" />
          <div className="orb orb-c" />
          <div className="float-chip chip-1">Bias</div>
          <div className="float-chip chip-2">Privacy</div>
          <div className="float-chip chip-3">Security</div>
          <div className="float-chip chip-4">Compliance</div>
          <div className="float-chip chip-5">Transparency</div>
        </div>
      </div>

      {/* Stats strip */}
      <div className="stats-strip">
        <div className="stat-box">
          <span className="stat-num">{summary.total}</span>
          <span className="stat-lbl">Documents reviewed</span>
        </div>
        <div className="stat-box">
          <span className="stat-num c-safe">{summary.publish}</span>
          <span className="stat-lbl">Cleared for publish</span>
        </div>
        <div className="stat-box">
          <span className="stat-num c-danger">{summary.blocked}</span>
          <span className="stat-lbl">Blocked</span>
        </div>
        <div className="stat-box">
          <span className="stat-num">5</span>
          <span className="stat-lbl">Risk domains</span>
        </div>
      </div>

      {/* How it works */}
      <div className="section-title">How it works</div>
      <div className="steps-grid">
        {[
          { n: '01', title: 'Upload',   desc: 'Drop a PDF, DOCX, TXT, or MD file into the upload page.' },
          { n: '02', title: 'Analyse',  desc: 'Five specialist agents scan the document simultaneously.' },
          { n: '03', title: 'Score',    desc: 'Each domain returns a risk score and high-risk field list.' },
          { n: '04', title: 'Decide',   desc: 'The orchestrator aggregates scores and makes a publish decision.' },
        ].map(s => (
          <div key={s.n} className="step-card">
            <span className="step-num">{s.n}</span>
            <strong>{s.title}</strong>
            <p>{s.desc}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

/* ─── Upload ─────────────────────────────────────────────────────── */
function UploadView({ onUpload, selectedFile, setSelectedFile, uploadState }) {
  const { loading, result } = uploadState;

  return (
    <section className="page">
      <div className="glass-panel upload-panel">
        <h2>Upload a document</h2>
        <p className="panel-sub">
          Supported formats: PDF, DOCX, TXT, MD. The agent pipeline will score the
          document across five ethical risk domains and return a publish decision.
        </p>

        <form className="upload-form" onSubmit={onUpload}>
          <label className="dropzone">
            <input
              type="file"
              name="file"
              accept=".pdf,.docx,.txt,.md"
              onChange={e => setSelectedFile(e.target.files?.[0] || null)}
            />
            <div className="drop-inner">
              <span className="drop-icon">⬆</span>
              <span className="drop-text">
                {selectedFile
                  ? <>Selected: <strong>{selectedFile.name}</strong></>
                  : 'Click to choose a file — or drag and drop here'}
              </span>
              {selectedFile && (
                <span className="drop-meta">
                  {(selectedFile.size / 1024).toFixed(1)} KB · {selectedFile.type || 'unknown type'}
                </span>
              )}
            </div>
          </label>

          <button className="btn-primary btn-submit" type="submit" disabled={loading || !selectedFile}>
            {loading ? <><span className="spinner" />Processing…</> : 'Submit for review'}
          </button>
        </form>
      </div>

      {/* Error */}
      {result?.error && (
        <div className="result-panel error-panel">
          <div className="rp-header">
            <span className="rp-icon">✕</span>
            <div>
              <h3>Upload failed</h3>
              <p>{result.error}</p>
            </div>
          </div>
        </div>
      )}

      {/* Success result */}
      {result && !result.error && (
        <ResultPanel entry={result} />
      )}
    </section>
  );
}

/* ─── Result panel (shared between Upload result + Dashboard detail) */
function ResultPanel({ entry }) {
  const publish = entry.publish;
  const score   = entry.overall_score ?? 0;
  const domainScores    = entry.domain_scores    ?? {};
  const highRiskFields  = entry.high_risk_fields ?? [];
  const recommendations = entry.recommendations  ?? [];

  return (
    <div className={`result-panel ${publish ? 'rp-publish' : 'rp-block'}`}>

      {/* Decision header */}
      <div className="rp-header">
        <div className={`decision-badge ${publish ? 'db-publish' : 'db-block'}`}>
          {publish ? '✓ Publish' : '✕ Do Not Publish'}
        </div>
        <div className="rp-scores">
          <div className="rp-score-main">
            <span className="rp-score-num">{Math.round(score * 100)}</span>
            <span className="rp-score-label">/100 overall</span>
          </div>
        </div>
      </div>

      {/* File info */}
      <div className="rp-filename">{entry.name}</div>

      {/* Summary */}
      {entry.summary && (
        <p className="rp-summary">{entry.summary}</p>
      )}

      {/* Domain scores */}
      {Object.keys(domainScores).length > 0 && (
        <div className="rp-section">
          <div className="rp-section-title">Domain scores</div>
          <div className="domain-grid">
            {Object.entries(domainScores).map(([domain, s]) => (
              <div key={domain} className="domain-row">
                <span className="domain-name">{domain}</span>
                <ScoreBar score={s} />
              </div>
            ))}
          </div>
        </div>
      )}

      {/* High-risk fields */}
      {highRiskFields.length > 0 && (
        <div className="rp-section">
          <div className="rp-section-title danger-title">
            ⚠ High-risk fields ({highRiskFields.length})
          </div>
          <div className="hrf-list">
            {highRiskFields.map((f, i) => (
              <div key={i} className="hrf-item">
                <div className="hrf-top">
                  <span className="hrf-agent">{f.agent}</span>
                  <span className="hrf-field">{f.field_name}</span>
                  <span className={`hrf-score ${scoreColor(f.score)}`}>
                    {Math.round(f.score * 100)}
                  </span>
                </div>
                {f.reason && <p className="hrf-reason">{f.reason}</p>}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Recommendations */}
      {recommendations.length > 0 && (
        <div className="rp-section">
          <div className="rp-section-title">Recommendations</div>
          <ul className="rec-list">
            {recommendations.map((r, i) => (
              <li key={i}>{r}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

/* ─── Dashboard ──────────────────────────────────────────────────── */
function DashboardView({ documents, summary }) {
  const [selected, setSelected] = useState(null);

  return (
    <section className="page">

      {/* Summary cards */}
      <div className="dash-stats">
        <div className="dstat">
          <p className="dstat-label">Total reviewed</p>
          <p className="dstat-value">{summary.total}</p>
        </div>
        <div className="dstat dstat-safe">
          <p className="dstat-label">Published</p>
          <p className="dstat-value c-safe">{summary.publish}</p>
        </div>
        <div className="dstat dstat-danger">
          <p className="dstat-label">Blocked</p>
          <p className="dstat-value c-danger">{summary.blocked}</p>
        </div>
        <div className="dstat">
          <p className="dstat-label">Avg risk score</p>
          <p className="dstat-value">
            {summary.total
              ? Math.round(documents.reduce((s, d) => s + (d.overall_score ?? 0), 0) / summary.total * 100)
              : '—'}
          </p>
        </div>
      </div>

      {documents.length === 0 ? (
        <div className="empty-state">
          <span className="empty-icon">▤</span>
          <p>No documents reviewed yet.</p>
          <Link to="/upload" className="btn-primary">Upload your first document</Link>
        </div>
      ) : (
        <div className="dash-body">

          {/* Document list */}
          <div className="doc-list">
            {documents.map(doc => (
              <button
                key={doc.id}
                className={`doc-row${selected?.id === doc.id ? ' doc-row-active' : ''}`}
                onClick={() => setSelected(selected?.id === doc.id ? null : doc)}
              >
                <div className="doc-row-left">
                  <span className={`dot ${doc.publish ? 'dot-safe' : 'dot-danger'}`} />
                  <div>
                    <p className="doc-row-name">{doc.name}</p>
                    <p className="doc-row-meta">{doc.submittedAt} · {doc.type}</p>
                  </div>
                </div>
                <div className="doc-row-right">
                  <span className={`badge ${doc.publish ? 'badge-safe' : 'badge-danger'}`}>
                    {doc.publish ? 'Publish' : 'Blocked'}
                  </span>
                  <span className={`score-pill ${scoreColor(doc.overall_score ?? 0)}`}>
                    {Math.round((doc.overall_score ?? 0) * 100)}
                  </span>
                </div>
              </button>
            ))}
          </div>

          {/* Detail panel */}
          {selected && (
            <div className="doc-detail">
              <ResultPanel entry={selected} />
            </div>
          )}
        </div>
      )}
    </section>
  );
}
