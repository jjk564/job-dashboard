const API_BASE = 'http://127.0.0.1:8000';

async function apiJson(path, options = {}) {
  const resp = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  });
  if (!resp.ok) {
    throw new Error(`HTTP ${resp.status}`);
  }
  return resp.json();
}

async function fetchPdfBase64(path) {
  const resp = await fetch(`${API_BASE}${path}`);
  if (!resp.ok) throw new Error(`PDF HTTP ${resp.status}`);
  const buf = await resp.arrayBuffer();
  const bytes = new Uint8Array(buf);
  let binary = '';
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode.apply(null, bytes.subarray(i, i + chunk));
  }
  return btoa(binary);
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  (async () => {
    try {
      if (msg.type === 'GET_ACTIVE_AUTOFILL') {
        const q = msg.url ? `?url=${encodeURIComponent(msg.url)}` : '';
        const data = await apiJson(`/api/assistant/active-autofill${q}`);
        sendResponse({ ok: true, data });
      } else if (msg.type === 'ANSWER_FIELDS') {
        const data = await apiJson('/api/assistant/answer-fields', {
          method: 'POST',
          body: JSON.stringify(msg.payload),
        });
        sendResponse({ ok: true, data });
      } else if (msg.type === 'FETCH_PDF') {
        const b64 = await fetchPdfBase64(msg.url);
        sendResponse({ ok: true, base64: b64 });
      } else if (msg.type === 'QUEUE_ACTION') {
        const data = await apiJson('/api/assistant/active-autofill/action', {
          method: 'POST',
          body: JSON.stringify(msg.payload),
        });
        sendResponse({ ok: true, data });
      } else if (msg.type === 'HEALTH') {
        const data = await apiJson('/api/health');
        sendResponse({ ok: true, data });
      } else {
        sendResponse({ ok: false, error: 'Unknown message type' });
      }
    } catch (err) {
      sendResponse({ ok: false, error: String(err && err.message ? err.message : err) });
    }
  })();
  return true; // keep channel open for async sendResponse
});
