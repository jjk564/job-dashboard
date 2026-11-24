"""
Playwright ATS Form Automation & Assisted Application Engine for JobPulse.

Uses `sync_playwright` inside `asyncio.to_thread` so browser subprocesses work reliably
on Windows under any asyncio event loop policy without blocking the FastAPI event loop.
"""
import asyncio
import json
import logging
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from .bot_trap_detector import detect_bot_traps, merge_bot_traps
from .email_code_reader import poll_for_security_code_sync
from .question_answerer import PACKETS_DIR, _extract_current_company, answer_single_question

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


def resolve_direct_ats_url(company: str, title: str, original_url: Optional[str] = None) -> Optional[str]:
    """
    Attempts to discover the direct ATS job posting URL (Greenhouse, Ashby, Lever)
    for a given company and job title when the posting was scraped from an aggregator or gated portal.
    """
    import urllib.request
    import json
    import re

    if not company:
        return None

    raw_slug = company.lower().strip()
    slug_clean = re.sub(r"[^a-z0-9]+", "-", raw_slug).strip("-")
    slug_compact = re.sub(r"[^a-z0-9]+", "", raw_slug)
    slugs = list(dict.fromkeys([slug_clean, slug_compact]))

    title_words = set(re.findall(r"[a-z0-9]+", (title or "").lower()))
    title_words.difference_update({"senior", "junior", "staff", "lead", "associate", "role", "position", "the", "and", "or", "in", "at", "for"})

    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    for slug in slugs:
        # 1. Check Greenhouse public board API
        try:
            req = urllib.request.Request(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs", headers=headers)
            with urllib.request.urlopen(req, timeout=3) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8", errors="ignore"))
                    jobs = data.get("jobs", [])
                    best_match = None
                    best_score = 0
                    for j in jobs:
                        j_title = (j.get("title") or "").lower()
                        j_words = set(re.findall(r"[a-z0-9]+", j_title))
                        overlap = len(title_words.intersection(j_words))
                        if overlap > best_score and overlap >= min(2, len(title_words)):
                            best_score = overlap
                            best_match = j.get("absolute_url")
                    if best_match:
                        return best_match
        except Exception:
            pass

        # 2. Check Lever public postings API
        try:
            req = urllib.request.Request(f"https://api.lever.co/v0/postings/{slug}?mode=json", headers=headers)
            with urllib.request.urlopen(req, timeout=3) as resp:
                if resp.status == 200:
                    jobs = json.loads(resp.read().decode("utf-8", errors="ignore"))
                    best_match = None
                    best_score = 0
                    for j in jobs:
                        j_title = (j.get("text") or "").lower()
                        j_words = set(re.findall(r"[a-z0-9]+", j_title))
                        overlap = len(title_words.intersection(j_words))
                        if overlap > best_score and overlap >= min(2, len(title_words)):
                            best_score = overlap
                            best_match = j.get("hostedUrl") or j.get("applyUrl")
                    if best_match:
                        return best_match
        except Exception:
            pass

        # 3. Check Ashby public job board API
        try:
            req = urllib.request.Request(f"https://api.ashbyhq.com/posting-api/job-board/{slug}", headers=headers)
            with urllib.request.urlopen(req, timeout=3) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8", errors="ignore"))
                    jobs = data.get("jobs", [])
                    best_match = None
                    best_score = 0
                    for j in jobs:
                        j_title = (j.get("title") or "").lower()
                        j_words = set(re.findall(r"[a-z0-9]+", j_title))
                        overlap = len(title_words.intersection(j_words))
                        if overlap > best_score and overlap >= min(2, len(title_words)):
                            best_score = overlap
                            best_match = j.get("jobUrl")
                    if best_match:
                        return best_match
        except Exception:
            pass

    return None


def _select_active_form_target(page: Any) -> Any:
    """
    If the page embeds an ATS application form inside an iframe (Greenhouse, Ashby, Lever,
    Workable, BambooHR, JazzHR, Breezy, etc.), returns that Frame; otherwise checks whether
    any non-CAPTCHA iframe hosts the application form when the main page has no inputs.
    """
    ats_iframe_hints = (
        "greenhouse.io/embed",
        "ashbyhq.com",
        "lever.co",
        "workable.com",
        "bamboohr.com",
        "breezy.hr",
        "applytojob.com",
        "jazzhr.com",
        "recruitee.com",
        "jobvite.com",
        "dover.com",
        "pinpointhq.com",
        "gem.com",
    )
    captcha_iframe_hints = ("recaptcha", "hcaptcha", "turnstile", "challenges.cloudflare.com", "arkoselabs")
    try:
        for frame in page.frames:
            if frame == page.main_frame:
                continue
            f_url = (frame.url or "").lower()
            if any(c in f_url for c in captcha_iframe_hints):
                continue
            if any(d in f_url for d in ats_iframe_hints):
                return frame
        # Fallback: if main page has no form inputs, find any non-CAPTCHA iframe with form inputs
        main_inputs = page.locator("form input:visible, input[type='email']:visible, input[type='file']").count()
        if main_inputs == 0:
            best_frame = None
            best_count = 0
            for frame in page.frames:
                if frame == page.main_frame:
                    continue
                f_url = (frame.url or "").lower()
                if not f_url or f_url == "about:blank" or any(c in f_url for c in captcha_iframe_hints):
                    continue
                try:
                    cnt = frame.locator("form input, input[type='email'], input[type='file'], textarea").count()
                    if cnt > best_count:
                        best_count = cnt
                        best_frame = frame
                except Exception:
                    pass
            if best_frame is not None and best_count >= 2:
                return best_frame
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
    raw_visible_text = ""
    try:
        raw_visible_text = target.inner_text("body") or ""
        visible_body_text = raw_visible_text.lower()
    except Exception:
        raw_visible_text = ""
        visible_body_text = page_content_low

    # Live scan for bot traps / human-read instructions on the ATS page + job description
    live_traps = detect_bot_traps(
        description=job_data.get("description") or "",
        page_text=raw_visible_text,
    )
    detected_bot_traps = merge_bot_traps(job_data.get("bot_traps"), live_traps)
    manual_review_fields: List[str] = []

    def _highlight_manual_field(loc_el: Any, reason_label: str) -> None:
        try:
            loc_el.evaluate(
                """(el, lbl) => {
                    const box = el.closest('[role="radiogroup"], .select__control, fieldset') || el;
                    box.style.outline = '2px dashed #f59e0b';
                    box.style.outlineOffset = '2px';
                    box.setAttribute('data-jobpulse-needs-input', lbl || 'Needs review');
                    if (!box.title) box.title = 'JobPulse left this blank for you to verify: ' + (lbl || '');
                }""",
                reason_label[:100],
            )
        except Exception:
            pass

    # A page that contains active form inputs or an Apply button is NOT a 404/closed posting
    has_form_or_apply = False
    try:
        has_form_or_apply = target.locator(
            "button:has-text('Apply'), a:has-text('Apply'), form input, input[type='file'], input[type='email']"
        ).count() > 0
    except Exception:
        pass

    curr_target_url = (getattr(target, "url", "") or (page.url if page else "")).lower()
    apply_url = (job_data.get("apply_url") or job_data.get("url") or "").lower()
    redirected_away = ("gh_jid=" in apply_url and "gh_jid=" not in curr_target_url and "/jobs/" not in curr_target_url)

    is_closed_posting = redirected_away or (
        any(
            phrase in visible_body_text
            for phrase in (
                "no longer open",
                "no longer accepting applications",
                "position has been filled",
                "job is no longer available",
                "posting has expired",
                "posting is closed",
                "position is closed",
                "page not found",
                "404 not found",
            )
        )
    )

    login_wall = False
    try:
        pw_inputs = target.locator("input[type='password']:visible")
        if pw_inputs.count() > 0:
            login_wall = True
    except Exception:
        pass

    # 3. Fill standard contact fields (strict selectors so unrelated custom/referral boxes are never overwritten!)
    full_name = (profile_data.get("full_name") or "").strip()
    parts = full_name.split()
    first_name = parts[0] if parts else ""
    last_name = " ".join(parts[1:]) if len(parts) > 1 else ""
    email = (profile_data.get("email") or "").strip()
    phone = (profile_data.get("phone") or "").strip()
    location = (profile_data.get("location") or "").strip()
    company = _extract_current_company(profile_data)
    linkedin = (profile_data.get("linkedin_url") or "").strip()
    github = (profile_data.get("github_url") or "").strip()
    portfolio = (profile_data.get("portfolio_url") or github or linkedin).strip()

    has_split_name = False
    try:
        has_split_name = target.locator(
            'input[name*="first_name" i]:visible, input[id*="first_name" i]:visible, '
            'input[name*="firstname" i]:visible, input[id*="firstname" i]:visible, '
            'input[autocomplete="given-name"]:visible'
        ).count() > 0
    except Exception:
        pass

    field_mappings = [
        (
            'input[name*="first_name" i], input[id*="first_name" i], '
            'input[name*="firstname" i], input[id*="firstname" i], input[autocomplete="given-name"]',
            first_name,
            ("refer", "manager", "supervisor", "emergency"),
        ),
        (
            'input[name*="last_name" i], input[id*="last_name" i], '
            'input[name*="lastname" i], input[id*="lastname" i], input[autocomplete="family-name"]',
            last_name,
            ("refer", "manager", "supervisor", "emergency"),
        ),
        (
            'input[name="name" i], input[id="name" i], input[autocomplete="name"], input[name*="full_name" i], input[id*="full_name" i]',
            "" if has_split_name else full_name,
            ("refer", "company", "employer", "school", "university", "manager", "emergency"),
        ),
        (
            'input[type="email"], input[name="email" i], input[id="email" i], input[autocomplete="email"]',
            email,
            ("refer", "manager", "supervisor", "emergency"),
        ),
        (
            'input[type="tel"], input[name="phone" i], input[id="phone" i], input[autocomplete="tel"]',
            phone,
            ("refer", "manager", "supervisor", "emergency", "country", "ext", "code"),
        ),
        (
            'input[name="org" i], input[name*="current_company" i], input[id*="current_company" i], '
            'input[name*="current_employer" i], input[id*="current_employer" i]',
            company,
            ("refer", "website", "url", "search"),
        ),
        (
            'input[name*="linkedin" i], input[id*="linkedin" i], input[placeholder*="linkedin" i]',
            linkedin,
            ("how did you", "hear", "source", "refer"),
        ),
        (
            'input[name*="github" i], input[id*="github" i], input[placeholder*="github" i]',
            github,
            ("how did you", "hear", "source", "refer"),
        ),
        (
            'input[id*="portfolio" i], input[placeholder*="portfolio" i], input[name*="portfolio" i], '
            'input[name*="personal_website" i], input[id*="personal_website" i]',
            portfolio,
            ("company website", "how did you", "hear", "source"),
        ),
    ]

    for selector, val, exclude_terms in field_mappings:
        if not val:
            continue
        try:
            locs = target.locator(selector)
            cnt = min(locs.count(), 5)
            for idx_m in range(cnt):
                loc = locs.nth(idx_m)
                if not loc.is_visible() or loc.is_disabled():
                    continue
                if loc.get_attribute("readonly") is not None:
                    continue
                # Guard against matching referral/unrelated inputs
                ctx_hint = loc.evaluate("""el => {
                    const lbl = (el.labels && el.labels.length) ? Array.from(el.labels).map(l => l.innerText).join(' ') : '';
                    return `${el.id || ''} ${el.name || ''} ${el.placeholder || ''} ${el.getAttribute('aria-label') || ''} ${lbl}`.toLowerCase();
                }""")
                if any(ex in ctx_hint for ex in exclude_terms):
                    continue
                current_val = (loc.input_value() or "").strip()
                if not current_val:
                    loc.fill(val, timeout=1500)
                    filled_count += 1
                    break
        except Exception:
            pass

    # Location field handling with typeahead commit (supports Lever, Greenhouse, Ashby, and Google Places)
    clean_location = re.sub(r"[\(\[\{].*?[\)\]\}]", "", location).split("-")[0].strip() or "Boston, MA"
    loc_type_str = clean_location.replace("Massachusetts", "MA").strip()
    if clean_location:
        try:
            loc_input = target.locator(
                '#location-input:visible, input[name="location"]:visible, '
                'input[name*="candidate_location" i]:visible, input[id*="candidate_location" i]:visible, '
                'input[id="location"]:visible, input[placeholder*="location" i]:visible'
            ).first
            if loc_input.count() > 0 and not loc_input.is_disabled() and loc_input.get_attribute("readonly") is None:
                current_loc_val = (loc_input.input_value() or "").strip()
                if not current_loc_val:
                    loc_input.click()
                    # Use press_sequentially with clean location string to trigger Lever / Google Places / Ashby typeahead
                    try:
                        loc_input.press_sequentially(loc_type_str, delay=60)
                    except Exception:
                        loc_input.fill(loc_type_str)
                    filled_count += 1
                    time.sleep(0.9)
                    try:
                        suggs = target.locator(
                            '.dropdown-location:visible, #location-0:visible, .dropdown-results:visible, '
                            '.pac-item:visible, .location-typeahead-list li:visible, '
                            '[role="listbox"] [role="option"]:visible, .select__option:visible, '
                            '[class*="suggestion"]:visible'
                        )
                        sugg_count = suggs.count()
                        if sugg_count > 0:
                            best_sugg = None
                            for s_idx in range(min(5, sugg_count)):
                                s_el = suggs.nth(s_idx)
                                s_txt = (s_el.inner_text() or "").lower()
                                if any(tok in s_txt for tok in ("ma", "massachusetts", "usa", "united states")):
                                    best_sugg = s_el
                                    break
                            (best_sugg or suggs.first).click(timeout=1500)
                        else:
                            loc_input.fill(clean_location)
                            loc_input.dispatch_event("change")
                            loc_input.press("Escape")
                            loc_input.blur()
                    except Exception:
                        try:
                            loc_input.press("Escape")
                            loc_input.dispatch_event("change")
                            loc_input.blur()
                        except Exception:
                            pass
        except Exception as loc_err:
            logger.debug(f"[LOCATION FILL ERR]: {loc_err}")

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
                has_cover_textarea = target.locator(
                    'textarea[id*="cover" i], textarea[name*="cover" i], '
                    'textarea[placeholder*="cover" i], textarea[aria-label*="cover" i]'
                ).count() > 0

                # Inspect each input's attributes and surrounding DOM container text
                meta_list = []
                for idx in range(total_files):
                    el = file_inputs.nth(idx)
                    meta = el.evaluate("""el => {
                        const id = (el.id || '').toLowerCase();
                        const name = (el.name || '').toLowerCase();
                        const aria = (el.getAttribute('aria-label') || '').toLowerCase();
                        const accept = (el.getAttribute('accept') || '').toLowerCase();

                        // Detect image-only inputs (e.g. Workable candidate avatar or profile picture)
                        const isImageOnly = Boolean(
                            accept && !accept.includes('pdf') && !accept.includes('doc') && !accept.includes('text') &&
                            (accept.includes('image') || accept.includes('.jpg') || accept.includes('.png') || accept.includes('.gif'))
                        );

                        let container = '';
                        const uiEl = el.closest('[data-ui], [data-testid], [class*="field"], [class*="upload"], section, form');
                        if (uiEl) {
                            container += ' ' + (uiEl.getAttribute('data-ui') || '');
                            container += ' ' + (uiEl.getAttribute('data-testid') || '');
                            container += ' ' + (uiEl.getAttribute('aria-label') || '');
                            const lbl = uiEl.querySelector('label, h1, h2, h3, h4, h5, h6, legend, [class*="label"], [class*="title"]');
                            if (lbl) container += ' ' + (lbl.innerText || '');
                        }
                        let cur = el.parentElement;
                        for (let k = 0; k < 3 && cur; k++) {
                            const t = (cur.innerText || '').slice(0, 150);
                            if (t) container += ' ' + t;
                            cur = cur.parentElement;
                        }
                        return { id, name, aria, accept, isImageOnly, container: container.toLowerCase() };
                    }""")
                    meta_list.append({"index": idx, "locator": el, **meta})

                # Exclude image/avatar uploads from candidate document consideration
                doc_inputs = [m for m in meta_list if not m["isImageOnly"] and not any(k in m["container"] for k in ("avatar", "headshot"))]
                if not doc_inputs:
                    doc_inputs = meta_list

                # Phase 1: Semantic matching via keywords
                for m in doc_inputs:
                    haystack = f"{m['id']} {m['name']} {m['aria']} {m['container']}"
                    if any(w in haystack for w in ("cover letter", "cover_letter", "coverletter", "cover")):
                        if cover_inp is None and not has_cover_textarea:
                            cover_inp = m["locator"]
                    elif any(w in haystack for w in ("resume", "résumé", "cv", "curriculum")):
                        if resume_inp is None:
                            resume_inp = m["locator"]

                # Phase 2: Positional / count fallback
                if len(doc_inputs) == 1:
                    if resume_inp is None:
                        resume_inp = doc_inputs[0]["locator"]
                elif len(doc_inputs) >= 2:
                    if resume_inp is None and cover_inp is not None:
                        for m in doc_inputs:
                            if m["locator"] != cover_inp:
                                resume_inp = m["locator"]
                                break
                    elif cover_inp is None and resume_inp is not None and not has_cover_textarea:
                        for m in doc_inputs:
                            if m["locator"] != resume_inp:
                                cover_inp = m["locator"]
                                break
                    elif resume_inp is None and cover_inp is None:
                        resume_inp = doc_inputs[0]["locator"]
                        if not has_cover_textarea:
                            cover_inp = doc_inputs[1]["locator"]

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

            # Upload Cover Letter PDF (only if dedicated cover_inp exists and no cover letter textarea was present)
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

                # If primary attempt failed (e.g. dynamic unmount shifted elements), re-query only if explicit cover input exists
                if not cl_uploaded and not has_cover_textarea:
                    try:
                        remaining_inputs = target.locator('input[type="file"]')
                        rem_count = remaining_inputs.count()
                        if rem_count > 1:
                            for r_idx in range(rem_count):
                                r_el = remaining_inputs.nth(r_idx)
                                r_text = r_el.evaluate("""el => {
                                    const p = el.closest('div, section, fieldset, li, tr, form') || el.parentElement;
                                    return `${el.id} ${el.name} ${el.getAttribute('aria-label') || ''} ${p ? p.innerText : ''}`.toLowerCase();
                                }""")
                                if any(w in r_text for w in ("cover", "letter")):
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
        r_count = min(radios.count(), 120)
        radio_groups: Dict[str, List[Dict[str, Any]]] = {}
        for i in range(r_count):
            r_el = radios.nth(i)
            r_name = r_el.get_attribute("name") or f"group_{i}"
            info = r_el.evaluate(
                """el => {
                    const isChecked = Boolean(el.checked);
                    let optLabel = '';
                    if (el.labels && el.labels.length > 0) {
                        optLabel = Array.from(el.labels).map(l => l.innerText).join(' ').trim();
                    }
                    if (!optLabel) {
                        optLabel = (
                            el.closest('[role="radio"]')?.innerText ||
                            el.closest('[data-testid*="radio-label"]')?.innerText ||
                            el.closest('label')?.innerText ||
                            el.getAttribute('aria-label') ||
                            el.value ||
                            ''
                        ).trim();
                    }
                    if (!optLabel && el.parentElement) {
                        optLabel = (el.parentElement.innerText || '').trim();
                    }
                    let promptText = '';
                    // 1. Check fieldset > legend
                    const fs = el.closest('fieldset');
                    if (fs) {
                        const leg = fs.querySelector('legend');
                        if (leg && leg.innerText.trim()) promptText = leg.innerText.trim();
                    }
                    // 2. Check [role="radiogroup"] aria-labelledby / aria-label
                    if (!promptText) {
                        const rg = el.closest('[role="radiogroup"]');
                        if (rg) {
                            const lblBy = rg.getAttribute('aria-labelledby');
                            if (lblBy) {
                                const parts = lblBy.split(/\s+/).map(id => document.getElementById(id)?.innerText?.trim()).filter(Boolean);
                                if (parts.length) promptText = parts.join(' ');
                            }
                            if (!promptText && rg.getAttribute('aria-label')) {
                                promptText = rg.getAttribute('aria-label').trim();
                            }
                        }
                    }
                    // 3. Scoped field-container walk (never cross <form> / <section> boundaries)
                    if (!promptText) {
                        let cur = el.parentElement;
                        for (let k = 0; k < 8 && cur && !['FORM', 'BODY', 'MAIN', 'SECTION'].includes(cur.tagName); k++) {
                            const isField = (
                                cur.getAttribute('data-testid') === 'field' ||
                                cur.classList.contains('application-question') ||
                                cur.classList.contains('eun831x1') ||
                                /(?:field|question|form-group|form-item)/i.test(String(cur.className || ''))
                            );
                            if (isField) {
                                const lbl = cur.querySelector('legend, label:not(:has(input[type="radio"])), [class*="label"]:not(:has(input)), [class*="question-text"], p, h3, h4, h5');
                                if (lbl) {
                                    const txt = (lbl.innerText || '').trim();
                                    if (txt && txt.length > 2 && txt.toLowerCase() !== optLabel.toLowerCase()) {
                                        promptText = txt;
                                        break;
                                    }
                                }
                                if (cur.previousElementSibling) {
                                    const prev = (cur.previousElementSibling.innerText || '').trim();
                                    if (prev && prev.length > 2 && prev.length < 300 && prev.toLowerCase() !== optLabel.toLowerCase()) {
                                        promptText = prev;
                                        break;
                                    }
                                }
                                break;
                            }
                            cur = cur.parentElement;
                        }
                    }
                    const isReq = el.hasAttribute('required') || el.getAttribute('aria-required') === 'true' || (promptText && promptText.includes('*'));
                    return { optLabel, promptText, isReq, isChecked };
                }"""
            )
            radio_groups.setdefault(r_name, []).append({"index": i, **info})

        for r_name, items in radio_groups.items():
            # Skip radio groups that already have a selection
            if any(it.get("isChecked") for it in items):
                continue
            prompt = next((it["promptText"] for it in items if it.get("promptText")), r_name).replace("*", "").strip()
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

            if qa["confidence"] == "manual_needed" or not (qa.get("answer") or "").strip():
                if is_req:
                    unanswered_required.append(prompt)
                manual_review_fields.append(prompt)
                _highlight_manual_field(radios.nth(items[0]["index"]), prompt)
                continue

            desired_ans = (qa.get("answer") or "").strip().lower()
            matched_item = next(
                (it for it in items if it["optLabel"].lower() == desired_ans),
                None,
            )
            if not matched_item:
                matched_item = next(
                    (it for it in items if desired_ans in it["optLabel"].lower() or it["optLabel"].lower() in desired_ans),
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
                manual_review_fields.append(prompt)
                _highlight_manual_field(radios.nth(items[0]["index"]), prompt)
    except Exception as e:
        logger.debug(f"Radio group discovery error: {e}")

    # 5.5 Custom Button-based Radio / Yes-No Toggle Groups (Ashby, Workable, Greenhouse React, Lever)
    try:
        custom_groups = target.locator(
            "[role='radiogroup']:visible, "
            "[class*='yesno' i]:visible, "
            "[class*='yes-no' i]:visible, "
            "[data-testid*='yes-no' i]:visible, "
            "[data-testid*='boolean' i]:visible"
        )
        cg_count = min(custom_groups.count(), 40)
        for g_idx in range(cg_count):
            grp = custom_groups.nth(g_idx)
            try:
                # Skip if this group already wraps native <input type="radio"> handled above
                if grp.locator("input[type='radio']").count() > 0:
                    continue
                btns = grp.locator("button:visible, [role='radio']:visible")
                b_cnt = btns.count()
                if b_cnt < 2 or b_cnt > 10:
                    continue
                g_info = grp.evaluate("""el => {
                    const opts = Array.from(el.querySelectorAll('button, [role="radio"]'))
                        .filter(b => b.offsetParent !== null)
                        .map(b => ({
                            text: (b.innerText || b.getAttribute('aria-label') || '').trim(),
                            active: b.getAttribute('aria-checked') === 'true' || b.getAttribute('aria-pressed') === 'true' || /active|selected|checked/i.test(String(b.className || ''))
                        }));
                    let prompt = '';
                    const lblBy = el.getAttribute('aria-labelledby');
                    if (lblBy) {
                        prompt = lblBy.split(/\s+/).map(id => document.getElementById(id)?.innerText?.trim()).filter(Boolean).join(' ');
                    }
                    if (!prompt && el.getAttribute('aria-label')) prompt = el.getAttribute('aria-label').trim();
                    if (!prompt) {
                        let cur = el.parentElement;
                        for (let k = 0; k < 5 && cur && !['FORM', 'BODY', 'MAIN', 'SECTION'].includes(cur.tagName); k++) {
                            const lbl = cur.querySelector('label, legend, [class*="label"], [class*="question"], p, h3, h4');
                            if (lbl && !el.contains(lbl) && (lbl.innerText || '').trim().length > 2) {
                                prompt = lbl.innerText.trim();
                                break;
                            }
                            cur = cur.parentElement;
                        }
                    }
                    const isReq = el.getAttribute('aria-required') === 'true' || (prompt && prompt.includes('*'));
                    return { opts, prompt, isReq };
                }""")
                opts_meta = g_info.get("opts") or []
                if any(o.get("active") for o in opts_meta):
                    continue
                prompt = (g_info.get("prompt") or "").replace("*", "").strip()
                opt_texts = [o["text"] for o in opts_meta if o.get("text")]
                if not prompt or len(opt_texts) < 2:
                    continue
                qa = answer_single_question(
                    question_text=prompt,
                    job_data=job_data,
                    profile_data=profile_data,
                    candidate_skills=candidate_skills,
                    app_kit=app_kit,
                    options=opt_texts,
                    field_type="radio",
                    required=bool(g_info.get("isReq")),
                )
                discovered_qa.append(qa)
                if qa["confidence"] == "manual_needed" or not (qa.get("answer") or "").strip():
                    if g_info.get("isReq"):
                        unanswered_required.append(prompt)
                    manual_review_fields.append(prompt)
                    _highlight_manual_field(grp, prompt)
                    continue
                desired = (qa.get("answer") or "").strip().lower()
                target_idx = next((idx for idx, txt in enumerate(opt_texts) if txt.lower() == desired), None)
                if target_idx is None:
                    target_idx = next((idx for idx, txt in enumerate(opt_texts) if desired in txt.lower() or txt.lower() in desired), None)
                if target_idx is not None:
                    btns.nth(target_idx).click(timeout=1500)
                    filled_count += 1
            except Exception as cg_err:
                logger.debug(f"[CUSTOM RADIO ERR] idx={g_idx}: {cg_err}")
    except Exception as e:
        logger.debug(f"Custom radio group error: {e}")

    # 5.7 Checkboxes (Privacy Policy, Terms, GDPR, Certifications, SMS Consent)
    try:
        checkboxes = target.locator("input[type='checkbox'], [role='checkbox']:visible")
        cb_count = min(checkboxes.count(), 40)
        for c_idx in range(cb_count):
            cb = checkboxes.nth(c_idx)
            try:
                cb_info = cb.evaluate("""el => {
                    const isInput = el.tagName.toLowerCase() === 'input';
                    const isChecked = isInput ? Boolean(el.checked) : (el.getAttribute('aria-checked') === 'true');
                    const isDisabled = isInput ? Boolean(el.disabled) : (el.getAttribute('aria-disabled') === 'true');
                    const idStr = `${el.id || ''} ${el.name || ''} ${el.className || ''}`.toLowerCase();
                    // Never touch CAPTCHA checkboxes!
                    const isCaptcha = idStr.includes('captcha') || idStr.includes('turnstile') || Boolean(el.closest('.g-recaptcha, .h-captcha, .cf-turnstile'));
                    let labelText = '';
                    if (isInput && el.labels && el.labels.length > 0) {
                        labelText = Array.from(el.labels).map(l => l.innerText).join(' ').trim();
                    }
                    if (!labelText) {
                        const lbl = el.closest('label');
                        if (lbl) labelText = (lbl.innerText || '').trim();
                    }
                    if (!labelText && el.getAttribute('aria-label')) {
                        labelText = el.getAttribute('aria-label').trim();
                    }
                    if (!labelText && el.parentElement) {
                        labelText = (el.parentElement.innerText || '').trim().slice(0, 260);
                    }
                    const isReq = el.hasAttribute('required') || el.getAttribute('aria-required') === 'true' || labelText.includes('*');
                    return { isInput, isChecked, isDisabled, isCaptcha, labelText, isReq };
                }""")
                if cb_info.get("isCaptcha") or cb_info.get("isChecked") or cb_info.get("isDisabled"):
                    continue
                cb_label = (cb_info.get("labelText") or "").replace("*", "").strip()
                if not cb_label or len(cb_label) < 3:
                    continue
                qa = answer_single_question(
                    question_text=cb_label,
                    job_data=job_data,
                    profile_data=profile_data,
                    candidate_skills=candidate_skills,
                    app_kit=app_kit,
                    options=["Yes", "No"],
                    field_type="checkbox",
                    required=bool(cb_info.get("isReq")),
                )
                ans_low = (qa.get("answer") or "").strip().lower()
                if qa["confidence"] != "manual_needed" and ans_low in ("yes", "true", "i agree", "i acknowledge", "i consent", "accept", "agree"):
                    try:
                        if cb_info.get("isInput"):
                            cb.check(force=True, timeout=1200)
                        else:
                            cb.click(force=True, timeout=1200)
                        filled_count += 1
                    except Exception:
                        try:
                            cb.evaluate("el => (el.closest('label') || el).click()")
                            filled_count += 1
                        except Exception:
                            pass
                elif cb_info.get("isReq") and qa["confidence"] == "manual_needed":
                    unanswered_required.append(cb_label[:80])
                    manual_review_fields.append(cb_label[:80])
                    _highlight_manual_field(cb, cb_label[:80])
            except Exception as cb_err:
                logger.debug(f"[CHECKBOX ERR] idx={c_idx}: {cb_err}")
    except Exception as e:
        logger.debug(f"Checkbox discovery error: {e}")

    # 6. Inspect and answer remaining labeled text inputs, textareas, selects, and React/Custom comboboxes
    try:
        elements = target.locator(
            "input:visible:not([type='file']):not([type='radio']):not([type='checkbox']):not([type='hidden']):not([type='submit']):not([type='button']):not([type='search']), "
            "textarea:visible, select:visible, "
            "div[role='combobox']:visible, button[role='combobox']:visible, "
            "button[aria-haspopup='listbox']:visible, div[aria-haspopup='listbox']:visible"
        )
        el_count = min(elements.count(), 150)
        handled_containers = set()
        logger.debug(f"[LOOP START] total elements={el_count}")
        for i in range(el_count):
            el = elements.nth(i)
            el_id = ""
            try:
                if el.is_disabled():
                    continue
                if el.get_attribute("readonly") is not None and (el.get_attribute("role") or "").lower() != "combobox":
                    continue
                tag_name = (el.evaluate("el => el.tagName.toLowerCase()")) or "input"
                inp_type = (el.get_attribute("type") or "text").lower()
                role_attr = (el.get_attribute("role") or "").lower()
                aria_popup = (el.get_attribute("aria-haspopup") or "").lower()
                el_id = el.get_attribute("id") or ""
                el_name = el.get_attribute("name") or ""
                is_combobox = role_attr == "combobox" or aria_popup == "listbox"

                # Deduplicate React-Select wrapper + inner <input role="combobox"> so each combobox is handled once
                if is_combobox:
                    container_sig = el.evaluate("""el => {
                        const c = el.closest('.select__control, [data-testid="field"], .application-question, [class*="select-container"]');
                        if (!c) return '';
                        if (!c.dataset.jpSig) c.dataset.jpSig = 'jp_' + Math.random().toString(36).slice(2, 9);
                        return c.dataset.jpSig;
                    }""")
                    if container_sig and container_sig in handled_containers:
                        continue
                    if container_sig:
                        handled_containers.add(container_sig)

                logger.debug(f"[LOOP ITEM] i={i}/{el_count}, tag={tag_name}, id={el_id}, role={role_attr}, combo={is_combobox}")

                is_req = (
                    el.get_attribute("required") is not None
                    or el.get_attribute("aria-required") == "true"
                )

                if tag_name in ("input", "textarea") and not is_combobox:
                    existing_val = (el.input_value() or "").strip()
                    if existing_val:
                        continue
                elif tag_name == "select":
                    cur_sel = el.evaluate("""el => {
                        const opt = el.options[el.selectedIndex];
                        const txt = opt ? (opt.text || '').trim().toLowerCase() : '';
                        const val = (el.value || '').trim();
                        const isPlaceholder = !val || !txt || /^(select|choose|--|please select|none|-+)$/i.test(txt) || txt.startsWith('select ') || txt.startsWith('choose ');
                        return { isPlaceholder, txt };
                    }""")
                    if not cur_sel.get("isPlaceholder"):
                        continue
                elif is_combobox:
                    existing_txt = (el.inner_text() or "").strip().lower()
                    if not existing_txt:
                        try:
                            existing_txt = el.evaluate("""el => {
                                const c = el.closest('.select__value-container, [class*="value-container"], .select__control');
                                if (!c) return '';
                                const singleVal = c.querySelector('.select__single-value, [class*="singleValue"], [class*="selected"]');
                                return singleVal ? (singleVal.innerText || '').trim() : '';
                            }""").lower()
                        except Exception:
                            pass
                    is_placeholder_cb = (
                        not existing_txt
                        or existing_txt in ("select", "select...", "select an option", "choose", "choose...", "--", "search", "type to search")
                        or existing_txt.startswith(("select ", "choose "))
                    )
                    if not is_placeholder_cb:
                        continue

                # Accurate, scoped label extraction (never climbs across whole form; never rejects labels containing "select"!)
                label_text = el.evaluate(
                    """el => {
                        const isPlaceholderOnly = (txt) => {
                            const t = (txt || '').trim().toLowerCase();
                            return !t || t.length < 2 || ['select', 'select...', 'select an option', 'select one', 'choose', 'choose...', 'choose an option', '--', 'search', 'textbox', 'combobox', 'option', 'please select'].includes(t);
                        };
                        // 1. Native el.labels
                        if (el.labels && el.labels.length > 0) {
                            const t = Array.from(el.labels).map(l => l.innerText).join(' ').trim();
                            if (!isPlaceholderOnly(t)) return t;
                        }
                        // 2. aria-labelledby (supports space-separated multi-ID lists!)
                        const ariaLbl = el.getAttribute('aria-labelledby');
                        if (ariaLbl) {
                            const parts = ariaLbl.split(/\s+/).map(id => document.getElementById(id)?.innerText?.trim()).filter(Boolean);
                            const joined = parts.join(' ').trim();
                            if (!isPlaceholderOnly(joined)) return joined;
                        }
                        // 3. aria-label (unless placeholder-only)
                        const aria = (el.getAttribute('aria-label') || '').trim();
                        if (!isPlaceholderOnly(aria)) return aria;
                        // 4. label[for=id]
                        if (el.id) {
                            try {
                                const forLbl = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
                                if (forLbl && !isPlaceholderOnly(forLbl.innerText)) return forLbl.innerText.trim();
                            } catch (e) {}
                        }
                        // 5. Closest fieldset > legend
                        const fs = el.closest('fieldset');
                        if (fs) {
                            const leg = fs.querySelector('legend');
                            if (leg && !isPlaceholderOnly(leg.innerText)) return leg.innerText.trim();
                        }
                        // 6. Scoped field-container walk (STOP before crossing <form>/<section>/<main> or multi-field wrappers!)
                        let cur = el.parentElement;
                        for (let k = 0; k < 8 && cur && !['FORM', 'BODY', 'MAIN', 'SECTION'].includes(cur.tagName); k++) {
                            // Stop if this wrapper contains more than 1 distinct top-level input/select/textarea/combobox
                            const siblingControls = cur.querySelectorAll('input:not([type="hidden"]):not([type="radio"]):not([type="checkbox"]), textarea, select, [role="combobox"], [aria-haspopup="listbox"]');
                            const distinctControls = new Set(Array.from(siblingControls).map(c => c.closest('.select__control') || c));
                            if (distinctControls.size > 1) break;

                            const candidates = cur.querySelectorAll('label, legend, [data-testid*="label"], [class*="label"], [class*="question"], h3, h4, h5, h6, p');
                            for (const c of candidates) {
                                if (c === el || el.contains(c)) continue;
                                // Only take text that precedes the control or wraps it cleanly
                                const ht = (c.innerText || '').trim();
                                if (!isPlaceholderOnly(ht) && ht !== (el.innerText || '').trim() && ht.length <= 320) {
                                    return ht;
                                }
                            }
                            // Check immediate preceding label-like sibling
                            if (cur.previousElementSibling) {
                                const prevTag = cur.previousElementSibling.tagName;
                                if (['LABEL', 'SPAN', 'P', 'H3', 'H4', 'H5', 'DIV'].includes(prevTag) &&
                                    !cur.previousElementSibling.querySelector('input, select, textarea, [role="combobox"]')) {
                                    const prevTxt = (cur.previousElementSibling.innerText || '').trim();
                                    if (!isPlaceholderOnly(prevTxt) && prevTxt.length <= 300) {
                                        return prevTxt;
                                    }
                                }
                            }
                            cur = cur.parentElement;
                        }
                        return (el.getAttribute('placeholder') || el.getAttribute('name') || el.getAttribute('id') || '').trim();
                    }"""
                )
                label_clean = (label_text or "").replace("*", "").strip()
                if "*" in (label_text or ""):
                    is_req = True

                if not label_clean or len(label_clean) < 2 or label_clean.lower() in ("select", "choose", "first option", "select..."):
                    raw_id = (el.get_attribute("id") or el.get_attribute("name") or "").replace("_", " ").replace("-", " ")
                    if any(k in raw_id.lower() for k in ("race", "ethnicity", "hispanic", "veteran", "disability", "gender", "pronoun", "country", "state", "city", "school", "degree", "major", "salary")):
                        label_clean = raw_id

                # Sanitize EEO select labels on Lever / Greenhouse so option text never pollutes the label
                raw_name = (el.get_attribute("name") or "").lower()
                raw_id_attr = (el.get_attribute("id") or "").lower()
                if "eeo[race]" in raw_name or "race" in raw_id_attr or "job_application_race" in raw_name:
                    label_clean = "Race"
                elif "eeo[gender]" in raw_name or "gender" in raw_id_attr or "job_application_gender" in raw_name:
                    label_clean = "Gender"
                elif "eeo[veteran]" in raw_name or "veteran" in raw_id_attr:
                    label_clean = "Veteran status"
                elif "eeo[disability]" in raw_name or "disability" in raw_id_attr:
                    label_clean = "Disability status"

                if not label_clean or len(label_clean) < 2:
                    continue

                options_list: Optional[List[str]] = None
                menu_locators: List[Any] = []
                combobox_opened = False

                if tag_name == "select":
                    options_list = el.evaluate(
                        "el => Array.from(el.options).map(o => o.text.trim()).filter(Boolean)"
                    )
                elif is_combobox:
                    # Open combobox FIRST so we can read its actual options and pass them to answer_single_question!
                    try:
                        el.scroll_into_view_if_needed(timeout=1500)
                        el.click(force=True, timeout=1200)
                        combobox_opened = True
                        time.sleep(0.3)
                    except Exception as click_err:
                        logger.debug(f"[COMBOBOX OPEN ERR] {el_id}: {click_err}")

                    aria_ctrl = el.get_attribute("aria-controls") or el.get_attribute("aria-owns") or ""
                    if aria_ctrl:
                        menu_locators.append(target.locator(f"#{aria_ctrl}"))
                    if el_id:
                        menu_locators.append(target.locator(f"#{el_id}-list"))
                    menu_locators.append(target.locator("[role='listbox']:visible, .select__menu:visible, ul[data-testid='menuList']:visible").first)

                    for m_loc in menu_locators:
                        try:
                            opts_found = m_loc.locator("[role='option'], li, div[data-testid='menuListLabel'], .select__option").all_inner_texts()
                            cleaned_opts = [o.strip() for o in opts_found if o and o.strip()]
                            if cleaned_opts:
                                options_list = cleaned_opts
                                break
                        except Exception:
                            pass

                effective_ftype = (
                    "combobox" if is_combobox else
                    ("number" if inp_type == "number" else
                     ("date" if inp_type == "date" else
                      ("url" if inp_type == "url" else tag_name)))
                )

                qa = answer_single_question(
                    question_text=label_clean,
                    job_data=job_data,
                    profile_data=profile_data,
                    candidate_skills=candidate_skills,
                    app_kit=app_kit,
                    options=options_list,
                    field_type=effective_ftype,
                    required=is_req,
                )
                logger.debug(f"[LOOP QA] {el_id or label_clean[:30]}: ans={qa.get('answer')}, conf={qa.get('confidence')}")
                discovered_qa.append(qa)

                # NEVER paste low-confidence guesses or generic essays into unrecognized fields!
                ans_val = (qa.get("answer") or "").strip()
                if qa["confidence"] == "manual_needed" or not ans_val:
                    if combobox_opened:
                        try:
                            el.press("Escape")
                            el.blur()
                        except Exception:
                            pass
                    if is_req or qa["confidence"] == "manual_needed":
                        if is_req:
                            unanswered_required.append(label_clean)
                        manual_review_fields.append(label_clean)
                        _highlight_manual_field(el, label_clean)
                    continue

                # Type-safe formatting guards before filling
                if effective_ftype == "number":
                    num_clean = re.sub(r"[^0-9.]", "", ans_val.split("-")[0])
                    if not num_clean:
                        if is_req:
                            unanswered_required.append(label_clean)
                        _highlight_manual_field(el, label_clean)
                        continue
                    ans_val = num_clean
                elif effective_ftype == "date" and not re.match(r"^\d{4}-\d{2}-\d{2}$", ans_val):
                    if is_req:
                        unanswered_required.append(label_clean)
                    _highlight_manual_field(el, label_clean)
                    continue
                elif effective_ftype == "url" and not ans_val.lower().startswith(("http://", "https://")):
                    ans_val = "https://" + ans_val

                logger.debug(f"[LOOP APPLYING] {el_id}: role={role_attr}, ans={ans_val}")
                if tag_name == "select":
                    sel_done = False
                    try:
                        el.select_option(label=ans_val, timeout=1500)
                        sel_done = True
                        filled_count += 1
                    except Exception:
                        pass
                    if not sel_done:
                        try:
                            matched_val = el.evaluate("""(sel, targetText) => {
                                const opts = Array.from(sel.options);
                                const targetLower = String(targetText).toLowerCase().trim();
                                const exact = opts.find(o => o.text.trim().toLowerCase() === targetLower);
                                if (exact) return exact.value || exact.text;
                                const partial = opts.find(o => {
                                    const t = o.text.trim().toLowerCase();
                                    return t && (t.includes(targetLower) || targetLower.includes(t));
                                });
                                if (partial) return partial.value || partial.text;
                                return null;
                            }""", str(ans_val))
                            if matched_val is not None:
                                el.select_option(value=matched_val, timeout=1500)
                                filled_count += 1
                            elif is_req:
                                unanswered_required.append(label_clean)
                                _highlight_manual_field(el, label_clean)
                        except Exception as sel_err:
                            logger.debug(f"[SELECT FALLBACK ERR] {el_id}: {sel_err}")
                elif is_combobox:
                    opt_loc = None
                    ans_lower = str(ans_val).strip().lower()

                    def _find_matching_option(loc_list: List[Any], search_val: str) -> Any:
                        sv_low = search_val.strip().lower()
                        for m_loc in loc_list:
                            try:
                                opt_els = m_loc.locator("[role='option'], li, div[data-testid='menuListLabel'], .select__option")
                                o_cnt = min(opt_els.count(), 40)
                                exact_el = None
                                partial_el = None
                                for oi in range(o_cnt):
                                    cand = opt_els.nth(oi)
                                    if not cand.is_visible():
                                        continue
                                    otxt = (cand.inner_text() or "").strip().lower()
                                    if not otxt:
                                        continue
                                    if otxt == sv_low:
                                        exact_el = cand
                                        break
                                    if not partial_el and (sv_low in otxt or otxt in sv_low):
                                        partial_el = cand
                                if exact_el is not None:
                                    return exact_el
                                if partial_el is not None:
                                    return partial_el
                            except Exception:
                                pass
                        return None

                    opt_loc = _find_matching_option(menu_locators, str(ans_val))

                    # Async/searchable combobox (e.g. School or Location): type search term to load options
                    if opt_loc is None and tag_name == "input":
                        try:
                            search_term = str(ans_val).split(",")[0].strip()
                            if search_term:
                                el.press_sequentially(search_term, delay=35)
                                time.sleep(0.45)
                                aria_ctrl_after = el.get_attribute("aria-controls") or el.get_attribute("aria-owns") or ""
                                if aria_ctrl_after:
                                    menu_locators.insert(0, target.locator(f"#{aria_ctrl_after}"))
                                opt_loc = _find_matching_option(menu_locators, search_term)
                        except Exception as type_err:
                            logger.debug(f"[COMBOBOX TYPE ERR] {el_id}: {type_err}")

                    if opt_loc is not None:
                        try:
                            opt_loc.click(force=True, timeout=1500)
                            filled_count += 1
                            time.sleep(0.25)
                        except Exception as e:
                            logger.debug(f"[COMBOBOX FILL error] {el_id}: {e}")
                            try:
                                el.press("Escape")
                                el.blur()
                            except Exception:
                                pass
                    else:
                        logger.debug(f"[COMBOBOX NO OPT_LOC FOUND] {el_id}: ans={ans_val}")
                        # Always close menu cleanly so an open dropdown NEVER blocks clicks below!
                        try:
                            if tag_name == "input":
                                el.fill("", timeout=800)
                            el.press("Escape")
                            el.blur()
                        except Exception:
                            pass
                        if is_req:
                            unanswered_required.append(label_clean)
                            manual_review_fields.append(label_clean)
                            _highlight_manual_field(el, label_clean)
                else:
                    el.fill(str(ans_val), timeout=1500)
                    filled_count += 1
            except Exception as item_err:
                logger.debug(f"[LOOP ITEM ERROR] i={i}, id={el_id}: {item_err}")
                try:
                    page.keyboard.press("Escape")
                except Exception:
                    pass
    except Exception as e:
        logger.debug(f"Custom field discovery error: {e}")

    # Close any lingering dropdowns / popovers / sticky focus so user clicks (CAPTCHAs & Submit) are never obstructed
    try:
        page.keyboard.press("Escape")
        target.evaluate("() => { if (document.activeElement && document.activeElement.blur) document.activeElement.blur(); }")
    except Exception:
        pass

    return {
        "target": target,
        "filled_count": filled_count,
        "resume_uploaded": resume_uploaded,
        "cover_letter_uploaded": cover_letter_uploaded,
        "has_captcha": has_captcha,
        "login_wall": login_wall,
        "is_closed_posting": is_closed_posting,
        "unanswered_required": list(dict.fromkeys(unanswered_required)),
        "manual_review_fields": list(dict.fromkeys(manual_review_fields)),
        "bot_traps": detected_bot_traps,
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
                    "bot_traps": [],
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
            found_traps = fill_res.get("bot_traps") or []

            if fill_res["is_closed_posting"]:
                browser.close()
                return {
                    "submitted": False,
                    "status_target": "REJECTED",
                    "autopilot_status": "expired",
                    "reason": "Posting closed: External career page indicates this posting is closed, removed, or redirected",
                    "filled_count": fill_res["filled_count"],
                    "discovered_qa": fill_res["discovered_qa"],
                    "bot_traps": found_traps,
                }

            human_traps = [t for t in found_traps if t.get("type") == "human_check"]
            if human_traps:
                trap_action = human_traps[0].get("action_required") or "Employer attention-check instruction detected"
                browser.close()
                return {
                    "submitted": False,
                    "status_target": "TO_APPLY",
                    "autopilot_status": "needs_manual_apply",
                    "reason": f"⚠️ Bot Trap Detected: {trap_action}",
                    "filled_count": fill_res["filled_count"],
                    "discovered_qa": fill_res["discovered_qa"],
                    "bot_traps": found_traps,
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
                    "bot_traps": found_traps,
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
                    "bot_traps": found_traps,
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
                    "bot_traps": found_traps,
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
