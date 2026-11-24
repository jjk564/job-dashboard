function sendTabMsg(tabId, msg) {
  return new Promise((resolve) => {
    chrome.tabs.sendMessage(tabId, msg, (res) => {
      if (chrome.runtime.lastError) {
        resolve({ ok: false, error: chrome.runtime.lastError.message, missingScript: true });
      } else {
        resolve(res || { ok: false, error: 'No response from page' });
      }
    });
  });
}

function sendBg(msg) {
  return new Promise((resolve) => {
    chrome.runtime.sendMessage(msg, (resp) => {
      if (chrome.runtime.lastError) {
        resolve({ ok: false, error: chrome.runtime.lastError.message });
      } else {
        resolve(resp || { ok: false, error: 'No response' });
      }
    });
  });
}

document.addEventListener('DOMContentLoaded', async () => {
  const statusEl = document.getElementById('status');
  const activeJobEl = document.getElementById('activeJob');
  const fillBtn = document.getElementById('fillBtn');
  const openDashBtn = document.getElementById('openDashBtn');

  openDashBtn.addEventListener('click', () => {
    chrome.tabs.create({ url: 'http://localhost:5173' });
  });

  const health = await sendBg({ type: 'HEALTH' });
  if (health && health.ok) {
    statusEl.textContent = '✓ Connected to JobPulse (127.0.0.1:8000)';
    statusEl.style.borderColor = '#10b981';
    statusEl.style.color = '#6ee7b7';
    fillBtn.disabled = false;

    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    const ctxResp = await sendBg({ type: 'GET_ACTIVE_AUTOFILL', url: tab?.url || '', force: true });
    if (ctxResp.ok && ctxResp.data?.job) {
      const j = ctxResp.data.job;
      activeJobEl.style.display = 'block';
      activeJobEl.textContent = `Active Job: ${j.company || 'Company'} — ${j.title || 'Role'}`;
    }
  } else {
    statusEl.textContent = '✕ JobPulse backend offline. Start JobPulse first (start.bat).';
    statusEl.style.borderColor = '#ef4444';
    statusEl.style.color = '#fca5a5';
  }

  fillBtn.addEventListener('click', async () => {
    fillBtn.disabled = true;
    fillBtn.textContent = 'Scanning & filling page...';
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab || !tab.id) {
      fillBtn.textContent = 'No active tab';
      fillBtn.disabled = false;
      return;
    }

    if (tab.url && (tab.url.startsWith('chrome://') || tab.url.startsWith('edge://') || tab.url.startsWith('about:'))) {
      statusEl.textContent = 'Open a job listing tab first (cannot run on browser system pages).';
      statusEl.style.borderColor = '#f59e0b';
      statusEl.style.color = '#fcd34d';
      fillBtn.textContent = 'Auto-Fill Current Tab';
      fillBtn.disabled = false;
      return;
    }

    let res = await sendTabMsg(tab.id, { type: 'TRIGGER_AUTOFILL' });

    // If tab was already open before loading/reloading the extension, or is on a custom ATS domain,
    // dynamically inject content.js right now and trigger autofill without requiring a refresh!
    if (!res.ok && res.missingScript) {
      try {
        await chrome.scripting.executeScript({
          target: { tabId: tab.id },
          files: ['content.js'],
        });
        await new Promise((r) => setTimeout(r, 250));
        res = await sendTabMsg(tab.id, { type: 'TRIGGER_AUTOFILL' });
      } catch (err) {
        res = { ok: false, error: `Could not inject into tab: ${err?.message || err}` };
      }
    }

    if (!res.ok) {
      statusEl.textContent = res.error || 'Could not reach page (try refreshing this tab).';
      statusEl.style.borderColor = '#ef4444';
      statusEl.style.color = '#fca5a5';
      fillBtn.disabled = false;
      fillBtn.textContent = 'Auto-Fill Current Tab';
      return;
    }

    const filled = res.filledCount ?? 0;
    const manual = res.manualCount ?? 0;
    if (res.isLandingPage) {
      statusEl.textContent = 'Job description page detected (no form inputs yet). Click "I\'m interested" / Apply — JobPulse will auto-fill the form automatically!';
      statusEl.style.borderColor = '#f59e0b';
      statusEl.style.color = '#fde68a';
      fillBtn.textContent = 'Auto-Fill Current Tab';
      fillBtn.disabled = false;
    } else if (filled === 0 && (res.totalControls ?? 0) === 0) {
      statusEl.textContent = 'No visible form inputs found yet. If the form is inside a login/CAPTCHA gate or another step, open the form and click Auto-Fill again.';
      statusEl.style.borderColor = '#f59e0b';
      statusEl.style.color = '#fde68a';
      fillBtn.textContent = 'Retry Auto-Fill';
      fillBtn.disabled = false;
    } else {
      statusEl.textContent = manual > 0
        ? `✓ Filled ${filled} field(s)! ${manual} box(es) in amber need manual review.`
        : `✓ Filled ${filled} field(s)! Check the bottom HUD bar.`;
      statusEl.style.borderColor = '#10b981';
      statusEl.style.color = '#6ee7b7';
      fillBtn.textContent = `✓ Filled ${filled} field(s)`;
      setTimeout(() => window.close(), 1400);
    }
  });
});
