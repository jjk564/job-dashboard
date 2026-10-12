import json
from collections import Counter
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from ..database import get_db
from ..models import Job
from ..services.matcher import extract_tech_keywords

router = APIRouter(prefix="/api/analytics", tags=["Analytics"])

@router.get("/metrics")
async def get_metrics(db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Job))
    jobs = res.scalars().all()

    total = len(jobs)
    wishlist = sum(1 for j in jobs if j.status == "WISHLIST")
    to_apply = sum(1 for j in jobs if j.status == "TO_APPLY")
    applied = sum(1 for j in jobs if j.status in ("APPLIED", "INTERVIEWING", "OFFER", "REJECTED"))
    interviewing = sum(1 for j in jobs if j.status == "INTERVIEWING")
    offer = sum(1 for j in jobs if j.status == "OFFER")
    rejected = sum(1 for j in jobs if j.status == "REJECTED")

    response_rate = round(((interviewing + offer + rejected) / applied * 100), 1) if applied > 0 else 0
    interview_rate = round(((interviewing + offer) / applied * 100), 1) if applied > 0 else 0

    # Skills demand counter
    skill_counts = Counter()
    for j in jobs:
        text = f"{j.title} {j.description or ''} {j.requirements or ''}"
        skills = extract_tech_keywords(text)
        for s in skills:
            skill_counts[s] += 1

    top_skills = [{"name": s, "count": c} for s, c in skill_counts.most_common(12)]

    # Workplace distribution
    workplace_dist = Counter(j.workplace_type for j in jobs)

    return {
        "funnel": {
            "total_tracked": total,
            "wishlist": wishlist,
            "to_apply": to_apply,
            "applied": applied,
            "interviewing": interviewing,
            "offer": offer,
            "rejected": rejected,
            "response_rate_percent": response_rate,
            "interview_rate_percent": interview_rate,
        },
        "top_demanded_skills": top_skills,
        "workplace_distribution": dict(workplace_dist),
    }
