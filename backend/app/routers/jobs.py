import json
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

    fit_score = None
    fit_breakdown_json = None
    if profile:
        fit_data = analyze_job_fit(
            job_text=f"{job_in.title} {job_in.description or ''} {job_in.requirements or ''}",
            candidate_skills=skills,
            profile_text=f"{profile.summary} {profile.master_resume_text}"
        )
        fit_score = fit_data["score"]
        fit_breakdown_json = json.dumps(fit_data)

    job = Job(
        **job_in.model_dump(),
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

    job.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(job)
    return job.to_dict()

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
