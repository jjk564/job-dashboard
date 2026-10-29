from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Query
from ..schemas import URLImportRequest, URLImportResponse
from ..services.job_fetcher import search_aggregated_jobs
from ..services.job_extractor import extract_job_from_url
from ..services.role_classifier import classify_role

router = APIRouter(prefix="/api/discovery", tags=["Discovery"])

@router.get("/search")
async def search_jobs(
    query: Optional[str] = Query(None),
    location: Optional[str] = Query(None),
    radius: Optional[int] = Query(None),
    include_remote: bool = Query(True),
    source: Optional[str] = Query(None),
    adzuna_app_id: Optional[str] = Query(None),
    adzuna_app_key: Optional[str] = Query(None),
    us_only: bool = Query(True),
    min_salary: Optional[float] = Query(None),
    include_undisclosed_salary: bool = Query(True),
    track: Optional[str] = Query(None),
    force_refresh: bool = Query(False),
) -> List[Dict[str, Any]]:
    """Search active listings across public job boards with optional US, salary, track, and location/radius filtering."""
    jobs = await search_aggregated_jobs(
        query=query,
        source=source,
        adzuna_app_id=adzuna_app_id,
        adzuna_app_key=adzuna_app_key,
        us_only=us_only,
        location=location,
        radius=radius,
        include_remote=include_remote,
        min_salary=min_salary,
        include_undisclosed_salary=include_undisclosed_salary,
        force_refresh=force_refresh,
    )
    enriched = []
    for j in jobs:
        classified = classify_role(j.get("title", ""), j.get("description", ""))
        j_copy = dict(j)
        j_copy["role_track"] = classified["track"]
        j_copy["role_level"] = classified["level"]
        j_copy["role_discipline"] = classified["discipline"]
        if track and track in ("ic", "manager") and classified["track"] != track:
            continue
        enriched.append(j_copy)
    return enriched

@router.post("/import-url", response_model=URLImportResponse)
async def import_job_from_url(req: URLImportRequest):
    """Scrapes structured details (title, company, description, salary) from any job URL."""
    try:
        extracted = await extract_job_from_url(req.url)
        return extracted
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to extract job from URL: {str(e)}")
