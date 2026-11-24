import json
import os
import re
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from ..database import get_db
from ..models import ApplicationActivity, Job, Profile, Skill, TailoredDocument
from ..schemas import (
    MatchAnalysisResponse,
    GenerateDocumentRequest,
    GenerateDocumentResponse,
    AutofillPayloadResponse,
)
from ..services.matcher import analyze_job_fit
from ..services.ai_generator import generate_ai_document
from ..services.browser_assistant import launch_assisted_application, launch_speedrun_queue
from ..services.bot_trap_detector import detect_bot_traps, merge_bot_traps
from ..services.question_answerer import PACKETS_DIR, answer_single_question

router = APIRouter(prefix="/api/assistant", tags=["Assistant"])

NATIVE_QUEUE_PATH = PACKETS_DIR / "native_browser_queue.json"


def _load_native_queue() -> Dict[str, Any]:
    if not NATIVE_QUEUE_PATH.exists():
        return {"jobs": [], "index": 0, "updated_at": None}
    try:
        data = json.loads(NATIVE_QUEUE_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("jobs"), list):
            return data
    except Exception:
        pass
    return {"jobs": [], "index": 0, "updated_at": None}


def _save_native_queue(state: Dict[str, Any]) -> None:
    PACKETS_DIR.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = datetime.utcnow().isoformat()
    NATIVE_QUEUE_PATH.write_text(json.dumps(state), encoding="utf-8")


class SpeedRunRequest(BaseModel):
    job_ids: Optional[List[int]] = None
    mode: Optional[str] = "playwright"  # "playwright" | "native_chrome"


class StageBrowserQueueRequest(BaseModel):
    job_ids: Optional[List[int]] = None
    open_browser: bool = True


class AnswerFieldsItem(BaseModel):
    id: str
    label: str
    options: Optional[List[str]] = None
    field_type: str = "text"
    required: bool = False


class AnswerFieldsRequest(BaseModel):
    job_id: Optional[int] = None
    url: Optional[str] = None
    fields: List[AnswerFieldsItem]
    page_text: Optional[str] = None


class NativeQueueActionRequest(BaseModel):
    action: str  # "mark_applied_next" | "skip" | "exit"
    job_id: Optional[int] = None


@router.post("/speed-run/start")
async def start_speed_run(
    req: Optional[SpeedRunRequest] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Launches a rapid sequential application queue for all or selected jobs
    in the 'Need to Apply' column. Pre-fills form fields, uploads tailored resumes,
    and provides a floating HUD for instant review, 2FA detection, and auto-advancement.
    """
    from ..services.autopilot import (
        ensure_candidate_profile,
        get_or_create_autopilot_config,
        prepare_job_application_materials,
    )

    if req and req.job_ids:
        query = select(Job).where(Job.id.in_(req.job_ids), Job.is_expired.is_(False))
    else:
        query = (
            select(Job)
            .where(Job.status.in_(["TO_APPLY", "WISHLIST"]), Job.is_expired.is_(False))
            .order_by(Job.fit_score.desc().nullslast(), Job.updated_at.desc())
        )

    res = await db.execute(query)
    jobs = res.scalars().all()

    jobs_with_url = [j for j in jobs if j.url and j.url.strip()]
    if not jobs_with_url:
        return {
            "success": False,
            "message": "No eligible jobs with application URLs found in 'Need to Apply'.",
            "count": 0,
        }

    # For speed-run on entire column, strictly queue direct ATS application forms
    from ..services.browser_assistant import is_direct_ats_url, classify_ats_url
    if not (req and req.job_ids):
        direct_jobs = [j for j in jobs_with_url if is_direct_ats_url(j.url)]
        if direct_jobs:
            jobs_with_url = direct_jobs

    cfg = await get_or_create_autopilot_config(db)
    profile_dict, skills = await ensure_candidate_profile(db)

    queue_payload = []
    for job in jobs_with_url:
        try:
            materials = await prepare_job_application_materials(
                db=db,
                job=job,
                profile_dict=profile_dict,
                skills=skills,
                fast_batch_mode=True,
            )
            queue_payload.append({
                "job_id": job.id,
                "job_url": job.url,
                "job_data": job.to_dict(),
                "profile_data": profile_dict,
                "candidate_skills": skills,
                "app_kit": materials.get("app_kit"),
                "files": materials.get("files"),
            })
        except Exception:
            queue_payload.append({
                "job_id": job.id,
                "job_url": job.url,
                "job_data": job.to_dict(),
                "profile_data": profile_dict,
                "candidate_skills": skills,
            })

    await db.commit()

    imap_config = {
        "imap_server": cfg.imap_server or "imap.gmail.com",
        "imap_email": (cfg.imap_email or profile_dict.get("email") or "").strip(),
        "imap_password": (cfg.imap_password or "").strip(),
    }

    if req and (req.mode or "").lower() == "native_chrome":
        _save_native_queue({
            "jobs": [
                {
                    "job_id": item["job_id"],
                    "job_url": item["job_url"],
                    "company": (item.get("job_data") or {}).get("company", ""),
                    "title": (item.get("job_data") or {}).get("title", ""),
                    "files": item.get("files") or {},
                }
                for item in queue_payload
            ],
            "index": 0,
        })
        first_url = queue_payload[0]["job_url"]
        try:
            webbrowser.open(first_url)
        except Exception:
            pass
        return {
            "success": True,
            "mode": "native_chrome",
            "count": len(queue_payload),
            "active_url": first_url,
            "message": f"Opened Speed-Run ({len(queue_payload)} jobs) in your regular browser! The JobPulse Chrome Extension will auto-fill each form with zero CAPTCHA interference.",
        }

    result = await launch_speedrun_queue(
        jobs_payload=queue_payload,
        imap_config=imap_config,
    )
    return result

@router.post("/{job_id}/match", response_model=MatchAnalysisResponse)
async def analyze_job_match(job_id: int, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Job).where(Job.id == job_id))
    job = res.scalars().first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    p_res = await db.execute(select(Profile).limit(1))
    profile = p_res.scalars().first()
    s_res = await db.execute(select(Skill))
    skills = [s.name for s in s_res.scalars().all()]

    job_text = f"{job.title} {job.description or ''} {job.requirements or ''}"
    profile_text = f"{profile.summary if profile else ''} {profile.master_resume_text if profile else ''}"

    analysis = analyze_job_fit(job_text, skills, profile_text)

    # Persist score to job
    job.fit_score = analysis["score"]
    job.fit_breakdown = json.dumps(analysis)
    await db.commit()
    await db.refresh(job)

    return analysis

@router.post("/{job_id}/generate", response_model=GenerateDocumentResponse)
async def generate_document(
    job_id: int,
    req: GenerateDocumentRequest,
    db: AsyncSession = Depends(get_db)
):
    res = await db.execute(select(Job).where(Job.id == job_id))
    job = res.scalars().first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    p_res = await db.execute(select(Profile).limit(1))
    profile = p_res.scalars().first()
    profile_dict = profile.to_dict() if profile else {}

    # Extract matched skills
    matched_skills = []
    if job.fit_breakdown:
        try:
            b = json.loads(job.fit_breakdown)
            matched_skills = b.get("matched_skills", [])
        except Exception:
            pass

    # Default to hadoku-resume when .devvault.local.json is active and no explicit provider was forced
    from ..services.hadoku_client import (
        get_hadoku_user_key,
        generate_hadoku_tailored_resume,
        generate_hadoku_cover_letter,
        generate_hadoku_application_extras,
        mint_hadoku_resume_variant,
    )
    effective_provider = req.provider or ("hadoku" if get_hadoku_user_key(req.api_key) else "template")
    if effective_provider == "template" and get_hadoku_user_key(req.api_key):
        effective_provider = "hadoku"

    content, provider_used = await generate_ai_document(
        doc_type=req.doc_type,
        job_data=job.to_dict(),
        profile_data=profile_dict,
        matched_skills=matched_skills,
        tone=req.tone or "professional",
        custom_instructions=req.custom_instructions,
        provider=effective_provider,
        api_key=req.api_key,
    )

    # Save to database
    doc = TailoredDocument(
        job_id=job.id,
        doc_type=req.doc_type,
        content=content
    )
    db.add(doc)
    await db.commit()

    return {
        "doc_type": req.doc_type,
        "content": content,
        "provider_used": provider_used,
    }


@router.post("/{job_id}/application-kit")
async def generate_job_application_kit(job_id: int, db: AsyncSession = Depends(get_db)):
    """
    Calls Hadoku Resume Service (/resume/api/application-extras) to produce the structured
    non-resume application kit: why_hook, intro_email, linkedin_note, salary_line,
    talking_points, screening_answers, and cover_letter_markdown.
    """
    from ..services.hadoku_client import (
        get_hadoku_user_key,
        generate_hadoku_tailored_resume,
        generate_hadoku_application_extras,
    )
    from ..services.ai_generator import generate_offline_template

    res = await db.execute(select(Job).where(Job.id == job_id))
    job = res.scalars().first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    p_res = await db.execute(select(Profile).limit(1))
    profile = p_res.scalars().first()
    profile_dict = profile.to_dict() if profile else {}

    matched_skills = []
    if job.fit_breakdown:
        try:
            matched_skills = json.loads(job.fit_breakdown).get("matched_skills", [])
        except Exception:
            pass

    if get_hadoku_user_key():
        tailored = await generate_hadoku_tailored_resume(
            job_title=job.title,
            company=job.company,
            description=job.description or f"{job.title} at {job.company}",
            tailor=True,
        )
        resume_md = (
            (tailored or {}).get("resume_markdown")
            or (profile.master_resume_text if profile else "")
            or generate_offline_template("tailored_resume", job.to_dict(), profile_dict, matched_skills)
        )
        extras = await generate_hadoku_application_extras(
            job_title=job.title,
            company=job.company,
            description=job.description or f"{job.title} at {job.company}",
            resume_markdown=resume_md,
            job_location=job.location,
            workplace_type=job.workplace_type,
        )
        if extras:
            return {
                "provider_used": "hadoku-resume",
                "why_hook": extras.get("why_hook", ""),
                "intro_email": extras.get("intro_email", ""),
                "linkedin_note": extras.get("linkedin_note", ""),
                "salary_line": extras.get("salary_line", ""),
                "talking_points": extras.get("talking_points", []),
                "screening_answers": extras.get("screening_answers", []),
                "cover_letter_markdown": extras.get("cover_letter_markdown", ""),
                "standard_fields": extras.get("standard_fields", ""),
            }

    # Local fallback if offline
    skills_str = ", ".join(matched_skills[:4]) if matched_skills else "Python, TypeScript, and modern systems"
    return {
        "provider_used": "local-fallback",
        "why_hook": f"I am excited by {job.company}'s work and the chance to bring my expertise in {skills_str} to the {job.title} team.",
        "intro_email": f"Hi Hiring Team,\n\nI recently applied for the {job.title} role at {job.company}. With hands-on experience in {skills_str}, I'd love to share how I can contribute to your roadmap.",
        "linkedin_note": f"Hi! I just applied for the {job.title} role at {job.company}. Given my background in {skills_str}, I'd love to connect!",
        "salary_line": profile_dict.get("desired_salary") or "Competitive / Open to discussion based on total compensation",
        "talking_points": [
            f"Proven delivery using {skills_str} in production environments.",
            f"Direct alignment with {job.company}'s {job.title} requirements.",
            "Strong track record of cross-functional ownership and automated testing.",
        ],
        "screening_answers": [
            {"q": "Why are you interested in this role?", "a": f"The {job.title} position at {job.company} aligns closely with my background in {skills_str}."},
            {"q": "Do you require visa sponsorship?", "a": profile_dict.get("work_authorization") or "Authorized to work in the US without sponsorship."},
            {"q": "What is your availability / notice period?", "a": profile_dict.get("notice_period") or "2 weeks notice; available to start promptly."},
        ],
        "cover_letter_markdown": generate_offline_template("cover_letter", job.to_dict(), profile_dict, matched_skills),
        "standard_fields": "",
    }


@router.post("/{job_id}/mint-packet")
async def mint_job_resume_packet(job_id: int, db: AsyncSession = Depends(get_db)):
    """
    Generates a tailored resume + cover letter for the job and mints a shareable
    Hadoku Resume Variant Packet (`https://hadoku.me/resume?v={slug}` + PDF download).
    """
    from ..services.hadoku_client import (
        get_hadoku_user_key,
        generate_hadoku_tailored_resume,
        generate_hadoku_cover_letter,
        mint_hadoku_resume_variant,
    )
    from ..services.ai_generator import generate_offline_template
    from ..models import ApplicationActivity

    res = await db.execute(select(Job).where(Job.id == job_id))
    job = res.scalars().first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if not get_hadoku_user_key():
        raise HTTPException(
            status_code=400,
            detail="No Hadoku vault credential found (.devvault.local.json). Run `npx @hadoku/dev-vault login` first.",
        )

    p_res = await db.execute(select(Profile).limit(1))
    profile = p_res.scalars().first()
    profile_dict = profile.to_dict() if profile else {}

    matched_skills = []
    if job.fit_breakdown:
        try:
            matched_skills = json.loads(job.fit_breakdown).get("matched_skills", [])
        except Exception:
            pass

    tailored = await generate_hadoku_tailored_resume(
        job_title=job.title,
        company=job.company,
        description=job.description or f"{job.title} at {job.company}",
        tailor=True,
    )
    resume_md = (
        (tailored or {}).get("resume_markdown")
        or generate_offline_template("tailored_resume", job.to_dict(), profile_dict, matched_skills)
    )

    cl_res = await generate_hadoku_cover_letter(
        job_title=job.title,
        company=job.company,
        description=job.description or f"{job.title} at {job.company}",
    )
    cover_md = (cl_res or {}).get("cover_letter_markdown")

    minted = await mint_hadoku_resume_variant(
        label=f"{job.company} - {job.title}",
        markdown=resume_md,
        cover_letter_markdown=cover_md,
        company=job.company,
        job_title=job.title,
        ttl_days=365,
    )
    if not minted:
        raise HTTPException(status_code=502, detail="Failed to mint packet variant on hadoku.me/resume/api/variants")

    # Save packet record in TailoredDocument and ApplicationActivity
    packet_summary = (
        f"# Minted Hadoku Application Packet\n"
        f"- **Packet Link:** {minted['url']}\n"
        f"- **Server PDF Download:** {minted['pdf_url']}\n"
        f"- **Variant Slug:** `{minted['slug']}`\n\n"
        f"---\n\n{resume_md}"
    )
    db.add(TailoredDocument(job_id=job.id, doc_type="packet", content=packet_summary))
    db.add(
        ApplicationActivity(
            job_id=job.id,
            activity_type="packet_minted",
            title=f"Minted Hadoku Packet ({minted['slug']})",
            details=f"Shareable URL: {minted['url']} | PDF: {minted['pdf_url']}",
        )
    )
    await db.commit()

    return minted

@router.get("/{job_id}/autofill-payload", response_model=AutofillPayloadResponse)
async def get_autofill_payload(job_id: int, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Job).where(Job.id == job_id))
    job = res.scalars().first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    p_res = await db.execute(select(Profile).limit(1))
    profile = p_res.scalars().first()
    if not profile:
        raise HTTPException(status_code=400, detail="Profile not configured")

    name_parts = (profile.full_name or "").split()
    first_name = name_parts[0] if name_parts else ""
    last_name = " ".join(name_parts[1:]) if len(name_parts) > 1 else ""

    # Check for latest cover letter
    doc_res = await db.execute(
        select(TailoredDocument)
        .where(TailoredDocument.job_id == job_id, TailoredDocument.doc_type == "cover_letter")
        .order_by(TailoredDocument.created_at.desc())
        .limit(1)
    )
    doc = doc_res.scalars().first()
    cover_snippet = doc.content if doc else f"I am excited to apply for the {job.title} role at {job.company}."

    return {
        "first_name": first_name,
        "last_name": last_name,
        "full_name": profile.full_name or "",
        "email": profile.email or "",
        "phone": profile.phone or "",
        "location": profile.location or "",
        "linkedin_url": profile.linkedin_url or "",
        "github_url": profile.github_url or "",
        "portfolio_url": profile.portfolio_url or "",
        "work_authorization": profile.work_authorization or "",
        "desired_salary": profile.desired_salary or "",
        "notice_period": profile.notice_period or "",
        "summary": profile.summary or "",
        "cover_letter_snippet": cover_snippet,
    }

@router.post("/{job_id}/launch-browser")
async def trigger_browser_assistant(job_id: int, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Job).where(Job.id == job_id))
    job = res.scalars().first()
    if not job or not job.url:
        raise HTTPException(status_code=400, detail="Job or job URL not found")

    from ..services.browser_assistant import classify_ats_url, resolve_direct_ats_url
    url_cls = classify_ats_url(job.url)
    if not url_cls.get("can_auto_attempt", True):
        # Attempt to automatically discover the direct ATS form (Greenhouse, Lever, Ashby)
        direct_url = resolve_direct_ats_url(
            company=job.company,
            title=job.title,
            original_url=job.url,
        )
        if direct_url:
            job.url = direct_url
            await db.commit()
            url_cls = classify_ats_url(job.url)

    if not url_cls.get("can_auto_attempt", True):
        portal = url_cls.get("portal") or "This portal"
        return {
            "success": False,
            "is_gated": True,
            "message": f"Cannot Auto-Fill: {url_cls['reason']}. {portal} requires candidate login / registration rather than providing a direct application form. Please open the link in your standard browser to log in or apply manually.",
        }

    from ..services.autopilot import (
        ensure_candidate_profile,
        get_or_create_autopilot_config,
        prepare_job_application_materials,
    )
    cfg = await get_or_create_autopilot_config(db)
    profile_dict, skills = await ensure_candidate_profile(db)
    materials = await prepare_job_application_materials(
        db=db,
        job=job,
        profile_dict=profile_dict,
        skills=skills,
        fast_batch_mode=True,
    )
    await db.commit()

    imap_config = {
        "imap_server": cfg.imap_server or "imap.gmail.com",
        "imap_email": (cfg.imap_email or profile_dict.get("email") or "").strip(),
        "imap_password": (cfg.imap_password or "").strip(),
    }

    result = await launch_assisted_application(
        job_url=job.url,
        profile_data=profile_dict,
        job_data=job.to_dict(),
        candidate_skills=skills,
        app_kit=materials.get("app_kit"),
        files=materials.get("files"),
        imap_config=imap_config,
    )
    return result


@router.post("/stage-browser-queue")
async def stage_native_browser_queue(
    req: Optional[StageBrowserQueueRequest] = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Stages one or more jobs for the JobPulse Native Chrome Extension and optionally opens
    the first URL directly in the user's regular desktop browser (zero Playwright / zero CAPTCHA loops).
    """
    from ..services.autopilot import ensure_candidate_profile, prepare_job_application_materials
    from ..services.browser_assistant import is_direct_ats_url, resolve_direct_ats_url, classify_ats_url

    if req and req.job_ids:
        q = select(Job).where(Job.id.in_(req.job_ids))
    else:
        q = (
            select(Job)
            .where(Job.status.in_(["TO_APPLY", "WISHLIST"]), Job.is_expired.is_(False))
            .order_by(Job.fit_score.desc().nullslast(), Job.updated_at.desc())
        )
    res = await db.execute(q)
    jobs = [j for j in res.scalars().all() if j.url and j.url.strip()]
    if not jobs:
        return {"success": False, "count": 0, "message": "No eligible jobs with URLs found to stage."}

    # When staging entire column, prioritize direct ATS postings first, then remaining jobs
    if not (req and req.job_ids):
        direct_jobs = [j for j in jobs if is_direct_ats_url(j.url)]
        if direct_jobs:
            jobs = direct_jobs

    profile_dict, skills = await ensure_candidate_profile(db)
    staged_items: List[Dict[str, Any]] = []
    for job in jobs[:25]:
        # Try resolving aggregator URL to direct ATS if single-job stage
        if req and req.job_ids and not classify_ats_url(job.url).get("can_auto_attempt", True):
            direct_url = resolve_direct_ats_url(company=job.company, title=job.title, original_url=job.url)
            if direct_url:
                job.url = direct_url
        try:
            materials = await prepare_job_application_materials(
                db=db,
                job=job,
                profile_dict=profile_dict,
                skills=skills,
                fast_batch_mode=True,
            )
            files = materials.get("files") or {}
        except Exception:
            files = {}

        staged_items.append({
            "job_id": job.id,
            "job_url": job.url,
            "company": job.company,
            "title": job.title,
            "files": files,
        })

    await db.commit()
    _save_native_queue({"jobs": staged_items, "index": 0})

    first_url = staged_items[0]["job_url"]
    if not req or req.open_browser:
        try:
            webbrowser.open(first_url)
        except Exception:
            pass

    return {
        "success": True,
        "count": len(staged_items),
        "active_url": first_url,
        "message": f"Staged {len(staged_items)} job(s) for Regular Chrome auto-fill. Install/enable the JobPulse Chrome Extension (extension/ folder) to auto-fill with zero CAPTCHA friction!",
    }


def _urls_roughly_match(tab_url: str, job_url: str, company: str = "") -> bool:
    if not tab_url or not job_url:
        return False
    t = tab_url.strip().lower()
    j = job_url.strip().lower()
    if t == j or t.split("?")[0] == j.split("?")[0]:
        return True
    try:
        pt, pj = urlparse(t), urlparse(j)
        host_t = (pt.netloc or "").replace("www.", "")
        host_j = (pj.netloc or "").replace("www.", "")
        same_host = bool(host_t and host_j and host_t == host_j)
        # SmartRecruiters redirects between jobs.smartrecruiters.com and smartr.me
        sr_pair = (
            ("smartrecruiters.com" in host_t or "smartr.me" in host_t)
            and ("smartrecruiters.com" in host_j or "smartr.me" in host_j)
        )
        if same_host or sr_pair:
            p_t = pt.path.rstrip("/")
            p_j = pj.path.rstrip("/")
            if p_j and (p_t.startswith(p_j) or p_j.startswith(p_t)):
                return True
            # Match by Greenhouse gh_jid query param
            if "gh_jid=" in pt.query and "gh_jid=" in pj.query:
                return pt.query == pj.query
            # SmartRecruiters OneClick UI redirect:
            # job_url: /M3USA/744000158547269-software-engineer-remote-
            # tab_url: /oneclick-ui/company/M3USA/publication/<uuid>?dcr_ci=M3USA
            j_segs = [s for s in p_j.split("/") if s]
            t_segs = [s for s in p_t.split("/") if s]
            company_slug = re.sub(r"[^a-z0-9]", "", (company or "").lower())
            first_j_slug = re.sub(r"[^a-z0-9]", "", j_segs[0]) if j_segs else ""
            t_haystack = f"{p_t} {pt.query}"
            for slug in (first_j_slug, company_slug):
                if slug and len(slug) >= 3 and slug not in ("jobs", "job", "careers", "apply", "company", "oneclickui"):
                    if f"/{slug}/" in f"{p_t}/" or f"={slug}" in t_haystack or slug in [re.sub(r"[^a-z0-9]", "", s) for s in t_segs]:
                        return True
            # Shared numeric/UUID job identifier segment (5+ chars)
            j_ids = {s for s in j_segs if len(s) >= 5 and re.search(r"\d", s)}
            t_ids = {s for s in t_segs if len(s) >= 5 and re.search(r"\d", s)}
            if j_ids and t_ids and (j_ids & t_ids):
                return True
    except Exception:
        pass
    return False


@router.get("/active-autofill")
async def get_active_autofill(
    url: Optional[str] = Query(None),
    force: bool = Query(False),
    db: AsyncSession = Depends(get_db),
):
    """
    Used by the JobPulse Native Chrome Extension to retrieve candidate profile,
    active job context, Bot Trap alerts, cover letter text, and tailored PDF download URLs.
    """
    from ..services.autopilot import ensure_candidate_profile, prepare_job_application_materials

    profile_dict, skills = await ensure_candidate_profile(db)
    queue_state = _load_native_queue()
    q_jobs = queue_state.get("jobs") or []
    q_idx = int(queue_state.get("index") or 0)

    matched_entry: Optional[Dict[str, Any]] = None
    matched_idx = q_idx

    # 1. Check if current tab URL matches active or any staged queue job
    if url and q_jobs:
        if 0 <= q_idx < len(q_jobs) and _urls_roughly_match(url, q_jobs[q_idx].get("job_url", ""), q_jobs[q_idx].get("company", "")):
            matched_entry = q_jobs[q_idx]
            matched_idx = q_idx
        else:
            for idx, entry in enumerate(q_jobs):
                if _urls_roughly_match(url, entry.get("job_url", ""), entry.get("company", "")):
                    matched_entry = entry
                    matched_idx = idx
                    break

    # 2. If no URL match in queue, check if current tab URL matches any job in the pipeline DB
    job_obj: Optional[Job] = None
    if matched_entry and matched_entry.get("job_id"):
        r = await db.execute(select(Job).where(Job.id == matched_entry["job_id"]))
        job_obj = r.scalars().first()
    elif url:
        r = await db.execute(select(Job).where(Job.url.isnot(None)).order_by(Job.updated_at.desc()).limit(250))
        for cand in r.scalars().all():
            if _urls_roughly_match(url, cand.url or "", cand.company or ""):
                job_obj = cand
                break

    # 3. Fallback: return active staged job when popup asks without URL OR when user explicitly forces autofill
    if job_obj is None and (not url or force) and 0 <= q_idx < len(q_jobs):
        matched_entry = q_jobs[q_idx]
        if matched_entry.get("job_id"):
            r = await db.execute(select(Job).where(Job.id == matched_entry["job_id"]))
            job_obj = r.scalars().first()

    job_payload: Optional[Dict[str, Any]] = None
    if job_obj is not None:
        files = (matched_entry or {}).get("files") or {}
        if not files or not (files.get("resume_pdf") and os.path.exists(files["resume_pdf"])):
            try:
                materials = await prepare_job_application_materials(
                    db=db,
                    job=job_obj,
                    profile_dict=profile_dict,
                    skills=skills,
                    fast_batch_mode=True,
                )
                files = materials.get("files") or {}
                await db.commit()
            except Exception:
                files = {}

        cover_text = ""
        cl_path = files.get("cover_letter_txt") or files.get("cover_letter_md")
        if cl_path and os.path.exists(cl_path):
            try:
                cover_text = Path(cl_path).read_text(encoding="utf-8").strip()
            except Exception:
                pass
        if not cover_text:
            doc_res = await db.execute(
                select(TailoredDocument)
                .where(TailoredDocument.job_id == job_obj.id, TailoredDocument.doc_type == "cover_letter")
                .order_by(TailoredDocument.created_at.desc())
                .limit(1)
            )
            cl_doc = doc_res.scalars().first()
            if cl_doc:
                cover_text = cl_doc.content

        j_dict = job_obj.to_dict()
        res_pdf_path = files.get("resume_pdf") or files.get("legacy_resume_pdf")
        cl_pdf_path = files.get("cover_letter_pdf") or files.get("legacy_cover_letter_pdf")
        job_payload = {
            "id": job_obj.id,
            "title": job_obj.title,
            "company": job_obj.company,
            "url": job_obj.url,
            "location": job_obj.location,
            "workplace_type": job_obj.workplace_type,
            "source": job_obj.source,
            "status": job_obj.status,
            "bot_traps": j_dict.get("bot_traps") or [],
            "answers": j_dict.get("answers") or [],
            "cover_letter_text": cover_text,
            "resume_filename": os.path.basename(res_pdf_path) if res_pdf_path else "Resume.pdf",
            "cover_letter_filename": os.path.basename(cl_pdf_path) if cl_pdf_path else "Cover_Letter.pdf",
            "resume_pdf_url": f"/api/assistant/jobs/{job_obj.id}/packet-file/resume_pdf" if res_pdf_path and os.path.exists(res_pdf_path) else None,
            "cover_letter_pdf_url": f"/api/assistant/jobs/{job_obj.id}/packet-file/cover_letter_pdf" if cl_pdf_path and os.path.exists(cl_pdf_path) else None,
        }

    return {
        "matched": job_payload is not None,
        "profile": profile_dict,
        "skills": skills,
        "job": job_payload,
        "queue": {
            "is_speed_run": len(q_jobs) > 1,
            "index": matched_idx,
            "total": len(q_jobs),
            "active_url": q_jobs[q_idx]["job_url"] if 0 <= q_idx < len(q_jobs) else None,
        },
    }


@router.post("/answer-fields")
async def answer_form_fields_batch(
    req: AnswerFieldsRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Batch-answers discovered ATS form fields using the hardened Python Q&A engine
    and scans live page text for Bot Traps. Powers the Native Chrome Extension.
    """
    from ..services.autopilot import ensure_candidate_profile

    profile_dict, skills = await ensure_candidate_profile(db)
    job_obj: Optional[Job] = None
    if req.job_id:
        r = await db.execute(select(Job).where(Job.id == req.job_id))
        job_obj = r.scalars().first()
    job_dict = job_obj.to_dict() if job_obj else {"url": req.url or "", "title": "", "company": ""}

    # Scan live page text for bot traps & merge with stored traps
    live_traps = detect_bot_traps(description=job_dict.get("description") or "", page_text=req.page_text or "")
    merged_traps = merge_bot_traps(job_dict.get("bot_traps"), live_traps)
    if job_obj and merged_traps and len(merged_traps) != len(job_dict.get("bot_traps") or []):
        job_obj.bot_traps_json = json.dumps(merged_traps)
        job_obj.updated_at = datetime.utcnow()
        await db.commit()

    results = []
    for fld in req.fields:
        qa = answer_single_question(
            question_text=fld.label,
            job_data=job_dict,
            profile_data=profile_dict,
            candidate_skills=skills,
            options=fld.options,
            field_type=fld.field_type,
            required=fld.required,
        )
        results.append({
            "id": fld.id,
            "label": fld.label,
            "answer": qa.get("answer", ""),
            "confidence": qa.get("confidence", "manual_needed"),
            "category": qa.get("category", "custom"),
        })

    return {
        "answers": results,
        "bot_traps": merged_traps,
    }


@router.post("/active-autofill/action")
async def handle_native_queue_action(
    req: NativeQueueActionRequest,
    db: AsyncSession = Depends(get_db),
):
    """Handles Mark Applied & Next, Skip, or Exit from the Native Chrome Extension HUD."""
    state = _load_native_queue()
    q_jobs = state.get("jobs") or []
    idx = int(state.get("index") or 0)
    target_job_id = req.job_id
    if not target_job_id and 0 <= idx < len(q_jobs):
        target_job_id = q_jobs[idx].get("job_id")

    if req.action in ("mark_applied_next", "mark_applied") and target_job_id:
        r = await db.execute(select(Job).where(Job.id == target_job_id))
        job = r.scalars().first()
        if job:
            job.status = "APPLIED"
            job.autopilot_status = "auto_applied"
            job.autopilot_reason = "Applied via Regular Chrome Extension"
            if not job.applied_at:
                job.applied_at = datetime.utcnow()
            job.updated_at = datetime.utcnow()
            db.add(ApplicationActivity(
                job_id=job.id,
                activity_type="status_change",
                title="Moved to APPLIED",
                details="Marked applied via JobPulse Chrome Extension",
            ))
            await db.commit()

    if req.action == "exit":
        _save_native_queue({"jobs": [], "index": 0})
        return {"success": True, "done": True, "next_url": None, "remaining": 0}

    # Advance index past the completed/skipped job
    next_idx = idx + 1
    if target_job_id:
        for i, it in enumerate(q_jobs):
            if it.get("job_id") == target_job_id:
                next_idx = i + 1
                break

    if next_idx < len(q_jobs):
        state["index"] = next_idx
        _save_native_queue(state)
        return {
            "success": True,
            "done": False,
            "next_url": q_jobs[next_idx].get("job_url"),
            "remaining": len(q_jobs) - next_idx,
        }

    _save_native_queue({"jobs": [], "index": 0})
    return {"success": True, "done": True, "next_url": None, "remaining": 0}


@router.get("/jobs/{job_id}/packet-file/{file_type}")
async def download_job_packet_file(
    job_id: int,
    file_type: str,
    db: AsyncSession = Depends(get_db),
):
    """Serves a job's exported tailored PDF (resume_pdf or cover_letter_pdf) to the local Chrome Extension."""
    if file_type not in ("resume_pdf", "cover_letter_pdf"):
        raise HTTPException(status_code=400, detail="Unsupported file_type")

    r = await db.execute(select(Job).where(Job.id == job_id))
    job = r.scalars().first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    from ..services.autopilot import ensure_candidate_profile, prepare_job_application_materials
    profile_dict, skills = await ensure_candidate_profile(db)
    materials = await prepare_job_application_materials(
        db=db,
        job=job,
        profile_dict=profile_dict,
        skills=skills,
        fast_batch_mode=True,
    )
    await db.commit()
    files = materials.get("files") or {}
    path_str = files.get(file_type) or files.get(f"legacy_{file_type}")
    if not path_str or not os.path.exists(path_str):
        raise HTTPException(status_code=404, detail="Exported PDF file not found")

    return FileResponse(
        path=path_str,
        media_type="application/pdf",
        filename=os.path.basename(path_str),
    )
