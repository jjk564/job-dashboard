import logging
import httpx
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "JobDashboard/1.0 (Mozilla/5.0; Candidate Assistant Bot)"
}

async def fetch_remoteok_jobs(query: Optional[str] = None) -> List[Dict[str, Any]]:
    """Fetch tech & remote jobs from RemoteOK public API."""
    url = "https://remoteok.com/api"
    results = []
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.get(url, headers=HEADERS)
            if resp.status_code == 200:
                data = resp.json()
                # First element in RemoteOK is usually legal metadata
                jobs = [j for j in data if isinstance(j, dict) and "position" in j]
                for j in jobs[:40]:
                    title = j.get("position", "")
                    company = j.get("company", "")
                    tags = j.get("tags", [])
                    description = j.get("description", "")
                    apply_url = j.get("url", "")
                    location = j.get("location", "Remote") or "Remote"
                    salary_min = float(j.get("salary_min", 0)) if j.get("salary_min") else None
                    salary_max = float(j.get("salary_max", 0)) if j.get("salary_max") else None

                    # Filter by query if provided
                    if query:
                        q_lower = query.lower()
                        match = (
                            q_lower in title.lower()
                            or q_lower in company.lower()
                            or any(q_lower in t.lower() for t in tags)
                        )
                        if not match:
                            continue

                    results.append({
                        "title": title,
                        "company": company,
                        "location": location,
                        "workplace_type": "remote",
                        "url": apply_url,
                        "salary_min": salary_min,
                        "salary_max": salary_max,
                        "salary_currency": "USD",
                        "tags": tags,
                        "description": description,
                        "source": "remoteok",
                    })
    except Exception as e:
        logger.warning(f"Error fetching RemoteOK jobs: {e}")
    return results

async def fetch_arbeitnow_jobs(query: Optional[str] = None) -> List[Dict[str, Any]]:
    """Fetch jobs from Arbeitnow public API."""
    url = "https://www.arbeitnow.com/api/job-board-api"
    results = []
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.get(url, headers=HEADERS)
            if resp.status_code == 200:
                data = resp.json()
                jobs = data.get("data", [])
                for j in jobs[:40]:
                    title = j.get("title", "")
                    company = j.get("company_name", "")
                    tags = j.get("tags", [])
                    description = j.get("description", "")
                    apply_url = j.get("url", "")
                    is_remote = j.get("remote", False)
                    location = j.get("location", "Remote" if is_remote else "Onsite")

                    if query:
                        q_lower = query.lower()
                        match = (
                            q_lower in title.lower()
                            or q_lower in company.lower()
                            or any(q_lower in str(t).lower() for t in tags)
                        )
                        if not match:
                            continue

                    results.append({
                        "title": title,
                        "company": company,
                        "location": location or "Remote",
                        "workplace_type": "remote" if is_remote else "hybrid",
                        "url": apply_url,
                        "salary_min": None,
                        "salary_max": None,
                        "salary_currency": "USD",
                        "tags": tags,
                        "description": description,
                        "source": "arbeitnow",
                    })
    except Exception as e:
        logger.warning(f"Error fetching Arbeitnow jobs: {e}")
    return results

async def fetch_jobicy_jobs(query: Optional[str] = None) -> List[Dict[str, Any]]:
    """Fetch jobs from Jobicy public API."""
    url = "https://jobicy.com/api/v2/remote-jobs?count=30"
    results = []
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.get(url, headers=HEADERS)
            if resp.status_code == 200:
                data = resp.json()
                jobs = data.get("jobs", [])
                for j in jobs:
                    title = j.get("jobTitle", "")
                    company = j.get("companyName", "")
                    tags = [j.get("jobCategory", "")] if j.get("jobCategory") else []
                    description = j.get("jobDescription", "")
                    apply_url = j.get("url", "")
                    location = j.get("jobGeo", "Remote")
                    salary_min = float(j.get("annualSalaryMin", 0)) if j.get("annualSalaryMin") else None
                    salary_max = float(j.get("annualSalaryMax", 0)) if j.get("annualSalaryMax") else None

                    if query:
                        q_lower = query.lower()
                        match = (
                            q_lower in title.lower()
                            or q_lower in company.lower()
                            or any(q_lower in t.lower() for t in tags)
                        )
                        if not match:
                            continue

                    results.append({
                        "title": title,
                        "company": company,
                        "location": location or "Remote",
                        "workplace_type": "remote",
                        "url": apply_url,
                        "salary_min": salary_min,
                        "salary_max": salary_max,
                        "salary_currency": j.get("salaryCurrency", "USD"),
                        "tags": tags,
                        "description": description,
                        "source": "jobicy",
                    })
    except Exception as e:
        logger.warning(f"Error fetching Jobicy jobs: {e}")
    return results

async def search_aggregated_jobs(query: Optional[str] = None) -> List[Dict[str, Any]]:
    """Aggregates listings from multiple free sources."""
    jobs_remoteok = await fetch_remoteok_jobs(query)
    jobs_arbeitnow = await fetch_arbeitnow_jobs(query)
    jobs_jobicy = await fetch_jobicy_jobs(query)

    combined = jobs_remoteok + jobs_arbeitnow + jobs_jobicy
    # Deduplicate by title + company
    seen = set()
    unique_jobs = []
    for j in combined:
        key = f"{j['title'].lower()}|{j['company'].lower()}"
        if key not in seen:
            seen.add(key)
            unique_jobs.append(j)

    return unique_jobs
