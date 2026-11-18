"""
Playwright ATS Form Automation & Assisted Application Engine for JobPulse.

Supports:
1. Autonomous Application Submission (`attempt_autonomous_submission`):
   - Navigates to job posting / ATS form (Greenhouse, Lever, Ashby, Workable, Breezy, generic forms)
   - Detects login walls or CAPTCHA gates (never attempts to solve or bypass CAPTCHAs; immediately
     routes gated postings to 'Need to Apply' / TO_APPLY)
   - Uploads tailored Resume PDF and Cover Letter PDF to file inputs
   - Inspects and answers all standard and custom form questions via `answer_single_question`
   - Submits the application when all required fields are confidently satisfied, or routes to
     'Need to Apply' (TO_APPLY) with a detailed reason and pre-generated answers.
2. Interactive Assisted Application (`launch_assisted_application`):
   - Opens a visible Chromium window, pre-fills all standard fields, uploads tailored resume & cover letter,
     and fills custom questions so the user can review and submit in 1 click.
"""
import asyncio
import logging
import os
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
    "JazzHR",
    "applytojob.com",
    "dover.com",
    "gem.com",
    "pinpointhq.com",
    "personio.de",
    "personio.com",
    "bamboo.hr",
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


async def _fill_form_on_page(
    page: Any,
    job_data: Dict[str, Any],
    profile_data: Dict[str, Any],
    candidate_skills: Optional[List[Any]] = None,
    app_kit: Optional[Dict[str, Any]] = None,
    files: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    Discovers and fills standard inputs, file uploads (Resume/Cover Letter), and custom screening
    questions on a Playwright Page.
    Never interacts with or attempts to solve any CAPTCHA challenge.
    """
    filled_count = 0
    unanswered_required: List[str] = []
    discovered_qa: List[Dict[str, Any]] = []
    resume_uploaded = False
    cover_letter_uploaded = False

    # 1. If the page has an 'Apply' / 'Apply for this job' button and no visible form inputs yet, click it
    try:
        input_count = await page.locator("form input, input[type='email'], input[type='file']").count()
        if input_count == 0:
            apply_btn = page.locator(
                "a:has-text('Apply for this job'), button:has-text('Apply for this job'), "
                "a:has-text('Apply Now'), button:has-text('Apply Now'), "
                "a:has-text('Apply'), button:has-text('Apply')"
            ).first
            if await apply_btn.count() > 0 and await apply_btn.is_visible():
                await apply_btn.click(timeout=4000)
                await asyncio.sleep(1.5)
    except Exception:
        pass

    # 2. Check for login wall or CAPTCHA gate (strictly respect safety rules: never solve or bypass CAPTCHAs)
    page_content_low = (await page.content()).lower()
    captcha_selectors = [
        "iframe[src*='recaptcha']",
        "iframe[src*='hcaptcha']",
        "iframe[src*='turnstile']",
        ".g-recaptcha",
        ".h-captcha",
        ".cf-turnstile",
        "#cf-turnstile",
    ]
    has_captcha = False
    for sel in captcha_selectors:
        try:
            loc = page.locator(sel)
            if await loc.count() > 0 and await loc.first.is_visible():
                has_captcha = True
                break
        except Exception:
            pass

    if "verify you are human" in page_content_low or "cf-browser-verification" in page_content_low:
        has_captcha = True

    login_wall = False
    try:
        pw_inputs = page.locator("input[type='password']:visible")
        if await pw_inputs.count() > 0:
            login_wall = True
    except Exception:
        pass

    # 3. Fill standard contact fields first
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
        ('input[name*="first_name" i], input[id*="first_name" i], input[autocomplete="given-name"]', first_name),
        ('input[name*="last_name" i], input[id*="last_name" i], input[autocomplete="family-name"]', last_name),
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
            loc = page.locator(selector).first
            if await loc.count() > 0 and await loc.is_visible():
                current_val = await loc.input_value()
                if not current_val:
                    await loc.fill(val, timeout=2000)
                    filled_count += 1
        except Exception:
            pass

    # 4. Upload Tailored Resume & Cover Letter PDFs to `<input type="file">`
    if files:
        resume_pdf = files.get("resume_pdf")
        cover_pdf = files.get("cover_letter_pdf")
        try:
            file_inputs = page.locator('input[type="file"]')
            f_count = await file_inputs.count()
            for idx in range(f_count):
                f_inp = file_inputs.nth(idx)
                name_attr = ((await f_inp.get_attribute("name")) or "").lower()
                id_attr = ((await f_inp.get_attribute("id")) or "").lower()
                aria_attr = ((await f_inp.get_attribute("aria-label")) or "").lower()
                combined_attr = f"{name_attr} {id_attr} {aria_attr}"

                if any(k in combined_attr for k in ("cover", "letter", "cl")):
                    if cover_pdf and os.path.exists(cover_pdf):
                        await f_inp.set_input_files(cover_pdf)
                        cover_letter_uploaded = True
                        filled_count += 1
                else:
                    if resume_pdf and os.path.exists(resume_pdf) and not resume_uploaded:
                        await f_inp.set_input_files(resume_pdf)
                        resume_uploaded = True
                        filled_count += 1
                    elif cover_pdf and os.path.exists(cover_pdf) and not cover_letter_uploaded:
                        await f_inp.set_input_files(cover_pdf)
                        cover_letter_uploaded = True
                        filled_count += 1
        except Exception as e:
            logger.debug(f"File input upload check: {e}")

    # 5. Inspect and answer all remaining labeled inputs, textareas, and selects
    try:
        elements = page.locator(
            "input[type='text']:visible, input[type='number']:visible, input[type='url']:visible, "
            "textarea:visible, select:visible"
        )
        el_count = min(await elements.count(), 40)
        for i in range(el_count):
            el = elements.nth(i)
            try:
                tag_name = (await el.evaluate("el => el.tagName.toLowerCase()")) or "input"
                inp_type = ((await el.get_attribute("type")) or "text").lower()
                is_req = (
                    (await el.get_attribute("required")) is not None
                    or (await el.get_attribute("aria-required")) == "true"
                )

                # Skip if already filled
                if tag_name in ("input", "textarea"):
                    existing_val = (await el.input_value()).strip()
                    if existing_val:
                        continue

                # Determine question label text
                label_text = await el.evaluate(
                    """el => {
                        if (el.labels && el.labels.length > 0) {
                            return Array.from(el.labels).map(l => l.innerText).join(' ').trim();
                        }
                        const aria = el.getAttribute('aria-label');
                        if (aria) return aria.trim();
                        const wrapper = el.closest('label, .field, .application-question, .form-group, [data-qa]');
                        if (wrapper) {
                            const lbl = wrapper.querySelector('label, .label, h4, legend');
                            if (lbl) return lbl.innerText.trim();
                        }
                        return el.getAttribute('placeholder') || el.getAttribute('name') || '';
                    }"""
                )
                label_clean = (label_text or "").replace("*", "").strip()
                if not label_clean or len(label_clean) < 2:
                    continue

                options_list: Optional[List[str]] = None
                if tag_name == "select":
                    options_list = await el.evaluate(
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
                discovered_qa.append(qa)

                if qa["confidence"] == "manual_needed" and is_req:
                    unanswered_required.append(label_clean)
                    continue

                ans_val = qa.get("answer") or ""
                if not ans_val:
                    if is_req:
                        unanswered_required.append(label_clean)
                    continue

                if tag_name == "select":
                    await el.select_option(label=ans_val, timeout=2000)
                    filled_count += 1
                else:
                    await el.fill(str(ans_val), timeout=2000)
                    filled_count += 1
            except Exception:
                pass
    except Exception as e:
        logger.debug(f"Custom field discovery error: {e}")

    return {
        "filled_count": filled_count,
        "resume_uploaded": resume_uploaded,
        "cover_letter_uploaded": cover_letter_uploaded,
        "has_captcha": has_captcha,
        "login_wall": login_wall,
        "unanswered_required": unanswered_required,
        "discovered_qa": discovered_qa,
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
    Attempts to autonomously fill and submit a job application via Playwright.
    Returns:
      {
        "submitted": bool,
        "status_target": "APPLIED" | "TO_APPLY",
        "autopilot_status": "auto_applied" | "needs_manual_apply",
        "reason": str,
        "filled_count": int,
        "discovered_qa": List[Dict],
      }
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

    # Check if candidate profile has required core identity fields (full_name + email)
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
        from playwright.async_api import async_playwright
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
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=headless)
            context = await browser.new_context()
            page = await context.new_page()
            try:
                resp = await page.goto(job_url, timeout=22000, wait_until="domcontentloaded")
                if resp and resp.status >= 400:
                    await browser.close()
                    return {
                        "submitted": False,
                        "status_target": "TO_APPLY",
                        "autopilot_status": "needs_manual_apply",
                        "reason": f"Need to Apply: Posting returned HTTP {resp.status} (documents & Q&A ready)",
                        "filled_count": 0,
                        "discovered_qa": [],
                    }

                await asyncio.sleep(1.5)
                fill_res = await _fill_form_on_page(
                    page=page,
                    job_data=job_data,
                    profile_data=profile_data,
                    candidate_skills=candidate_skills,
                    app_kit=app_kit,
                    files=files,
                )

                if fill_res["login_wall"]:
                    await browser.close()
                    return {
                        "submitted": False,
                        "status_target": "TO_APPLY",
                        "autopilot_status": "needs_manual_apply",
                        "reason": "Need to Apply: Portal requires candidate account login / password",
                        "filled_count": fill_res["filled_count"],
                        "discovered_qa": fill_res["discovered_qa"],
                    }

                if fill_res["has_captcha"]:
                    await browser.close()
                    return {
                        "submitted": False,
                        "status_target": "TO_APPLY",
                        "autopilot_status": "needs_manual_apply",
                        "reason": "Need to Apply: CAPTCHA verification challenge requires manual completion",
                        "filled_count": fill_res["filled_count"],
                        "discovered_qa": fill_res["discovered_qa"],
                    }

                if require_full_qa_confidence and fill_res["unanswered_required"]:
                    missing_str = ", ".join(fill_res["unanswered_required"][:2])
                    await browser.close()
                    return {
                        "submitted": False,
                        "status_target": "TO_APPLY",
                        "autopilot_status": "needs_manual_apply",
                        "reason": f"Need to Apply: Custom required question(s) need manual review ({missing_str})",
                        "filled_count": fill_res["filled_count"],
                        "discovered_qa": fill_res["discovered_qa"],
                    }

                if fill_res["filled_count"] < 2:
                    await browser.close()
                    return {
                        "submitted": False,
                        "status_target": "TO_APPLY",
                        "autopilot_status": "needs_manual_apply",
                        "reason": "Need to Apply: No direct embedded ATS form detected on page (documents & Q&A ready)",
                        "filled_count": fill_res["filled_count"],
                        "discovered_qa": fill_res["discovered_qa"],
                    }

                # Locate and click the Submit Application button
                submit_btn = page.locator(
                    "button[type='submit']:visible, input[type='submit']:visible, "
                    "button:has-text('Submit Application'):visible, button:has-text('Submit application'):visible, "
                    "button:has-text('Submit'):visible"
                ).first

                if await submit_btn.count() == 0:
                    await browser.close()
                    return {
                        "submitted": False,
                        "status_target": "TO_APPLY",
                        "autopilot_status": "needs_manual_apply",
                        "reason": f"Need to Apply: Pre-filled {fill_res['filled_count']} fields, but final Submit button requires manual click",
                        "filled_count": fill_res["filled_count"],
                        "discovered_qa": fill_res["discovered_qa"],
                    }

                await submit_btn.click(timeout=5000)
                await asyncio.sleep(2.5)

                # Verify confirmation text on page
                after_html = (await page.content()).lower()
                confirmation_signals = (
                    "thank you for applying",
                    "application has been submitted",
                    "application submitted",
                    "we have received your application",
                    "thanks for applying",
                    "your application was sent",
                    "confirmation",
                )
                confirmed = any(sig in after_html for sig in confirmation_signals)
                await browser.close()

                if confirmed:
                    return {
                        "submitted": True,
                        "status_target": "APPLIED",
                        "autopilot_status": "auto_applied",
                        "reason": f"Autonomously submitted application ({fill_res['filled_count']} fields + tailored resume & cover letter)",
                        "filled_count": fill_res["filled_count"],
                        "discovered_qa": fill_res["discovered_qa"],
                    }
                else:
                    return {
                        "submitted": False,
                        "status_target": "TO_APPLY",
                        "autopilot_status": "needs_manual_apply",
                        "reason": "Need to Apply: Form filled, but submission confirmation could not be verified automatically",
                        "filled_count": fill_res["filled_count"],
                        "discovered_qa": fill_res["discovered_qa"],
                    }
            except Exception as inner_e:
                await browser.close()
                return {
                    "submitted": False,
                    "status_target": "TO_APPLY",
                    "autopilot_status": "needs_manual_apply",
                    "reason": f"Need to Apply: Browser navigation interrupted ({str(inner_e)[:120]})",
                    "filled_count": 0,
                    "discovered_qa": [],
                }
    except Exception as e:
        logger.warning(f"Autonomous Playwright runner fallback: {e}")
        return {
            "submitted": False,
            "status_target": "TO_APPLY",
            "autopilot_status": "needs_manual_apply",
            "reason": f"Need to Apply: Browser automation unavailable ({str(e)[:100]}) — Tailored Resume, Cover Letter & Q&A pre-generated",
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
    Launches a visible Chromium session with Playwright to pre-fill standard ATS form fields,
    upload tailored Resume & Cover Letter PDFs, and answer custom screening questions.
    Leaves the browser window open for user review and final submission.
    """
    if not job_url:
        return {"success": False, "message": "No application URL provided."}

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return {
            "success": False,
            "message": "Playwright is not installed. Please run 'pip install playwright && playwright install chromium'.",
        }

    async def _runner():
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=False)
                context = await browser.new_context()
                page = await context.new_page()
                await page.goto(job_url, timeout=30000)
                await asyncio.sleep(2)

                fill_res = await _fill_form_on_page(
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
                # Keep browser open for user interaction for 5 minutes
                await asyncio.sleep(300)
                await browser.close()
        except Exception as e:
            logger.error(f"Playwright assistant error: {e}")

    asyncio.create_task(_runner())

    return {
        "success": True,
        "message": f"Assisted browser session opened for {job_url}. Tailored resume, cover letter, and screening answers pre-filled for your review.",
    }
