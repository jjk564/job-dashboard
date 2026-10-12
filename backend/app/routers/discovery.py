from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Query
from ..schemas import URLImportRequest, URLImportResponse
from ..services.job_fetcher import search_aggregated_jobs
from ..services.job_extractor import extract_job_from_url

router = APIRouter(prefix="/api/discovery", tags=["Discovery"])

@router.get("/search")
async def search_jobs(query: Optional[str] = Query(None)) -> List[Dict[str, Any]]:
    """Search active listings across public job boards (RemoteOK, Arbeitnow, Jobicy)."""
    jobs = await search_aggregated_jobs(query)
    return jobs

@router.post("/import-url", response_model=URLImportResponse)
async def import_job_from_url(req: URLImportRequest):
    """Scrapes structured details (title, company, description, salary) from any job URL."""
    try:
        extracted = await extract_job_from_url(req.url)
        return extracted
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to extract job from URL: {str(e)}")
