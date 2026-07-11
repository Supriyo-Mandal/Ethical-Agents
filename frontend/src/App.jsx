import { useEffect, useMemo, useState } from 'react';
import { Link, NavLink, Route, Routes, useLocation } from 'react-router-dom';

const initialDocs = [
  {
    id: 'demo-1',
    name: 'Quarterly Compliance Review',
    type: 'PDF',
    submittedAt: '2026-07-10 09:15',
    status: 'YES',
    metadata: { owner: 'Compliance Team', severity: 'Low', source: 'mock-seed' }
  },
  {
    id: 'demo-2',
    name: 'Vendor Assessment',
    type: 'DOCX',
    submittedAt: '2026-07-09 16:10',
    status: 'NO',
    metadata: { owner: 'Operations', severity: 'Medium', source: 'mock-seed' }
  }
];

const pageConfig = [
  { to: '/', label: 'Home', icon: '◉' },
  { to: '/upload', label: 'Upload', icon: '⬆' },
  { to: '/dashboard', label: 'Dashboard', icon: '▤' },
  { to: '/help', label: 'Help & Support', icon: '❓' }
];

export default function App() {
  const location = useLocation();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [documents, setDocuments] = useState(() => {
    const saved = window.localStorage.getItem('ethical-agent-documents');
    return saved ? JSON.parse(saved) : initialDocs;
  });
  const [uploadState, setUploadState] = useState({ loading: false, result: null });
  const [selectedFile, setSelectedFile] = useState(null);

  useEffect(() => {
    window.localStorage.setItem('ethical-agent-documents', JSON.stringify(documents));
  }, [documents]);

  const summary = useMemo(() => {
    const yesCount = documents.filter((item) => item.status === 'YES').length;
    const noCount = documents.filter((item) => item.status === 'NO').length;
    return { yesCount, noCount, total: documents.length };
  }, [documents]);

  const handleUpload = async (event) => {
    event.preventDefault();
    const file = selectedFile || event.target.elements.file?.files?.[0];
    if (!file) return;

    setUploadState({ loading: true, result: null });

    try {
      const formData = new FormData();
      formData.append('file', file);

      const res = await fetch('http://localhost:8000/upload', { method: 'POST', body: formData });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || 'Upload failed');
      }

      const data = await res.json();
      const decision = data.publish ? 'YES' : 'NO';
      const nextEntry = {
        id: `${Date.now()}`,
        name: file.name,
        type: file.type || 'Unknown',
        submittedAt: new Date().toLocaleString(),
        status: decision,
        metadata: { summary: data.summary, source: 'backend', ...Object.fromEntries((data.metadata?.fields ?? []).map((f) => [f.name ?? f.key, f.value])) }
      };

      setDocuments((prev) => [nextEntry, ...prev].slice(0, 8));
      setUploadState({ loading: false, result: nextEntry });
    } catch (err) {
      setUploadState({ loading: false, result: { error: err.message } });
    }

    setSelectedFile(null);
    event.target.reset();
  };

  return (
    <div className="app-shell">
      <button className="drawer-toggle" onClick={() => setSidebarOpen((open) => !open)}>
        ☰
      </button>

      <aside className={`sidebar ${sidebarOpen ? 'open' : ''}`}>
        <div className="brand">
          <div className="brand-mark">EA</div>
          <div>
            <p className="eyebrow">ethical agent</p>
            <h2>Review Hub</h2>
          </div>
        </div>

        <nav className="nav-links">
          {pageConfig.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}
              onClick={() => setSidebarOpen(false)}
            >
              <span className="nav-icon">{item.icon}</span>
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-footer">
          <p>Always-on document review</p>
          <small>Secure, animated, and built for clarity.</small>
        </div>
      </aside>

      {sidebarOpen && <div className="sidebar-backdrop" onClick={() => setSidebarOpen(false)} />}

      <main className="main-panel">
        <header className="topbar">
          <div>
            <p className="eyebrow">workspace overview</p>
            <h1>{location.pathname === '/' ? 'Home' : location.pathname.replace('/', '') || 'Home'}</h1>
          </div>
          <Link to="/upload" className="pill-btn">New Review</Link>
        </header>

        <Routes>
          <Route path="/" element={<HomeView />} />
          <Route path="/upload" element={<UploadView onUpload={handleUpload} selectedFile={selectedFile} setSelectedFile={setSelectedFile} uploadState={uploadState} />} />
          <Route path="/dashboard" element={<DashboardView documents={documents} summary={summary} />} />
          <Route path="/help" element={<HelpView />} />
        </Routes>
      </main>
    </div>
  );
}

function HomeView() {
  return (
    <section className="page home-page">
      <div className="hero-card">
        <div className="hero-copy">
          <p className="eyebrow">intelligent review</p>
          <h2>Upload a document and let the workspace evaluate it for trust, compliance, and completeness.</h2>
          <p>Ethical Agent provides a calm, cinematic review experience where every document can be reviewed, stored, and tracked in a single command center.</p>
          <div className="hero-actions">
            <Link to="/upload" className="primary-btn">Start Upload</Link>
            <Link to="/dashboard" className="secondary-btn">View Dashboard</Link>
          </div>
        </div>
        <div className="orbital-stack" aria-hidden="true">
          <div className="orb orb-one" />
          <div className="orb orb-two" />
          <div className="orb orb-three" />
          <div className="floating-card card-a">Live review</div>
          <div className="floating-card card-b">Structured metadata</div>
          <div className="floating-card card-c">Audit history</div>
        </div>
      </div>
    </section>
  );
}

function UploadView({ onUpload, selectedFile, setSelectedFile, uploadState }) {
  return (
    <section className="page upload-page">
      <div className="panel-glass">
        <h2>Upload a document</h2>
        <p>Send the file to the backend for processing. Once the review finishes, the result and metadata will be reflected in the dashboard.</p>
        <form className="upload-form" onSubmit={onUpload}>
          <label className="dropzone">
            <input type="file" name="file" onChange={(event) => setSelectedFile(event.target.files?.[0] || null)} />
            <span>{selectedFile ? `Selected: ${selectedFile.name}` : 'Choose a PDF, DOCX, TXT, or MD file'}</span>
          </label>
          <button className="primary-btn" type="submit" disabled={uploadState.loading}>
            {uploadState.loading ? 'Processing…' : 'Submit for review'}
          </button>
        </form>

        {uploadState.result?.error && (
          <div className="result-card warn">
            <div className="result-head"><strong>Error</strong><span>Upload failed</span></div>
            <p>{uploadState.result.error}</p>
          </div>
        )}
        {uploadState.result?.status && (
          <div className={`result-card ${uploadState.result.status === 'YES' ? 'success' : 'warn'}`}>
            <div className="result-head">
              <strong>{uploadState.result.status}</strong>
              <span>{uploadState.result.status === 'YES' ? 'Accepted' : 'Needs review'}</span>
            </div>
            <p>{uploadState.result.name} was reviewed successfully.</p>
            <div className="metadata-grid">
              {Object.entries(uploadState.result.metadata).map(([key, value]) => (
                <div key={key} className="meta-item">
                  <strong>{key}</strong>
                  <span>{String(value)}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </section>
  );
}

function DashboardView({ documents, summary }) {
  return (
    <section className="page dashboard-page">
      <div className="summary-grid">
        <div className="summary-card">
          <p>Total reviewed</p>
          <h3>{summary.total}</h3>
        </div>
        <div className="summary-card good">
          <p>Accepted</p>
          <h3>{summary.yesCount}</h3>
        </div>
        <div className="summary-card warning">
          <p>Needs review</p>
          <h3>{summary.noCount}</h3>
        </div>
      </div>

      <div className="dashboard-list">
        {documents.map((doc) => (
          <article key={doc.id} className="doc-card">
            <div className="doc-head">
              <h3>{doc.name}</h3>
              <span className={`badge ${doc.status === 'YES' ? 'success' : 'warn'}`}>{doc.status}</span>
            </div>
            <p>{doc.type} • {doc.submittedAt}</p>
            <div className="metadata-grid">
              {Object.entries(doc.metadata).map(([key, value]) => (
                <div key={`${doc.id}-${key}`} className="meta-item">
                  <strong>{key}</strong>
                  <span>{String(value)}</span>
                </div>
              ))}
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

function HelpView() {
  return (
    <section className="page help-page">
      <div className="panel-glass">
        <h2>Help & Support</h2>
        <p>Our support team is here to help with upload issues, review questions, or account concerns.</p>
        <div className="support-grid">
          <div className="support-card">
            <h3>Contact options</h3>
            <ul>
              <li>Email: help@ethicalagent.example</li>
              <li>Phone: +1 (800) 555-0189</li>
              <li>Hours: Mon-Fri • 8:00 AM - 6:00 PM</li>
            </ul>
          </div>
          <div className="support-card">
            <h3>Common support topics</h3>
            <ul>
              <li>Upload problems and file size limits</li>
              <li>Review outcome interpretation</li>
              <li>Dashboard visibility and history</li>
            </ul>
          </div>
        </div>
      </div>
    </section>
  );
}
