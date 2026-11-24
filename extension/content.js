(() => {
  if (window.__jobPulseExtensionLoaded) return;
  window.__jobPulseExtensionLoaded = true;

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

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

  function isVisible(el) {
    if (!el || !el.isConnected) return false;
    const style = window.getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
    const rect = el.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  }

  function setNativeValue(el, val) {
    const tag = el.tagName.toLowerCase();
    const proto = tag === 'textarea' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
    if (setter) {
      setter.call(el, val);
    } else {
      el.value = val;
    }
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
    el.dispatchEvent(new Event('blur', { bubbles: true }));
  }

  function isPlaceholderOnly(txt) {
    const t = (txt || '').trim().toLowerCase();
    return !t || t.length < 2 || [
      'select', 'select...', 'select an option', 'select one',
      'choose', 'choose...', 'choose an option', '--', 'search',
      'textbox', 'combobox', 'option', 'please select'
    ].includes(t);
  }

  function extractLabel(el) {
    if (el.labels && el.labels.length > 0) {
      const t = Array.from(el.labels).map((l) => l.innerText).join(' ').trim();
      if (!isPlaceholderOnly(t)) return t;
    }
    const ariaLbl = el.getAttribute('aria-labelledby');
    if (ariaLbl) {
      const joined = ariaLbl.split(/\s+/).map((id) => document.getElementById(id)?.innerText?.trim()).filter(Boolean).join(' ');
      if (!isPlaceholderOnly(joined)) return joined;
    }
    const aria = (el.getAttribute('aria-label') || '').trim();
    if (!isPlaceholderOnly(aria)) return aria;
    if (el.id) {
      try {
        const forLbl = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
        if (forLbl && !isPlaceholderOnly(forLbl.innerText)) return forLbl.innerText.trim();
      } catch (_) {}
    }
    const fs = el.closest('fieldset');
    if (fs) {
      const leg = fs.querySelector('legend');
      if (leg && !isPlaceholderOnly(leg.innerText)) return leg.innerText.trim();
    }
    let cur = el.parentElement;
    for (let k = 0; k < 8 && cur && !['FORM', 'BODY', 'MAIN', 'SECTION'].includes(cur.tagName); k++) {
      const siblingControls = cur.querySelectorAll('input:not([type="hidden"]):not([type="radio"]):not([type="checkbox"]), textarea, select, [role="combobox"], [aria-haspopup="listbox"]');
      const distinctControls = new Set(Array.from(siblingControls).map((c) => c.closest('.select__control') || c));
      if (distinctControls.size > 1) break;
      const candidates = cur.querySelectorAll('label, legend, [data-testid*="label"], [class*="label"], [class*="question"], h3, h4, h5, p');
      for (const c of candidates) {
        if (c === el || el.contains(c)) continue;
        const ht = (c.innerText || '').trim();
        if (!isPlaceholderOnly(ht) && ht !== (el.innerText || '').trim() && ht.length <= 320) {
          return ht;
        }
      }
      if (cur.previousElementSibling) {
        const prev = cur.previousElementSibling;
        if (['LABEL', 'SPAN', 'P', 'H3', 'H4', 'H5', 'DIV'].includes(prev.tagName) &&
            !prev.querySelector('input, select, textarea, [role="combobox"]')) {
          const prevTxt = (prev.innerText || '').trim();
          if (!isPlaceholderOnly(prevTxt) && prevTxt.length <= 300) return prevTxt;
        }
      }
      cur = cur.parentElement;
    }
    return (el.getAttribute('placeholder') || el.getAttribute('name') || el.getAttribute('id') || '').trim();
  }

  function highlightManual(el, label) {
    try {
      const box = el.closest('[role="radiogroup"], .select__control, fieldset') || el;
      box.style.outline = '2px dashed #f59e0b';
      box.style.outlineOffset = '2px';
      box.title = `JobPulse needs your input: ${label}`;
    } catch (_) {}
  }

  async function attachFiles(job) {
    let uploaded = 0;
    if (!job || (!job.resume_pdf_url && !job.cover_letter_pdf_url)) return 0;

    const fileInputs = Array.from(document.querySelectorAll('input[type="file"]')).filter((inp) => {
      const accept = (inp.getAttribute('accept') || '').toLowerCase();
      if (accept && !accept.includes('pdf') && !accept.includes('doc') && (accept.includes('image') || accept.includes('.png') || accept.includes('.jpg'))) {
        return false;
      }
      return true;
    });
    if (!fileInputs.length) return 0;

    let resumeInput = null;
    let coverInput = null;
    const hasCoverTextarea = Boolean(document.querySelector('textarea[id*="cover" i], textarea[name*="cover" i], textarea[placeholder*="cover" i]'));

    for (const inp of fileInputs) {
      const ctx = `${inp.id} ${inp.name} ${inp.getAttribute('aria-label') || ''} ${inp.closest('div, section, fieldset')?.innerText?.slice(0, 180) || ''}`.toLowerCase();
      if (ctx.includes('avatar') || ctx.includes('headshot')) continue;
      if ((ctx.includes('cover letter') || ctx.includes('cover_letter') || ctx.includes('cover')) && !hasCoverTextarea && !coverInput) {
        coverInput = inp;
      } else if ((ctx.includes('resume') || ctx.includes('résumé') || ctx.includes('cv')) && !resumeInput) {
        resumeInput = inp;
      }
    }
    if (!resumeInput && fileInputs.length > 0) {
      resumeInput = fileInputs.find((i) => i !== coverInput) || fileInputs[0];
    }

    async function setPdf(inputEl, pdfUrl, filename) {
      if (!inputEl || !pdfUrl) return false;
      if (inputEl.files && inputEl.files.length > 0) return false;
      const res = await sendBg({ type: 'FETCH_PDF', url: pdfUrl });
      if (!res.ok || !res.base64) return false;
      const raw = atob(res.base64);
      const arr = new Uint8Array(raw.length);
      for (let i = 0; i < raw.length; i++) arr[i] = raw.charCodeAt(i);
      const file = new File([arr], filename || 'Resume.pdf', { type: 'application/pdf' });
      const dt = new DataTransfer();
      dt.items.add(file);
      inputEl.files = dt.files;
      inputEl.dispatchEvent(new Event('input', { bubbles: true }));
      inputEl.dispatchEvent(new Event('change', { bubbles: true }));
      return true;
    }

    if (resumeInput && job.resume_pdf_url) {
      if (await setPdf(resumeInput, job.resume_pdf_url, job.resume_filename || 'Resume.pdf')) uploaded++;
    }
    if (coverInput && job.cover_letter_pdf_url && !hasCoverTextarea) {
      if (await setPdf(coverInput, job.cover_letter_pdf_url, job.cover_letter_filename || 'Cover_Letter.pdf')) uploaded++;
    }
    return uploaded;
  }

  async function runAutoFill(ctxData) {
    const job = ctxData.job || null;
    const fieldsMeta = [];
    const elById = new Map();
    let seq = 0;

    // 1. Collect native inputs, textareas, selects
    const controls = Array.from(document.querySelectorAll(
      'input:not([type="file"]):not([type="radio"]):not([type="checkbox"]):not([type="hidden"]):not([type="submit"]):not([type="button"]):not([type="search"]), textarea, select'
    )).filter((el) => isVisible(el) && !el.disabled && !el.readOnly);

    for (const el of controls) {
      const tag = el.tagName.toLowerCase();
      const inpType = (el.getAttribute('type') || 'text').toLowerCase();
      if ((tag === 'input' || tag === 'textarea') && (el.value || '').trim()) continue;
      if (tag === 'select') {
        const selOpt = el.options[el.selectedIndex];
        const selTxt = (selOpt?.text || '').trim().toLowerCase();
        if (el.value && selTxt && !isPlaceholderOnly(selTxt)) continue;
      }
      const rawLabel = extractLabel(el);
      let label = rawLabel.replace(/\*/g, '').trim();
      const nm = (el.name || '').toLowerCase();
      const idLow = (el.id || '').toLowerCase();
      if (nm.includes('eeo[race]') || idLow.includes('race')) label = 'Race';
      else if (nm.includes('eeo[gender]') || idLow.includes('gender')) label = 'Gender';
      else if (nm.includes('eeo[veteran]') || idLow.includes('veteran')) label = 'Veteran status';
      else if (nm.includes('eeo[disability]') || idLow.includes('disability')) label = 'Disability status';

      if (!label || label.length < 2) continue;
      const fid = `f_${seq++}`;
      elById.set(fid, { kind: tag, el, inpType, label });
      const options = tag === 'select'
        ? Array.from(el.options).map((o) => o.text.trim()).filter(Boolean)
        : null;
      fieldsMeta.push({
        id: fid,
        label,
        options,
        field_type: tag === 'input' ? (inpType === 'number' || inpType === 'date' || inpType === 'url' ? inpType : 'text') : tag,
        required: Boolean(el.required || el.getAttribute('aria-required') === 'true' || rawLabel.includes('*')),
      });
    }

    // 2. Collect native radio groups
    const radioGroups = new Map();
    document.querySelectorAll('input[type="radio"]').forEach((r) => {
      const name = r.name || `rg_${seq++}`;
      if (!radioGroups.has(name)) radioGroups.set(name, []);
      radioGroups.get(name).push(r);
    });
    for (const [gName, radios] of radioGroups.entries()) {
      if (radios.some((r) => r.checked)) continue;
      const opts = radios.map((r) => (
        (r.labels && r.labels[0]?.innerText) ||
        r.closest('label')?.innerText ||
        r.getAttribute('aria-label') ||
        r.value || ''
      ).trim());
      const fs = radios[0].closest('fieldset');
      let prompt = fs?.querySelector('legend')?.innerText?.trim() || extractLabel(radios[0]) || gName;
      prompt = prompt.replace(/\*/g, '').trim();
      if (!prompt) continue;
      const fid = `r_${seq++}`;
      elById.set(fid, { kind: 'radio_group', radios, opts, label: prompt });
      fieldsMeta.push({
        id: fid,
        label: prompt,
        options: opts.filter(Boolean),
        field_type: 'radio',
        required: radios.some((r) => r.required || r.getAttribute('aria-required') === 'true'),
      });
    }

    // 3. Collect checkboxes (skip CAPTCHAs & checked)
    const checkboxes = Array.from(document.querySelectorAll('input[type="checkbox"]')).filter((cb) => {
      if (cb.checked || cb.disabled) return false;
      const sig = `${cb.id} ${cb.name} ${cb.className}`.toLowerCase();
      if (sig.includes('captcha') || sig.includes('turnstile') || cb.closest('.g-recaptcha, .h-captcha, .cf-turnstile')) return false;
      return true;
    });
    for (const cb of checkboxes) {
      const label = (
        (cb.labels && cb.labels[0]?.innerText) ||
        cb.closest('label')?.innerText ||
        cb.getAttribute('aria-label') ||
        cb.parentElement?.innerText?.slice(0, 220) || ''
      ).replace(/\*/g, '').trim();
      if (!label || label.length < 3) continue;
      const fid = `c_${seq++}`;
      elById.set(fid, { kind: 'checkbox', el: cb, label });
      fieldsMeta.push({
        id: fid,
        label,
        options: ['Yes', 'No'],
        field_type: 'checkbox',
        required: Boolean(cb.required || cb.getAttribute('aria-required') === 'true'),
      });
    }

    // 4. Ask Python backend to answer all fields + scan live page for Bot Traps
    const pageText = (document.body?.innerText || '').slice(0, 12000);
    const ansResp = await sendBg({
      type: 'ANSWER_FIELDS',
      payload: {
        job_id: job?.id || null,
        url: window.location.href,
        fields: fieldsMeta,
        page_text: pageText,
      },
    });

    let filledCount = 0;
    const manualFields = [];
    let botTraps = job?.bot_traps || [];

    if (ansResp.ok && ansResp.data) {
      if (Array.isArray(ansResp.data.bot_traps)) {
        botTraps = ansResp.data.bot_traps;
      }
      for (const item of ansResp.data.answers || []) {
        const meta = elById.get(item.id);
        if (!meta) continue;
        const ans = (item.answer || '').trim();
        if (item.confidence === 'manual_needed' || !ans) {
          manualFields.push(meta.label);
          highlightManual(meta.el || meta.radios?.[0], meta.label);
          continue;
        }
        if (meta.kind === 'input' || meta.kind === 'textarea') {
          let valToSet = ans;
          if (meta.inpType === 'number') {
            valToSet = ans.split('-')[0].replace(/[^0-9.]/g, '');
            if (!valToSet) { manualFields.push(meta.label); highlightManual(meta.el, meta.label); continue; }
          }
          if (meta.inpType === 'date' && !/^\d{4}-\d{2}-\d{2}$/.test(valToSet)) {
            manualFields.push(meta.label); highlightManual(meta.el, meta.label); continue;
          }
          setNativeValue(meta.el, valToSet);
          filledCount++;
        } else if (meta.kind === 'select') {
          const opts = Array.from(meta.el.options);
          const ansLow = ans.toLowerCase();
          const match = opts.find((o) => o.text.trim().toLowerCase() === ansLow)
            || opts.find((o) => {
              const t = o.text.trim().toLowerCase();
              return t && (t.includes(ansLow) || ansLow.includes(t));
            });
          if (match) {
            meta.el.value = match.value;
            meta.el.dispatchEvent(new Event('change', { bubbles: true }));
            filledCount++;
          } else {
            manualFields.push(meta.label);
            highlightManual(meta.el, meta.label);
          }
        } else if (meta.kind === 'radio_group') {
          const ansLow = ans.toLowerCase();
          let targetIdx = meta.opts.findIndex((o) => o.toLowerCase() === ansLow);
          if (targetIdx < 0) targetIdx = meta.opts.findIndex((o) => o.toLowerCase().includes(ansLow) || ansLow.includes(o.toLowerCase()));
          if (targetIdx >= 0) {
            const targetRadio = meta.radios[targetIdx];
            (targetRadio.closest('label') || targetRadio).click();
            filledCount++;
          }
        } else if (meta.kind === 'checkbox') {
          const ansLow = ans.toLowerCase();
          if (['yes', 'true', 'i agree', 'i acknowledge', 'i consent', 'accept', 'agree'].includes(ansLow)) {
            meta.el.click();
            filledCount++;
          }
        }
      }
    }

    // 5. Handle React-Select / Custom Comboboxes & Custom Button Radio Groups
    const comboControls = Array.from(document.querySelectorAll(
      'div[role="combobox"], button[role="combobox"], button[aria-haspopup="listbox"], div[aria-haspopup="listbox"], input[role="combobox"]'
    )).filter((el) => isVisible(el) && !el.disabled);
    const seenContainers = new Set();

    for (const el of comboControls.slice(0, 35)) {
      try {
        const container = el.closest('.select__control, [data-testid="field"], .application-question, [class*="select-container"]') || el;
        if (seenContainers.has(container)) continue;
        seenContainers.add(container);

        const existingTxt = (
          container.querySelector?.('.select__single-value, [class*="singleValue"]')?.innerText ||
          el.innerText || ''
        ).trim().toLowerCase();
        if (existingTxt && !isPlaceholderOnly(existingTxt)) continue;

        const rawLabel = extractLabel(el);
        let label = rawLabel.replace(/\*/g, '').trim();
        const sig = `${el.id || ''} ${el.name || ''}`.toLowerCase();
        if (sig.includes('race')) label = 'Race';
        else if (sig.includes('gender')) label = 'Gender';
        else if (sig.includes('veteran')) label = 'Veteran status';
        else if (sig.includes('disability')) label = 'Disability status';
        if (!label || label.length < 2) continue;

        el.click();
        await sleep(250);
        const ctrlId = el.getAttribute('aria-controls') || el.getAttribute('aria-owns') || '';
        const menuEl = (ctrlId && document.getElementById(ctrlId)) ||
          document.querySelector('[role="listbox"], .select__menu, ul[data-testid="menuList"]');
        const optEls = menuEl
          ? Array.from(menuEl.querySelectorAll('[role="option"], li, div[data-testid="menuListLabel"], .select__option')).filter(isVisible)
          : [];
        const optTexts = optEls.map((o) => (o.innerText || '').trim()).filter(Boolean);

        const oneResp = await sendBg({
          type: 'ANSWER_FIELDS',
          payload: {
            job_id: job?.id || null,
            url: window.location.href,
            fields: [{ id: 'cb', label, options: optTexts.length ? optTexts : null, field_type: 'combobox', required: rawLabel.includes('*') }],
          },
        });
        const ansItem = oneResp.ok ? oneResp.data?.answers?.[0] : null;
        const ans = (ansItem?.answer || '').trim();
        if (!ans || ansItem?.confidence === 'manual_needed') {
          el.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
          el.blur();
          manualFields.push(label);
          highlightManual(el, label);
          continue;
        }
        const ansLow = ans.toLowerCase();
        const matchOpt = optEls.find((o) => (o.innerText || '').trim().toLowerCase() === ansLow)
          || optEls.find((o) => {
            const t = (o.innerText || '').trim().toLowerCase();
            return t && (t.includes(ansLow) || ansLow.includes(t));
          });
        if (matchOpt) {
          matchOpt.click();
          filledCount++;
          await sleep(180);
        } else {
          el.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
          el.blur();
          manualFields.push(label);
          highlightManual(el, label);
        }
      } catch (_) {}
    }

    // 6. Cover letter textarea fallback if still empty
    if (job?.cover_letter_text) {
      const clTa = document.querySelector('textarea[id*="cover" i], textarea[name*="cover" i], textarea[placeholder*="cover" i]');
      if (clTa && isVisible(clTa) && !(clTa.value || '').trim()) {
        setNativeValue(clTa, job.cover_letter_text);
        filledCount++;
      }
    }

    // 7. Attach tailored Resume & Cover Letter PDFs
    const filesAttached = await attachFiles(job);
    filledCount += filesAttached;

    // Clear focus so user can immediately click CAPTCHAs / Submit
    if (document.activeElement && document.activeElement.blur) {
      document.activeElement.blur();
    }

    return { filledCount, manualFields, botTraps };
  }

  function renderHud(ctxData, fillResult) {
    const existing = document.getElementById('jobpulse-native-hud');
    if (existing) existing.remove();

    const job = ctxData.job;
    const queue = ctxData.queue || { is_speed_run: false, index: 0, total: 0 };
    const traps = fillResult.botTraps || job?.bot_traps || [];

    const container = document.createElement('div');
    container.id = 'jobpulse-native-hud';
    container.dataset.dock = 'bottom';
    container.style.cssText = `
      position: fixed;
      bottom: 12px;
      left: 50%;
      transform: translateX(-50%);
      z-index: 9999;
      background: rgba(15, 23, 42, 0.96);
      color: #f8fafc;
      border: 1.5px solid #10b981;
      border-radius: 12px;
      box-shadow: 0 10px 30px rgba(0, 0, 0, 0.55);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      padding: 8px 14px;
      display: flex;
      flex-direction: column;
      gap: 8px;
      max-width: 96vw;
      box-sizing: border-box;
      backdrop-filter: blur(8px);
    `;

    // Bot Trap Warning Strip
    if (traps.length > 0) {
      const primary = traps[0];
      const isHoneypot = primary.type === 'ai_honeypot';
      const trapDiv = document.createElement('div');
      trapDiv.id = 'jobpulse-native-trap-banner';
      trapDiv.style.cssText = `
        background: ${isHoneypot ? 'rgba(153, 27, 27, 0.94)' : 'rgba(146, 64, 14, 0.95)'};
        border: 1px solid ${isHoneypot ? '#f87171' : '#fbbf24'};
        border-radius: 8px;
        padding: 7px 12px;
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        justify-content: space-between;
        gap: 10px;
        font-size: 12px;
        color: #fef3c7;
      `;
      const left = document.createElement('div');
      left.style.cssText = 'display: flex; flex-direction: column; gap: 2px; max-width: 700px;';
      left.innerHTML = `
        <div style="font-weight:800;color:#fde68a;">${isHoneypot ? '🚫 AI HONEYPOT TRAP — DO NOT FOLLOW' : `⚠️ BOT TRAP (${traps.length}) — ACTION REQUIRED`}</div>
        <div style="font-weight:600;color:#fff;"></div>
        <div style="font-size:11px;color:#fde68a;font-style:italic;opacity:0.9;"></div>
      `;
      left.children[1].textContent = primary.action_required || '';
      left.children[2].textContent = primary.excerpt ? `"${primary.excerpt.slice(0, 200)}"` : '';
      trapDiv.appendChild(left);

      if (primary.trigger_phrase && !isHoneypot) {
        const copyPhrase = document.createElement('button');
        copyPhrase.type = 'button';
        copyPhrase.style.cssText = 'background:#f59e0b;color:#0f172a;border:none;border-radius:6px;padding:5px 10px;font-size:11px;font-weight:800;cursor:pointer;white-space:nowrap;';
        copyPhrase.textContent = `📋 Copy "${primary.trigger_phrase}"`;
        copyPhrase.onclick = () => {
          navigator.clipboard.writeText(primary.trigger_phrase).catch(() => {});
          copyPhrase.textContent = '✓ Copied!';
          setTimeout(() => { copyPhrase.textContent = `📋 Copy "${primary.trigger_phrase}"`; }, 2000);
        };
        trapDiv.appendChild(copyPhrase);
      }
      container.appendChild(trapDiv);
    }

    const row = document.createElement('div');
    row.style.cssText = 'display:flex;flex-wrap:wrap;align-items:center;gap:8px;font-size:12px;';

    const badge = document.createElement('span');
    badge.style.cssText = 'background:#059669;color:#fff;padding:3px 8px;border-radius:6px;font-weight:700;font-size:11px;white-space:nowrap;';
    badge.textContent = queue.is_speed_run
      ? `⚡ NATIVE SPEED-RUN [${queue.index + 1}/${queue.total}]`
      : '⚡ JOBPULSE NATIVE';
    row.appendChild(badge);

    const status = document.createElement('span');
    status.id = 'jobpulse-native-status';
    status.style.cssText = 'color:#cbd5e1;font-size:11.5px;max-width:340px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;';
    const manualCount = (fillResult.manualFields || []).length;
    status.textContent = manualCount > 0
      ? `Filled ${fillResult.filledCount} · ${manualCount} box(es) in amber need review · CAPTCHAs work natively`
      : `Filled ${fillResult.filledCount} fields · Review, complete any CAPTCHA & Submit`;
    status.title = status.textContent;
    row.appendChild(status);

    const actions = document.createElement('div');
    actions.style.cssText = 'display:flex;flex-wrap:wrap;align-items:center;gap:6px;margin-left:auto;';

    const mkBtn = (txt, css, onClick) => {
      const b = document.createElement('button');
      b.type = 'button';
      b.textContent = txt;
      b.style.cssText = css + ' cursor:pointer;white-space:nowrap;font-family:inherit;';
      b.onclick = onClick;
      return b;
    };

    if (job?.id) {
      const appliedBtn = mkBtn(
        queue.is_speed_run ? '✓ Mark Applied & Next' : '✓ Mark Applied',
        'background:#10b981;color:#fff;border:none;border-radius:7px;padding:6px 12px;font-size:11.5px;font-weight:700;',
        async () => {
          appliedBtn.disabled = true;
          appliedBtn.textContent = 'Saving...';
          const resp = await sendBg({
            type: 'QUEUE_ACTION',
            payload: { action: 'mark_applied_next', job_id: job.id },
          });
          if (resp.ok && resp.data?.next_url) {
            window.location.href = resp.data.next_url;
          } else {
            appliedBtn.textContent = '✓ Marked Applied!';
            status.textContent = 'Saved as Applied in JobPulse!';
          }
        }
      );
      actions.appendChild(appliedBtn);
    }

    const refillBtn = mkBtn(
      '↻ Re-Fill',
      'background:#1e293b;color:#38bdf8;border:1px solid #0284c7;border-radius:7px;padding:6px 10px;font-size:11.5px;font-weight:600;',
      async () => {
        refillBtn.textContent = 'Filling...';
        const res = await runAutoFill(ctxData);
        renderHud(ctxData, res);
      }
    );
    actions.appendChild(refillBtn);

    if (job?.cover_letter_text) {
      const clBtn = mkBtn(
        '📋 Cover Letter',
        'background:#1e293b;color:#fbbf24;border:1px solid #d97706;border-radius:7px;padding:6px 9px;font-size:11.5px;font-weight:500;',
        () => {
          navigator.clipboard.writeText(job.cover_letter_text).catch(() => {});
          clBtn.textContent = '✓ Copied!';
          setTimeout(() => { clBtn.textContent = '📋 Cover Letter'; }, 2000);
        }
      );
      actions.appendChild(clBtn);
    }

    if (queue.is_speed_run) {
      const skipBtn = mkBtn(
        '⏭ Skip',
        'background:#334155;color:#e2e8f0;border:1px solid #475569;border-radius:7px;padding:6px 9px;font-size:11.5px;',
        async () => {
          const resp = await sendBg({
            type: 'QUEUE_ACTION',
            payload: { action: 'skip', job_id: job?.id },
          });
          if (resp.ok && resp.data?.next_url) {
            window.location.href = resp.data.next_url;
          } else {
            container.remove();
          }
        }
      );
      actions.appendChild(skipBtn);
    }

    let minimized = false;
    const minBtn = mkBtn(
      '—',
      'background:#1e293b;color:#94a3b8;border:1px solid #334155;border-radius:7px;padding:6px 8px;font-size:11.5px;',
      () => {
        minimized = !minimized;
        const trap = document.getElementById('jobpulse-native-trap-banner');
        if (minimized) {
          badge.style.display = 'none';
          status.style.display = 'none';
          if (trap) trap.style.display = 'none';
          Array.from(actions.children).forEach((c) => { if (c !== minBtn) c.style.display = 'none'; });
          minBtn.textContent = '⚡ JobPulse';
          container.style.left = 'auto';
          container.style.right = '14px';
          container.style.transform = 'none';
        } else {
          badge.style.display = '';
          status.style.display = '';
          if (trap) trap.style.display = 'flex';
          Array.from(actions.children).forEach((c) => { c.style.display = ''; });
          minBtn.textContent = '—';
          container.style.right = 'auto';
          container.style.left = '50%';
          container.style.transform = 'translateX(-50%)';
        }
      }
    );
    actions.appendChild(minBtn);

    const closeBtn = mkBtn(
      '✕',
      'background:transparent;color:#94a3b8;border:1px solid #334155;border-radius:7px;padding:6px 8px;font-size:11.5px;',
      () => container.remove()
    );
    actions.appendChild(closeBtn);

    row.appendChild(actions);
    container.appendChild(row);
    document.body.appendChild(container);
  }

  async function initOnPage(forceRun = false) {
    const resp = await sendBg({ type: 'GET_ACTIVE_AUTOFILL', url: window.location.href });
    if (!resp.ok || !resp.data) return;
    if (!forceRun && !resp.data.matched) return;
    await sleep(900);
    const fillResult = await runAutoFill(resp.data);
    renderHud(resp.data, fillResult);
  }

  // Allow manual trigger from Extension popup on ANY page
  chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
    if (msg.type === 'TRIGGER_AUTOFILL') {
      initOnPage(true).then(() => sendResponse({ ok: true })).catch((e) => sendResponse({ ok: false, error: String(e) }));
      return true;
    }
  });

  // Auto-run when tab matches a staged JobPulse application
  initOnPage(false);
})();
