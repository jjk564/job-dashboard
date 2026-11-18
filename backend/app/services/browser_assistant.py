"""
Playwright ATS Form Automation & Assisted Application Engine for JobPulse.

Uses `sync_playwright` inside `asyncio.to_thread` so browser subprocesses work reliably
on Windows under any asyncio event loop policy without blocking the FastAPI event loop.
"""
import asyncio
import logging
import os
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from .question_answerer import answer_single_question

logger = logging.getLogger(__name__)

# Portals that require candidate account authentication / SSO before an application form is accessible
AUTH_GATED_DOMAINS = (
    "myworkdayjobs.com",
    "workday.com",
    "linkedin.com",
    "indeed.com",
    "glassdoor.com",
    "ziprecruiter.com",
    "icims.com",
    "taleo.net",
    "brassring.com",
    "successfactors.com",
    "ultipro.com",
    "adp.com",
    "usajobs.gov",
)

# Direct ATS platforms that host public, single-page or direct-apply forms without login walls
DIRECT_ATS_DOMAINS = (
    "greenhouse.io",
    "lever.co",
    "ashbyhq.com",
    "workable.com",
    "breezy.hr",
    "recruitee.com",
    "jazzhr.com",
    "applytojob.com",
    "dover.com",
    "gem.com",
    "pinpointhq.com",
    "personio.de",
    "personio.com",
    "bamboohr.com",
)


def classify_ats_url(job_url: Optional[str]) -> Dict[str, Any]:
    """
    Classifies a job URL to determine whether it is a direct-apply ATS board,
    an auth-gated portal requiring manual login, or a generic company career page.
    """
    if not job_url or not job_url.strip():
        return {
            "can_auto_attempt": False,
            "ats_type": "missing_url",
            "reason": "Job posting does not have an application URL",
        }

    url_clean = job_url.strip()
    parsed = urlparse(url_clean)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return {
            "can_auto_attempt": False,
            "ats_type": "invalid_url",
            "reason": f"Invalid application URL format: {url_clean}",
        }

    host = parsed.netloc.lower()
    for gated in AUTH_GATED_DOMAINS:
        if gated in host:
            return {
                "can_auto_attempt": False,
                "ats_type": "auth_gated",
                "portal": gated,
                "reason": f"Portal ({gated}) requires candidate account login / authentication",
            }

    if "gh_jid=" in url_clean.lower():
        return {
            "can_auto_attempt": True,
            "ats_type": "greenhouse",
            "portal": "greenhouse.io",
            "reason": "Direct Greenhouse ATS form detected via gh_jid",
        }

    for direct in DIRECT_ATS_DOMAINS:
        if direct.lower() in host:
            return {
                "can_auto_attempt": True,
                "ats_type": direct.split(".")[0].lower(),
                "portal": direct,
                "reason": f"Direct ATS form supported ({direct})",
            }

    return {
        "can_auto_attempt": True,
        "ats_type": "generic",
        "portal": host,
        "reason": f"Company career portal ({host})",
    }


def _select_active_form_target(page: Any) -> Any:
    """
    If the page embeds a Greenhouse, Ashby, or Lever application form inside an iframe
    (e.g., #grnhse_iframe or boards.greenhouse.io/embed/job_app), returns that Frame;
    otherwise returns the main Page.
    """
    try:
        for frame in page.frames:
            f_url = (frame.url or "").lower()
            if any(d in f_url for d in ("greenhouse.io/embed", "ashbyhq.com", "lever.co", "workable.com")):
                return frame
    except Exception:
        pass
    return page


def _dismiss_cookie_banners(page: Any) -> None:
    """Dismisses floating cookie consent banners that might overlay the Submit button."""
    cookie_selectors = [
        "button:has-text('Accept all')",
        "button:has-text('Accept All')",
        "button:has-text('Accept cookies')",
        "button:has-text('Decline all')",
        "button:has-text('Got it')",
        "button:has-text('I agree')",
    ]
    for sel in cookie_selectors:
        try:
            btn = page.locator(sel).first
            if btn.count() > 0 and btn.is_visible():
                btn.click(timeout=1200)
                time.sleep(0.3)
                break
        except Exception:
            pass


def _fill_form_sync(
    page: Any,
    job_data: Dict[str, Any],
    profile_data: Dict[str, Any],
    candidate_skills: Optional[List[Any]] = None,
    app_kit: Optional[Dict[str, Any]] = None,
    files: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    Synchronous Playwright form discovery and autofill routine (executed inside worker thread).
    Never interacts with or attempts to solve any CAPTCHA challenge.
    """
    filled_count = 0
    unanswered_required: List[str] = []
    discovered_qa: List[Dict[str, Any]] = []
    resume_uploaded = False
    cover_letter_uploaded = False

    _dismiss_cookie_banners(page)
    target = _select_active_form_target(page)

    # 1. If the page has an 'Apply' / 'Apply for this job' button and no visible form inputs yet, click it
    try:
        input_count = target.locator("form input, input[type='email'], input[type='file']").count()
        if input_count == 0:
            apply_btn = page.locator(
                "a:has-text('Apply for this job'), button:has-text('Apply for this job'), "
                "a:has-text('Apply Now'), button:has-text('Apply Now'), "
                "a:has-text('Apply'), button:has-text('Apply')"
            ).first
            if apply_btn.count() > 0 and apply_btn.is_visible():
                apply_btn.click(timeout=3500)
                time.sleep(1.5)
                _dismiss_cookie_banners(page)
                target = _select_active_form_target(page)
    except Exception:
        pass

    # 2. Check for login wall or visible CAPTCHA gate
    page_content_low = ""
    try:
        page_content_low = (target.content() or "").lower()
    except Exception:
        pass

    captcha_selectors = [
        "iframe[src*='recaptcha']:visible",
        "iframe[src*='hcaptcha']:visible",
        "iframe[src*='turnstile']:visible",
        ".g-recaptcha:visible",
        ".h-captcha:visible",
        ".cf-turnstile:visible",
    ]
    has_captcha = False
    for sel in captcha_selectors:
        try:
            loc = target.locator(sel)
            if loc.count() > 0:
                # Note: Invisible reCAPTCHA badge (size=invisible) does not block click unless a challenge popup opens;
                # check if it's an interactive checkbox challenge
                src_attr = (loc.first.get_attribute("src") or "").lower()
                if "size=invisible" not in src_attr:
                    has_captcha = True
                    break
        except Exception:
            pass

    if "verify you are human" in page_content_low or "cf-browser-verification" in page_content_low:
        has_captcha = True

    is_closed_posting = any(
        phrase in page_content_low
        for phrase in (
            "no longer open",
            "no longer accepting applications",
            "position has been filled",
            "job is no longer available",
            "page not found",
        )
    )

    login_wall = False
    try:
        pw_inputs = target.locator("input[type='password']:visible")
        if pw_inputs.count() > 0:
            login_wall = True
    except Exception:
        pass

    # 3. Fill standard contact fields (handles both first_name and firstname conventions)
    full_name = (profile_data.get("full_name") or "").strip()
    parts = full_name.split()
    first_name = parts[0] if parts else ""
    last_name = " ".join(parts[1:]) if len(parts) > 1 else ""
    email = (profile_data.get("email") or "").strip()
    phone = (profile_data.get("phone") or "").strip()
    location = (profile_data.get("location") or "").strip()
    linkedin = (profile_data.get("linkedin_url") or "").strip()
    github = (profile_data.get("github_url") or "").strip()
    portfolio = (profile_data.get("portfolio_url") or github or linkedin).strip()

    field_mappings = [
        (
            'input[name*="first_name" i], input[id*="first_name" i], '
            'input[name*="firstname" i], input[id*="firstname" i], input[autocomplete="given-name"]',
            first_name,
        ),
        (
            'input[name*="last_name" i], input[id*="last_name" i], '
            'input[name*="lastname" i], input[id*="lastname" i], input[autocomplete="family-name"]',
            last_name,
        ),
        ('input[name="name" i], input[id="name" i], input[autocomplete="name"], input[name*="full_name" i]', full_name),
        ('input[type="email"], input[name*="email" i], input[id*="email" i]', email),
        ('input[type="tel"], input[name*="phone" i], input[id*="phone" i]', phone),
        ('input[name*="location" i], input[id*="location" i], input[name*="city" i]', location),
        ('input[name*="linkedin" i], input[id*="linkedin" i], input[placeholder*="linkedin" i]', linkedin),
        ('input[name*="github" i], input[id*="github" i], input[placeholder*="github" i]', github),
        ('input[name*="website" i], input[id*="portfolio" i], input[placeholder*="portfolio" i], input[name*="portfolio" i]', portfolio),
    ]

    for selector, val in field_mappings:
        if not val:
            continue
        try:
            loc = target.locator(selector).first
            if loc.count() > 0 and loc.is_visible():
                current_val = loc.input_value()
                if not current_val:
                    loc.fill(val, timeout=1500)
                    filled_count += 1
        except Exception:
            pass

    if not phone:
        try:
            phone_loc = target.locator('input[type="tel"]:visible, input[name*="phone" i]:visible, input[id*="phone" i]:visible').first
            if phone_loc.count() > 0:
                is_phone_req = (
                    phone_loc.get_attribute("required") is not None
                    or phone_loc.get_attribute("aria-required") == "true"
                )
                if is_phone_req:
                    unanswered_required.append("Phone Number (missing in My Profile)")
        except Exception:
            pass

    # 4. Upload Tailored Resume & Cover Letter PDFs to `<input type="file">`
    # Note: React ATS forms (Greenhouse, Workable, Ashby) unmount `<input type="file">` as soon as a file is set,
    # shifting subsequent file inputs from nth(1) to nth(0). Always re-query instead of indexing a stale count.
    if files:
        resume_pdf = files.get("resume_pdf")
        cover_pdf = files.get("cover_letter_pdf")
        if resume_pdf and os.path.exists(resume_pdf):
            try:
                res_inp = target.locator(
                    'input[type="file"][id*="resume" i], input[type="file"][name*="resume" i], '
                    'input[type="file"][aria-label*="resume" i], input[type="file"][id*="cv" i]'
                ).first
                if res_inp.count() > 0:
                    res_inp.set_input_files(resume_pdf, timeout=2000)
                    resume_uploaded = True
                    filled_count += 1
                else:
                    any_file = target.locator('input[type="file"]').first
                    if any_file.count() > 0:
                        any_file.set_input_files(resume_pdf, timeout=2000)
                        resume_uploaded = True
                        filled_count += 1
                time.sleep(0.4)
            except Exception as e:
                logger.debug(f"Resume upload check: {e}")

        if cover_pdf and os.path.exists(cover_pdf):
            try:
                cl_inp = target.locator(
                    'input[type="file"][id*="cover" i], input[type="file"][name*="cover" i], '
                    'input[type="file"][aria-label*="cover" i]'
                ).first
                if cl_inp.count() > 0:
                    cl_inp.set_input_files(cover_pdf, timeout=2000)
                    cover_letter_uploaded = True
                    filled_count += 1
                time.sleep(0.3)
            except Exception as e:
                logger.debug(f"Cover letter upload check: {e}")

    # 5. Discover and answer Radio Button groups (`input[type="radio"]`)
    try:
        radios = target.locator("input[type='radio']:visible")
        r_count = min(radios.count(), 30)
        radio_groups: Dict[str, List[Dict[str, Any]]] = {}
        for i in range(r_count):
            r_el = radios.nth(i)
            r_name = r_el.get_attribute("name") or f"group_{i}"
            info = r_el.evaluate(
                """el => {
                    const optLabel = (el.closest('label')?.innerText || el.getAttribute('aria-label') || el.value || '').trim();
                    let cur = el;
                    let promptText = '';
                    for (let k = 0; k < 6; k++) {
                        if (!cur.parentElement) break;
                        cur = cur.parentElement;
                        const txt = (cur.innerText || '').trim();
                        const lines = txt.split('\\n').map(s => s.replace('*', '').trim()).filter(Boolean);
                        if (lines.length > 2 && lines[0].toLowerCase() !== optLabel.toLowerCase()) {
                            promptText = lines[0];
                            break;
                        }
                    }
                    const isReq = el.hasAttribute('required') || el.getAttribute('aria-required') === 'true';
                    return { optLabel, promptText, isReq };
                }"""
            )
            radio_groups.setdefault(r_name, []).append({"index": i, **info})

        for r_name, items in radio_groups.items():
            prompt = next((it["promptText"] for it in items if it.get("promptText")), r_name)
            options_list = [it["optLabel"] for it in items if it.get("optLabel")]
            is_req = any(it.get("isReq") for it in items)

            qa = answer_single_question(
                question_text=prompt,
                job_data=job_data,
                profile_data=profile_data,
                candidate_skills=candidate_skills,
                app_kit=app_kit,
                options=options_list,
                field_type="radio",
                required=is_req,
            )
            discovered_qa.append(qa)

            if qa["confidence"] == "manual_needed" and is_req:
                unanswered_required.append(prompt)
                continue

            desired_ans = (qa.get("answer") or "").strip().lower()
            matched_item = next(
                (it for it in items if it["optLabel"].lower() == desired_ans or desired_ans in it["optLabel"].lower()),
                None,
            )
            if matched_item:
                try:
                    r_loc = radios.nth(matched_item["index"])
                    r_loc.check(force=True, timeout=1500)
                    filled_count += 1
                except Exception:
                    pass
            elif is_req:
                unanswered_required.append(prompt)
    except Exception as e:
        logger.debug(f"Radio group discovery error: {e}")

    # 6. Inspect and answer remaining labeled text inputs, textareas, selects, and React-Select comboboxes
    try:
        elements = target.locator(
            "input[type='text']:visible, input[type='number']:visible, input[type='url']:visible, "
            "textarea:visible, select:visible"
        )
        el_count = min(elements.count(), 35)
        for i in range(el_count):
            el = elements.nth(i)
            try:
                tag_name = (el.evaluate("el => el.tagName.toLowerCase()")) or "input"
                inp_type = (el.get_attribute("type") or "text").lower()
                role_attr = (el.get_attribute("role") or "").lower()
                el_id = el.get_attribute("id") or ""
                el_name = el.get_attribute("name") or ""
                if not el_id and not el_name and role_attr == "combobox":
                    # Internal dummy React-Select input
                    continue

                is_req = (
                    el.get_attribute("required") is not None
                    or el.get_attribute("aria-required") == "true"
                )

                if tag_name in ("input", "textarea"):
                    existing_val = (el.input_value() or "").strip()
                    if existing_val:
                        continue

                label_text = el.evaluate(
                    """el => {
                        if (el.labels && el.labels.length > 0) {
                            return Array.from(el.labels).map(l => l.innerText).join(' ').trim();
                        }
                        const aria = el.getAttribute('aria-label');
                        if (aria) return aria.trim();
                        const wrapper = el.closest('label, .field, .application-question, .form-group, .select__container, [data-qa]');
                        if (wrapper) {
                            const lbl = wrapper.querySelector('label, .label, h4, legend');
                            if (lbl) return lbl.innerText.trim();
                        }
                        return el.getAttribute('placeholder') || el.getAttribute('name') || el.getAttribute('id') || '';
                    }"""
                )
                label_clean = (label_text or "").replace("*", "").strip()
                if not label_clean or len(label_clean) < 2:
                    continue

                # Skip optional EEO comboboxes unless required (never skip 'country' as Greenhouse requires Country when Phone is filled)
                if role_attr == "combobox" and not is_req and any(
                    k in label_clean.lower() for k in ("gender", "hispanic", "race", "veteran", "disability")
                ):
                    continue

                options_list: Optional[List[str]] = None
                if tag_name == "select":
                    options_list = el.evaluate(
                        "el => Array.from(el.options).map(o => o.text.trim()).filter(Boolean)"
                    )
                elif role_attr == "combobox" and "country" not in label_clean.lower():
                    try:
                        el.click(force=True, timeout=1000)
                        time.sleep(0.2)
                        opts = target.locator(".select__option:visible, [id*='react-select'][role='option']:visible")
                        opt_cnt = min(opts.count(), 25)
                        if opt_cnt > 0:
                            options_list = [opts.nth(k).inner_text().strip() for k in range(opt_cnt)]
                    except Exception:
                        pass

                qa = answer_single_question(
                    question_text=label_clean,
                    job_data=job_data,
                    profile_data=profile_data,
                    candidate_skills=candidate_skills,
                    app_kit=app_kit,
                    options=options_list,
                    field_type="number" if inp_type == "number" else tag_name,
                    required=is_req,
                )
                discovered_qa.append(qa)

                if qa["confidence"] == "manual_needed" and is_req:
                    if role_attr == "combobox":
                        try:
                            el.press("Escape")
                        except Exception:
                            pass
                    unanswered_required.append(label_clean)
                    continue

                ans_val = qa.get("answer") or ""
                if not ans_val:
                    if role_attr == "combobox":
                        try:
                            el.press("Escape")
                        except Exception:
                            pass
                    if is_req:
                        unanswered_required.append(label_clean)
                    continue

                if tag_name == "select":
                    el.select_option(label=ans_val, timeout=1500)
                    filled_count += 1
                elif role_attr == "combobox":
                    opt_loc = target.locator(
                        f".select__option:has-text('{ans_val}'):visible, "
                        f"[id*='react-select'][role='option']:has-text('{ans_val}'):visible"
                    ).first
                    if opt_loc.count() > 0:
                        opt_loc.click(timeout=1200)
                        filled_count += 1
                    else:
                        el.click(force=True, timeout=1000)
                        el.fill(str(ans_val), timeout=1000)
                        time.sleep(0.25)
                        filtered_opt = target.locator(
                            ".select__option:visible, [id*='react-select'][role='option']:visible"
                        ).first
                        if filtered_opt.count() > 0:
                            filtered_opt.click(timeout=1000)
                        else:
                            el.press("Enter")
                            el.press("Escape")
                        filled_count += 1
                else:
                    el.fill(str(ans_val), timeout=1500)
                    filled_count += 1
            except Exception:
                pass
    except Exception as e:
        logger.debug(f"Custom field discovery error: {e}")

    return {
        "target": target,
        "filled_count": filled_count,
        "resume_uploaded": resume_uploaded,
        "cover_letter_uploaded": cover_letter_uploaded,
        "has_captcha": has_captcha,
        "login_wall": login_wall,
        "is_closed_posting": is_closed_posting,
        "unanswered_required": unanswered_required,
        "discovered_qa": discovered_qa,
    }


def _attempt_submission_sync(
    job_url: str,
    job_data: Dict[str, Any],
    profile_data: Dict[str, Any],
    candidate_skills: Optional[List[Any]],
    app_kit: Optional[Dict[str, Any]],
    files: Optional[Dict[str, str]],
    headless: bool,
    require_full_qa_confidence: bool,
) -> Dict[str, Any]:
    """Runs synchronous Playwright inside a dedicated worker thread."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context()
        page = context.new_page()
        try:
            resp = page.goto(job_url, timeout=14000, wait_until="domcontentloaded")
            page.set_default_timeout(2500)
            if resp and resp.status >= 400:
                browser.close()
                return {
                    "submitted": False,
                    "status_target": "TO_APPLY",
                    "autopilot_status": "needs_manual_apply",
                    "reason": f"Need to Apply: Posting returned HTTP {resp.status} (Tailored Resume, Cover Letter & Q&A ready)",
                    "filled_count": 0,
                    "discovered_qa": [],
                }

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

            if fill_res["is_closed_posting"]:
                browser.close()
                return {
                    "submitted": False,
                    "status_target": "TO_APPLY",
                    "autopilot_status": "needs_manual_apply",
                    "reason": "Need to Apply: External career page indicates this posting may be closed or redirected",
                    "filled_count": fill_res["filled_count"],
                    "discovered_qa": fill_res["discovered_qa"],
                }

            if fill_res["login_wall"]:
                browser.close()
                return {
                    "submitted": False,
                    "status_target": "TO_APPLY",
                    "autopilot_status": "needs_manual_apply",
                    "reason": "Need to Apply: Portal requires candidate account login / password (documents & Q&A ready)",
                    "filled_count": fill_res["filled_count"],
                    "discovered_qa": fill_res["discovered_qa"],
                }

            if fill_res["has_captcha"]:
                browser.close()
                return {
                    "submitted": False,
                    "status_target": "TO_APPLY",
                    "autopilot_status": "needs_manual_apply",
                    "reason": "Need to Apply: CAPTCHA verification challenge requires manual completion (documents & Q&A ready)",
                    "filled_count": fill_res["filled_count"],
                    "discovered_qa": fill_res["discovered_qa"],
                }

            if require_full_qa_confidence and fill_res["unanswered_required"]:
                missing_str = ", ".join(fill_res["unanswered_required"][:2])
                browser.close()
                return {
                    "submitted": False,
                    "status_target": "TO_APPLY",
                    "autopilot_status": "needs_manual_apply",
                    "reason": f"Need to Apply: Required field(s) need manual entry ({missing_str}) — Tailored Resume, Cover Letter & Q&A ready",
                    "filled_count": fill_res["filled_count"],
                    "discovered_qa": fill_res["discovered_qa"],
                }

            if fill_res["filled_count"] < 2:
                browser.close()
                return {
                    "submitted": False,
                    "status_target": "TO_APPLY",
                    "autopilot_status": "needs_manual_apply",
                    "reason": "Need to Apply: Multi-step or custom career portal without direct single-page ATS form (Tailored Resume, Cover Letter & Q&A ready)",
                    "filled_count": fill_res["filled_count"],
                    "discovered_qa": fill_res["discovered_qa"],
                }

            _dismiss_cookie_banners(page)
            submit_btn = target.locator(
                "button[type='submit']:visible, input[type='submit']:visible, "
                "button:has-text('Submit Application'):visible, button:has-text('Submit application'):visible, "
                "button:has-text('Submit'):visible"
            ).first

            if submit_btn.count() == 0:
                browser.close()
                return {
                    "submitted": False,
                    "status_target": "TO_APPLY",
                    "autopilot_status": "needs_manual_apply",
                    "reason": f"Need to Apply: Pre-filled {fill_res['filled_count']} fields, but final Submit button requires manual review",
                    "filled_count": fill_res["filled_count"],
                    "discovered_qa": fill_res["discovered_qa"],
                }

            try:
                submit_btn.scroll_into_view_if_needed(timeout=2000)
                submit_btn.click(timeout=3000)
            except Exception:
                submit_btn.click(force=True, timeout=3000)

            time.sleep(2.5)

            after_html = (target.content() or "").lower()
            confirmation_signals = (
                "thank you for applying",
                "application has been submitted",
                "application submitted",
                "we have received your application",
                "thanks for applying",
                "your application was sent",
                "all done",
            )
            confirmed = any(sig in after_html for sig in confirmation_signals)
            has_security_code = "verification code" in after_html or "security code" in after_html
            has_captcha_after = (
                "recaptcha" in after_html and ("challenge" in after_html or "verify" in after_html)
            )
            browser.close()

            if confirmed:
                return {
                    "submitted": True,
                    "status_target": "APPLIED",
                    "autopilot_status": "auto_applied",
                    "reason": f"Autonomously submitted application ({fill_res['filled_count']} fields + tailored resume & cover letter)",
                    "filled_count": fill_res["filled_count"],
                    "discovered_qa": fill_res["discovered_qa"],
                }
            elif has_security_code:
                return {
                    "submitted": False,
                    "status_target": "TO_APPLY",
                    "autopilot_status": "needs_manual_apply",
                    "reason": f"Need to Apply: ATS sent a one-time email verification code after pre-filling {fill_res['filled_count']} fields",
                    "filled_count": fill_res["filled_count"],
                    "discovered_qa": fill_res["discovered_qa"],
                }
            elif has_captcha_after:
                return {
                    "submitted": False,
                    "status_target": "TO_APPLY",
                    "autopilot_status": "needs_manual_apply",
                    "reason": f"Need to Apply: ATS triggered a CAPTCHA challenge on submit after filling {fill_res['filled_count']} fields",
                    "filled_count": fill_res["filled_count"],
                    "discovered_qa": fill_res["discovered_qa"],
                }
            else:
                return {
                    "submitted": False,
                    "status_target": "TO_APPLY",
                    "autopilot_status": "needs_manual_apply",
                    "reason": f"Need to Apply: Pre-filled {fill_res['filled_count']} fields + Resume PDF, awaiting final human submit check",
                    "filled_count": fill_res["filled_count"],
                    "discovered_qa": fill_res["discovered_qa"],
                }
        except Exception as inner_e:
            try:
                browser.close()
            except Exception:
                pass
            err_msg = str(inner_e).splitlines()[0][:100] if str(inner_e) else "Navigation timeout"
            return {
                "submitted": False,
                "status_target": "TO_APPLY",
                "autopilot_status": "needs_manual_apply",
                "reason": f"Need to Apply: External career portal required manual navigation ({err_msg}) — Tailored Resume, Cover Letter & Q&A ready",
                "filled_count": 0,
                "discovered_qa": [],
            }


async def attempt_autonomous_submission(
    job_data: Dict[str, Any],
    profile_data: Dict[str, Any],
    candidate_skills: Optional[List[Any]] = None,
    app_kit: Optional[Dict[str, Any]] = None,
    files: Optional[Dict[str, str]] = None,
    headless: bool = True,
    auto_submit: bool = True,
    require_full_qa_confidence: bool = True,
) -> Dict[str, Any]:
    """
    Attempts to autonomously fill and submit a job application via Playwright in a worker thread.
    """
    job_url = (job_data.get("url") or "").strip()
    url_info = classify_ats_url(job_url)
    if not url_info["can_auto_attempt"]:
        return {
            "submitted": False,
            "status_target": "TO_APPLY",
            "autopilot_status": "needs_manual_apply",
            "reason": f"Need to Apply: {url_info['reason']}",
            "filled_count": 0,
            "discovered_qa": [],
        }

    if not (profile_data.get("full_name") or "").strip() or not (profile_data.get("email") or "").strip():
        return {
            "submitted": False,
            "status_target": "TO_APPLY",
            "autopilot_status": "needs_manual_apply",
            "reason": "Need to Apply: Candidate profile is missing Full Name or Email (documents & Q&A pre-generated)",
            "filled_count": 0,
            "discovered_qa": [],
        }

    if not auto_submit:
        return {
            "submitted": False,
            "status_target": "TO_APPLY",
            "autopilot_status": "needs_manual_apply",
            "reason": "Need to Apply: Auto-submit disabled (Tailored Resume, Cover Letter & Q&A ready)",
            "filled_count": 0,
            "discovered_qa": [],
        }

    try:
        import playwright  # noqa: F401
    except ImportError:
        return {
            "submitted": False,
            "status_target": "TO_APPLY",
            "autopilot_status": "needs_manual_apply",
            "reason": "Need to Apply: Playwright browser engine not installed (Tailored Resume, Cover Letter & Q&A ready)",
            "filled_count": 0,
            "discovered_qa": [],
        }

    try:
        return await asyncio.to_thread(
            _attempt_submission_sync,
            job_url,
            job_data,
            profile_data,
            candidate_skills,
            app_kit,
            files,
            headless,
            require_full_qa_confidence,
        )
    except Exception as e:
        err_str = str(e) or type(e).__name__
        logger.warning(f"Autonomous Playwright runner fallback: {err_str}")
        return {
            "submitted": False,
            "status_target": "TO_APPLY",
            "autopilot_status": "needs_manual_apply",
            "reason": f"Need to Apply: Browser session fallback ({err_str[:90]}) — Tailored Resume, Cover Letter & Q&A pre-generated",
            "filled_count": 0,
            "discovered_qa": [],
        }


async def launch_assisted_application(
    job_url: str,
    profile_data: Dict[str, Any],
    job_data: Optional[Dict[str, Any]] = None,
    candidate_skills: Optional[List[Any]] = None,
    app_kit: Optional[Dict[str, Any]] = None,
    files: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    Launches a visible Chromium session with Playwright in a background worker thread to pre-fill
    standard ATS form fields, upload tailored Resume & Cover Letter PDFs, and answer custom
    screening questions. Leaves the browser window open for user review and final submission.
    """
    if not job_url:
        return {"success": False, "message": "No application URL provided."}

    try:
        import playwright  # noqa: F401
    except ImportError:
        return {
            "success": False,
            "message": "Playwright is not installed. Please run 'pip install playwright && playwright install chromium'.",
        }

    def _assisted_sync():
        from playwright.sync_api import sync_playwright
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=False)
                context = browser.new_context()
                page = context.new_page()
                page.goto(job_url, timeout=30000, wait_until="domcontentloaded")
                time.sleep(2.0)

                fill_res = _fill_form_sync(
                    page=page,
                    job_data=job_data or {"url": job_url},
                    profile_data=profile_data,
                    candidate_skills=candidate_skills,
                    app_kit=app_kit,
                    files=files,
                )
                logger.info(
                    f"Assisted application launched. Pre-filled {fill_res['filled_count']} fields "
                    f"(Resume uploaded: {fill_res['resume_uploaded']})."
                )
                time.sleep(300)
                browser.close()
        except Exception as e:
            logger.error(f"Playwright assistant error: {e}")

    asyncio.create_task(asyncio.to_thread(_assisted_sync))

    return {
        "success": True,
        "message": f"Assisted browser session opened for {job_url}. Tailored resume, cover letter, and screening answers pre-filled for your review.",
    }
