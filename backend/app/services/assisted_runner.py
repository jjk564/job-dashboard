"""
Interactive Desktop Browser Runner for JobPulse 'Open with Auto-Fill' and 'Speed-Run Queue'.

Invoked in the user's interactive Windows desktop session so that Chromium
opens visibly in the foreground with a persistent user profile (preserving cookies,
session state, and Cloudflare clearance), pre-fills the ATS form, uploads tailored PDF
documents, answers screening questions, monitors for Greenhouse security codes, and
presents a floating JobPulse HUD for rapid review, application marking, and queue progression.
"""
import json
import logging
import os
import sys
import time
import traceback
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

LOG_PATH = BACKEND_DIR / "generated_packets" / "assisted_runner.log"
BROWSER_DATA_DIR = BACKEND_DIR / "browser_data" / "chrome_user_profile"


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
    # 1. Attempt API patch
    try:
        import urllib.request
        req = urllib.request.Request(
            f"http://127.0.0.1:8000/api/jobs/{job_id}",
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

    # 2. SQLite direct fallback
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


HUD_INJECTION_SCRIPT = """
(config) => {
  try {
    const existing = document.getElementById('jobpulse-hud-overlay');
    if (existing) existing.remove();

    const container = document.createElement('div');
    container.id = 'jobpulse-hud-overlay';
    container.style.cssText = `
      position: fixed;
      top: 14px;
      left: 50%;
      transform: translateX(-50%);
      z-index: 2147483647;
      background: #0f172a;
      color: #f8fafc;
      border: 1.5px solid #3b82f6;
      border-radius: 12px;
      box-shadow: 0 10px 30px rgba(0, 0, 0, 0.6), 0 0 15px rgba(59, 130, 246, 0.25);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      padding: 8px 18px;
      display: flex;
      align-items: center;
      gap: 16px;
      user-select: none;
      max-width: 95vw;
      box-sizing: border-box;
    `;

    // Left Section: Pill & Job Info
    const left = document.createElement('div');
    left.style.cssText = 'display: flex; align-items: center; gap: 10px; font-size: 13px;';

    const badge = document.createElement('span');
    badge.style.cssText = 'background: #2563eb; color: white; padding: 3px 9px; border-radius: 6px; font-weight: 700; font-size: 11px; letter-spacing: 0.5px; white-space: nowrap;';
    badge.innerText = config.isSpeedRun ? `⚡ SPEED-RUN [${config.index + 1}/${config.total}]` : '⚡ AUTOPILOT';

    const info = document.createElement('div');
    info.style.cssText = 'display: flex; flex-direction: column; max-width: 280px;';

    const title = document.createElement('span');
    title.style.cssText = 'font-weight: 700; color: #f1f5f9; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; font-size: 13px;';
    title.innerText = config.company ? `${config.company} — ${config.title}` : config.title;
    title.title = title.innerText;

    info.appendChild(title);
    left.appendChild(badge);
    left.appendChild(info);
    container.appendChild(left);

    // Center Section: Status Note
    const status = document.createElement('div');
    status.id = 'jobpulse-hud-status';
    status.style.cssText = 'font-size: 12px; color: #94a3b8; border-left: 1px solid #334155; padding-left: 14px; white-space: nowrap;';
    status.innerText = config.statusText || 'Auto-filled. Review & submit, or advance:';
    container.appendChild(status);

    // Right Section: Action Buttons
    const right = document.createElement('div');
    right.style.cssText = 'display: flex; align-items: center; gap: 8px;';

    // Apply Button
    const applyBtn = document.createElement('button');
    applyBtn.id = 'jobpulse-hud-apply-btn';
    applyBtn.style.cssText = 'background: #10b981; color: white; border: none; border-radius: 7px; padding: 7px 15px; font-size: 12px; font-weight: 700; cursor: pointer; transition: background 0.15s; white-space: nowrap; display: flex; align-items: center; gap: 4px;';
    applyBtn.innerText = config.isSpeedRun ? '✓ Mark Applied & Next' : '✓ Mark Applied';
    applyBtn.onmouseover = () => { applyBtn.style.background = '#059669'; };
    applyBtn.onmouseout = () => { applyBtn.style.background = '#10b981'; };
    applyBtn.onclick = () => {
      applyBtn.disabled = true;
      applyBtn.innerText = 'Advancing...';
      applyBtn.style.opacity = '0.7';
      if (window.onJobPulseAction) {
        window.onJobPulseAction({ action: 'apply_and_next', jobId: config.jobId });
      }
    };
    right.appendChild(applyBtn);

    // Skip Button (Speed-Run only)
    if (config.isSpeedRun) {
      const skipBtn = document.createElement('button');
      skipBtn.id = 'jobpulse-hud-skip-btn';
      skipBtn.style.cssText = 'background: #334155; color: #cbd5e1; border: 1px solid #475569; border-radius: 7px; padding: 7px 12px; font-size: 12px; font-weight: 500; cursor: pointer; transition: background 0.15s; white-space: nowrap;';
      skipBtn.innerText = '⏭ Skip';
      skipBtn.onmouseover = () => { skipBtn.style.background = '#475569'; };
      skipBtn.onmouseout = () => { skipBtn.style.background = '#334155'; };
      skipBtn.onclick = () => {
        skipBtn.disabled = true;
        skipBtn.innerText = 'Skipping...';
        if (window.onJobPulseAction) {
          window.onJobPulseAction({ action: 'skip', jobId: config.jobId });
        }
      };
      right.appendChild(skipBtn);
    }

    // Exit Button
    const exitBtn = document.createElement('button');
    exitBtn.id = 'jobpulse-hud-exit-btn';
    exitBtn.style.cssText = 'background: transparent; color: #94a3b8; border: 1px solid #334155; border-radius: 7px; padding: 7px 10px; font-size: 12px; cursor: pointer; transition: all 0.15s; white-space: nowrap;';
    exitBtn.innerText = config.isSpeedRun ? '✕ Exit' : '✕ Close';
    exitBtn.onmouseover = () => { exitBtn.style.color = '#ef4444'; exitBtn.style.borderColor = '#ef4444'; };
    exitBtn.onmouseout = () => { exitBtn.style.color = '#94a3b8'; exitBtn.style.borderColor = '#334155'; };
    exitBtn.onclick = () => {
      if (window.onJobPulseAction) {
        window.onJobPulseAction({ action: 'exit', jobId: config.jobId });
      }
    };
    right.appendChild(exitBtn);

    container.appendChild(right);
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

    # Check for queue (Speed-Run) vs single-job mode
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
                # If primary profile was locked by another running browser instance, try auxiliary profile
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

            try:
                context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            except Exception:
                pass

            page = context.pages[0] if context.pages else context.new_page()

            # Global action tracker received from browser HUD buttons
            current_action = {"action": None, "job_id": None}

            def handle_hud_action(action_data):
                log(f"HUD event received from browser: {action_data}")
                if isinstance(action_data, dict):
                    current_action["action"] = action_data.get("action")
                    current_action["job_id"] = action_data.get("jobId")
                elif isinstance(action_data, str):
                    current_action["action"] = action_data

            try:
                context.expose_function("onJobPulseAction", handle_hud_action)
            except Exception as exp_err:
                log(f"Note on expose_function: {exp_err}")

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

                current_action["action"] = None
                current_action["job_id"] = job_id

                # Anti-automation bypass script on page load
                try:
                    page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
                except Exception:
                    pass

                try:
                    log(f"Navigating to {job_url}...")
                    page.goto(job_url, timeout=35000, wait_until="domcontentloaded")
                    page.set_default_timeout(3000)
                    time.sleep(2.0)
                except Exception as nav_e:
                    log(f"Navigation warning: {nav_e}")

                target = page
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
                        f"cover_letter_uploaded={fill_res.get('cover_letter_uploaded')})."
                    )
                except Exception as fill_e:
                    log(f"Form filling error: {fill_e}\n{traceback.format_exc()}")

                # Scroll to Submit button so the user sees the filled form ready for submission
                try:
                    _dismiss_cookie_banners(page)
                    submit_btn = target.locator(
                        "button[type='submit']:visible, input[type='submit']:visible, "
                        "button:has-text('Submit Application'):visible, button:has-text('Submit application'):visible, "
                        "button:has-text('Submit'):visible"
                    ).first
                    if submit_btn.count() > 0:
                        submit_btn.scroll_into_view_if_needed(timeout=2000)
                        log("Scrolled Submit button into view.")
                except Exception as scroll_e:
                    log(f"Scroll to submit warning: {scroll_e}")

                # Inject HUD
                try:
                    if fill_res.get("is_closed_posting"):
                        status_text = "⚠️ Posting closed or redirected. Click Skip or Next."
                    elif filled_count > 0:
                        status_text = f"Auto-filled {filled_count} fields. Review form & submit, or advance:"
                    else:
                        status_text = "Page loaded. Review form & submit, or advance:"
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
                        },
                    )
                    log("Injected floating JobPulse HUD overlay.")
                except Exception as hud_e:
                    log(f"HUD injection warning: {hud_e}")

                # Watch loop for this job
                start_job_ts = time.time()
                code_filled = False
                job_completed = False
                notified_gate = False

                while time.time() - start_job_ts < 1800:
                    try:
                        if page.is_closed():
                            log("Browser page was closed by user.")
                            return

                        # Check if user clicked a HUD action
                        act = current_action.get("action")
                        if act in ("apply_and_next", "mark_applied"):
                            log(f"Action '{act}' triggered by user for job {job_id}.")
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
                        curr_url = page.url.lower()
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
                                log("Detected aggregator account registration gate.")
                                try:
                                    page.evaluate(
                                        HUD_DONE_SCRIPT,
                                        "⚠️ Third-party account gate detected (WeWorkRemotely). Log in, or click [⏭ Skip] / [✓ Mark Applied]."
                                    )
                                except Exception:
                                    pass

                        # Check Greenhouse 2FA security code box
                        if not code_filled:
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
                    except Exception as loop_e:
                        log(f"Watch loop warning: {loop_e}")

                    time.sleep(1.2)

                if not job_completed and not is_speed_run:
                    # In single-job mode, if time expired or user finished, wrap up
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
