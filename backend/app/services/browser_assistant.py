"""
Playwright ATS Form Automation & Assisted Application Engine for JobPulse.

Uses `sync_playwright` inside `asyncio.to_thread` so browser subprocesses work reliably
on Windows under any asyncio event loop policy without blocking the FastAPI event loop.
"""
import asyncio
import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from .email_code_reader import poll_for_security_code_sync
from .question_answerer import PACKETS_DIR, answer_single_question

logger = logging.getLogger(__name__)

# Portals and aggregators that require candidate account authentication / SSO or lock listings behind registrations
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
    "weworkremotely.com",
    "jobicy.com",
    "remoteok.com",
    "builtin.com",
    "simplyhired.com",
    "monster.com",
    "dice.com",
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
    "jobvite.com",
    "eightfold.ai",
)


def is_direct_ats_url(job_url: Optional[str]) -> bool:
    """
    Returns True if the URL points directly to a supported single-page ATS form
    (e.g. Greenhouse, Lever, Ashby, Workable, BambooHR, ApplyToJob).
    """
    if not job_url or not job_url.strip():
        return False
    u = job_url.strip().lower()
    if "gh_jid=" in u:
        return True
    try:
        parsed = urlparse(u)
        host = (parsed.netloc or "").lower()
        return any(d in host for d in DIRECT_ATS_DOMAINS)
    except Exception:
        return False


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
    job_url: Optional[str] = None,
    **kwargs,
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

    # Use visible body text (excluding script tags) to avoid false positives on i18n translation JSON bundles
    visible_body_text = ""
    try:
        visible_body_text = (target.inner_text("body") or "").lower()
    except Exception:
        visible_body_text = page_content_low

    # A page that contains active form inputs or an Apply button is NOT a 404/closed posting
    has_form_or_apply = False
    try:
        has_form_or_apply = target.locator(
            "button:has-text('Apply'), a:has-text('Apply'), form input, input[type='file'], input[type='email']"
        ).count() > 0
    except Exception:
        pass

    is_closed_posting = not has_form_or_apply and any(
        phrase in visible_body_text
        for phrase in (
            "no longer open",
            "no longer accepting applications",
            "position has been filled",
            "job is no longer available",
            "page not found",
            "404 not found",
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
    if files:
        resume_pdf = files.get("resume_pdf")
        cover_pdf = files.get("cover_letter_pdf")

        # Fallback to legacy file paths if primary candidate-named files don't exist
        if resume_pdf and not os.path.exists(resume_pdf):
            resume_pdf = files.get("legacy_resume_pdf")
        if cover_pdf and not os.path.exists(cover_pdf):
            cover_pdf = files.get("legacy_cover_letter_pdf")

        try:
            file_inputs = target.locator('input[type="file"]')
            total_files = file_inputs.count()
            logger.debug(f"Detected {total_files} file inputs on application page")

            resume_inp = None
            cover_inp = None

            if total_files > 0:
                # Inspect each input's attributes and surrounding DOM container text
                meta_list = []
                for idx in range(total_files):
                    el = file_inputs.nth(idx)
                    meta = el.evaluate("""el => {
                        const id = (el.id || '').toLowerCase();
                        const name = (el.name || '').toLowerCase();
                        const aria = (el.getAttribute('aria-label') || '').toLowerCase();
                        let container = '';
                        const parent = el.closest('div, section, fieldset, li, tr, form') || el.parentElement;
                        if (parent) {
                            container = (parent.innerText || '').toLowerCase();
                        }
                        return { id, name, aria, container };
                    }""")
                    meta_list.append({"index": idx, "locator": el, **meta})

                # Phase 1: Semantic matching via keywords
                for m in meta_list:
                    haystack = f"{m['id']} {m['name']} {m['aria']} {m['container']}"
                    if any(w in haystack for w in ("cover letter", "cover_letter", "coverletter", "cover")):
                        if cover_inp is None:
                            cover_inp = m["locator"]
                    elif any(w in haystack for w in ("resume", "résumé", "cv", "curriculum")):
                        if resume_inp is None:
                            resume_inp = m["locator"]

                # Phase 2: Positional / count fallback
                if total_files == 1:
                    if resume_inp is None and cover_inp is None:
                        resume_inp = file_inputs.first
                elif total_files >= 2:
                    if resume_inp is None and cover_inp is not None:
                        for m in meta_list:
                            if m["locator"] != cover_inp:
                                resume_inp = m["locator"]
                                break
                    elif cover_inp is None and resume_inp is not None:
                        for m in meta_list:
                            if m["locator"] != resume_inp:
                                cover_inp = m["locator"]
                                break
                    elif resume_inp is None and cover_inp is None:
                        resume_inp = file_inputs.nth(0)
                        cover_inp = file_inputs.nth(1)

            # Upload Resume PDF
            if resume_pdf and os.path.exists(resume_pdf) and resume_inp is not None:
                try:
                    resume_inp.set_input_files(resume_pdf, timeout=3000)
                    resume_uploaded = True
                    filled_count += 1
                    logger.info(f"Resume uploaded successfully: {os.path.basename(resume_pdf)}")
                    time.sleep(0.5)
                except Exception as e:
                    logger.debug(f"Resume upload error: {e}")

            # Upload Cover Letter PDF
            if cover_pdf and os.path.exists(cover_pdf):
                cl_uploaded = False
                if cover_inp is not None:
                    try:
                        cover_inp.set_input_files(cover_pdf, timeout=3000)
                        cl_uploaded = True
                        cover_letter_uploaded = True
                        filled_count += 1
                        logger.info(f"Cover letter uploaded successfully: {os.path.basename(cover_pdf)}")
                        time.sleep(0.5)
                    except Exception as e:
                        logger.debug(f"Cover letter initial upload error: {e}")

                # If primary attempt failed (e.g. dynamic unmount shifted elements), re-query
                if not cl_uploaded:
                    try:
                        remaining_inputs = target.locator('input[type="file"]')
                        rem_count = remaining_inputs.count()
                        if rem_count > 0:
                            for r_idx in range(rem_count):
                                r_el = remaining_inputs.nth(r_idx)
                                r_text = r_el.evaluate("""el => {
                                    const p = el.closest('div, section, fieldset, li, tr, form') || el.parentElement;
                                    return `${el.id} ${el.name} ${el.getAttribute('aria-label') || ''} ${p ? p.innerText : ''}`.toLowerCase();
                                }""")
                                if any(w in r_text for w in ("cover", "letter")) or (rem_count == 1 and resume_uploaded):
                                    r_el.set_input_files(cover_pdf, timeout=3000)
                                    cover_letter_uploaded = True
                                    filled_count += 1
                                    logger.info(f"Cover letter uploaded via fallback: {os.path.basename(cover_pdf)}")
                                    break
                    except Exception as e:
                        logger.debug(f"Cover letter fallback upload error: {e}")

        except Exception as e:
            logger.debug(f"File upload discovery/upload error: {e}")

        # Section 4.5: Cover Letter Textarea Fallback (if no file input or file input failed)
        if not cover_letter_uploaded:
            try:
                cl_textarea = target.locator(
                    'textarea[id*="cover" i], textarea[name*="cover" i], '
                    'textarea[placeholder*="cover" i], textarea[aria-label*="cover" i]'
                ).first
                if cl_textarea.count() > 0 and not (cl_textarea.input_value() or "").strip():
                    txt_path = files.get("cover_letter_txt") or files.get("cover_letter_md")
                    cl_text = ""
                    if txt_path and os.path.exists(txt_path):
                        with open(txt_path, "r", encoding="utf-8") as f:
                            cl_text = f.read().strip()
                    if cl_text:
                        cl_textarea.fill(cl_text, timeout=2000)
                        cover_letter_uploaded = True
                        filled_count += 1
                        logger.info("Cover letter filled into textarea")
            except Exception as e:
                logger.debug(f"Cover letter textarea fill error: {e}")

    # 5. Discover and answer Radio Button groups (`input[type="radio"]`)
    try:
        radios = target.locator("input[type='radio']")
        r_count = min(radios.count(), 30)
        radio_groups: Dict[str, List[Dict[str, Any]]] = {}
        for i in range(r_count):
            r_el = radios.nth(i)
            r_name = r_el.get_attribute("name") or f"group_{i}"
            info = r_el.evaluate(
                """el => {
                    let optLabel = (
                        el.closest('[role="radio"]')?.innerText ||
                        el.closest('[data-testid*="radio-label"]')?.innerText ||
                        el.closest('label')?.innerText ||
                        el.getAttribute('aria-label') ||
                        el.value ||
                        ''
                    ).trim();
                    if (!optLabel && el.parentElement) {
                        optLabel = (el.parentElement.innerText || '').trim();
                    }
                    let cur = el;
                    let promptText = '';
                    while (cur && cur !== document.body) {
                        if (cur.getAttribute('data-testid') === 'field' || cur.classList.contains('eun831x1') || cur.parentElement?.classList?.contains('application-question')) {
                            if (cur.previousElementSibling) {
                                const txt = (cur.previousElementSibling.innerText || '').trim();
                                if (txt && txt.length > 2) {
                                    promptText = txt;
                                    break;
                                }
                            }
                        }
                        if (cur.previousElementSibling) {
                            const prev = (cur.previousElementSibling.innerText || '').trim();
                            if (prev && prev.length > 2 && prev.toLowerCase() !== optLabel.toLowerCase()) {
                                promptText = prev;
                                break;
                            }
                        }
                        cur = cur.parentElement;
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
                (it for it in items if it["optLabel"].lower() == desired_ans or desired_ans in it["optLabel"].lower() or it["optLabel"].lower() in desired_ans),
                None,
            )
            if not matched_item and desired_ans.startswith("yes"):
                matched_item = next(
                    (it for it in items if "yes" in it["optLabel"].lower() or it["optLabel"].lower() == "true"),
                    None,
                )

            if matched_item:
                checked_ok = False
                try:
                    r_loc = radios.nth(matched_item["index"])
                    # On React/Rippling, click the enclosing custom radio component or label
                    r_loc.evaluate("el => (el.closest('[role=\"radio\"]') || el.closest('label') || el).click()")
                    checked_ok = True
                    filled_count += 1
                except Exception:
                    pass

                if not checked_ok:
                    try:
                        r_loc = radios.nth(matched_item["index"])
                        r_loc.check(force=True, timeout=1000)
                        checked_ok = True
                        filled_count += 1
                    except Exception:
                        pass

                # If native input is visually hidden / aria-hidden, click visible text or label
                if not checked_ok:
                    try:
                        lbl_text = matched_item["optLabel"]
                        click_target = target.locator(
                            f"text='{lbl_text}':visible, label:has-text('{lbl_text}'):visible"
                        ).first
                        if click_target.count() > 0:
                            click_target.click(force=True, timeout=1000)
                            filled_count += 1
                    except Exception:
                        pass
            elif is_req:
                unanswered_required.append(prompt)
    except Exception as e:
        logger.debug(f"Radio group discovery error: {e}")

    # 6. Inspect and answer remaining labeled text inputs, textareas, selects, and React/Custom comboboxes
    try:
        elements = target.locator(
            "input:visible:not([type='file']):not([type='radio']):not([type='checkbox']):not([type='hidden']):not([type='submit']):not([type='button']), "
            "textarea:visible, select:visible, div[role='combobox']:visible, button[role='combobox']:visible"
        )
        el_count = min(elements.count(), 45)
        logger.debug(f"[LOOP START] total elements={el_count}")
        for i in range(el_count):
            el = elements.nth(i)
            try:
                tag_name = (el.evaluate("el => el.tagName.toLowerCase()")) or "input"
                inp_type = (el.get_attribute("type") or "text").lower()
                role_attr = (el.get_attribute("role") or "").lower()
                el_id = el.get_attribute("id") or ""
                el_name = el.get_attribute("name") or ""
                logger.debug(f"[LOOP ITEM] i={i}/{el_count}, tag={tag_name}, id={el_id}, role={role_attr}")
                if not el_id and not el_name and role_attr == "combobox" and tag_name == "input":
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
                elif role_attr == "combobox":
                    existing_txt = (el.inner_text() or "").strip().lower()
                    if existing_txt and existing_txt not in ("select", "choose", "--", "search"):
                        continue

                label_text = el.evaluate(
                    """el => {
                        // 1. Native labels
                        if (el.labels && el.labels.length > 0) {
                            const t = Array.from(el.labels).map(l => l.innerText).join(' ').trim();
                            if (t) return t;
                        }
                        // 2. aria-labelledby
                        const ariaLbl = el.getAttribute('aria-labelledby');
                        if (ariaLbl) {
                            const target = document.getElementById(ariaLbl);
                            if (target && target.innerText.trim()) return target.innerText.trim();
                        }
                        // 3. aria-label (unless generic)
                        const aria = (el.getAttribute('aria-label') || '').trim();
                        if (aria && !['select', 'search', 'textbox', 'combobox', 'option'].includes(aria.toLowerCase())) {
                            return aria;
                        }
                        // 4. label[for=id]
                        if (el.id) {
                            const forLbl = document.querySelector(`label[for="${el.id}"]`);
                            if (forLbl && forLbl.innerText.trim()) return forLbl.innerText.trim();
                        }
                        // 5. Container walk & previousElementSibling (critical for Rippling & React forms!)
                        let cur = el;
                        for (let k = 0; k < 12 && cur; k++) {
                            const isFieldContainer = (
                                cur.getAttribute('data-testid') === 'field' ||
                                (cur.className && String(cur.className).includes('eun831x1')) ||
                                (cur.parentElement && cur.parentElement.getAttribute('data-testid') === 'field')
                            );
                            if (isFieldContainer) {
                                if (cur.previousElementSibling) {
                                    const txt = (cur.previousElementSibling.innerText || '').trim();
                                    if (txt && txt.length > 2) return txt;
                                }
                            }
                            if (cur.previousElementSibling) {
                                const prev = (cur.previousElementSibling.innerText || '').trim();
                                if (prev && prev.length > 2 && !prev.toLowerCase().includes('select')) {
                                    return prev;
                                }
                            }
                            const headings = cur.querySelectorAll('label, h1, h2, h3, h4, h5, h6, legend, p[class*="label"], span[class*="label"], [data-testid*="label"], [class*="question"]');
                            for (const h of headings) {
                                const ht = (h.innerText || '').trim();
                                if (ht && ht.length > 2 && ht !== el.innerText && !ht.toLowerCase().includes('select')) {
                                    return ht;
                                }
                            }
                            cur = cur.parentElement;
                        }
                        return el.getAttribute('placeholder') || el.getAttribute('name') || el.getAttribute('id') || '';
                    }"""
                )
                label_clean = (label_text or "").replace("*", "").strip()
                if not label_clean or len(label_clean) < 2:
                    continue

                # Skip optional EEO comboboxes unless required (never skip 'country' as Greenhouse requires Country when Phone is filled)
                # Gender and pronouns are actively filled with candidate's preference (Male / He/him/his)
                if role_attr == "combobox" and not is_req and any(
                    k in label_clean.lower() for k in ("hispanic", "race", "veteran", "disability")
                ):
                    continue

                options_list: Optional[List[str]] = None
                if tag_name == "select":
                    options_list = el.evaluate(
                        "el => Array.from(el.options).map(o => o.text.trim()).filter(Boolean)"
                    )

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
                logger.debug(f"[LOOP QA] {el_id}: ans={qa.get('answer')}, conf={qa.get('confidence')}")
                discovered_qa.append(qa)

                if qa["confidence"] == "manual_needed" and is_req:
                    unanswered_required.append(label_clean)
                    continue

                ans_val = qa.get("answer") or ""
                if not ans_val:
                    if is_req:
                        unanswered_required.append(label_clean)
                    continue

                logger.debug(f"[LOOP APPLYING] {el_id}: role={role_attr}, ans={ans_val}")
                if tag_name == "select":
                    el.select_option(label=ans_val, timeout=1500)
                    filled_count += 1
                elif role_attr == "combobox":
                    # 1. Scroll combobox into view and click to open its menu
                    try:
                        el.scroll_into_view_if_needed(timeout=1500)
                        el.click(force=True, timeout=1200)
                        time.sleep(0.35)
                    except Exception as click_err:
                        logger.debug(f"[COMBOBOX OPEN ERR] {el_id}: {click_err}")

                    # 2. STRICTLY scope option search to THIS combobox's menu container!
                    # Prevents unclosed or animating menus from prior questions from stealing the click
                    opt_loc = None
                    aria_ctrl = el.get_attribute("aria-controls") or ""
                    menu_locators = []
                    if el_id:
                        menu_locators.append(target.locator(f"#{el_id}-list"))
                    if aria_ctrl:
                        menu_locators.append(target.locator(f"#{aria_ctrl}"))
                    if not menu_locators:
                        menu_locators.append(target.locator("[role='listbox']:visible, ul[data-testid='menuList']:visible").first)

                    for m_loc in menu_locators:
                        try:
                            candidate = m_loc.locator("[role='option'], li, div[data-testid='menuListLabel'], .select__option").filter(has_text=str(ans_val)).first
                            candidate.wait_for(state="visible", timeout=1500)
                            opt_loc = candidate
                            break
                        except Exception:
                            pass

                    # Fallback retry: click el again if menu was not open
                    if not opt_loc:
                        try:
                            el.scroll_into_view_if_needed(timeout=1000)
                            el.click(force=True, timeout=1200)
                            time.sleep(0.35)
                            for m_loc in menu_locators:
                                candidate = m_loc.locator("[role='option'], li, div[data-testid='menuListLabel'], .select__option").filter(has_text=str(ans_val)).first
                                candidate.wait_for(state="visible", timeout=1500)
                                opt_loc = candidate
                                break
                        except Exception:
                            pass

                    if opt_loc:
                        try:
                            parent_id = opt_loc.evaluate("el => el.parentElement.id || el.parentElement.tagName")
                            logger.debug(f"[COMBOBOX CLICK ATTEMPT] {el_id}: target opt parent={parent_id}")
                            opt_loc.click(force=True, timeout=1500)
                            filled_count += 1
                            time.sleep(0.3)
                            logger.debug(f"[COMBOBOX FILL] {el_id}: selected {ans_val}, new val={el.inner_text()}")
                        except Exception as e:
                            logger.debug(f"[COMBOBOX FILL error] {el_id}: {e}")
                    else:
                        logger.debug(f"[COMBOBOX NO OPT_LOC FOUND] {el_id}: ans={ans_val}")
                        if tag_name == "input":
                            el.fill(str(ans_val), timeout=1000)
                            time.sleep(0.2)
                            target.locator(".select__option:visible, [role='option']:visible").filter(has_text=str(ans_val)).first.click(timeout=1000)
                        else:
                            try:
                                el.press("Escape")
                            except Exception:
                                pass
                else:
                    el.fill(str(ans_val), timeout=1500)
                    filled_count += 1
            except Exception as item_err:
                logger.debug(f"[LOOP ITEM ERROR] i={i}, id={el_id}: {item_err}")
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


def _fill_greenhouse_security_code_sync(target: Any, code: str) -> bool:
    """
    Types an 8-character Greenhouse security code into #security-input-0..7
    (or a single security code input) and clicks the Submit Application button.
    """
    clean_code = (code or "").strip()
    if not clean_code:
        return False

    try:
        box0 = target.locator("#security-input-0:visible")
        if box0.count() > 0:
            for idx, ch in enumerate(clean_code[:8]):
                box = target.locator(f"#security-input-{idx}:visible")
                if box.count() > 0:
                    box.fill(ch, timeout=1000)
            time.sleep(0.3)
            submit_btn = target.locator(
                "button[type='submit']:visible, input[type='submit']:visible, "
                "button:has-text('Submit Application'):visible, button:has-text('Submit application'):visible"
            ).first
            if submit_btn.count() > 0:
                try:
                    submit_btn.click(timeout=3000)
                except Exception:
                    submit_btn.click(force=True, timeout=3000)
            return True
    except Exception as e:
        logger.debug(f"Greenhouse security code fill error: {e}")

    return False


def _attempt_submission_sync(
    job_url: str,
    job_data: Dict[str, Any],
    profile_data: Dict[str, Any],
    candidate_skills: Optional[List[Any]],
    app_kit: Optional[Dict[str, Any]],
    files: Optional[Dict[str, str]],
    headless: bool,
    require_full_qa_confidence: bool,
    imap_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Runs synchronous Playwright inside a dedicated worker thread."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            args=["--start-maximized"] if not headless else None,
            ignore_default_args=["--enable-automation", "--no-sandbox"],
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36" if headless else None,
        )
        page = context.new_page()
        try:
            page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        except Exception:
            pass
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

            submit_click_ts = time.time()
            try:
                submit_btn.scroll_into_view_if_needed(timeout=2000)
                submit_btn.click(timeout=3000)
            except Exception:
                submit_btn.click(force=True, timeout=3000)

            confirmation_signals = (
                "thank you for applying",
                "application has been submitted",
                "application submitted",
                "we have received your application",
                "your application has been received",
                "thanks for applying",
                "your application was sent",
                "all done",
                "thank you for your interest",
                "application received",
                "submission successful",
            )
            confirmed = False
            has_security_code = False
            after_html = ""

            # Poll for up to 10 seconds for confirmation redirect or security code box
            for _ in range(20):
                time.sleep(0.5)
                try:
                    curr_url = (page.url or "").lower()
                    if any(k in curr_url for k in ("/confirmation", "confirm", "thank_you", "thanks", "success")):
                        confirmed = True
                        break
                    after_html = (target.content() or "").lower()
                    if any(sig in after_html for sig in confirmation_signals):
                        confirmed = True
                        break
                    if "security-input-0" in after_html or target.locator("#security-input-0:visible").count() > 0 or "verification code" in after_html or "security code" in after_html:
                        has_security_code = True
                        break
                except Exception:
                    pass

            if not after_html:
                try:
                    after_html = (target.content() or "").lower()
                except Exception:
                    after_html = ""

            # If Greenhouse requested an 8-character email security code, attempt automatic retrieval!
            if not confirmed and has_security_code:
                icfg = imap_config or {}
                has_imap = bool(icfg.get("imap_email") and icfg.get("imap_password"))
                wait_secs = 28 if has_imap else 3
                code = poll_for_security_code_sync(
                    imap_server=icfg.get("imap_server") or "imap.gmail.com",
                    imap_email=icfg.get("imap_email"),
                    imap_password=icfg.get("imap_password"),
                    min_timestamp=submit_click_ts - 15,
                    max_wait_seconds=wait_secs,
                )
                if code:
                    if _fill_greenhouse_security_code_sync(target, code):
                        # Poll up to 8 seconds for confirmation after code verification
                        for _ in range(16):
                            time.sleep(0.5)
                            try:
                                curr_url = (page.url or "").lower()
                                if any(k in curr_url for k in ("/confirmation", "confirm", "thank_you", "thanks", "success")):
                                    confirmed = True
                                    break
                                after_code_html = (target.content() or "").lower()
                                if any(sig in after_code_html for sig in confirmation_signals):
                                    confirmed = True
                                    break
                            except Exception:
                                pass

                        if confirmed:
                            browser.close()
                            return {
                                "submitted": True,
                                "status_target": "APPLIED",
                                "autopilot_status": "auto_applied",
                                "reason": f"Autonomously submitted application + verified 8-char email security code ({fill_res['filled_count']} fields)",
                                "filled_count": fill_res["filled_count"],
                                "discovered_qa": fill_res["discovered_qa"],
                            }

            has_captcha_after = (
                ("recaptcha" in after_html and ("challenge" in after_html or "verify" in after_html))
                or "challenges.cloudflare.com" in after_html
                or "turnstile" in after_html
                or "cf-turnstile" in after_html
                or target.locator("iframe[src*='challenges.cloudflare.com']").count() > 0
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
                    "reason": f"Need to Apply: ATS sent a one-time email verification code after pre-filling {fill_res['filled_count']} fields (configure Gmail App Password in Autopilot or click Open with Auto-Fill)",
                    "filled_count": fill_res["filled_count"],
                    "discovered_qa": fill_res["discovered_qa"],
                }
            elif has_captcha_after:
                return {
                    "submitted": False,
                    "status_target": "TO_APPLY",
                    "autopilot_status": "needs_manual_apply",
                    "reason": f"Need to Apply: ATS triggered a Cloudflare / CAPTCHA human verification check on submit after pre-filling {fill_res['filled_count']} fields (click Open with Auto-Fill to submit in 1 click)",
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
    imap_config: Optional[Dict[str, Any]] = None,
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

    target_loc = (profile_data.get("location") or "").strip() or "Boston, MA"
    job_loc = (job_data.get("location") or "").strip()
    wp = (job_data.get("workplace_type") or "").strip().lower()
    title = (job_data.get("title") or "").strip()
    from .location_matcher import is_job_in_range
    if not is_job_in_range(
        job_location=job_loc,
        target_location=target_loc,
        radius_miles=50,
        workplace_type=wp,
        include_remote=True,
        title=title,
    ):
        return {
            "submitted": False,
            "status_target": "TO_APPLY",
            "autopilot_status": "needs_manual_apply",
            "reason": f"Need to Apply: Job is {wp or 'on-site'} in {job_loc or 'unspecified location'}, outside your 50-mile commute radius from {target_loc} (remote or local commute only)",
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
            imap_config,
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
    imap_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Launches a visible Chromium session on the user's interactive desktop to pre-fill
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

    PACKETS_DIR.mkdir(parents=True, exist_ok=True)
    payload_path = PACKETS_DIR / "assisted_launch.json"
    payload_path.write_text(
        json.dumps(
            {
                "job_id": (job_data or {}).get("id"),
                "job_url": job_url,
                "job_data": job_data or {"url": job_url},
                "profile_data": profile_data,
                "candidate_skills": candidate_skills or [],
                "app_kit": app_kit,
                "files": files,
                "imap_config": imap_config or {},
            }
        ),
        encoding="utf-8",
    )

    runner_script = Path(__file__).resolve().parent / "assisted_runner.py"

    if os.name == "nt":
        python_exe = sys.executable
        pythonw_exe = Path(python_exe).parent / "pythonw.exe"
        exe_to_use = str(pythonw_exe if pythonw_exe.exists() else python_exe)
        DETACHED_PROCESS = 0x00000008
        CREATE_NEW_PROCESS_GROUP = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        CREATE_NO_WINDOW = 0x08000000
        flags = CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS | CREATE_NO_WINDOW
        try:
            subprocess.Popen(
                [exe_to_use, str(runner_script), str(payload_path)],
                cwd=str(runner_script.parents[2]),
                creationflags=flags,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
            )
            return {
                "success": True,
                "message": f"Visible Chromium browser window opened on your desktop for {job_url}. Pre-filling fields, tailored PDF resume & cover letter, and screening answers now!",
            }
        except Exception as e:
            logger.warning(f"Detached interactive runner launch error: {e}")

    # Fallback: launch in background thread
    from .assisted_runner import run_interactive_browser
    asyncio.create_task(asyncio.to_thread(run_interactive_browser, str(payload_path)))

    return {
        "success": True,
        "message": f"Assisted browser session opened for {job_url}. Tailored resume, cover letter, and screening answers pre-filled for your review.",
    }


async def launch_speedrun_queue(
    jobs_payload: List[Dict[str, Any]],
    imap_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Launches the desktop browser in Speed-Run queue mode, processing each job
    sequentially with a top-floating HUD for one-click verification and advancement.
    """
    if not jobs_payload:
        return {"success": False, "message": "No jobs provided for Speed-Run queue.", "count": 0}

    try:
        import playwright  # noqa: F401
    except ImportError:
        return {
            "success": False,
            "message": "Playwright is not installed. Please run 'pip install playwright && playwright install chromium'.",
            "count": 0,
        }

    PACKETS_DIR.mkdir(parents=True, exist_ok=True)
    payload_path = PACKETS_DIR / "speedrun_launch.json"
    payload_path.write_text(
        json.dumps(
            {
                "mode": "speed_run",
                "jobs": jobs_payload,
                "imap_config": imap_config or {},
            }
        ),
        encoding="utf-8",
    )

    runner_script = Path(__file__).resolve().parent / "assisted_runner.py"

    if os.name == "nt":
        python_exe = sys.executable
        pythonw_exe = Path(python_exe).parent / "pythonw.exe"
        exe_to_use = str(pythonw_exe if pythonw_exe.exists() else python_exe)
        DETACHED_PROCESS = 0x00000008
        CREATE_NEW_PROCESS_GROUP = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        CREATE_NO_WINDOW = 0x08000000
        flags = CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS | CREATE_NO_WINDOW
        try:
            subprocess.Popen(
                [exe_to_use, str(runner_script), str(payload_path)],
                cwd=str(runner_script.parents[2]),
                creationflags=flags,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
            )
            return {
                "success": True,
                "message": f"⚡ Speed-Run started with {len(jobs_payload)} job(s)! Browser opened on desktop.",
                "count": len(jobs_payload),
            }
        except Exception as e:
            logger.warning(f"Detached Speed-Run launch error: {e}")

    # Fallback: launch in background thread
    from .assisted_runner import run_interactive_browser
    asyncio.create_task(asyncio.to_thread(run_interactive_browser, str(payload_path)))

    return {
        "success": True,
        "message": f"⚡ Speed-Run started with {len(jobs_payload)} job(s) in background task.",
        "count": len(jobs_payload),
    }
