document.addEventListener('DOMContentLoaded', async () => {
  const statusEl = document.getElementById('status');
  const fillBtn = document.getElementById('fillBtn');
  const openDashBtn = document.getElementById('openDashBtn');

  openDashBtn.addEventListener('click', () => {
    chrome.tabs.create({ url: 'http://localhost:5173' });
  });

  chrome.runtime.sendMessage({ type: 'HEALTH' }, (resp) => {
    if (resp && resp.ok) {
      statusEl.textContent = '✓ Connected to JobPulse (127.0.0.1:8000)';
      statusEl.style.borderColor = '#10b981';
      statusEl.style.color = '#6ee7b7';
      fillBtn.disabled = false;
    } else {
      statusEl.textContent = '✕ JobPulse backend offline. Start JobPulse first (start.bat).';
      statusEl.style.borderColor = '#ef4444';
      statusEl.style.color = '#fca5a5';
    }
  });

  fillBtn.addEventListener('click', async () => {
    fillBtn.disabled = true;
    fillBtn.textContent = 'Filling page...';
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab || !tab.id) {
      fillBtn.textContent = 'No active tab';
      return;
    }
    chrome.tabs.sendMessage(tab.id, { type: 'TRIGGER_AUTOFILL' }, (res) => {
      if (chrome.runtime.lastError || !res?.ok) {
        statusEl.textContent = 'Could not reach content script on this tab (try refreshing the page).';
        fillBtn.disabled = false;
        fillBtn.textContent = 'Auto-Fill Current Tab';
      } else {
        statusEl.textContent = '✓ Auto-Fill triggered! Check the bottom HUD bar.';
        fillBtn.textContent = '✓ Filled!';
        setTimeout(() => window.close(), 1200);
      }
    });
  });
});
