import json
import asyncio
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from ..database import get_db
from ..models import Job, ApplicationActivity, TailoredDocument, Profile, Skill
from ..schemas import JobCreate, JobUpdate, JobResponse, ActivityCreate, ActivityResponse
from ..services.matcher import analyze_job_fit
from ..services.expiration_checker import check_job_expiration

router = APIRouter(prefix="/api/jobs", tags=["Jobs"])

@router.get("", response_model=List[JobResponse])
async def list_jobs(
    status: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    query = select(Job).options(
        selectinload(Job.activities),
        selectinload(Job.tailored_documents)
    ).order_by(Job.updated_at.desc())

    if status:
        query = query.where(Job.status == status)
    if priority:
        query = query.where(Job.priority == priority)

    res = await db.execute(query)
    jobs = res.scalars().all()
    return [j.to_dict() for j in jobs]

@router.post("", response_model=JobResponse)
async def create_job(job_in: JobCreate, db: AsyncSession = Depends(get_db)):
    # Auto-calculate fit score if profile exists
    p_res = await db.execute(select(Profile).limit(1))
    profile = p_res.scalars().first()
    s_res = await db.execute(select(Skill))
    skills = [s.name for s in s_res.scalars().all()]

    desc = job_in.description or ""
    salary_min = job_in.salary_min
    salary_max = job_in.salary_max

    # If description is a short snippet or placeholder and URL is present, try extracting full description
    if job_in.url and (len(desc.strip()) < 300 or "via simplifyjobs" in desc.lower()):
        try:
            from ..services.job_extractor import extract_job_from_url
            extracted = await extract_job_from_url(job_in.url)
            if extracted.get("description") and len(extracted["description"]) > len(desc):
                desc = extracted["description"]
            if extracted.get("salary_min") and not salary_min:
                salary_min = extracted["salary_min"]
            if extracted.get("salary_max") and not salary_max:
                salary_max = extracted["salary_max"]
        except Exception:
            pass

    fit_score = None
    fit_breakdown_json = None
    if profile:
        fit_data = analyze_job_fit(
            job_text=f"{job_in.title} {desc} {job_in.requirements or ''}",
            candidate_skills=skills,
            profile_text=f"{profile.summary} {profile.master_resume_text}"
        )
        fit_score = fit_data["score"]
        fit_breakdown_json = json.dumps(fit_data)

    job_data = job_in.model_dump()
    job_data["description"] = desc
    job_data["salary_min"] = salary_min
    job_data["salary_max"] = salary_max

    job = Job(
        **job_data,
        fit_score=fit_score,
        fit_breakdown=fit_breakdown_json
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    # Add initial activity
    act = ApplicationActivity(
        job_id=job.id,
        activity_type="status_change",
        title=f"Job added to {job.status}",
        details=f"Added from {job.source}"
    )
    db.add(act)
    await db.commit()
    await db.refresh(job)

    return job.to_dict()

@router.post("/check-all-status")
async def check_all_jobs_status(db: AsyncSession = Depends(get_db)):
    """Verifies all active pipeline jobs (WISHLIST, TO_APPLY, APPLIED) for expiration."""
    res = await db.execute(
        select(Job)
        .options(selectinload(Job.activities), selectinload(Job.tailored_documents))
        .where(Job.status.in_(["WISHLIST", "TO_APPLY", "APPLIED"]))
    )
    jobs = res.scalars().all()
    sem = asyncio.Semaphore(5)

    async def verify_single(job: Job):
        async with sem:
            is_expired, reason = await check_job_expiration(job.url, job.deadline)
            was_expired = job.is_expired
            job.is_expired = is_expired
            if is_expired:
                job.expired_at = datetime.utcnow()
                job.expired_reason = reason
                if not was_expired:
                    act = ApplicationActivity(
                        job_id=job.id,
                        activity_type="status_change",
                        title="Job posting detected as expired",
                        details=reason or "Posting link closed or deadline passed",
                    )
                    db.add(act)
            else:
                job.expired_reason = None
                job.expired_at = None
            job.updated_at = datetime.utcnow()
            return is_expired

    results = await asyncio.gather(*(verify_single(j) for j in jobs), return_exceptions=True)
    await db.commit()
    for j in jobs:
        await db.refresh(j)

    # Return full pipeline jobs list so all columns (Archive, Interviewing, Offer) remain populated
    all_res = await db.execute(
        select(Job)
        .options(selectinload(Job.activities), selectinload(Job.tailored_documents))
        .order_by(Job.updated_at.desc())
    )
    all_jobs = all_res.scalars().all()

    expired_count = sum(1 for r in results if r is True)
    return {
        "checked": len(jobs),
        "expired_found": expired_count,
        "jobs": [j.to_dict() for j in all_jobs],
    }

@router.post("/{job_id}/check-status", response_model=JobResponse)
async def check_single_job_status(job_id: int, db: AsyncSession = Depends(get_db)):
    """Checks whether a specific job posting has expired or closed."""
    res = await db.execute(
        select(Job)
        .options(selectinload(Job.activities), selectinload(Job.tailored_documents))
        .where(Job.id == job_id)
    )
    job = res.scalars().first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    is_expired, reason = await check_job_expiration(job.url, job.deadline)
    was_expired = job.is_expired
    job.is_expired = is_expired
    if is_expired:
        job.expired_at = datetime.utcnow()
        job.expired_reason = reason
        if not was_expired:
            act = ApplicationActivity(
                job_id=job.id,
                activity_type="status_change",
                title="Job posting detected as expired",
                details=reason or "Posting link closed or deadline passed",
            )
            db.add(act)
    else:
        job.expired_reason = None
        job.expired_at = None

    job.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(job)
    return job.to_dict()

@router.get("/{job_id}", response_model=JobResponse)
async def get_job(job_id: int, db: AsyncSession = Depends(get_db)):
    res = await db.execute(
        select(Job)
        .options(selectinload(Job.activities), selectinload(Job.tailored_documents))
        .where(Job.id == job_id)
    )
    job = res.scalars().first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job.to_dict()

@router.patch("/{job_id}", response_model=JobResponse)
async def update_job(job_id: int, job_update: JobUpdate, db: AsyncSession = Depends(get_db)):
    res = await db.execute(
        select(Job)
        .options(selectinload(Job.activities), selectinload(Job.tailored_documents))
        .where(Job.id == job_id)
    )
    job = res.scalars().first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    old_status = job.status
    update_data = job_update.model_dump(exclude_unset=True)

    if "fit_breakdown" in update_data and update_data["fit_breakdown"] is not None:
        update_data["fit_breakdown"] = json.dumps(update_data["fit_breakdown"])

    for k, v in update_data.items():
        setattr(job, k, v)

    # Log status change
    if "status" in update_data and update_data["status"] != old_status:
        if update_data["status"] == "APPLIED" and not job.applied_at:
            job.applied_at = datetime.utcnow()
        act = ApplicationActivity(
            job_id=job.id,
            activity_type="status_change",
            title=f"Moved to {job.status}",
            details=f"Status transitioned from {old_status} to {job.status}"
        )
        db.add(act)

    # Auto-recalculate fit score if description or requirements updated and fit_score not explicitly passed
    if ("description" in update_data or "requirements" in update_data) and "fit_score" not in update_data:
        p_res = await db.execute(select(Profile).limit(1))
        profile = p_res.scalars().first()
        s_res = await db.execute(select(Skill))
        skills = [s.name for s in s_res.scalars().all()]
        if profile:
            fit_data = analyze_job_fit(
                job_text=f"{job.title} {job.description or ''} {job.requirements or ''}",
                candidate_skills=skills,
                profile_text=f"{profile.summary} {profile.master_resume_text}"
            )
            job.fit_score = fit_data["score"]
            job.fit_breakdown = json.dumps(fit_data)

    job.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(job)
    return job.to_dict()

@router.post("/{job_id}/refresh-from-url", response_model=JobResponse)
async def refresh_job_from_url(job_id: int, db: AsyncSession = Depends(get_db)):
    """Fetches full job description from the job URL and recalculates fit score."""
    res = await db.execute(
        select(Job)
        .options(selectinload(Job.activities), selectinload(Job.tailored_documents))
        .where(Job.id == job_id)
    )
    job = res.scalars().first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if not job.url:
        raise HTTPException(status_code=400, detail="Job does not have a URL to fetch")

    from ..services.job_extractor import extract_job_from_url
    try:
        extracted = await extract_job_from_url(job.url)
        if extracted.get("description"):
            job.description = extracted["description"]
        if extracted.get("salary_min") and not job.salary_min:
            job.salary_min = extracted["salary_min"]
        if extracted.get("salary_max") and not job.salary_max:
            job.salary_max = extracted["salary_max"]

        p_res = await db.execute(select(Profile).limit(1))
        profile = p_res.scalars().first()
        s_res = await db.execute(select(Skill))
        skills = [s.name for s in s_res.scalars().all()]
        if profile:
            fit_data = analyze_job_fit(
                job_text=f"{job.title} {job.description or ''} {job.requirements or ''}",
                candidate_skills=skills,
                profile_text=f"{profile.summary} {profile.master_resume_text}"
            )
            job.fit_score = fit_data["score"]
            job.fit_breakdown = json.dumps(fit_data)

        job.updated_at = datetime.utcnow()
        await db.commit()
        await db.refresh(job)
        return job.to_dict()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to extract from URL: {str(e)}")

@router.delete("/{job_id}")
async def delete_job(job_id: int, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Job).where(Job.id == job_id))
    job = res.scalars().first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    await db.delete(job)
    await db.commit()
    return {"success": True, "message": "Job deleted"}

@router.post("/{job_id}/activities", response_model=ActivityResponse)
async def add_activity(job_id: int, act_in: ActivityCreate, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Job).where(Job.id == job_id))
    if not res.scalars().first():
        raise HTTPException(status_code=404, detail="Job not found")

    act = ApplicationActivity(
        job_id=job_id,
        activity_type=act_in.activity_type,
        title=act_in.title,
        details=act_in.details
    )
    db.add(act)
    await db.commit()
    await db.refresh(act)
    return act.to_dict()
