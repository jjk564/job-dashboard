import logging
import asyncio
import os
import re
import xml.etree.ElementTree as ET
from typing import List, Dict, Any, Optional
import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "JobPulse/1.0 (Mozilla/5.0; Candidate Assistant Bot; +https://github.com/jjk564/job-dashboard)"
}

def clean_html(raw_html: str) -> str:
    """Helper to convert HTML strings to clean readable text."""
    if not raw_html:
        return ""
    soup = BeautifulSoup(raw_html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text(separator=" ")
    return " ".join(text.split())

# 1. RemoteOK
async def fetch_remoteok_jobs(query: Optional[str] = None) -> List[Dict[str, Any]]:
    """Fetch tech & remote jobs from RemoteOK public API."""
    url = "https://remoteok.com/api"
    results = []
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.get(url, headers=HEADERS)
            if resp.status_code == 200:
                data = resp.json()
                jobs = [j for j in data if isinstance(j, dict) and "position" in j]
                for j in jobs[:40]:
                    title = j.get("position", "")
                    company = j.get("company", "")
                    tags = j.get("tags", [])
                    description = clean_html(j.get("description", ""))
                    apply_url = j.get("url", "")
                    location = j.get("location", "Remote") or "Remote"
                    salary_min = float(j.get("salary_min", 0)) if j.get("salary_min") else None
                    salary_max = float(j.get("salary_max", 0)) if j.get("salary_max") else None

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

# 2. Arbeitnow
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
                    description = clean_html(j.get("description", ""))
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

# 3. Jobicy
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
                    description = clean_html(j.get("jobDescription", ""))
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

# 4. We Work Remotely (RSS Feeds)
async def fetch_weworkremotely_jobs(query: Optional[str] = None) -> List[Dict[str, Any]]:
    """Fetch top tech roles from We Work Remotely official RSS feeds."""
    feeds = [
        "https://weworkremotely.com/categories/remote-programming-jobs.rss",
        "https://weworkremotely.com/categories/remote-devops-sysadmin-jobs.rss",
    ]
    results = []
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            for feed_url in feeds:
                try:
                    resp = await client.get(feed_url, headers=HEADERS)
                    if resp.status_code != 200:
                        continue
                    root = ET.fromstring(resp.text)
                    for item in root.findall(".//item"):
                        raw_title = item.find("title").text if item.find("title") is not None else ""
                        link = item.find("link").text if item.find("link") is not None else ""
                        desc_node = item.find("description")
                        desc = clean_html(desc_node.text) if desc_node is not None and desc_node.text else ""

                        # Parse title: "Company: Role" or "Company - Role"
                        company = "Company"
                        title = raw_title
                        if ":" in raw_title:
                            parts = raw_title.split(":", 1)
                            company = parts[0].strip()
                            title = parts[1].strip()
                        elif " - " in raw_title:
                            parts = raw_title.split(" - ", 1)
                            company = parts[0].strip()
                            title = parts[1].strip()

                        if query:
                            q_lower = query.lower()
                            if q_lower not in title.lower() and q_lower not in company.lower() and q_lower not in desc.lower():
                                continue

                        results.append({
                            "title": title,
                            "company": company,
                            "location": "Remote",
                            "workplace_type": "remote",
                            "url": link,
                            "salary_min": None,
                            "salary_max": None,
                            "salary_currency": "USD",
                            "tags": ["remote", "weworkremotely"],
                            "description": desc,
                            "source": "weworkremotely",
                        })
                except Exception as inner_e:
                    logger.debug(f"Feed error for {feed_url}: {inner_e}")
    except Exception as e:
        logger.warning(f"Error fetching We Work Remotely jobs: {e}")
    return results

# 5. Himalayas (Public API)
async def fetch_himalayas_jobs(query: Optional[str] = None) -> List[Dict[str, Any]]:
    """Fetch remote opportunities from Himalayas public API."""
    url = "https://himalayas.app/jobs/api?limit=50"
    results = []
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.get(url, headers=HEADERS)
            if resp.status_code == 200:
                data = resp.json()
                jobs = data.get("jobs", [])
                for j in jobs:
                    title = j.get("title", "")
                    company = j.get("companyName", "")
                    categories = j.get("categories", [])
                    description = clean_html(j.get("description", ""))
                    apply_url = j.get("applicationLink") or f"https://himalayas.app/companies/{j.get('companySlug')}/jobs/{j.get('guid')}"
                    location_restrictions = j.get("locationRestrictions", [])
                    location = ", ".join(location_restrictions) if location_restrictions else "Worldwide Remote"
                    salary_min = float(j.get("minSalary", 0)) if j.get("minSalary") else None
                    salary_max = float(j.get("maxSalary", 0)) if j.get("maxSalary") else None

                    if query:
                        q_lower = query.lower()
                        match = (
                            q_lower in title.lower()
                            or q_lower in company.lower()
                            or any(q_lower in str(c).lower() for c in categories)
                            or q_lower in description[:500].lower()
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
                        "salary_currency": j.get("currency", "USD") or "USD",
                        "tags": categories[:5],
                        "description": description,
                        "source": "himalayas",
                    })
    except Exception as e:
        logger.warning(f"Error fetching Himalayas jobs: {e}")
    return results

# 6. Hacker News "Who is Hiring?" (Algolia API)
async def fetch_hackernews_jobs(query: Optional[str] = None) -> List[Dict[str, Any]]:
    """Fetch startup & tech roles from the latest monthly Hacker News Who is Hiring thread."""
    results = []
    try:
        async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
            # 1. Find latest 'Ask HN: Who is hiring?' thread by author 'whoishiring'
            story_res = await client.get(
                "https://hn.algolia.com/api/v1/search_by_date?query=Ask+HN:+Who+is+hiring&tags=story,author_whoishiring&hitsPerPage=1"
            )
            if story_res.status_code != 200:
                return []
            hits = story_res.json().get("hits", [])
            if not hits:
                return []

            story_id = hits[0].get("objectID")
            thread_title = hits[0].get("title", "Ask HN: Who is hiring?")

            # 2. Fetch comments in this thread (filtered by query if provided)
            params: Dict[str, Any] = {
                "tags": f"comment,story_{story_id}",
                "hitsPerPage": 40,
            }
            if query:
                params["query"] = query

            comments_res = await client.get("https://hn.algolia.com/api/v1/search", params=params)
            if comments_res.status_code != 200:
                return []

            comments = comments_res.json().get("hits", [])
            for c in comments:
                html_text = c.get("comment_text", "")
                if not html_text:
                    continue
                clean_desc = clean_html(html_text)
                first_line = clean_desc.split(". ")[0] if clean_desc else ""

                # Parse company and title: common format "Company | Role | Location | Remote"
                company = "YC / Tech Startup"
                title = first_line[:60]
                location = "Remote"
                is_remote = "remote" in clean_desc.lower()

                if "|" in first_line:
                    parts = [p.strip() for p in first_line.split("|")]
                    if len(parts) >= 1 and parts[0]:
                        company = re.sub(r"\(.*?\)", "", parts[0]).strip()
                    if len(parts) >= 2 and parts[1]:
                        title = parts[1].strip()
                    if len(parts) >= 3 and parts[2]:
                        location = parts[2].strip()

                cid = c.get("objectID")
                hn_url = f"https://news.ycombinator.com/item?id={cid}"

                results.append({
                    "title": title or "Software Engineer",
                    "company": company or "HN Startup",
                    "location": location or ("Remote" if is_remote else "Onsite"),
                    "workplace_type": "remote" if is_remote else "hybrid",
                    "url": hn_url,
                    "salary_min": None,
                    "salary_max": None,
                    "salary_currency": "USD",
                    "tags": ["hacker-news", "startup", "direct-hire"],
                    "description": clean_desc,
                    "source": "hackernews",
                })
    except Exception as e:
        logger.warning(f"Error fetching Hacker News Who is Hiring jobs: {e}")
    return results

# 7. Adzuna API (Indexes Indeed, Monster, ZipRecruiter, LinkedIn, etc.)
async def fetch_adzuna_jobs(
    query: Optional[str] = None,
    app_id: Optional[str] = None,
    app_key: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Fetch live jobs across Indeed, ZipRecruiter & major boards via Adzuna API."""
    # Check env vars if not passed
    app_id = app_id or os.getenv("ADZUNA_APP_ID")
    app_key = app_key or os.getenv("ADZUNA_APP_KEY")

    if not app_id or not app_key:
        logger.debug("Adzuna API ID and Key not provided.")
        return []

    search_query = query or "software developer"
    url = f"https://api.adzuna.com/v1/api/jobs/us/search/1"
    params = {
        "app_id": app_id,
        "app_key": app_key,
        "results_per_page": 30,
        "what": search_query,
        "content-type": "application/json",
    }
    results = []
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            resp = await client.get(url, params=params)
            if resp.status_code == 200:
                data = resp.json()
                items = data.get("results", [])
                for item in items:
                    title = item.get("title", "")
                    company = item.get("company", {}).get("display_name", "Company")
                    loc_display = item.get("location", {}).get("display_name", "USA")
                    salary_min = float(item.get("salary_min", 0)) if item.get("salary_min") else None
                    salary_max = float(item.get("salary_max", 0)) if item.get("salary_max") else None
                    desc = clean_html(item.get("description", ""))
                    apply_url = item.get("redirect_url", "")
                    category = item.get("category", {}).get("label", "IT Jobs")
                    is_remote = "remote" in title.lower() or "remote" in desc.lower() or "remote" in loc_display.lower()

                    results.append({
                        "title": title,
                        "company": company,
                        "location": loc_display,
                        "workplace_type": "remote" if is_remote else "hybrid",
                        "url": apply_url,
                        "salary_min": salary_min,
                        "salary_max": salary_max,
                        "salary_currency": "USD",
                        "tags": ["adzuna", "indeed-aggregated", category.lower()],
                        "description": desc,
                        "source": "adzuna",
                    })
    except Exception as e:
        logger.warning(f"Error fetching Adzuna jobs: {e}")
    return results

# Aggregated Search with Source Filtering
async def search_aggregated_jobs(
    query: Optional[str] = None,
    source: Optional[str] = None,
    adzuna_app_id: Optional[str] = None,
    adzuna_app_key: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Aggregates listings concurrently across all supported boards with deduplication."""

    tasks = []
    source_lower = (source or "all").lower()

    if source_lower in ("all", "weworkremotely"):
        tasks.append(fetch_weworkremotely_jobs(query))
    if source_lower in ("all", "himalayas"):
        tasks.append(fetch_himalayas_jobs(query))
    if source_lower in ("all", "hackernews"):
        tasks.append(fetch_hackernews_jobs(query))
    if source_lower in ("all", "remoteok"):
        tasks.append(fetch_remoteok_jobs(query))
    if source_lower in ("all", "arbeitnow"):
        tasks.append(fetch_arbeitnow_jobs(query))
    if source_lower in ("all", "jobicy"):
        tasks.append(fetch_jobicy_jobs(query))
    if source_lower in ("all", "adzuna"):
        tasks.append(fetch_adzuna_jobs(query, adzuna_app_id, adzuna_app_key))

    # Run selected sources in parallel
    results_lists = await asyncio.gather(*tasks, return_exceptions=True)

    combined = []
    for r in results_lists:
        if isinstance(r, list):
            combined.extend(r)
        elif isinstance(r, Exception):
            logger.warning(f"Error during parallel job fetch: {r}")

    # Deduplicate by title + company
    seen = set()
    unique_jobs = []
    for j in combined:
        key = f"{j['title'].lower().strip()}|{j['company'].lower().strip()}"
        if key not in seen:
            seen.add(key)
            unique_jobs.append(j)

    return unique_jobs
