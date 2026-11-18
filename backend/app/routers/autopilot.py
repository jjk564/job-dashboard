"""
REST API Router for the Autonomous JobPulse Autopilot Engine.
"""
import json
from datetime import datetime
from typing import Any, Dict, Optional
from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from ..database import get_db
from ..models import Job
from ..schemas import (
    AutopilotConfigResponse,
    AutopilotConfigUpdate,
    AutopilotRunRequest,
)
from ..services.autopilot import (
    ensure_candidate_profile,
    get_or_create_autopilot_config,
    is_autopilot_running,
    process_single_job_autopilot,
    run_autopilot_cycle,
)
from ..services.question_answerer import answer_single_question

router = APIRouter(prefix="/api/autopilot", tags=["Autopilot"])


@router.get("/config", response_model=AutopilotConfigResponse)
async def get_autopilot_config(db: AsyncSession = Depends(get_db)):
    cfg = await get_or_create_autopilot_config(db)
    data = cfg.to_dict()
    data["is_running"] = is_autopilot_running()
    return data


@router.put("/config", response_model=AutopilotConfigResponse)
async def update_autopilot_config(
    payload: AutopilotConfigUpdate,
    db: AsyncSession = Depends(get_db),
):
    cfg = await get_or_create_autopilot_config(db)
    updates = payload.model_dump(exclude_unset=True)

    if "enabled" in updates and updates["enabled"] is not None:
        cfg.enabled = bool(updates["enabled"])
    if "interval_minutes" in updates and updates["interval_minutes"] is not None:
        cfg.interval_minutes = max(5, int(updates["interval_minutes"]))
    if "search_profile_id" in updates:
        cfg.search_profile_id = updates["search_profile_id"]
    if "sources" in updates and updates["sources"] is not None:
        cfg.sources_json = json.dumps(updates["sources"] or ["all"])
    if "min_discover_score" in updates and updates["min_discover_score"] is not None:
        cfg.min_discover_score = max(0, min(100, int(updates["min_discover_score"])))
    if "min_auto_apply_score" in updates and updates["min_auto_apply_score"] is not None:
        cfg.min_auto_apply_score = max(0, min(100, int(updates["min_auto_apply_score"])))
    if "max_jobs_per_run" in updates and updates["max_jobs_per_run"] is not None:
        cfg.max_jobs_per_run = max(1, min(100, int(updates["max_jobs_per_run"])))
    if "auto_submit" in updates and updates["auto_submit"] is not None:
        cfg.auto_submit = bool(updates["auto_submit"])
    if "headless" in updates and updates["headless"] is not None:
        cfg.headless = bool(updates["headless"])
    if "require_full_qa_confidence" in updates and updates["require_full_qa_confidence"] is not None:
        cfg.require_full_qa_confidence = bool(updates["require_full_qa_confidence"])
    if "ai_provider" in updates and updates["ai_provider"]:
        cfg.ai_provider = updates["ai_provider"]
    if "blocked_companies" in updates and updates["blocked_companies"] is not None:
        cfg.blocked_companies_json = json.dumps([c.strip() for c in updates["blocked_companies"] if c and c.strip()])
    if "imap_server" in updates and updates["imap_server"] is not None:
        cfg.imap_server = updates["imap_server"].strip() or "imap.gmail.com"
    if "imap_email" in updates and updates["imap_email"] is not None:
        cfg.imap_email = updates["imap_email"].strip()
    if "imap_password" in updates and updates["imap_password"] is not None:
        cfg.imap_password = updates["imap_password"].strip()

    cfg.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(cfg)

    data = cfg.to_dict()
    data["is_running"] = is_autopilot_running()
    return data


@router.post("/run")
async def trigger_autopilot_cycle(
    req: Optional[AutopilotRunRequest] = Body(default=None),
    db: AsyncSession = Depends(get_db),
):
    """
    Triggers an autonomous Autopilot cycle:
    - Scrapes suitable job listings (when `scrape_new=True`)
    - Generates tailored resumes & cover letters
    - Answers all necessary screening questions
    - Submits applications whenever possible (`APPLIED`)
    - Routes all other jobs into `TO_APPLY` ("Need to Apply") with materials attached.
    """
    overrides = req.model_dump(exclude_unset=True) if req else {}
    summary = await run_autopilot_cycle(db, overrides=overrides)

    # Also return full updated pipeline jobs list so the frontend Kanban updates immediately
    j_res = await db.execute(
        select(Job)
        .options(selectinload(Job.activities), selectinload(Job.tailored_documents))
        .execution_options(populate_existing=True)
        .order_by(Job.updated_at.desc())
    )
    all_jobs = [j.to_dict() for j in j_res.scalars().all()]
    return {
        "summary": summary,
        "jobs": all_jobs,
    }


@router.post("/jobs/{job_id}/run")
async def run_autopilot_for_single_job(
    job_id: int,
    payload: Optional[Dict[str, Any]] = Body(default=None),
    db: AsyncSession = Depends(get_db),
):
    """
    Runs the full Autopilot workflow on a single job in the pipeline:
    Generates tailored resume, tailored cover letter, answers all questions,
    and attempts autonomous application submission (or prepares for Need to Apply).
    """
    res = await db.execute(
        select(Job)
        .options(selectinload(Job.activities), selectinload(Job.tailored_documents))
        .where(Job.id == job_id)
    )
    job = res.scalars().first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    cfg = await get_or_create_autopilot_config(db)
    cfg_dict = cfg.to_dict()
    opts = payload or {}

    profile_dict, skills = await ensure_candidate_profile(db)
    imap_config = {
        "imap_server": cfg.imap_server or "imap.gmail.com",
        "imap_email": (cfg.imap_email or profile_dict.get("email") or "").strip(),
        "imap_password": (cfg.imap_password or "").strip(),
    }

    result = await process_single_job_autopilot(
        db=db,
        job=job,
        profile_dict=profile_dict,
        skills=skills,
        min_auto_apply_score=opts.get("min_auto_apply_score", cfg_dict["min_auto_apply_score"]),
        auto_submit=opts.get("auto_submit", cfg_dict["auto_submit"]),
        headless=opts.get("headless", cfg_dict["headless"]),
        require_full_qa_confidence=opts.get("require_full_qa_confidence", cfg_dict["require_full_qa_confidence"]),
        ai_provider=opts.get("ai_provider", cfg_dict["ai_provider"]),
        api_key=opts.get("api_key"),
        imap_config=imap_config,
    )

    # Reload full job with relationships
    refreshed_res = await db.execute(
        select(Job)
        .options(selectinload(Job.activities), selectinload(Job.tailored_documents))
        .execution_options(populate_existing=True)
        .where(Job.id == job_id)
    )
    updated_job = refreshed_res.scalars().first()

    return {
        "result": result,
        "job": updated_job.to_dict() if updated_job else job.to_dict(),
    }


@router.post("/jobs/{job_id}/answer-question")
async def answer_custom_job_question(
    job_id: int,
    payload: Dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Answers a specific screening question for a job and appends/updates it in the job's Q&A bank.
    """
    question_text = (payload.get("question") or "").strip()
    if not question_text:
        raise HTTPException(status_code=400, detail="Question text is required")

    res = await db.execute(
        select(Job)
        .options(selectinload(Job.activities), selectinload(Job.tailored_documents))
        .where(Job.id == job_id)
    )
    job = res.scalars().first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    profile_dict, skills = await ensure_candidate_profile(db)
    qa = answer_single_question(
        question_text=question_text,
        job_data=job.to_dict(),
        profile_data=profile_dict,
        candidate_skills=skills,
        options=payload.get("options"),
        required=True,
    )

    existing_answers = []
    if job.answers_json:
        try:
            existing_answers = json.loads(job.answers_json)
        except Exception:
            existing_answers = []

    updated = False
    for idx, item in enumerate(existing_answers):
        if (item.get("question") or "").strip().lower() == question_text.lower():
            existing_answers[idx] = qa
            updated = True
            break
    if not updated:
        existing_answers.insert(0, qa)

    job.answers_json = json.dumps(existing_answers)
    job.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(job)

    return {
        "answer_item": qa,
        "answers": existing_answers,
    }


@router.post("/test-email")
async def test_autopilot_email_reader(
    payload: Optional[Dict[str, Any]] = Body(default=None),
    db: AsyncSession = Depends(get_db),
):
    """
    Tests IMAP connection for automatic Greenhouse / ATS verification code retrieval.
    """
    import asyncio
    from ..services.email_code_reader import test_imap_connection

    cfg = await get_or_create_autopilot_config(db)
    profile_dict, _ = await ensure_candidate_profile(db)
    body = payload or {}

    server = (body.get("imap_server") or cfg.imap_server or "imap.gmail.com").strip()
    email_addr = (body.get("imap_email") or cfg.imap_email or profile_dict.get("email") or "").strip()
    password = (body.get("imap_password") or cfg.imap_password or "").strip()

    if body.get("save") and password:
        cfg.imap_server = server
        cfg.imap_email = email_addr
        cfg.imap_password = password
        cfg.updated_at = datetime.utcnow()
        await db.commit()

    return await asyncio.to_thread(test_imap_connection, server, email_addr, password)


@router.post("/submit-security-code")
async def submit_manual_security_code(
    payload: Dict[str, Any] = Body(...),
):
    """
    Drops an 8-character Greenhouse security code into the local manual code file
    so any active Playwright session (headless or assisted desktop window) fills it immediately.
    """
    from ..services.email_code_reader import save_manual_security_code

    code = (payload.get("code") or "").strip()
    if not code:
        raise HTTPException(status_code=400, detail="Security code is required")

    save_manual_security_code(code, job_id=payload.get("job_id"))
    return {
        "success": True,
        "message": f"Security code '{code}' queued for active browser session.",
    }

