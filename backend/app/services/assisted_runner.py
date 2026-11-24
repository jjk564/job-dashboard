"""
Interactive Desktop Browser Runner for JobPulse 'Open with Auto-Fill' and 'Speed-Run Queue'.

Invoked in the user's interactive Windows desktop session so that Chromium opens visibly
in the foreground with a persistent user profile, pre-fills the ATS form, uploads tailored
PDF documents, answers screening questions, detects live Bot Traps, monitors for Greenhouse
2FA codes, and presents a non-intrusive bottom-docked JobPulse HUD (with zero cross-frame
CDP bindings or prototype tampering that could interfere with CAPTCHA widgets).
"""
import json
import os
import subprocess
import sys
import time
import traceback
import urllib.request
import webbrowser
from pathlib import Path
from typing import Any, Dict, List, Optional

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

LOG_PATH = BACKEND_DIR / "generated_packets" / "assisted_runner.log"
BROWSER_DATA_DIR = BACKEND_DIR / "browser_data" / "chrome_user_profile"
API_BASE = "http://127.0.0.1:8000"


def log(msg: str) -> None:
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except Exception:
        pass


def update_job_status_applied(job_id: int) -> None:
    """Updates job status to APPLIED via backend REST API, with SQLite fallback."""
    if not job_id:
        return
    log(f"Updating job {job_id} to APPLIED...")
    try:
        req = urllib.request.Request(
            f"{API_BASE}/api/jobs/{job_id}",
            data=json.dumps({
                "status": "APPLIED",
                "autopilot_status": "auto_applied",
                "autopilot_reason": "Applied via Autopilot Speed-Run",
            }).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="PATCH",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            log(f"PATCH /api/jobs/{job_id} returned HTTP {resp.status}")
            return
    except Exception as api_err:
        log(f"API PATCH failed ({api_err}); using direct SQLite update.")

    try:
        import sqlite3
        db_file = BACKEND_DIR / "jobs.db"
        if db_file.exists():
            conn = sqlite3.connect(str(db_file), timeout=15)
            c = conn.cursor()
            c.execute(
                "UPDATE jobs SET status = 'APPLIED', autopilot_status = 'auto_applied', autopilot_reason = 'Applied via Autopilot Speed-Run', applied_at = datetime('now'), updated_at = datetime('now') WHERE id = ?",
                (job_id,),
            )
            c.execute(
                "INSERT INTO application_activities (job_id, activity_type, title, details, created_at) "
                "VALUES (?, 'status_change', 'Moved to APPLIED', 'Marked applied via Autopilot Speed-Run', datetime('now'))",
                (job_id,),
            )
            conn.commit()
            conn.close()
            log(f"Direct SQLite update succeeded for job {job_id}.")
    except Exception as dbe:
        log(f"Direct SQLite update error: {dbe}")


def persist_live_bot_traps(job_id: Optional[int], bot_traps: List[Dict[str, Any]]) -> None:
    """Saves any newly detected live-page bot traps back to the Job record."""
    if not job_id or not bot_traps:
        return
    try:
        req = urllib.request.Request(
            f"{API_BASE}/api/jobs/{job_id}",
            data=json.dumps({"bot_traps": bot_traps}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="PATCH",
        )
        with urllib.request.urlopen(req, timeout=4):
            pass
    except Exception:
        pass


def stage_job_for_regular_browser(job_id: Optional[int], target_url: str) -> None:
    """Stages the active job for the native Chrome Extension before opening the regular browser."""
    if job_id:
        try:
            req = urllib.request.Request(
                f"{API_BASE}/api/assistant/stage-browser-queue",
                data=json.dumps({"job_ids": [job_id], "open_browser": False}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=4):
                log(f"Staged job {job_id} for native Chrome extension autofill.")
        except Exception as st_err:
            log(f"Note: could not stage job for Chrome extension: {st_err}")
    webbrowser.open(target_url)


# Bottom-docked, collapsible, non-intrusive HUD that communicates via a top-frame DOM attribute
# (zero CDP Runtime.addBinding / expose_function injected into cross-origin CAPTCHA iframes!)
HUD_INJECTION_SCRIPT = """
(config) => {
  try {
    const existing = document.getElementById('jobpulse-hud-overlay');
    if (existing) existing.remove();

    const container = document.createElement('div');
    container.id = 'jobpulse-hud-overlay';
    container.dataset.jobpulseAction = '';
    container.dataset.dock = 'bottom';
    container.style.cssText = `
      position: fixed;
      bottom: 12px;
      left: 50%;
      transform: translateX(-50%);
      z-index: 9999;
      background: rgba(15, 23, 42, 0.96);
      color: #f8fafc;
      border: 1.5px solid #3b82f6;
      border-radius: 12px;
      box-shadow: 0 10px 30px rgba(0, 0, 0, 0.55), 0 0 14px rgba(59, 130, 246, 0.25);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      padding: 8px 14px;
      display: flex;
      flex-direction: column;
      gap: 8px;
      user-select: none;
      max-width: 96vw;
      box-sizing: border-box;
      backdrop-filter: blur(8px);
    `;

    const dispatchAction = (payload) => {
      container.dataset.jobpulseAction = JSON.stringify({ ...payload, ts: Date.now() });
    };

    // Optional Bot Trap Warning Strip (impossible to miss!)
    const traps = Array.isArray(config.botTraps) ? config.botTraps : [];
    if (traps.length > 0) {
      const trapBanner = document.createElement('div');
      trapBanner.id = 'jobpulse-hud-trap-banner';
      const hasHoneypot = traps.some(t => t.type === 'ai_honeypot');
      trapBanner.style.cssText = `
        background: ${hasHoneypot ? 'rgba(153, 27, 27, 0.92)' : 'rgba(146, 64, 14, 0.94)'};
        border: 1px solid ${hasHoneypot ? '#f87171' : '#fbbf24'};
        border-radius: 8px;
        padding: 7px 12px;
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        justify-content: space-between;
        gap: 10px;
        font-size: 12px;
        color: #fef3c7;
        user-select: text;
      `;

      const primaryTrap = traps[0];
      const leftTrap = document.createElement('div');
      leftTrap.style.cssText = 'display: flex; flex-direction: column; gap: 2px; max-width: 720px;';

      const trapTitle = document.createElement('div');
      trapTitle.style.cssText = 'font-weight: 800; color: #fde68a; font-size: 12px;';
      trapTitle.innerText = primaryTrap.type === 'ai_honeypot'
        ? '🚫 AI HONEYPOT TRAP DETECTED — DO NOT FOLLOW:'
        : `⚠️ BOT TRAP (${traps.length}) — ACTION REQUIRED BEFORE SUBMITTING:`;

      const trapAction = document.createElement('div');
      trapAction.style.cssText = 'font-weight: 600; color: #ffffff; font-size: 12px;';
      trapAction.innerText = primaryTrap.action_required || 'Read the special instruction in the job description.';

      const trapExcerpt = document.createElement('div');
      trapExcerpt.style.cssText = 'font-size: 11px; color: #fde68a; opacity: 0.9; font-style: italic;';
      trapExcerpt.innerText = `"${(primaryTrap.excerpt || '').slice(0, 200)}"`;

      leftTrap.appendChild(trapTitle);
      leftTrap.appendChild(trapAction);
      if (primaryTrap.excerpt) leftTrap.appendChild(trapExcerpt);
      trapBanner.appendChild(leftTrap);

      if (primaryTrap.trigger_phrase && primaryTrap.type !== 'ai_honeypot') {
        const copyPhraseBtn = document.createElement('button');
        copyPhraseBtn.style.cssText = 'background: #f59e0b; color: #0f172a; border: none; border-radius: 6px; padding: 5px 10px; font-size: 11px; font-weight: 800; cursor: pointer; white-space: nowrap;';
        copyPhraseBtn.innerText = `📋 Copy "${primaryTrap.trigger_phrase}"`;
        copyPhraseBtn.onclick = () => {
          navigator.clipboard?.writeText(primaryTrap.trigger_phrase).catch(() => {});
          dispatchAction({ action: 'copy_text', text: primaryTrap.trigger_phrase, jobId: config.jobId });
          copyPhraseBtn.innerText = '✓ Copied!';
          setTimeout(() => { copyPhraseBtn.innerText = `📋 Copy "${primaryTrap.trigger_phrase}"`; }, 2000);
        };
        trapBanner.appendChild(copyPhraseBtn);
      }

      container.appendChild(trapBanner);
    }

    // Main Control Row
    const mainRow = document.createElement('div');
    mainRow.id = 'jobpulse-hud-main-row';
    mainRow.style.cssText = 'display: flex; flex-wrap: wrap; align-items: center; gap: 10px;';

    // Left Section: Badge & Job Title
    const left = document.createElement('div');
    left.style.cssText = 'display: flex; align-items: center; gap: 8px; font-size: 12px;';

    const badge = document.createElement('span');
    badge.style.cssText = 'background: #2563eb; color: white; padding: 3px 8px; border-radius: 6px; font-weight: 700; font-size: 11px; letter-spacing: 0.4px; white-space: nowrap;';
    badge.innerText = config.isSpeedRun ? `⚡ SPEED-RUN [${config.index + 1}/${config.total}]` : '⚡ AUTOPILOT';

    const title = document.createElement('span');
    title.style.cssText = 'font-weight: 700; color: #f1f5f9; max-width: 220px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; font-size: 12px;';
    title.innerText = config.company ? `${config.company} — ${config.title}` : config.title;
    title.title = title.innerText;

    left.appendChild(badge);
    left.appendChild(title);
    mainRow.appendChild(left);

    // Status Note
    const status = document.createElement('div');
    status.id = 'jobpulse-hud-status';
    status.style.cssText = 'font-size: 11.5px; color: #cbd5e1; border-left: 1px solid #334155; padding-left: 10px; max-width: 340px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;';
    status.innerText = config.statusText || 'Auto-filled. Review & submit:';
    status.title = status.innerText;
    mainRow.appendChild(status);

    // Action Buttons
    const right = document.createElement('div');
    right.style.cssText = 'display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin-left: auto;';

    const makeBtn = (id, text, styleCss, titleText, onClick) => {
      const b = document.createElement('button');
      b.id = id;
      b.type = 'button';
      b.style.cssText = styleCss + ' cursor: pointer; white-space: nowrap; font-family: inherit;';
      b.innerText = text;
      if (titleText) b.title = titleText;
      b.onclick = onClick;
      return b;
    };

    const applyBtn = makeBtn(
      'jobpulse-hud-apply-btn',
      config.isSpeedRun ? '✓ Mark Applied & Next' : '✓ Mark Applied',
      'background: #10b981; color: white; border: none; border-radius: 7px; padding: 6px 12px; font-size: 11.5px; font-weight: 700;',
      'Mark this job Applied and advance',
      () => {
        applyBtn.disabled = true;
        applyBtn.innerText = 'Advancing...';
        applyBtn.style.opacity = '0.7';
        dispatchAction({ action: 'apply_and_next', jobId: config.jobId });
      }
    );
    right.appendChild(applyBtn);

    const browserBtn = makeBtn(
      'jobpulse-hud-browser-btn',
      config.hasCaptcha ? '🌐 Finish in Regular Chrome (CAPTCHA)' : '🌐 Regular Chrome',
      config.hasCaptcha
        ? 'background: #0284c7; color: #ffffff; border: 1px solid #38bdf8; border-radius: 7px; padding: 6px 11px; font-size: 11.5px; font-weight: 700;'
        : 'background: #1e293b; color: #38bdf8; border: 1px solid #0284c7; border-radius: 7px; padding: 6px 10px; font-size: 11.5px; font-weight: 600;',
      'Opens in your regular Chrome browser (zero Playwright/CAPTCHA interference) and stages auto-fill for the JobPulse Chrome Extension',
      () => dispatchAction({ action: 'open_standard_browser', jobId: config.jobId })
    );
    right.appendChild(browserBtn);

    const folderBtn = makeBtn(
      'jobpulse-hud-folder-btn',
      '📂 Resume PDF',
      'background: #1e293b; color: #c4b5fd; border: 1px solid #7c3aed; border-radius: 7px; padding: 6px 9px; font-size: 11.5px; font-weight: 500;',
      'Reveal tailored Resume PDF in Windows Explorer',
      () => dispatchAction({ action: 'open_resume_folder', jobId: config.jobId })
    );
    right.appendChild(folderBtn);

    const copyBtn = makeBtn(
      'jobpulse-hud-copy-btn',
      '📋 Cover Letter',
      'background: #1e293b; color: #fbbf24; border: 1px solid #d97706; border-radius: 7px; padding: 6px 9px; font-size: 11.5px; font-weight: 500;',
      'Copy tailored Cover Letter to clipboard',
      () => {
        copyBtn.innerText = '✓ Copied!';
        setTimeout(() => { copyBtn.innerText = '📋 Cover Letter'; }, 2000);
        dispatchAction({ action: 'copy_cover_letter', jobId: config.jobId });
      }
    );
    right.appendChild(copyBtn);

    if (config.isSpeedRun) {
      const skipBtn = makeBtn(
        'jobpulse-hud-skip-btn',
        '⏭ Skip',
        'background: #334155; color: #e2e8f0; border: 1px solid #475569; border-radius: 7px; padding: 6px 10px; font-size: 11.5px; font-weight: 500;',
        'Skip to next job in queue',
        () => {
          skipBtn.disabled = true;
          skipBtn.innerText = 'Skipping...';
          dispatchAction({ action: 'skip', jobId: config.jobId });
        }
      );
      right.appendChild(skipBtn);
    }

    // Dock Top / Bottom Toggle (so HUD never covers CAPTCHAs or Submit buttons)
    const dockBtn = makeBtn(
      'jobpulse-hud-dock-btn',
      '⇅',
      'background: #1e293b; color: #94a3b8; border: 1px solid #334155; border-radius: 7px; padding: 6px 8px; font-size: 11.5px;',
      'Move HUD between bottom and top of screen',
      () => {
        if (container.dataset.dock === 'bottom') {
          container.dataset.dock = 'top';
          container.style.bottom = 'auto';
          container.style.top = '12px';
        } else {
          container.dataset.dock = 'bottom';
          container.style.top = 'auto';
          container.style.bottom = '12px';
        }
      }
    );
    right.appendChild(dockBtn);

    // Minimize / Expand Toggle
    let minimized = false;
    const minBtn = makeBtn(
      'jobpulse-hud-min-btn',
      '—',
      'background: #1e293b; color: #94a3b8; border: 1px solid #334155; border-radius: 7px; padding: 6px 8px; font-size: 11.5px;',
      'Minimize HUD out of the way',
      () => {
        minimized = !minimized;
        const trapEl = document.getElementById('jobpulse-hud-trap-banner');
        if (minimized) {
          left.style.display = 'none';
          status.style.display = 'none';
          if (trapEl) trapEl.style.display = 'none';
          Array.from(right.children).forEach(ch => {
            if (ch !== minBtn) ch.style.display = 'none';
          });
          minBtn.innerText = '⚡ JobPulse HUD';
          container.style.left = 'auto';
          container.style.right = '14px';
          container.style.transform = 'none';
          container.style.padding = '5px 10px';
        } else {
          left.style.display = 'flex';
          status.style.display = 'block';
          if (trapEl) trapEl.style.display = 'flex';
          Array.from(right.children).forEach(ch => { ch.style.display = ''; });
          minBtn.innerText = '—';
          container.style.right = 'auto';
          container.style.left = '50%';
          container.style.transform = 'translateX(-50%)';
          container.style.padding = '8px 14px';
        }
      }
    );
    right.appendChild(minBtn);

    const exitBtn = makeBtn(
      'jobpulse-hud-exit-btn',
      '✕',
      'background: transparent; color: #94a3b8; border: 1px solid #334155; border-radius: 7px; padding: 6px 9px; font-size: 11.5px;',
      config.isSpeedRun ? 'Exit Speed-Run' : 'Close HUD session',
      () => dispatchAction({ action: 'exit', jobId: config.jobId })
    );
    right.appendChild(exitBtn);

    mainRow.appendChild(right);
    container.appendChild(mainRow);
    document.body.appendChild(container);
  } catch (err) {
    console.error('JobPulse HUD injection error:', err);
  }
}
"""

HUD_DONE_SCRIPT = """
(msg) => {
  try {
    const status = document.getElementById('jobpulse-hud-status');
    if (status) {
      status.innerText = msg;
      status.style.color = '#34d399';
      status.style.fontWeight = 'bold';
    }
  } catch (e) {}
}
"""

READ_AND_CLEAR_HUD_ACTION_SCRIPT = """
() => {
  try {
    const el = document.getElementById('jobpulse-hud-overlay');
    if (!el || !el.dataset.jobpulseAction) return null;
    const raw = el.dataset.jobpulseAction;
    el.dataset.jobpulseAction = '';
    return JSON.parse(raw);
  } catch (e) {
    return null;
  }
}
"""


def _copy_text_to_windows_clipboard(text: str) -> None:
    if not text:
        return
    try:
        import pyperclip
        pyperclip.copy(text)
        return
    except Exception:
        pass
    try:
        proc = subprocess.Popen(["clip"], stdin=subprocess.PIPE)
        proc.communicate(input=text.encode("utf-16le"))
    except Exception:
        pass


def run_interactive_browser(payload_path: str) -> None:
    log(f"Starting interactive browser for payload: {payload_path}")
    path_obj = Path(payload_path)
    if not path_obj.exists():
        log(f"Error: payload file does not exist: {payload_path}")
        return

    try:
        data = json.loads(path_obj.read_text(encoding="utf-8"))
    except Exception as e:
        log(f"Error reading payload JSON: {e}")
        return

    raw_jobs = data.get("jobs")
    if raw_jobs and isinstance(raw_jobs, list) and len(raw_jobs) > 0:
        queue = raw_jobs
        is_speed_run = True
        log(f"Speed-Run Queue mode activated with {len(queue)} jobs.")
    else:
        queue = [data]
        is_speed_run = False
        log("Single-job mode activated.")

    imap_cfg = data.get("imap_config") or {}

    from playwright.sync_api import sync_playwright
    from app.services.browser_assistant import (
        _dismiss_cookie_banners,
        _fill_form_sync,
        _fill_greenhouse_security_code_sync,
    )
    from app.services.email_code_reader import poll_for_security_code_sync

    BROWSER_DATA_DIR.mkdir(parents=True, exist_ok=True)

    try:
        with sync_playwright() as p:
            log("Launching persistent desktop Chrome context...")
            context = None
            for ch in ["chrome", "msedge", None]:
                try:
                    kwargs = {
                        "user_data_dir": str(BROWSER_DATA_DIR),
                        "headless": False,
                        "args": ["--start-maximized"],
                        "ignore_default_args": ["--enable-automation", "--no-sandbox"],
                        "no_viewport": True,
                    }
                    if ch:
                        kwargs["channel"] = ch
                    context = p.chromium.launch_persistent_context(**kwargs)
                    log(f"Launched persistent context with channel: {ch}")
                    break
                except Exception as ch_err:
                    log(f"Channel {ch} persistent launch failed: {ch_err}")

            if not context:
                aux_profile_dir = BACKEND_DIR / "browser_data" / "chrome_user_profile_aux"
                aux_profile_dir.mkdir(parents=True, exist_ok=True)
                for ch in ["chrome", "msedge", None]:
                    try:
                        kwargs = {
                            "user_data_dir": str(aux_profile_dir),
                            "headless": False,
                            "args": ["--start-maximized"],
                            "ignore_default_args": ["--enable-automation", "--no-sandbox"],
                            "no_viewport": True,
                        }
                        if ch:
                            kwargs["channel"] = ch
                        context = p.chromium.launch_persistent_context(**kwargs)
                        log(f"Launched auxiliary persistent context with channel: {ch}")
                        break
                    except Exception:
                        pass

            if not context:
                log("Falling back to ephemeral browser context...")
                browser = p.chromium.launch(
                    headless=False,
                    args=["--start-maximized"],
                    ignore_default_args=["--enable-automation", "--no-sandbox"],
                )
                context = browser.new_context(no_viewport=True)

            # Note: Do NOT inject prototype-deleting init scripts or context.expose_function
            # CDP bindings into all frames, as doing so corrupts cross-origin CAPTCHA iframes!
            page = context.pages[0] if context.pages else context.new_page()

            total_jobs = len(queue)
            for idx, item in enumerate(queue):
                job_url = item.get("job_url")
                if not job_url:
                    log(f"Skipping queue item {idx + 1}: empty job_url")
                    continue

                job_id = item.get("job_id") or (item.get("job_data") or {}).get("id")
                job_data = item.get("job_data") or {"url": job_url}
                company = job_data.get("company") or "Company"
                title = job_data.get("title") or "Position"
                profile_data = item.get("profile_data") or {}
                candidate_skills = item.get("candidate_skills") or []
                app_kit = item.get("app_kit")
                files = item.get("files")

                log(f"\n--- Queue [{idx + 1}/{total_jobs}]: {company} - {title} ---")
                log(f"Target URL: {job_url}")

                try:
                    log(f"Navigating to {job_url}...")
                    page.goto(job_url, timeout=35000, wait_until="domcontentloaded")
                    page.set_default_timeout(3000)
                    time.sleep(2.0)
                except Exception as nav_e:
                    log(f"Navigation warning: {nav_e}")

                target = page
                fill_res: Dict[str, Any] = {}
                filled_count = 0
                try:
                    log("Filling form fields & uploading documents...")
                    fill_res = _fill_form_sync(
                        page=page,
                        job_data=job_data,
                        profile_data=profile_data,
                        candidate_skills=candidate_skills,
                        app_kit=app_kit,
                        files=files,
                    )
                    target = fill_res.get("target") or page
                    filled_count = fill_res.get("filled_count", 0)
                    log(
                        f"Form filled: {filled_count} fields filled "
                        f"(resume_uploaded={fill_res.get('resume_uploaded')}, "
                        f"cover_letter_uploaded={fill_res.get('cover_letter_uploaded')}, "
                        f"has_captcha={fill_res.get('has_captcha')}, "
                        f"manual_review={len(fill_res.get('manual_review_fields') or [])}, "
                        f"bot_traps={len(fill_res.get('bot_traps') or [])})."
                    )
                except Exception as fill_e:
                    log(f"Form filling error: {fill_e}\n{traceback.format_exc()}")

                bot_traps = fill_res.get("bot_traps") or job_data.get("bot_traps") or []
                if bot_traps and job_id:
                    persist_live_bot_traps(job_id, bot_traps)

                # Dismiss any cookie banner and ensure no focus/dropdown blocks user clicks
                try:
                    _dismiss_cookie_banners(page)
                    page.keyboard.press("Escape")
                except Exception:
                    pass

                # Inject clean bottom-docked HUD
                try:
                    unanswered = fill_res.get("unanswered_required") or []
                    has_captcha = bool(fill_res.get("has_captcha"))
                    if fill_res.get("is_closed_posting"):
                        status_text = "⚠️ Posting closed or redirected. Click Skip."
                    elif has_captcha and unanswered:
                        status_text = f"Filled {filled_count} · {len(unanswered)} field(s) in amber · 🛡️ CAPTCHA present (use Regular Chrome if it loops)"
                    elif has_captcha:
                        status_text = f"Filled {filled_count} fields · 🛡️ CAPTCHA detected (click Regular Chrome if it loops)"
                    elif unanswered:
                        status_text = f"Filled {filled_count} · {len(unanswered)} required box(es) outlined in amber need review"
                    elif filled_count > 0:
                        status_text = f"Auto-filled {filled_count} fields. Review & submit:"
                    else:
                        status_text = "Page loaded. Review form & submit:"

                    page.evaluate(
                        HUD_INJECTION_SCRIPT,
                        {
                            "isSpeedRun": is_speed_run,
                            "index": idx,
                            "total": total_jobs,
                            "company": company,
                            "title": title,
                            "jobId": job_id,
                            "statusText": status_text,
                            "hasCaptcha": has_captcha,
                            "botTraps": bot_traps,
                            "unansweredRequired": unanswered,
                        },
                    )
                    log("Injected bottom-docked JobPulse HUD overlay.")
                except Exception as hud_e:
                    log(f"HUD injection warning: {hud_e}")

                # Watch loop for this job (top-frame only, zero iframe polling on non-Greenhouse pages)
                start_job_ts = time.time()
                code_filled = False
                job_completed = False
                notified_gate = False
                is_greenhouse_page = "greenhouse" in (job_url or "").lower() or "gh_jid=" in (job_url or "").lower()

                while time.time() - start_job_ts < 1800:
                    try:
                        if page.is_closed():
                            log("Browser page was closed by user.")
                            return

                        # Read and consume any user HUD action from top-frame DOM attribute
                        hud_evt = page.evaluate(READ_AND_CLEAR_HUD_ACTION_SCRIPT)
                        if isinstance(hud_evt, dict):
                            act = hud_evt.get("action")
                            log(f"HUD event received: {hud_evt}")
                            if act == "open_standard_browser":
                                target_url = getattr(page, "url", None) or job_url
                                stage_job_for_regular_browser(job_id, target_url)
                            elif act == "open_resume_folder":
                                cur_files = files or {}
                                res_path = cur_files.get("resume_pdf") or cur_files.get("legacy_resume_pdf")
                                if res_path and os.path.exists(res_path):
                                    abs_res = os.path.abspath(res_path)
                                    subprocess.Popen(f'explorer.exe /select,"{abs_res}"')
                            elif act == "copy_cover_letter":
                                cur_files = files or {}
                                cl_path = cur_files.get("cover_letter_txt") or cur_files.get("cover_letter_md")
                                if cl_path and os.path.exists(cl_path):
                                    _copy_text_to_windows_clipboard(Path(cl_path).read_text(encoding="utf-8").strip())
                            elif act == "copy_text":
                                _copy_text_to_windows_clipboard(str(hud_evt.get("text") or ""))
                            elif act in ("apply_and_next", "mark_applied"):
                                update_job_status_applied(job_id)
                                job_completed = True
                                break
                            elif act == "skip":
                                log(f"Job {job_id} skipped by user.")
                                job_completed = True
                                break
                            elif act == "exit":
                                log("User requested exit from queue.")
                                return

                        # Detect submission via URL change
                        curr_url = (page.url or "").lower()
                        if any(sig in curr_url for sig in ["/confirmation", "/thank_you", "/thank-you", "/applied", "/submitted"]):
                            log("Detected confirmation URL change!")
                            try:
                                page.evaluate(HUD_DONE_SCRIPT, "Application submitted! Advancing in 3s...")
                            except Exception:
                                pass
                            time.sleep(3.0)
                            update_job_status_applied(job_id)
                            job_completed = True
                            break

                        if "weworkremotely.com/job-seekers" in curr_url or "register?alert=" in curr_url:
                            if not notified_gate:
                                notified_gate = True
                                try:
                                    page.evaluate(
                                        HUD_DONE_SCRIPT,
                                        "⚠️ Third-party account gate detected. Log in, or click [⏭ Skip]."
                                    )
                                except Exception:
                                    pass

                        # Check Greenhouse 2FA security code box ONLY on Greenhouse pages
                        if not code_filled and (is_greenhouse_page or "greenhouse" in curr_url):
                            try:
                                sec_box = target.locator("#security-input-0:visible")
                                if sec_box.count() > 0 and not (sec_box.input_value() or "").strip():
                                    log("Detected Greenhouse security code box! Polling Gmail via IMAP...")
                                    code = poll_for_security_code_sync(
                                        imap_server=imap_cfg.get("imap_server") or "imap.gmail.com",
                                        imap_email=imap_cfg.get("imap_email"),
                                        imap_password=imap_cfg.get("imap_password"),
                                        min_timestamp=start_job_ts - 60,
                                        max_wait_seconds=15,
                                    )
                                    if code:
                                        log(f"Retrieved security code {code}! Auto-filling code inputs...")
                                        if _fill_greenhouse_security_code_sync(target, code):
                                            log("Successfully filled security code!")
                                            code_filled = True
                            except Exception:
                                pass
                    except Exception as loop_e:
                        log(f"Watch loop warning: {loop_e}")

                    time.sleep(1.0)

                if not job_completed and not is_speed_run:
                    break

            log("Queue execution complete!")
            if is_speed_run:
                try:
                    if not page.is_closed():
                        page.evaluate(
                            HUD_DONE_SCRIPT,
                            f"🎉 Speed-Run complete! Processed {total_jobs} application(s).",
                        )
                        time.sleep(4.0)
                except Exception:
                    pass

            try:
                context.close()
            except Exception:
                pass
            log("Interactive runner session finished cleanly.")

    except Exception as e:
        log(f"Fatal interactive browser runner error: {e}\n{traceback.format_exc()}")


if __name__ == "__main__":
    default_payload = str(BACKEND_DIR / "generated_packets" / "assisted_launch.json")
    target_payload = sys.argv[1] if len(sys.argv) > 1 else default_payload
    run_interactive_browser(target_payload)
