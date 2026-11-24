"""
Autonomous JobPulse Autopilot Engine.

End-to-end autonomous workflow:
1. Scrapes suitable job listings across direct company ATS boards, SimplifyJobs, Hadoku corpus,
   and remote tech boards guided by the active SearchProfile and candidate Skills inventory.
2. Evaluates ATS fit score, role track/level, and expiration status.
3. Generates a Tailored Resume and Tailored Cover Letter for each suitable job and exports uploadable PDFs.
4. Answers all standard and custom screening questions via the Question Answering Engine.
5. Attempts autonomous application submission whenever possible:
   - Successfully submitted applications advance automatically to `APPLIED`.
   - All other jobs that cannot meet auto-submission requirements (auth walls, CAPTCHAs, custom questions
     needing human review, fit score below auto-submit threshold, or unconfirmed form submission) are
     routed into the `TO_APPLY` ("Need to Apply") column of the Pipeline with their tailored resume,
     cover letter, pre-answered questions, and exact reason attached.
"""
import asyncio
import json
import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from ..database import AsyncSessionLocal
from ..models import (
    AutopilotConfig,
    Job,
    Profile,
    Skill,
    TailoredDocument,
    ApplicationActivity,
)
from .ai_generator import generate_ai_document, generate_offline_template
from .bot_trap_detector import detect_bot_traps, merge_bot_traps
from .browser_assistant import attempt_autonomous_submission, classify_ats_url, resolve_direct_ats_url
from .expiration_checker import check_job_expiration
from .hadoku_client import get_hadoku_user_key
from .job_extractor import extract_job_from_url
from .job_fetcher import (
    fetch_bigtech_jobs,
    fetch_company_boards_jobs,
    fetch_glassdoor_jobs,
    fetch_hadoku_scraper_jobs,
    fetch_himalayas_jobs,
    fetch_indeed_jobs,
    fetch_jobicy_jobs,
    fetch_linkedin_jobs,
    fetch_remoteok_jobs,
    fetch_simplify_jobs,
    fetch_themuse_jobs,
    fetch_weworkremotely_jobs,
    fetch_ziprecruiter_jobs,
    search_aggregated_jobs,
)
from .matcher import analyze_job_fit
from .location_matcher import is_job_in_range
from .question_answerer import (
    export_application_files,
    generate_comprehensive_qa_bundle,
)
from .role_classifier import classify_role, score_job_for_search_profile

logger = logging.getLogger(__name__)

# Global state for background daemon loop and active execution lock
_AUTOPILOT_LOCK = asyncio.Lock()
_IS_RUNNING = False
_DAEMON_TASK: Optional[asyncio.Task] = None


def is_autopilot_running() -> bool:
    return _IS_RUNNING


async def get_or_create_autopilot_config(db: AsyncSession) -> AutopilotConfig:
    res = await db.execute(select(AutopilotConfig).order_by(AutopilotConfig.id.asc()).limit(1))
    cfg = res.scalars().first()
    if not cfg:
        cfg = AutopilotConfig(
            enabled=False,
            interval_minutes=60,
            search_profile_id=None,
            sources_json=json.dumps(["all"]),
            min_discover_score=50,
            min_auto_apply_score=70,
            max_jobs_per_run=15,
            auto_submit=True,
            headless=True,
            require_full_qa_confidence=True,
            ai_provider="hadoku",
            blocked_companies_json=json.dumps([]),
        )
        db.add(cfg)
        await db.commit()
        await db.refresh(cfg)
    return cfg


async def ensure_candidate_profile(db: AsyncSession) -> tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Loads the primary candidate Profile and Skills list from the database."""
    p_res = await db.execute(select(Profile).order_by(Profile.id.asc()).limit(1))
    profile = p_res.scalars().first()
    profile_dict = profile.to_dict() if profile else {
        "full_name": "",
        "email": "",
        "phone": "",
        "location": "Remote, US",
        "title": "Software Engineer",
        "summary": "Software engineer experienced in building reliable applications and scalable backend systems.",
        "linkedin_url": "",
        "github_url": "",
        "portfolio_url": "",
        "work_authorization": "Authorized to work in the US without sponsorship",
        "desired_salary": "",
        "notice_period": "Immediate / 2 weeks",
        "master_resume_text": "",
    }

    s_res = await db.execute(select(Skill))
    skills = [s.to_dict() for s in s_res.scalars().all()]
    return profile_dict, skills


async def prepare_job_application_materials(
    db: AsyncSession,
    job: Job,
    profile_dict: Dict[str, Any],
    skills: List[Dict[str, Any]],
    ai_provider: str = "template",
    api_key: Optional[str] = None,
    fast_batch_mode: bool = False,
) -> Dict[str, Any]:
    """
    Generates and persists:
    1. Enriched job description (if short snippet) & updated ATS fit score
    2. Tailored Resume (saved to TailoredDocument + exported to PDF/MD/TXT)
    3. Tailored Cover Letter (saved to TailoredDocument + exported to PDF/MD/TXT)
    4. Full Screening Question & Answer Bank (saved to job.answers_json + TailoredDocument)
    """
    skill_names = [s["name"] for s in skills if s.get("name")]

    # 1. Enrich short description from URL when possible (bounded by a strict 5s timeout)
    desc = job.description or ""
    if job.url and (len(desc.strip()) < 250 or "via simplifyjobs" in desc.lower()):
        try:
            extracted = await asyncio.wait_for(extract_job_from_url(job.url), timeout=5.0)
            if extracted.get("description") and len(extracted["description"]) > len(desc):
                job.description = extracted["description"]
                desc = job.description
            if extracted.get("salary_min") and not job.salary_min:
                job.salary_min = extracted["salary_min"]
            if extracted.get("salary_max") and not job.salary_max:
                job.salary_max = extracted["salary_max"]
        except Exception:
            pass

    # 2. Classify, scan bot traps, and score
    classified = classify_role(job.title or "", desc)
    job.role_track = classified["track"]
    job.role_level = classified["level"]
    job.role_discipline = classified["discipline"]

    existing_traps = []
    if job.bot_traps_json:
        try:
            existing_traps = json.loads(job.bot_traps_json)
        except Exception:
            existing_traps = []
    scanned_traps = detect_bot_traps(desc)
    merged_traps = merge_bot_traps(existing_traps, scanned_traps)
    if merged_traps:
        job.bot_traps_json = json.dumps(merged_traps)

    fit_data = analyze_job_fit(
        job_text=f"{job.title} {desc} {job.requirements or ''}",
        candidate_skills=skill_names,
        profile_text=f"{profile_dict.get('summary', '')} {profile_dict.get('master_resume_text', '')}",
    )
    if job.fit_score is None or len(desc) > 300:
        job.fit_score = max(job.fit_score or 0, fit_data["score"])
    if not job.fit_breakdown:
        job.fit_breakdown = json.dumps(fit_data)

    matched_skills = fit_data.get("matched_skills") or skill_names[:5]

    # Use fast local ResumeBlock assembler during multi-job batch runs or when template is selected,
    # and bound external LLM calls with a strict timeout so Autopilot never stalls.
    effective_provider = "template" if fast_batch_mode else (ai_provider or "template")
    if effective_provider in ("hadoku", "hadoku-resume") and not get_hadoku_user_key(api_key):
        effective_provider = "template"

    job_dict = job.to_dict()

    # 3. Generate Tailored Resume
    try:
        resume_md, resume_provider = await asyncio.wait_for(
            generate_ai_document(
                doc_type="tailored_resume",
                job_data=job_dict,
                profile_data=profile_dict,
                matched_skills=matched_skills,
                tone="professional",
                provider=effective_provider,
                api_key=api_key,
            ),
            timeout=8.0,
        )
    except Exception:
        resume_md = generate_offline_template("tailored_resume", job_dict, profile_dict, matched_skills)
        resume_provider = "template"

    # 4. Generate Tailored Cover Letter
    try:
        cover_md, _ = await asyncio.wait_for(
            generate_ai_document(
                doc_type="cover_letter",
                job_data=job_dict,
                profile_data=profile_dict,
                matched_skills=matched_skills,
                tone="professional",
                provider=effective_provider,
                api_key=api_key,
            ),
            timeout=8.0,
        )
    except Exception:
        cover_md = generate_offline_template("cover_letter", job_dict, profile_dict, matched_skills)

    # 5. Answer all standard & role-specific screening questions
    qa_bundle = generate_comprehensive_qa_bundle(
        job_data=job_dict,
        profile_data=profile_dict,
        candidate_skills=skills,
        app_kit=None,
    )
    job.answers_json = json.dumps(qa_bundle)

    # 6. Upsert TailoredDocuments on the job
    doc_res = await db.execute(select(TailoredDocument).where(TailoredDocument.job_id == job.id))
    existing_docs = {d.doc_type: d for d in doc_res.scalars().all()}

    if "tailored_resume" in existing_docs:
        existing_docs["tailored_resume"].content = resume_md
        existing_docs["tailored_resume"].created_at = datetime.utcnow()
    else:
        db.add(TailoredDocument(job_id=job.id, doc_type="tailored_resume", content=resume_md))

    if "cover_letter" in existing_docs:
        existing_docs["cover_letter"].content = cover_md
        existing_docs["cover_letter"].created_at = datetime.utcnow()
    else:
        db.add(TailoredDocument(job_id=job.id, doc_type="cover_letter", content=cover_md))

    qa_md_lines = [f"# Tailored Screening Q&A — {job.title} at {job.company}\n"]
    for item in qa_bundle:
        qa_md_lines.append(f"### {item['question']}\n{item['answer']}\n")
    qa_md = "\n".join(qa_md_lines)

    if "application_kit" in existing_docs:
        existing_docs["application_kit"].content = qa_md
        existing_docs["application_kit"].created_at = datetime.utcnow()
    else:
        db.add(TailoredDocument(job_id=job.id, doc_type="application_kit", content=qa_md))

    # 7. Export uploadable PDF/MD/TXT files for Playwright form submission
    exported_files = export_application_files(
        job_id=job.id,
        company=job.company,
        job_title=job.title,
        resume_markdown=resume_md,
        cover_letter_markdown=cover_md,
        candidate_name=profile_dict.get("full_name") or "Justin Kilpatrick",
    )

    return {
        "resume_markdown": resume_md,
        "cover_letter_markdown": cover_md,
        "provider_used": resume_provider,
        "answers": qa_bundle,
        "app_kit": None,
        "files": exported_files,
    }


async def process_single_job_autopilot(
    db: AsyncSession,
    job: Job,
    profile_dict: Dict[str, Any],
    skills: List[Dict[str, Any]],
    min_auto_apply_score: int = 70,
    auto_submit: bool = True,
    headless: bool = True,
    require_full_qa_confidence: bool = True,
    ai_provider: str = "template",
    api_key: Optional[str] = None,
    fast_batch_mode: bool = False,
    imap_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Runs the full autonomous pipeline on a single Job:
    1. Checks expiration (with 5s timeout)
    2. Generates tailored resume, tailored cover letter, and answers all screening questions
    3. Attempts autonomous application submission if eligible (with 14s timeout)
    4. Moves job to APPLIED if submitted, or routes to TO_APPLY ('Need to Apply') with full materials attached.
    """
    # 1. Check if posting has expired
    try:
        is_exp, exp_reason = await asyncio.wait_for(
            check_job_expiration(job.url, job.deadline),
            timeout=5.0,
        )
    except Exception:
        is_exp, exp_reason = False, None

    if is_exp:
        job.is_expired = True
        job.expired_at = datetime.utcnow()
        job.expired_reason = exp_reason or "Job posting closed or deadline passed"
        job.autopilot_status = "skipped"
        job.autopilot_reason = f"Skipped: {job.expired_reason}"
        job.updated_at = datetime.utcnow()
        await db.commit()
        return {
            "job_id": job.id,
            "title": job.title,
            "company": job.company,
            "fit_score": job.fit_score,
            "outcome": "skipped_expired",
            "status": job.status,
            "reason": job.autopilot_reason,
            "documents_generated": False,
            "questions_answered": 0,
        }

    # 2. Generate tailored resume, tailored cover letter, exported PDFs, and Q&A bank
    materials = await prepare_job_application_materials(
        db=db,
        job=job,
        profile_dict=profile_dict,
        skills=skills,
        ai_provider=ai_provider,
        api_key=api_key,
        fast_batch_mode=fast_batch_mode,
    )
    qa_list = materials["answers"]
    score = job.fit_score or 0

    # 2.5 Bot Trap Safety Guardrail (checked FIRST so the user ALWAYS sees the Bot Trap alert!)
    job_traps = job.to_dict().get("bot_traps") or []
    human_traps = [t for t in job_traps if t.get("type") == "human_check"]
    if human_traps:
        trap_action = human_traps[0].get("action_required") or "Custom applicant instruction detected in listing"
        reason = (
            f"⚠️ Bot Trap Detected: {trap_action} "
            f"— Tailored Resume, Cover Letter & {len(qa_list)} answers ready"
        )
        job.status = "TO_APPLY"
        job.autopilot_status = "needs_manual_apply"
        job.autopilot_reason = reason
        job.updated_at = datetime.utcnow()
        db.add(
            ApplicationActivity(
                job_id=job.id,
                activity_type="autopilot_queued",
                title="Routed to Need to Apply (Bot Trap Detected)",
                details=reason,
            )
        )
        await db.commit()
        return {
            "job_id": job.id,
            "title": job.title,
            "company": job.company,
            "fit_score": score,
            "outcome": "needs_manual_apply",
            "status": "TO_APPLY",
            "reason": reason,
            "documents_generated": True,
            "questions_answered": len(qa_list),
            "bot_traps_count": len(job_traps),
        }

    # 3. Check if fit score meets the autonomous submission threshold
    if score < min_auto_apply_score:
        reason = (
            f"Need to Apply: Fit score ({score}%) below auto-submit threshold ({min_auto_apply_score}%) "
            f"— Tailored Resume, Cover Letter & {len(qa_list)} answers pre-generated"
        )
        job.status = "TO_APPLY"
        job.autopilot_status = "needs_manual_apply"
        job.autopilot_reason = reason
        job.updated_at = datetime.utcnow()
        db.add(
            ApplicationActivity(
                job_id=job.id,
                activity_type="autopilot_queued",
                title="Routed to Need to Apply (Tailored Kit Ready)",
                details=reason,
            )
        )
        await db.commit()
        return {
            "job_id": job.id,
            "title": job.title,
            "company": job.company,
            "fit_score": score,
            "outcome": "needs_manual_apply",
            "status": "TO_APPLY",
            "reason": reason,
            "documents_generated": True,
            "questions_answered": len(qa_list),
        }

    # 4. Check if any pre-extracted questions from description require manual review
    manual_questions = [q["question"] for q in qa_list if q.get("confidence") == "manual_needed"]
    if require_full_qa_confidence and manual_questions:
        q_preview = manual_questions[0][:80]
        reason = (
            f"Need to Apply: {len(manual_questions)} question(s) need manual verification ('{q_preview}') "
            f"— Tailored Resume, Cover Letter & draft answers ready"
        )
        job.status = "TO_APPLY"
        job.autopilot_status = "needs_manual_apply"
        job.autopilot_reason = reason
        job.updated_at = datetime.utcnow()
        db.add(
            ApplicationActivity(
                job_id=job.id,
                activity_type="autopilot_queued",
                title="Routed to Need to Apply (Question Review Needed)",
                details=reason,
            )
        )
        await db.commit()
        return {
            "job_id": job.id,
            "title": job.title,
            "company": job.company,
            "fit_score": score,
            "outcome": "needs_manual_apply",
            "status": "TO_APPLY",
            "reason": reason,
            "documents_generated": True,
            "questions_answered": len(qa_list),
        }

    # 5. Fast check whether URL is an auth-gated portal; attempt direct ATS resolution first!
    url_cls = classify_ats_url(job.url)
    if not url_cls["can_auto_attempt"] and job.company and job.title:
        try:
            direct_url = await asyncio.wait_for(
                asyncio.to_thread(resolve_direct_ats_url, job.company, job.title, job.url),
                timeout=4.0,
            )
            if direct_url:
                job.url = direct_url
                url_cls = classify_ats_url(job.url)
        except Exception:
            pass

    if not url_cls["can_auto_attempt"]:
        reason = f"Need to Apply: {url_cls['reason']} — Tailored Resume, Cover Letter & {len(qa_list)} answers ready"
        job.status = "TO_APPLY"
        job.autopilot_status = "needs_manual_apply"
        job.autopilot_reason = reason
        job.updated_at = datetime.utcnow()
        db.add(
            ApplicationActivity(
                job_id=job.id,
                activity_type="autopilot_queued",
                title="Routed to Need to Apply (Tailored Kit Ready)",
                details=reason,
            )
        )
        await db.commit()
        return {
            "job_id": job.id,
            "title": job.title,
            "company": job.company,
            "fit_score": score,
            "outcome": "needs_manual_apply",
            "status": "TO_APPLY",
            "reason": reason,
            "documents_generated": True,
            "questions_answered": len(qa_list),
        }

    # 5.5. Verify location and remote eligibility before attempting autonomous submission
    target_loc = (profile_dict.get("location") or "").strip() or "Boston, MA"
    radius_mi = 50
    if not is_job_in_range(
        job_location=job.location or "",
        target_location=target_loc,
        radius_miles=radius_mi,
        workplace_type=job.workplace_type or "",
        include_remote=True,
        title=job.title or "",
    ):
        reason = (
            f"Need to Apply: Position is {job.workplace_type or 'on-site'} in {job.location or 'unspecified location'}, "
            f"outside your {radius_mi}-mile commute radius from {target_loc} (remote or local commute only) "
            f"— Tailored Resume, Cover Letter & {len(qa_list)} answers ready"
        )
        job.status = "TO_APPLY"
        job.autopilot_status = "needs_manual_apply"
        job.autopilot_reason = reason
        job.updated_at = datetime.utcnow()
        db.add(
            ApplicationActivity(
                job_id=job.id,
                activity_type="autopilot_queued",
                title="Routed to Need to Apply (Location / Remote Preference)",
                details=reason,
            )
        )
        await db.commit()
        return {
            "job_id": job.id,
            "title": job.title,
            "company": job.company,
            "fit_score": score,
            "outcome": "needs_manual_apply",
            "status": "TO_APPLY",
            "reason": reason,
            "documents_generated": True,
            "questions_answered": len(qa_list),
        }

    # 6. Attempt Autonomous Submission via Playwright ATS engine
    has_imap = bool(imap_config and imap_config.get("imap_password"))
    sub_timeout = 55.0 if has_imap else 30.0
    try:
        sub_res = await asyncio.wait_for(
            attempt_autonomous_submission(
                job_data=job.to_dict(),
                profile_data=profile_dict,
                candidate_skills=skills,
                app_kit=materials.get("app_kit"),
                files=materials.get("files"),
                headless=headless,
                auto_submit=auto_submit,
                require_full_qa_confidence=require_full_qa_confidence,
                imap_config=imap_config,
            ),
            timeout=sub_timeout,
        )
    except asyncio.TimeoutError:
        sub_res = {
            "submitted": False,
            "status_target": "TO_APPLY",
            "autopilot_status": "needs_manual_apply",
            "reason": "Need to Apply: External ATS page timed out during automated submission — Tailored Resume, Cover Letter & Q&A ready",
            "filled_count": 0,
            "discovered_qa": [],
        }

    # Merge any live form questions & bot traps discovered during Playwright inspection
    if sub_res.get("discovered_qa"):
        existing_q_norm = {q["question"].strip().lower() for q in qa_list}
        for dqa in sub_res["discovered_qa"]:
            if dqa["question"].strip().lower() not in existing_q_norm:
                qa_list.append(dqa)
                existing_q_norm.add(dqa["question"].strip().lower())
        job.answers_json = json.dumps(qa_list)

    if sub_res.get("bot_traps"):
        merged_live = merge_bot_traps(job.to_dict().get("bot_traps"), sub_res["bot_traps"])
        if merged_live:
            job.bot_traps_json = json.dumps(merged_live)

    if sub_res["submitted"]:
        job.status = "APPLIED"
        job.applied_at = datetime.utcnow()
        job.autopilot_status = "auto_applied"
        job.autopilot_reason = sub_res["reason"]
        job.updated_at = datetime.utcnow()
        db.add(
            ApplicationActivity(
                job_id=job.id,
                activity_type="status_change",
                title="Autonomously Applied via JobPulse Autopilot",
                details=f"{sub_res['reason']} | Tailored Resume + Cover Letter + {len(qa_list)} Q&A items.",
            )
        )
        outcome = "auto_applied"
    else:
        job.status = "TO_APPLY"
        job.autopilot_status = "needs_manual_apply"
        job.autopilot_reason = sub_res["reason"]
        job.updated_at = datetime.utcnow()
        db.add(
            ApplicationActivity(
                job_id=job.id,
                activity_type="autopilot_queued",
                title="Routed to Need to Apply (Tailored Kit Ready)",
                details=f"{sub_res['reason']} | Tailored Resume, Cover Letter & {len(qa_list)} answers attached.",
            )
        )
        outcome = "needs_manual_apply"

    await db.commit()
    return {
        "job_id": job.id,
        "title": job.title,
        "company": job.company,
        "fit_score": score,
        "outcome": outcome,
        "status": job.status,
        "reason": job.autopilot_reason,
        "documents_generated": True,
        "questions_answered": len(qa_list),
    }


# Non-software engineering & non-technical title exclusions for Software / AI Engineering SearchProfiles
_NON_SOFTWARE_TITLE_RE = re.compile(
    r"\b(?:energy\s+engineer|mechanical\s+engineer|civil\s+engineer|structural\s+engineer|"
    r"chemical\s+engineer|electrical\s+engineer|biomedical\s+engineer|industrial\s+engineer|"
    r"manufacturing\s+engineer|hvac|sales\s+rep(?:resentative)?|business\s+development(?:\s+rep(?:resentative)?)?|"
    r"account\s+executive|broker\s+dealer|accounting\s+operations|investor\s+relations|"
    r"strategic\s+finance|compensation\s+analyst|transportation\s+analyst|recruiter|"
    r"talent\s+acquisition|human\s+resources|legal\s+counsel)\b",
    re.IGNORECASE,
)

_TECH_TITLE_WORD_RE = re.compile(
    r"\b(?:software|developer|swe|sde|ai|ml|machine\s+learning|llm|nlp|data\s+engineer|"
    r"data\s+scientist|full[\s-]?stack|back[\s-]?end|front[\s-]?end|python|typescript|"
    r"devops|sre|cloud|platform|systems|security|cybersecurity|automation|research\s+engineer|"
    r"forward\s+deployed|product\s+engineer|ai\s+engineer|ml\s+engineer|qa|sdet|test\s+engineer)\b",
    re.IGNORECASE,
)


def _clean_profile_location(raw_loc: Optional[str]) -> Optional[str]:
    if not raw_loc or not raw_loc.strip():
        return None
    cleaned = re.sub(r"[\(\[\{].*?[\)\]\}]", "", raw_loc).split("-")[0].strip()
    if cleaned.lower() in ("", "remote", "united states", "us", "usa", "anywhere"):
        return None
    return cleaned


async def _fast_scrape_for_profile(
    sp_dict: Dict[str, Any],
    profile_dict: Dict[str, Any],
    query_override: Optional[str] = None,
    source_override: Optional[str] = None,
    configured_sources: Optional[List[str]] = None,
) -> tuple[List[Dict[str, Any]], Dict[str, int]]:
    """
    Performs polite, high-coverage parallel discovery across mainstream boards
    (Indeed, LinkedIn, Glassdoor, ZipRecruiter, Big Tech), direct company ATS feeds
    (Greenhouse/Ashby/Lever, SimplifyJobs, Hadoku), and remote boards with per-source timeouts.

    Returns (combined_jobs, sources_breakdown).
    """
    us_only = sp_dict.get("us_only", True)
    raw_loc = (sp_dict.get("location") or "").strip() or (profile_dict.get("location") or "").strip()
    location = _clean_profile_location(raw_loc)
    radius = sp_dict.get("radius_miles") or 50
    include_remote = sp_dict.get("remote_pref", "any") in ("any", "remote")

    sp_name_low = (sp_dict.get("name") or "").lower()
    sp_levels_low = [str(l).lower() for l in (sp_dict.get("levels") or [])]
    wants_junior = any(l in ("junior", "entry", "entry-level", "intern", "new grad", "associate") for l in sp_levels_low)

    if query_override:
        primary_query = query_override
        mainstream_query = query_override
    elif any(w in sp_name_low for w in ("it", "system", "security", "support", "help desk")):
        primary_query = "it support"
        mainstream_query = "it support"
    elif any(w in sp_name_low for w in ("ai", "machine learning", "ml")):
        # Direct ATS/niche boards search specific AI/SWE terms; mainstream boards get high-recall entry-level SWE query
        # and then our multi-signal SearchProfile scorer ranks AI/Python/ML/SWE roles right to the top!
        primary_query = "entry level ai software engineer" if wants_junior else "ai software engineer"
        mainstream_query = "entry level software engineer" if wants_junior else "ai software engineer"
    else:
        primary_query = "entry level software engineer" if wants_junior else "software engineer"
        mainstream_query = primary_query

    if source_override and source_override != "all":
        try:
            items = await asyncio.wait_for(
                search_aggregated_jobs(
                    query=mainstream_query if source_override in ("indeed", "linkedin", "glassdoor", "ziprecruiter", "bigtech") else primary_query,
                    source=source_override,
                    us_only=us_only,
                    location=location,
                    radius=radius,
                    include_remote=include_remote,
                ),
                timeout=18.0,
            )
            return items, {source_override: len(items)}
        except Exception as e:
            logger.warning(f"Source override '{source_override}' scrape timed out or failed: {e}")
            return [], {source_override: 0}

    active_sources_set = {str(s).lower().strip() for s in (configured_sources or ["all"]) if s}
    use_all = not active_sources_set or "all" in active_sources_set

    async def _safe_named_fetch(name: str, coro, timeout_sec: float = 12.0) -> tuple[str, List[Dict[str, Any]]]:
        try:
            res = await asyncio.wait_for(coro, timeout=timeout_sec)
            return name, (res if isinstance(res, list) else [])
        except Exception as exc:
            logger.debug(f"Autopilot source '{name}' timed out or failed: {exc}")
            return name, []

    tasks = []
    # 1. Mainstream job boards (Indeed, LinkedIn, Glassdoor, ZipRecruiter, Big Tech) — 16s polite timeout
    if use_all or "indeed" in active_sources_set:
        tasks.append(_safe_named_fetch(
            "indeed",
            fetch_indeed_jobs(mainstream_query, us_only=us_only, location=location, radius=radius, include_remote=include_remote),
            timeout_sec=16.0,
        ))
    if use_all or "linkedin" in active_sources_set:
        tasks.append(_safe_named_fetch(
            "linkedin",
            fetch_linkedin_jobs(mainstream_query, us_only=us_only, location=location, radius=radius, include_remote=include_remote),
            timeout_sec=16.0,
        ))
    if use_all or "glassdoor" in active_sources_set:
        tasks.append(_safe_named_fetch(
            "glassdoor",
            fetch_glassdoor_jobs(mainstream_query, us_only=us_only, location=location, radius=radius, include_remote=include_remote),
            timeout_sec=16.0,
        ))
    if use_all or "ziprecruiter" in active_sources_set:
        tasks.append(_safe_named_fetch(
            "ziprecruiter",
            fetch_ziprecruiter_jobs(mainstream_query, us_only=us_only, location=location, radius=radius, include_remote=include_remote),
            timeout_sec=16.0,
        ))
    if use_all or "bigtech" in active_sources_set:
        tasks.append(_safe_named_fetch(
            "bigtech",
            fetch_bigtech_jobs(mainstream_query, us_only=us_only, location=location, include_remote=include_remote),
            timeout_sec=12.0,
        ))

    # 2. Direct ATS boards (Greenhouse/Ashby/Lever, SimplifyJobs, Hadoku corpus)
    if use_all or "simplify" in active_sources_set:
        tasks.append(_safe_named_fetch(
            "simplify",
            fetch_simplify_jobs(mainstream_query, us_only=us_only, location=location, include_remote=include_remote),
            timeout_sec=10.0,
        ))
    if use_all or "company_boards" in active_sources_set:
        tasks.append(_safe_named_fetch(
            "company_boards",
            fetch_company_boards_jobs(mainstream_query, us_only=us_only, location=location, include_remote=include_remote),
            timeout_sec=20.0,
        ))
    if use_all or "hadoku" in active_sources_set:
        tasks.append(_safe_named_fetch(
            "hadoku",
            fetch_hadoku_scraper_jobs(mainstream_query, us_only=us_only, location=location, include_remote=include_remote),
            timeout_sec=10.0,
        ))

    # 3. Curated & Remote boards (The Muse, Himalayas, RemoteOK, WWR, Jobicy)
    if use_all or "themuse" in active_sources_set:
        tasks.append(_safe_named_fetch(
            "themuse",
            fetch_themuse_jobs(mainstream_query, us_only=us_only, location=location, include_remote=include_remote),
            timeout_sec=10.0,
        ))
    if use_all or "himalayas" in active_sources_set:
        tasks.append(_safe_named_fetch(
            "himalayas",
            fetch_himalayas_jobs(primary_query, us_only=us_only),
            timeout_sec=10.0,
        ))
    if use_all or "remoteok" in active_sources_set:
        tasks.append(_safe_named_fetch(
            "remoteok",
            fetch_remoteok_jobs(primary_query, us_only=us_only),
            timeout_sec=10.0,
        ))
    if use_all or "weworkremotely" in active_sources_set:
        tasks.append(_safe_named_fetch(
            "weworkremotely",
            fetch_weworkremotely_jobs(primary_query, us_only=us_only),
            timeout_sec=10.0,
        ))
    if use_all or "jobicy" in active_sources_set:
        tasks.append(_safe_named_fetch(
            "jobicy",
            fetch_jobicy_jobs(primary_query, us_only=us_only),
            timeout_sec=10.0,
        ))

    batches = await asyncio.gather(*tasks, return_exceptions=True)
    combined: List[Dict[str, Any]] = []
    sources_breakdown: Dict[str, int] = {}
    for res_tuple in batches:
        if isinstance(res_tuple, tuple) and len(res_tuple) == 2:
            src_name, items = res_tuple
            sources_breakdown[src_name] = len(items)
            combined.extend(items)
    return combined, sources_breakdown


def _select_source_balanced_candidates(
    candidates: List[tuple[int, Dict[str, Any], Dict[str, Any], Dict[str, Any]]],
    max_jobs: int,
) -> List[tuple[int, Dict[str, Any], Dict[str, Any], Dict[str, Any]]]:
    """
    Selects up to `max_jobs` top-scoring candidates while ensuring mainstream boards
    (Indeed, LinkedIn, Glassdoor, ZipRecruiter, BigTech) and direct ATS boards are
    fairly represented instead of letting one noisy board consume every slot.
    """
    if len(candidates) <= max_jobs:
        return candidates

    # Group by source, each pre-sorted by score descending
    by_source: Dict[str, List[tuple[int, Dict[str, Any], Dict[str, Any], Dict[str, Any]]]] = {}
    for cand in sorted(candidates, key=lambda x: x[0], reverse=True):
        src = (cand[1].get("source") or cand[1].get("source_site") or "other").lower()
        by_source.setdefault(src, []).append(cand)

    # Priority round-robin order: mainstream boards & direct ATS boards first
    preferred_order = [
        "indeed", "linkedin", "glassdoor", "ziprecruiter", "bigtech",
        "company_boards", "simplify", "hadoku", "themuse", "himalayas",
        "remoteok", "weworkremotely", "jobicy",
    ]
    ordered_sources = [s for s in preferred_order if s in by_source] + [
        s for s in by_source if s not in preferred_order
    ]

    selected: List[tuple[int, Dict[str, Any], Dict[str, Any], Dict[str, Any]]] = []
    while len(selected) < max_jobs and ordered_sources:
        still_active = []
        for src in ordered_sources:
            if len(selected) >= max_jobs:
                break
            bucket = by_source[src]
            if bucket:
                selected.append(bucket.pop(0))
                if bucket:
                    still_active.append(src)
        ordered_sources = still_active

    selected.sort(key=lambda x: x[0], reverse=True)
    return selected


async def run_autopilot_cycle(
    db: AsyncSession,
    overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Executes a complete Autonomous Autopilot cycle:
    1. Scrapes suitable job listings matching the active SearchProfile & candidate skills.
    2. Scores and deduplicates listings; imports suitable jobs into the pipeline.
    3. Generates tailored resumes, tailored cover letters, and answers all necessary questions.
    4. Submits applications automatically whenever possible -> `APPLIED`.
    5. Routes all other jobs that cannot be auto-submitted into `TO_APPLY` ("Need to Apply").
    Commits progress incrementally after every job so results appear immediately.
    """
    global _IS_RUNNING
    if _AUTOPILOT_LOCK.locked():
        return {
            "status": "already_running",
            "message": "An Autopilot cycle is already running.",
        }

    async with _AUTOPILOT_LOCK:
        _IS_RUNNING = True
        started_at = datetime.utcnow()
        try:
            cfg = await get_or_create_autopilot_config(db)
            cfg_dict = cfg.to_dict()
            ov = overrides or {}

            scrape_new = ov.get("scrape_new", True)
            process_existing_queue = ov.get("process_existing_queue", True)
            min_discover_score = (
                ov.get("min_discover_score")
                if ov.get("min_discover_score") is not None
                else cfg_dict["min_discover_score"]
            )
            min_auto_apply_score = (
                ov.get("min_auto_apply_score")
                if ov.get("min_auto_apply_score") is not None
                else cfg_dict["min_auto_apply_score"]
            )
            max_jobs = (
                ov.get("max_jobs")
                if ov.get("max_jobs") is not None
                else cfg_dict["max_jobs_per_run"]
            )
            auto_submit = (
                ov.get("auto_submit")
                if ov.get("auto_submit") is not None
                else cfg_dict["auto_submit"]
            )
            headless = (
                ov.get("headless")
                if ov.get("headless") is not None
                else cfg_dict["headless"]
            )
            require_full_qa = (
                ov.get("require_full_qa_confidence")
                if ov.get("require_full_qa_confidence") is not None
                else cfg_dict["require_full_qa_confidence"]
            )
            ai_provider = ov.get("ai_provider") or cfg_dict["ai_provider"] or "template"
            api_key = ov.get("api_key")
            blocked_companies = {
                c.strip().lower()
                for c in (cfg_dict.get("blocked_companies") or [])
                if c and c.strip()
            }

            # Load candidate profile & skills
            profile_dict, skills = await ensure_candidate_profile(db)
            skill_names = [s["name"] for s in skills if s.get("name")]
            resume_text = f"{profile_dict.get('summary', '')} {profile_dict.get('master_resume_text', '')}"

            # Load active SearchProfile
            from ..routers.search_profiles import ensure_seed_search_profiles
            search_profiles = await ensure_seed_search_profiles(db, "default")
            target_sp_id = ov.get("search_profile_id") or cfg_dict.get("search_profile_id")
            active_sp = None
            if target_sp_id:
                active_sp = next((p for p in search_profiles if p.id == target_sp_id), None)
            if not active_sp:
                active_sp = next((p for p in search_profiles if p.is_default), search_profiles[0])
            sp_dict = active_sp.to_dict()

            # Existing pipeline jobs for deduplication
            existing_res = await db.execute(select(Job))
            existing_jobs = list(existing_res.scalars().all())
            existing_urls = {j.url.strip().lower() for j in existing_jobs if j.url}
            existing_keys = {
                (j.company.strip().lower(), j.title.strip().lower(), (j.location or "Remote").strip().lower())
                for j in existing_jobs
            }

            scraped_total = 0
            sources_breakdown: Dict[str, int] = {}
            imported_jobs: List[Job] = []

            # ====================================================================
            # STEP 1: Autonomous Scraping & Discovery (Mainstream + Direct ATS)
            # ====================================================================
            if scrape_new:
                raw_discovered, sources_breakdown = await _fast_scrape_for_profile(
                    sp_dict=sp_dict,
                    profile_dict=profile_dict,
                    query_override=(ov.get("query_override") or "").strip() or None,
                    source_override=(ov.get("source_override") or "").strip() or None,
                    configured_sources=cfg_dict.get("sources") or ["all"],
                )
                scraped_total = len(raw_discovered)

                scored_candidates: List[tuple[int, Dict[str, Any], Dict[str, Any], Dict[str, Any]]] = []
                fallback_candidates: List[tuple[int, Dict[str, Any], Dict[str, Any], Dict[str, Any]]] = []

                for item in raw_discovered:
                    title = (item.get("title") or "").strip()
                    company = (item.get("company") or "").strip()
                    url_clean = (item.get("url") or "").strip()
                    loc = (item.get("location") or "Remote").strip()

                    if not title or not company:
                        continue
                    if company.lower() in blocked_companies:
                        continue

                    dedup_key = (company.lower(), title.lower(), loc.lower())
                    if (url_clean and url_clean.lower() in existing_urls) or dedup_key in existing_keys:
                        continue

                    wp = (item.get("workplace_type") or item.get("remote_type") or "remote").lower()
                    if wp not in ("remote", "hybrid", "onsite"):
                        wp = "remote" if "remote" in loc.lower() else "onsite"

                    # Location & Commute radius check:
                    # Non-remote (hybrid or onsite) jobs must be within radius_miles of target location
                    target_loc = (sp_dict.get("location") or "").strip() or (profile_dict.get("location") or "").strip() or "Boston, MA"
                    radius_mi = sp_dict.get("radius_miles") or 50
                    include_remote = sp_dict.get("remote_pref", "any") in ("any", "remote")
                    if not is_job_in_range(
                        job_location=loc,
                        target_location=target_loc,
                        radius_miles=radius_mi,
                        workplace_type=wp,
                        include_remote=include_remote,
                        title=title,
                    ):
                        continue

                    classified = classify_role(title, item.get("description") or "")
                    sp_track = sp_dict.get("track", "either")
                    if sp_track in ("ic", "manager") and classified["track"] in ("ic", "manager") and classified["track"] != sp_track:
                        continue

                    # 1. Level filtering: If profile restricts levels, hard-filter non-matching levels
                    sp_levels = [lvl.lower().strip() for lvl in (sp_dict.get("levels") or [])]
                    if sp_levels:
                        allowed_levels = set()
                        for lvl in sp_levels:
                            if lvl in ("entry", "entry-level", "new grad", "intern", "associate", "junior"):
                                allowed_levels.add("junior")
                            elif lvl in ("mid", "mid-level", "intermediate"):
                                allowed_levels.add("mid")
                            elif lvl in ("senior", "sr", "sr.", "lead"):
                                allowed_levels.add("senior")
                            elif lvl in ("staff", "principal"):
                                allowed_levels.add("staff")
                                allowed_levels.add("principal")
                            else:
                                allowed_levels.add(lvl)

                        title_low = title.lower()
                        is_senior_title = any(
                            re.search(rf"\b{re.escape(term)}\b", title_low)
                            for term in (
                                "senior", "sr", "lead", "staff", "principal", "head of", "director", "manager", "vp", "chief", "architect"
                            )
                        )
                        if is_senior_title and not allowed_levels.intersection({"senior", "staff", "principal"}):
                            logger.debug(f"[AUTOPILOT FILTER] Excluding senior job: '{title}'")
                            continue

                        job_lvl = (classified.get("level") or "").lower().strip()
                        if job_lvl and job_lvl not in allowed_levels:
                            logger.debug(f"[AUTOPILOT FILTER] Excluding level '{job_lvl}' not in {allowed_levels}: '{title}'")
                            continue

                    # 2. Discipline filtering: For software/AI engineering search profiles, strictly exclude non-software roles
                    sp_name_check = sp_dict.get("name", "").lower()
                    if sp_track == "ic" and any(k in sp_name_check for k in ("engineer", "software", "ai", "data", "developer")):
                        if _NON_SOFTWARE_TITLE_RE.search(title):
                            logger.debug(f"[AUTOPILOT FILTER] Excluding non-software title: '{title}'")
                            continue
                        if classified.get("discipline") in ("adjacent", "unknown") and not _TECH_TITLE_WORD_RE.search(title):
                            logger.debug(f"[AUTOPILOT FILTER] Excluding non-engineering job: '{title}'")
                            continue

                    scored = score_job_for_search_profile(
                        title=title,
                        description=item.get("description") or "",
                        company=company,
                        workplace_type=wp,
                        role_track=classified["track"],
                        role_level=classified["level"],
                        profile_keywords=sp_dict.get("keywords") or [],
                        profile_levels=sp_dict.get("levels") or [],
                        profile_remote_pref=sp_dict.get("remote_pref") or "any",
                        profile_companies=sp_dict.get("target_companies") or [],
                        candidate_skills=skill_names,
                        master_resume_text=resume_text,
                    )

                    if url_clean:
                        existing_urls.add(url_clean.lower())
                    existing_keys.add(dedup_key)

                    if scored["score"] >= min_discover_score:
                        scored_candidates.append((scored["score"], item, classified, scored))
                    elif classified["discipline"] == "eng" and scored["score"] >= max(38, min_discover_score - 12):
                        # Short snippet from LinkedIn/ATS/Simplify before full description extraction
                        fallback_candidates.append((scored["score"], item, classified, scored))

                primary_selected = _select_source_balanced_candidates(scored_candidates, max_jobs)
                if len(primary_selected) < max_jobs and fallback_candidates:
                    remaining_slots = max_jobs - len(primary_selected)
                    primary_selected.extend(_select_source_balanced_candidates(fallback_candidates, remaining_slots))
                selected_to_import = primary_selected[:max_jobs]

                for fit_sc, item, classified, scored in selected_to_import:
                    loc = (item.get("location") or "Remote").strip()
                    wp = (item.get("workplace_type") or item.get("remote_type") or "remote").lower()
                    if wp not in ("remote", "hybrid", "onsite"):
                        wp = "remote"
                    desc_txt = item.get("description") or ""
                    traps = detect_bot_traps(desc_txt)
                    new_job = Job(
                        title=item["title"].strip(),
                        company=item["company"].strip(),
                        location=loc,
                        workplace_type=wp,
                        url=(item.get("url") or "").strip() or None,
                        salary_min=item.get("salary_min"),
                        salary_max=item.get("salary_max"),
                        description=desc_txt,
                        source=item.get("source") or item.get("source_site") or "autopilot_scraper",
                        status="TO_APPLY",
                        priority="high" if fit_sc >= 80 else "medium",
                        fit_score=fit_sc,
                        fit_breakdown=json.dumps(scored),
                        role_track=classified["track"],
                        role_level=classified["level"],
                        role_discipline=classified["discipline"],
                        autopilot_status="pending",
                        bot_traps_json=json.dumps(traps) if traps else None,
                    )
                    db.add(new_job)
                    imported_jobs.append(new_job)

                if imported_jobs:
                    await db.commit()
                    for j in imported_jobs:
                        await db.refresh(j)

            # ====================================================================
            # STEP 2: Select Jobs to Process (Existing TO_APPLY Queue + Newly Imported)
            # ====================================================================
            jobs_to_process: List[Job] = []
            imported_ids = {j.id for j in imported_jobs}

            if process_existing_queue:
                q_res = await db.execute(
                    select(Job)
                    .where(
                        Job.status == "TO_APPLY",
                        Job.is_expired == False,  # noqa: E712
                    )
                    .order_by(Job.fit_score.desc().nullslast(), Job.updated_at.desc())
                )
                # Prioritize unprocessed TO_APPLY jobs in the user's pipeline first
                existing_unprocessed = [
                    j for j in q_res.scalars().all()
                    if j.id not in imported_ids and j.autopilot_status != "auto_applied"
                ]
                jobs_to_process.extend(existing_unprocessed)

            jobs_to_process.extend(imported_jobs)
            jobs_to_process = jobs_to_process[:max_jobs]

            # ====================================================================
            # STEP 3: Tailor Documents, Answer All Questions, & Submit or Route
            # ====================================================================
            job_results: List[Dict[str, Any]] = []
            auto_applied_count = 0
            need_to_apply_count = 0
            skipped_expired_count = 0
            docs_generated_count = 0
            total_questions_answered = 0
            use_fast_batch = len(jobs_to_process) > 2

            imap_config = {
                "imap_server": cfg.imap_server or "imap.gmail.com",
                "imap_email": (cfg.imap_email or profile_dict.get("email") or "").strip(),
                "imap_password": (cfg.imap_password or "").strip(),
            }

            for job in jobs_to_process:
                res_item = await process_single_job_autopilot(
                    db=db,
                    job=job,
                    profile_dict=profile_dict,
                    skills=skills,
                    min_auto_apply_score=min_auto_apply_score,
                    auto_submit=auto_submit,
                    headless=headless,
                    require_full_qa_confidence=require_full_qa,
                    ai_provider=ai_provider,
                    api_key=api_key,
                    fast_batch_mode=use_fast_batch,
                    imap_config=imap_config,
                )
                job_results.append(res_item)
                if res_item["documents_generated"]:
                    docs_generated_count += 1
                total_questions_answered += res_item.get("questions_answered", 0)

                if res_item["outcome"] == "auto_applied":
                    auto_applied_count += 1
                elif res_item["outcome"] == "needs_manual_apply":
                    need_to_apply_count += 1
                elif res_item["outcome"] == "skipped_expired":
                    skipped_expired_count += 1

                # Commit incremental progress after every job so the UI & DB stay in sync
                now_ts = datetime.utcnow()
                partial_summary = {
                    "started_at": started_at.isoformat(),
                    "finished_at": now_ts.isoformat(),
                    "duration_seconds": round((now_ts - started_at).total_seconds(), 2),
                    "search_profile_used": sp_dict["name"],
                    "scraped_count": scraped_total,
                    "sources_breakdown": sources_breakdown,
                    "imported_count": len(imported_jobs),
                    "processed_count": len(job_results),
                    "resumes_generated": docs_generated_count,
                    "cover_letters_generated": docs_generated_count,
                    "questions_answered": total_questions_answered,
                    "auto_applied_count": auto_applied_count,
                    "routed_to_need_to_apply_count": need_to_apply_count,
                    "skipped_expired_count": skipped_expired_count,
                    "job_results": job_results,
                }
                cfg.last_run_at = now_ts
                cfg.last_run_summary_json = json.dumps(partial_summary)
                await db.commit()

            finished_at = datetime.utcnow()
            summary = {
                "started_at": started_at.isoformat(),
                "finished_at": finished_at.isoformat(),
                "duration_seconds": round((finished_at - started_at).total_seconds(), 2),
                "search_profile_used": sp_dict["name"],
                "scraped_count": scraped_total,
                "sources_breakdown": sources_breakdown,
                "imported_count": len(imported_jobs),
                "processed_count": len(job_results),
                "resumes_generated": docs_generated_count,
                "cover_letters_generated": docs_generated_count,
                "questions_answered": total_questions_answered,
                "auto_applied_count": auto_applied_count,
                "routed_to_need_to_apply_count": need_to_apply_count,
                "skipped_expired_count": skipped_expired_count,
                "job_results": job_results,
            }

            cfg.last_run_at = finished_at
            cfg.last_run_summary_json = json.dumps(summary)
            await db.commit()

            return summary
        finally:
            _IS_RUNNING = False


async def _autopilot_daemon_loop():
    """
    Background scheduler loop that checks `AutopilotConfig.enabled` and runs autonomous
    cycles at `interval_minutes`.
    """
    while True:
        try:
            await asyncio.sleep(30)
            if _IS_RUNNING:
                continue
            async with AsyncSessionLocal() as db:
                cfg = await get_or_create_autopilot_config(db)
                if not cfg.enabled:
                    continue
                interval_sec = max(5, (cfg.interval_minutes or 60)) * 60
                now = datetime.utcnow()
                if cfg.last_run_at is None or (now - cfg.last_run_at).total_seconds() >= interval_sec:
                    logger.info("Starting scheduled autonomous JobPulse Autopilot cycle...")
                    await run_autopilot_cycle(db)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Autopilot background daemon error: {e}")


def start_autopilot_background_daemon():
    global _DAEMON_TASK
    if _DAEMON_TASK is None or _DAEMON_TASK.done():
        _DAEMON_TASK = asyncio.create_task(_autopilot_daemon_loop())


def stop_autopilot_background_daemon():
    global _DAEMON_TASK
    if _DAEMON_TASK and not _DAEMON_TASK.done():
        _DAEMON_TASK.cancel()
