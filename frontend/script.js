const uploadForm = document.getElementById('uploadForm');
const fileInput = document.getElementById('fileInput');
const resultCard = document.getElementById('resultCard');
const resultPill = document.getElementById('resultPill');
const resultTitle = document.getElementById('resultTitle');
const resultMessage = document.getElementById('resultMessage');
const metadataList = document.getElementById('metadataList');
const historyList = document.getElementById('historyList');
const submitBtn = document.getElementById('submitBtn');
const connectionStatus = document.getElementById('connectionStatus');
const dropzone = document.getElementById('dropzone');

const API = {
  upload: '/api/documents/upload',
  history: '/api/documents'
};

let documents = [];

const fallbackDocuments = [
  {
    id: 'demo-1',
    name: 'Quarterly-Compliance.pdf',
    type: 'application/pdf',
    submittedAt: '2026-07-10 09:15',
    status: 'YES',
    metadata: {
      owner: 'Compliance Team',
      retained: 'Yes',
      source: 'mock-seed'
    }
  },
  {
    id: 'demo-2',
    name: 'Vendor-Review.docx',
    type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    submittedAt: '2026-07-09 16:10',
    status: 'NO',
    metadata: {
      risk: 'Low',
      checksum: '3ef9ba7',
      source: 'mock-seed'
    }
  }
];

document.addEventListener('DOMContentLoaded', init);

function init() {
  wireDropzone();
  loadHistory();
  uploadForm.addEventListener('submit', handleUpload);
}

function wireDropzone() {
  ['dragenter', 'dragover'].forEach((eventName) => {
    dropzone.addEventListener(eventName, (event) => {
      event.preventDefault();
      dropzone.classList.add('is-active');
    });
  });

  ['dragleave', 'drop'].forEach((eventName) => {
    dropzone.addEventListener(eventName, (event) => {
      event.preventDefault();
      dropzone.classList.remove('is-active');
    });
  });

  dropzone.addEventListener('drop', (event) => {
    const droppedFile = event.dataTransfer?.files?.[0];
    if (droppedFile) {
      fileInput.files = event.dataTransfer.files;
      const fileNameLabel = document.createElement('div');
      fileNameLabel.className = 'dropzone-hint';
      fileNameLabel.textContent = `Selected: ${droppedFile.name}`;
      dropzone.replaceChildren(
        document.createElement('div').appendChild(document.createElement('span')).parentNode
      );
      dropzone.innerHTML = `<div class="dropzone-content"><span class="dropzone-icon">✓</span><p class="dropzone-title">${droppedFile.name}</p><p class="dropzone-hint">Ready to submit</p></div>`;
    }
  });
}

function setConnectionStatus(message, isConnected = true) {
  connectionStatus.textContent = message;
  connectionStatus.style.background = isConnected ? 'rgba(34, 197, 94, 0.16)' : 'rgba(245, 158, 11, 0.16)';
  connectionStatus.style.color = isConnected ? '#8ef7b5' : '#ffd08a';
}

async function loadHistory() {
  try {
    const response = await fetch(API.history, { cache: 'no-store' });
    if (!response.ok) throw new Error('History endpoint unavailable');
    const payload = await response.json();
    documents = Array.isArray(payload.documents)
      ? payload.documents
      : Array.isArray(payload)
        ? payload
        : fallbackDocuments;
    setConnectionStatus('Connected to backend', true);
  } catch (error) {
    documents = JSON.parse(localStorage.getItem('ethical-agent-documents') || '[]');
    if (!documents.length) {
      documents = fallbackDocuments;
    }
    setConnectionStatus('Backend unavailable • showing demo data', false);
  } finally {
    renderHistory();
  }
}

async function handleUpload(event) {
  event.preventDefault();

  const file = fileInput.files[0];
  if (!file) {
    showResult({
      status: 'NO',
      title: 'No file selected',
      message: 'Choose a document before submitting it for review.',
      metadata: { error: 'Missing file' }
    });
    return;
  }

  submitBtn.disabled = true;
  submitBtn.textContent = 'Uploading...';

  const formData = new FormData();
  formData.append('file', file);
  formData.append('name', file.name);

  try {
    const response = await fetch(API.upload, {
      method: 'POST',
      body: formData
    });

    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.message || 'Upload failed');

    const normalized = normalizePayload(file, payload);
    showResult(normalized);
    documents = [normalized, ...documents].slice(0, 8);
    persistDocuments();
    renderHistory();
    setConnectionStatus('Upload received by backend', true);
  } catch (error) {
    const fallback = createFallbackUpload(file, error.message);
    showResult(fallback);
    documents = [fallback, ...documents].slice(0, 8);
    persistDocuments();
    renderHistory();
    setConnectionStatus('Backend not reachable • stored locally', false);
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = 'Submit for review';
    uploadForm.reset();
    dropzone.innerHTML = `
      <div class="dropzone-content">
        <span class="dropzone-icon">⬆</span>
        <p class="dropzone-title">Drag & drop or click to upload</p>
        <p class="dropzone-hint">Supported formats: PDF, DOCX, TXT, MD</p>
      </div>
    `;
  }
}

function normalizePayload(file, payload) {
  const decision = (payload.response || payload.status || payload.decision || 'YES').toString().toUpperCase();
  const metadata = payload.metadata || payload.data || payload.result || {}; 

  return {
    id: payload.id || `${Date.now()}`,
    name: payload.name || file.name,
    type: payload.type || file.type || 'application/octet-stream',
    submittedAt: payload.submittedAt || new Date().toLocaleString(),
    status: decision === 'NO' ? 'NO' : 'YES',
    metadata: {
      ...metadata,
      uploadedBy: payload.uploadedBy || 'Current user',
      source: 'backend'
    }
  };
}

function createFallbackUpload(file, errorMessage) {
  return {
    id: `local-${Date.now()}`,
    name: file.name,
    type: file.type || 'application/octet-stream',
    submittedAt: new Date().toLocaleString(),
    status: 'NO',
    metadata: {
      error: errorMessage,
      source: 'local-fallback',
      note: 'The backend API is not available yet. This entry was stored locally until the endpoint is supplied.'
    }
  };
}

function showResult(result) {
  resultCard.classList.remove('hidden');
  resultPill.textContent = result.status === 'YES' ? 'YES' : 'NO';
  resultPill.style.background = result.status === 'YES' ? 'rgba(34, 197, 94, 0.16)' : 'rgba(245, 158, 11, 0.16)';
  resultPill.style.color = result.status === 'YES' ? '#8ef7b5' : '#ffd08a';

  resultTitle.textContent = result.status === 'YES' ? 'Document uploaded successfully' : 'Review metadata';
  resultMessage.textContent = result.message || (result.status === 'YES'
    ? 'The document has been accepted and the processing response was positive.'
    : 'The backend returned a negative outcome. Review the metadata below.');

  metadataList.innerHTML = '';
  Object.entries(result.metadata || {}).forEach(([key, value]) => {
    const item = document.createElement('div');
    item.className = 'metadata-item';
    item.innerHTML = `<strong>${key.replace(/_/g, ' ')}</strong><span>${String(value)}</span>`;
    metadataList.appendChild(item);
  });
}

function renderHistory() {
  if (!documents.length) {
    historyList.innerHTML = '<div class="empty-state">No documents have been submitted yet.</div>';
    return;
  }

  historyList.innerHTML = documents
    .map((doc) => {
      const metadataPreview = Object.entries(doc.metadata || {})
        .slice(0, 3)
        .map(([key, value]) => `${key}: ${String(value)}`)
        .join(' • ');

      return `
        <article class="history-card">
          <header>
            <h3>${doc.name}</h3>
            <span class="status-chip ${doc.status === 'YES' ? 'yes' : 'no'}">${doc.status}</span>
          </header>
          <div class="history-meta">
            <div><strong>Submitted:</strong> ${doc.submittedAt}</div>
            <div><strong>Type:</strong> ${doc.type}</div>
            <div><strong>Details:</strong> ${metadataPreview || 'No metadata provided'}</div>
          </div>
        </article>
      `;
    })
    .join('');
}

function persistDocuments() {
  localStorage.setItem('ethical-agent-documents', JSON.stringify(documents));
}
