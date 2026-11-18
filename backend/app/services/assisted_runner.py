"""
Interactive Desktop Browser Runner for JobPulse 'Open with Auto-Fill'.

Invoked in the user's interactive Windows desktop session (WinSta0\\Default) so that
the Chromium browser window opens visibly in the foreground even when the FastAPI backend
was launched from a background daemon service.
"""
import json
import os
import sys
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.browser_assistant import (  # noqa: E402
    _dismiss_cookie_banners,
    _fill_form_sync,
    _fill_greenhouse_security_code_sync,
)
from app.services.email_code_reader import poll_for_security_code_sync  # noqa: E402


def run_interactive_browser(payload_path: str) -> None:
    path_obj = Path(payload_path)
    if not path_obj.exists():
        return

    data = json.loads(path_obj.read_text(encoding="utf-8"))
    job_url = data.get("job_url")
    if not job_url:
        return

    job_data = data.get("job_data") or {"url": job_url}
    profile_data = data.get("profile_data") or {}
    candidate_skills = data.get("candidate_skills") or []
    app_kit = data.get("app_kit")
    files = data.get("files")
    imap_cfg = data.get("imap_config") or {}

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=["--start-maximized"],
        )
        context = browser.new_context(no_viewport=True)
        page = context.new_page()
        page.goto(job_url, timeout=30000, wait_until="domcontentloaded")
        page.set_default_timeout(3000)
        time.sleep(1.5)

        fill_res = _fill_form_sync(
            page=page,
            job_data=job_data,
            profile_data=profile_data,
            candidate_skills=candidate_skills,
            app_kit=app_kit,
            files=files,
        )
        target = fill_res["target"]

        # Scroll to the Submit button so the user immediately sees the filled form ready to submit
        try:
            _dismiss_cookie_banners(page)
            submit_btn = target.locator(
                "button[type='submit']:visible, input[type='submit']:visible, "
                "button:has-text('Submit Application'):visible, button:has-text('Submit application'):visible, "
                "button:has-text('Submit'):visible"
            ).first
            if submit_btn.count() > 0:
                submit_btn.scroll_into_view_if_needed(timeout=2000)
        except Exception:
            pass

        # Stay open while the user interacts with the page; if Greenhouse security code boxes appear
        # and IMAP or manual code drop-box provides a code, auto-fill the 8 boxes automatically!
        start_ts = time.time()
        code_filled = False
        while time.time() - start_ts < 600:
            try:
                if page.is_closed():
                    break
                if not code_filled:
                    sec_box = target.locator("#security-input-0:visible")
                    if sec_box.count() > 0 and not (sec_box.input_value() or "").strip():
                        code = poll_for_security_code_sync(
                            imap_server=imap_cfg.get("imap_server"),
                            imap_email=imap_cfg.get("imap_email"),
                            imap_password=imap_cfg.get("imap_password"),
                            min_timestamp=start_ts - 60,
                            max_wait_seconds=4,
                        )
                        if code:
                            _fill_greenhouse_security_code_sync(target, code)
                            code_filled = True
            except Exception:
                pass
            time.sleep(1.5)

        try:
            browser.close()
        except Exception:
            pass


if __name__ == "__main__":
    default_payload = str(BACKEND_DIR / "generated_packets" / "assisted_launch.json")
    target_payload = sys.argv[1] if len(sys.argv) > 1 else default_payload
    run_interactive_browser(target_payload)
