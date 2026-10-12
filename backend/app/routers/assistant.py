import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from ..database import get_db
from ..models import Job, Profile, Skill, TailoredDocument
from ..schemas import (
    MatchAnalysisResponse,
    GenerateDocumentRequest,
    GenerateDocumentResponse,
    AutofillPayloadResponse,
)
from ..services.matcher import analyze_job_fit
from ..services.ai_generator import generate_ai_document
from ..services.browser_assistant import launch_assisted_application

router = APIRouter(prefix="/api/assistant", tags=["Assistant"])

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

    content, provider_used = await generate_ai_document(
        doc_type=req.doc_type,
        job_data=job.to_dict(),
        profile_data=profile_dict,
        matched_skills=matched_skills,
        tone=req.tone or "professional",
        custom_instructions=req.custom_instructions,
        provider=req.provider or "template",
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

    p_res = await db.execute(select(Profile).limit(1))
    profile = p_res.scalars().first()
    profile_dict = profile.to_dict() if profile else {}

    result = await launch_assisted_application(job.url, profile_dict)
    return result
