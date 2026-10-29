import json
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from ..database import get_db
from ..models import SearchProfile, Job, Profile, Skill
from ..schemas import (
    SearchProfileCreate,
    SearchProfileUpdate,
    SearchProfileResponse,
    DirectivesResponse,
    IngestBatchRequest,
)
from ..services.role_classifier import classify_role, score_job_for_search_profile

router = APIRouter(tags=["Search Profiles & Directives"])


def resolve_user_id(x_user_id: Optional[str] = Header(default=None, alias="X-User-Id")) -> str:
    """
    Resolves the caller's user identity from the edge-injected X-User-Id header
    (when hosted behind hadoku.me) or defaults to 'default' for local standalone runs.
    """
    if x_user_id and x_user_id.strip():
        return x_user_id.strip()[:128]
    return "default"


async def ensure_seed_search_profiles(db: AsyncSession, user_id: str) -> List[SearchProfile]:
    res = await db.execute(
        select(SearchProfile)
        .where(SearchProfile.user_id == user_id)
        .order_by(SearchProfile.is_default.desc(), SearchProfile.id.asc())
    )
    existing = list(res.scalars().all())
    if existing:
        return existing

    # Seed starter profiles tailored to software/backend and IT/systems tracks
    p1 = SearchProfile(
        user_id=user_id,
        name="Software & Data Engineering (IC)",
        is_default=True,
        keywords_json=json.dumps(["Python", "SQL", "Go", "REST APIs", "SQLite", "Git", "Data Pipelines", "FastAPI", "TypeScript"]),
        target_companies_json=json.dumps(["Stripe", "Cloudflare", "Databricks", "OpenAI", "Anthropic", "Linear", "Supabase", "Vercel"]),
        track="ic",
        levels_json=json.dumps(["junior", "mid", "senior"]),
        remote_pref="any",
        location="",
        radius_miles=50,
        min_salary=None,
        include_undisclosed_salary=True,
        us_only=True,
    )
    p2 = SearchProfile(
        user_id=user_id,
        name="IT, Systems & Security Ops (IC)",
        is_default=False,
        keywords_json=json.dumps(["Active Directory", "Microsoft 365", "Windows Server", "Linux", "Networking", "ServiceNow", "Cybersecurity", "Bash", "PowerShell"]),
        target_companies_json=json.dumps([]),
        track="ic",
        levels_json=json.dumps(["junior", "mid", "senior"]),
        remote_pref="any",
        location="",
        radius_miles=50,
        min_salary=None,
        include_undisclosed_salary=True,
        us_only=True,
    )
    db.add_all([p1, p2])
    await db.commit()
    await db.refresh(p1)
    await db.refresh(p2)
    return [p1, p2]


@router.get("/api/search-profiles", response_model=List[SearchProfileResponse])
async def list_search_profiles(
    user_id: str = Depends(resolve_user_id),
    db: AsyncSession = Depends(get_db),
):
    profiles = await ensure_seed_search_profiles(db, user_id)
    return [p.to_dict() for p in profiles]


@router.post("/api/search-profiles", response_model=SearchProfileResponse)
async def create_search_profile(
    payload: SearchProfileCreate,
    user_id: str = Depends(resolve_user_id),
    db: AsyncSession = Depends(get_db),
):
    await ensure_seed_search_profiles(db, user_id)

    if payload.is_default:
        res = await db.execute(select(SearchProfile).where(SearchProfile.user_id == user_id))
        for existing in res.scalars().all():
            existing.is_default = False

    sp = SearchProfile(
        user_id=user_id,
        name=payload.name.strip() or "Untitled Profile",
        is_default=bool(payload.is_default),
        keywords_json=json.dumps([k.strip() for k in payload.keywords if k.strip()]),
        target_companies_json=json.dumps([c.strip() for c in payload.target_companies if c.strip()]),
        track=payload.track if payload.track in ("ic", "manager", "either") else "ic",
        levels_json=json.dumps(payload.levels or []),
        remote_pref=payload.remote_pref if payload.remote_pref in ("remote", "hybrid", "onsite", "any") else "any",
        location=(payload.location or "").strip(),
        radius_miles=payload.radius_miles if payload.radius_miles is not None else 50,
        min_salary=payload.min_salary,
        include_undisclosed_salary=True if payload.include_undisclosed_salary is None else payload.include_undisclosed_salary,
        us_only=True if payload.us_only is None else payload.us_only,
    )
    db.add(sp)
    await db.commit()
    await db.refresh(sp)
    return sp.to_dict()


@router.put("/api/search-profiles/{profile_id}", response_model=SearchProfileResponse)
async def update_search_profile(
    profile_id: int,
    payload: SearchProfileUpdate,
    user_id: str = Depends(resolve_user_id),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(
        select(SearchProfile).where(
            SearchProfile.id == profile_id,
            SearchProfile.user_id == user_id,
        )
    )
    sp = res.scalars().first()
    if not sp:
        raise HTTPException(status_code=404, detail="Search profile not found")

    data = payload.model_dump(exclude_unset=True)
    if data.get("is_default"):
        other_res = await db.execute(
            select(SearchProfile).where(
                SearchProfile.user_id == user_id,
                SearchProfile.id != profile_id,
            )
        )
        for other in other_res.scalars().all():
            other.is_default = False
        sp.is_default = True
    elif "is_default" in data and data["is_default"] is False:
        sp.is_default = False

    if "name" in data and data["name"] is not None:
        sp.name = data["name"].strip() or sp.name
    if "keywords" in data and data["keywords"] is not None:
        sp.keywords_json = json.dumps([k.strip() for k in data["keywords"] if k.strip()])
    if "target_companies" in data and data["target_companies"] is not None:
        sp.target_companies_json = json.dumps([c.strip() for c in data["target_companies"] if c.strip()])
    if "track" in data and data["track"] in ("ic", "manager", "either"):
        sp.track = data["track"]
    if "levels" in data and data["levels"] is not None:
        sp.levels_json = json.dumps(data["levels"])
    if "remote_pref" in data and data["remote_pref"] in ("remote", "hybrid", "onsite", "any"):
        sp.remote_pref = data["remote_pref"]
    if "location" in data and data["location"] is not None:
        sp.location = data["location"].strip()
    if "radius_miles" in data and data["radius_miles"] is not None:
        sp.radius_miles = data["radius_miles"]
    if "min_salary" in data:
        sp.min_salary = data["min_salary"]
    if "include_undisclosed_salary" in data and data["include_undisclosed_salary"] is not None:
        sp.include_undisclosed_salary = data["include_undisclosed_salary"]
    if "us_only" in data and data["us_only"] is not None:
        sp.us_only = data["us_only"]

    sp.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(sp)
    return sp.to_dict()


@router.delete("/api/search-profiles/{profile_id}")
async def delete_search_profile(
    profile_id: int,
    user_id: str = Depends(resolve_user_id),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(
        select(SearchProfile).where(
            SearchProfile.id == profile_id,
            SearchProfile.user_id == user_id,
        )
    )
    sp = res.scalars().first()
    if not sp:
        raise HTTPException(status_code=404, detail="Search profile not found")

    was_default = sp.is_default
    await db.delete(sp)
    await db.commit()

    if was_default:
        rem_res = await db.execute(
            select(SearchProfile)
            .where(SearchProfile.user_id == user_id)
            .order_by(SearchProfile.id.asc())
        )
        first_rem = rem_res.scalars().first()
        if first_rem:
            first_rem.is_default = True
            await db.commit()

    return {"success": True, "message": "Search profile deleted"}


@router.post("/api/search-profiles/{profile_id}/score-pipeline")
async def score_pipeline_with_profile(
    profile_id: int,
    user_id: str = Depends(resolve_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Re-classifies and re-scores all pipeline jobs against the specified SearchProfile,
    updating role_track, role_level, fit_score, and fit_breakdown.
    """
    res = await db.execute(
        select(SearchProfile).where(
            SearchProfile.id == profile_id,
            SearchProfile.user_id == user_id,
        )
    )
    sp = res.scalars().first()
    if not sp:
        raise HTTPException(status_code=404, detail="Search profile not found")

    sp_dict = sp.to_dict()

    # Also load master candidate profile & skills
    p_res = await db.execute(select(Profile).limit(1))
    cand_profile = p_res.scalars().first()
    s_res = await db.execute(select(Skill))
    cand_skills = [s.name for s in s_res.scalars().all()]
    resume_text = f"{cand_profile.summary} {cand_profile.master_resume_text}" if cand_profile else ""

    j_res = await db.execute(
        select(Job)
        .options(selectinload(Job.activities), selectinload(Job.tailored_documents))
        .order_by(Job.updated_at.desc())
    )
    jobs = list(j_res.scalars().all())

    for job in jobs:
        classified = classify_role(job.title or "", job.description or "")
        job.role_track = classified["track"]
        job.role_level = classified["level"]
        job.role_discipline = classified["discipline"]

        scored = score_job_for_search_profile(
            title=job.title or "",
            description=f"{job.description or ''} {job.requirements or ''}",
            company=job.company or "",
            workplace_type=job.workplace_type,
            role_track=job.role_track,
            role_level=job.role_level,
            profile_keywords=sp_dict["keywords"],
            profile_levels=sp_dict["levels"],
            profile_remote_pref=sp_dict["remote_pref"],
            profile_companies=sp_dict["target_companies"],
            candidate_skills=cand_skills,
            master_resume_text=resume_text,
        )
        job.fit_score = scored["score"]
        job.fit_breakdown = json.dumps(scored)

    await db.commit()
    for job in jobs:
        await db.refresh(job)

    return {
        "profile_id": sp.id,
        "profile_name": sp.name,
        "jobs_scored": len(jobs),
        "jobs": [j.to_dict() for j in jobs],
    }


@router.get("/api/directives", response_model=DirectivesResponse)
async def get_scrape_directives(db: AsyncSession = Depends(get_db)):
    """
    hadoku-scraper compatible pull endpoint.
    Returns the deduplicated union of target companies and keywords across all SearchProfiles.
    """
    res = await db.execute(select(SearchProfile))
    profiles = list(res.scalars().all())
    if not profiles:
        profiles = await ensure_seed_search_profiles(db, "default")

    companies_set = []
    keywords_set = []
    seen_c = set()
    seen_k = set()

    for p in profiles:
        p_dict = p.to_dict()
        for c in p_dict["target_companies"]:
            c_low = c.lower().strip()
            if c_low and c_low not in seen_c:
                seen_c.add(c_low)
                companies_set.append(c.strip())
        for k in p_dict["keywords"]:
            k_low = k.lower().strip()
            if k_low and k_low not in seen_k:
                seen_k.add(k_low)
                keywords_set.append(k.strip())

    return {
        "companies": companies_set,
        "keywords": keywords_set,
        "profiles_count": len(profiles),
    }


@router.post("/api/ingest")
async def ingest_scraped_jobs(
    payload: IngestBatchRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    hadoku-scraper compatible webhook endpoint for ingesting batches of scraped postings.
    Deduplicates by URL or (company, title, location), classifies orthogonal track & level,
    and scores against the active default SearchProfile.
    """
    profiles = await ensure_seed_search_profiles(db, "default")
    default_sp = next((p for p in profiles if p.is_default), profiles[0]).to_dict()

    p_res = await db.execute(select(Profile).limit(1))
    cand_profile = p_res.scalars().first()
    s_res = await db.execute(select(Skill))
    cand_skills = [s.name for s in s_res.scalars().all()]
    resume_text = f"{cand_profile.summary} {cand_profile.master_resume_text}" if cand_profile else ""

    existing_res = await db.execute(select(Job))
    existing_jobs = list(existing_res.scalars().all())
    existing_urls = {j.url.strip().lower() for j in existing_jobs if j.url}
    existing_keys = {
        (j.company.strip().lower(), j.title.strip().lower(), (j.location or "").strip().lower())
        for j in existing_jobs
    }

    inserted = 0
    skipped = 0

    for item in payload.jobs:
        url_clean = (item.url or "").strip()
        key = (
            (item.company or "").strip().lower(),
            (item.title or "").strip().lower(),
            (item.location or "Remote").strip().lower(),
        )
        if (url_clean and url_clean.lower() in existing_urls) or key in existing_keys:
            skipped += 1
            continue

        wp = (item.workplace_type or item.remote_type or "remote").lower()
        if wp not in ("remote", "hybrid", "onsite"):
            wp = "remote" if "remote" in (item.location or "").lower() else "onsite"

        classified = classify_role(item.title, item.description or "")
        scored = score_job_for_search_profile(
            title=item.title,
            description=item.description or "",
            company=item.company,
            workplace_type=wp,
            role_track=classified["track"],
            role_level=classified["level"],
            profile_keywords=default_sp["keywords"],
            profile_levels=default_sp["levels"],
            profile_remote_pref=default_sp["remote_pref"],
            profile_companies=default_sp["target_companies"],
            candidate_skills=cand_skills,
            master_resume_text=resume_text,
        )

        new_job = Job(
            title=item.title,
            company=item.company,
            location=item.location or "Remote",
            workplace_type=wp,
            url=url_clean or None,
            salary_min=item.salary_min,
            salary_max=item.salary_max,
            description=item.description or "",
            source=item.source_site or item.source or payload.source or "scraper",
            status="TO_APPLY",
            priority="high" if scored["score"] >= 80 else "medium",
            fit_score=scored["score"],
            fit_breakdown=json.dumps(scored),
            role_track=classified["track"],
            role_level=classified["level"],
            role_discipline=classified["discipline"],
        )
        db.add(new_job)
        if url_clean:
            existing_urls.add(url_clean.lower())
        existing_keys.add(key)
        inserted += 1

    await db.commit()
    return {
        "inserted": inserted,
        "skipped": skipped,
        "batch_number": payload.batch_number,
        "is_final": payload.is_final,
    }
