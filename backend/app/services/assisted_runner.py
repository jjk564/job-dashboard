"""
Interactive Desktop Browser Runner for JobPulse 'Open with Auto-Fill'.

Invoked in the user's interactive Windows desktop session so that Chromium
opens visibly in the foreground, pre-fills the ATS form, uploads tailored PDF
documents, answers screening questions, and monitors for Greenhouse security codes.
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


def log(msg: str) -> None:
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
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

    job_url = data.get("job_url")
    if not job_url:
        log("Error: job_url is empty")
        return

    job_data = data.get("job_data") or {"url": job_url}
    profile_data = data.get("profile_data") or {}
    candidate_skills = data.get("candidate_skills") or []
    app_kit = data.get("app_kit")
    files = data.get("files")
    imap_cfg = data.get("imap_config") or {}

    log(f"Target URL: {job_url}")

    from playwright.sync_api import sync_playwright
    from app.services.browser_assistant import (
        _dismiss_cookie_banners,
        _fill_form_sync,
        _fill_greenhouse_security_code_sync,
    )
    from app.services.email_code_reader import poll_for_security_code_sync

    try:
        with sync_playwright() as p:
            log("Launching Chromium (headless=False)...")
            browser = p.chromium.launch(
                headless=False,
                args=["--start-maximized"],
            )
            context = browser.new_context(no_viewport=True)
            page = context.new_page()

            try:
                log(f"Navigating to {job_url}...")
                page.goto(job_url, timeout=35000, wait_until="domcontentloaded")
                page.set_default_timeout(3000)
                time.sleep(2.0)
            except Exception as nav_e:
                log(f"Navigation warning: {nav_e}")

            target = page
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
                log(
                    f"Form filled: {fill_res.get('filled_count', 0)} fields filled "
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

            # Keep the browser open while the user reviews and submits the application.
            # While open, if Greenhouse security code boxes appear, auto-retrieve from Gmail and fill them!
            log("Entering interactive watch loop (up to 30 minutes)...")
            start_ts = time.time()
            code_filled = False
            while time.time() - start_ts < 1800:
                try:
                    if page.is_closed():
                        log("User closed browser window. Exiting runner.")
                        break

                    if not code_filled:
                        sec_box = target.locator("#security-input-0:visible")
                        if sec_box.count() > 0 and not (sec_box.input_value() or "").strip():
                            log("Detected Greenhouse security code box! Polling Gmail via IMAP...")
                            code = poll_for_security_code_sync(
                                imap_server=imap_cfg.get("imap_server") or "imap.gmail.com",
                                imap_email=imap_cfg.get("imap_email"),
                                imap_password=imap_cfg.get("imap_password"),
                                min_timestamp=start_ts - 60,
                                max_wait_seconds=15,
                            )
                            if code:
                                log(f"Retrieved security code {code}! Auto-filling code inputs...")
                                if _fill_greenhouse_security_code_sync(target, code):
                                    log("Successfully filled security code!")
                                    code_filled = True
                except Exception as loop_e:
                    log(f"Watch loop warning: {loop_e}")

                time.sleep(1.5)

            try:
                browser.close()
            except Exception:
                pass
            log("Interactive runner session finished cleanly.")

    except Exception as e:
        log(f"Fatal interactive browser runner error: {e}\n{traceback.format_exc()}")


if __name__ == "__main__":
    default_payload = str(BACKEND_DIR / "generated_packets" / "assisted_launch.json")
    target_payload = sys.argv[1] if len(sys.argv) > 1 else default_payload
    run_interactive_browser(target_payload)
