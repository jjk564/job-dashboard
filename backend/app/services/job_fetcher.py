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

def is_us_eligible(
    location: str,
    title: str = "",
    text: str = "",
    location_list: Optional[List[str]] = None
) -> bool:
    """
    Filters out foreign and non-US jobs.
    Ensures jobs are either based in the US, US-remote, or global remote open to US.
    """
    loc_lower = (location or "").lower()
    title_lower = (title or "").lower()
    full_header = f"{title_lower} {loc_lower}"

    # 1. Reject German / foreign specific hiring abbreviations and markers
    foreign_markers = [
        "(m/w/d)", "(d/m/w)", "(w/m/d)", "m/w/d", "d/m/w", "w/m/d",
        "festanstellung", "vollzeit", "standort", "stellenanzeige",
        "zur verstärkung", "sobre a vaga", "vaga afirmativa",
    ]
    for marker in foreign_markers:
        if marker in full_header or marker in text[:400].lower():
            return False

    # 2. Check structured location restrictions (e.g. Himalayas, Jobicy)
    if location_list is not None and len(location_list) > 0:
        locs_lower = [str(l).lower() for l in location_list]
        has_us = any(
            any(u in l for u in ["united states", "usa", "u.s.", "north america", "worldwide", "global", "americas", "anywhere"])
            for l in locs_lower
        )
        if not has_us:
            return False

        # If it specifically lists foreign country without US, reject
        has_foreign_only = any(
            any(f in l for f in [
                "germany", "deutschland", "brazil", "brasil", "portugal", "singapore",
                "india", "united kingdom", "uk", "france", "spain", "poland", "netherlands",
                "australia", "japan", "italy", "switzerland", "sweden", "austria", "belgium"
            ]) for l in locs_lower
        ) and not any(u in l for u in ["united states", "usa", "u.s.", "north america", "worldwide", "global", "americas", "anywhere"] for l in locs_lower)
        if has_foreign_only:
            return False

    # 3. Check location string for explicit foreign exclusivity
    explicit_foreign_regions = [
        "europe only", "eu only", "uk only", "emea only", "apac only", "latam only",
        "germany", "deutschland", "berlin", "munich", "frankfurt", "london", "paris",
        "tokyo", "japan", "singapore", "brazil", "são paulo", "portugal", "lisbon",
        "india", "bangalore", "mumbai", "sydney", "melbourne", "australia",
        "netherlands", "amsterdam", "poland", "warsaw", "madrid", "spain",
    ]
    for region in explicit_foreign_regions:
        if region in loc_lower:
            # If it doesn't also explicitly state US / Worldwide / Americas / Anywhere, reject
            if not any(u in loc_lower for u in ["united states", "usa", "u.s.", "us remote", "worldwide", "global", "americas", "anywhere"]):
                return False

    return True

def matches_query(
    query: Optional[str],
    title: str,
    company: str,
    tags: List[Any],
    description: str
) -> bool:
    """
    Smart keyword and synonym matching across title, company, tags, and description.
    Enables developer searches to match software engineer roles, etc.
    """
    if not query:
        return True
    q = query.lower().strip()
    if not q:
        return True

    tag_str = " ".join(str(t) for t in tags)
    full_text = f"{title} {company} {tag_str} {description[:1200]}".lower()

    # 1. Direct substring match
    if q in full_text:
        return True

    # 2. Tech synonyms expansion
    synonym_groups = [
        {"developer", "engineer", "dev", "programmer", "software", "coder", "architect"},
        {"frontend", "front-end", "ui", "react", "vue", "angular", "javascript", "typescript"},
        {"backend", "back-end", "api", "server", "python", "node", "golang", "java", "django", "fastapi"},
        {"fullstack", "full-stack", "full stack"},
        {"devops", "sre", "infrastructure", "cloud", "aws", "kubernetes", "docker"},
        {"data", "machine learning", "ml", "ai", "data engineer", "data scientist"},
    ]
    for group in synonym_groups:
        if any(term in q for term in group):
            if any(term in full_text for term in group):
                return True

    # 3. Individual words all present
    words = [w for w in q.split() if len(w) > 2]
    if words and all(w in full_text for w in words):
        return True

    return False


# 1. RemoteOK
async def fetch_remoteok_jobs(query: Optional[str] = None, us_only: bool = True) -> List[Dict[str, Any]]:
    """Fetch tech & remote jobs from RemoteOK public API."""
    url = "https://remoteok.com/api"
    results = []
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.get(url, headers=HEADERS)
            if resp.status_code == 200:
                data = resp.json()
                jobs = [j for j in data if isinstance(j, dict) and "position" in j]
                for j in jobs:
                    title = j.get("position", "")
                    company = j.get("company", "")
                    tags = j.get("tags", [])
                    description = clean_html(j.get("description", ""))
                    apply_url = j.get("url", "")
                    location = j.get("location", "Remote") or "Remote"
                    salary_min = float(j.get("salary_min", 0)) if j.get("salary_min") else None
                    salary_max = float(j.get("salary_max", 0)) if j.get("salary_max") else None

                    # US filter
                    if us_only and not is_us_eligible(location=location, title=title, text=description):
                        continue

                    if not matches_query(query, title, company, tags, description):
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
                    if len(results) >= 40:
                        break
    except Exception as e:
        logger.warning(f"Error fetching RemoteOK jobs: {e}")
    return results

# 2. Arbeitnow
async def fetch_arbeitnow_jobs(query: Optional[str] = None, us_only: bool = True) -> List[Dict[str, Any]]:
    """Fetch jobs from Arbeitnow public API."""
    url = "https://www.arbeitnow.com/api/job-board-api"
    results = []
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.get(url, headers=HEADERS)
            if resp.status_code == 200:
                data = resp.json()
                jobs = data.get("data", [])
                for j in jobs:
                    title = j.get("title", "")
                    company = j.get("company_name", "")
                    tags = j.get("tags", [])
                    description = clean_html(j.get("description", ""))
                    apply_url = j.get("url", "")
                    is_remote = j.get("remote", False)
                    location = j.get("location", "Remote" if is_remote else "Onsite") or "Remote"

                    # US filter
                    if us_only and not is_us_eligible(location=location, title=title, text=description):
                        continue

                    if not matches_query(query, title, company, tags, description):
                        continue

                    results.append({
                        "title": title,
                        "company": company,
                        "location": location,
                        "workplace_type": "remote" if is_remote else "hybrid",
                        "url": apply_url,
                        "salary_min": None,
                        "salary_max": None,
                        "salary_currency": "USD",
                        "tags": tags,
                        "description": description,
                        "source": "arbeitnow",
                    })
                    if len(results) >= 40:
                        break
    except Exception as e:
        logger.warning(f"Error fetching Arbeitnow jobs: {e}")
    return results

# 3. Jobicy
async def fetch_jobicy_jobs(query: Optional[str] = None, us_only: bool = True) -> List[Dict[str, Any]]:
    """Fetch jobs from Jobicy public API."""
    url = "https://jobicy.com/api/v2/remote-jobs?count=50&geo=usa" if us_only else "https://jobicy.com/api/v2/remote-jobs?count=50"
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
                    location = j.get("jobGeo", "Remote") or "Remote"
                    salary_min = float(j.get("annualSalaryMin", 0)) if j.get("annualSalaryMin") else None
                    salary_max = float(j.get("annualSalaryMax", 0)) if j.get("annualSalaryMax") else None

                    # US filter
                    if us_only and not is_us_eligible(location=location, title=title, text=description):
                        continue

                    if not matches_query(query, title, company, tags, description):
                        continue

                    results.append({
                        "title": title,
                        "company": company,
                        "location": location,
                        "workplace_type": "remote",
                        "url": apply_url,
                        "salary_min": salary_min,
                        "salary_max": salary_max,
                        "salary_currency": j.get("salaryCurrency", "USD") or "USD",
                        "tags": tags,
                        "description": description,
                        "source": "jobicy",
                    })
                    if len(results) >= 40:
                        break
    except Exception as e:
        logger.warning(f"Error fetching Jobicy jobs: {e}")
    return results


# 4. We Work Remotely (RSS Feeds)
async def fetch_weworkremotely_jobs(query: Optional[str] = None, us_only: bool = True) -> List[Dict[str, Any]]:
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

                        location = "Remote (USA/Global)"

                        # US filter
                        if us_only and not is_us_eligible(location=location, title=title, text=desc):
                            continue

                        if not matches_query(query, title, company, ["remote", "weworkremotely"], desc):
                            continue

                        results.append({
                            "title": title,
                            "company": company,
                            "location": location,
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

# 5. Himalayas (Public API) - Filtered to US Only
async def fetch_himalayas_jobs(query: Optional[str] = None, us_only: bool = True) -> List[Dict[str, Any]]:
    """Fetch remote opportunities from Himalayas public API (filtered for US eligibility)."""
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
                    location = ", ".join(location_restrictions) if location_restrictions else "United States / Remote"
                    salary_min = float(j.get("minSalary", 0)) if j.get("minSalary") else None
                    salary_max = float(j.get("maxSalary", 0)) if j.get("maxSalary") else None

                    # Strict US filtering for Himalayas
                    if us_only and not is_us_eligible(
                        location=location,
                        title=title,
                        text=description,
                        location_list=location_restrictions
                    ):
                        continue

                    if not matches_query(query, title, company, categories, description):
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
async def fetch_hackernews_jobs(query: Optional[str] = None, us_only: bool = True) -> List[Dict[str, Any]]:
    """Fetch startup & tech roles from the latest monthly Hacker News Who is Hiring thread."""
    results = []
    try:
        async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
            story_res = await client.get(
                "https://hn.algolia.com/api/v1/search_by_date?query=Ask+HN:+Who+is+hiring&tags=story,author_whoishiring&hitsPerPage=1"
            )
            if story_res.status_code != 200:
                return []
            hits = story_res.json().get("hits", [])
            if not hits:
                return []

            story_id = hits[0].get("objectID")

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
                location = "Remote (USA)"
                is_remote = "remote" in clean_desc.lower()

                if "|" in first_line:
                    parts = [p.strip() for p in first_line.split("|")]
                    if len(parts) >= 1 and parts[0]:
                        company = re.sub(r"\(.*?\)", "", parts[0]).strip()
                    if len(parts) >= 2 and parts[1]:
                        title = parts[1].strip()
                    if len(parts) >= 3 and parts[2]:
                        location = parts[2].strip()

                # US filter
                if us_only and not is_us_eligible(location=location, title=title, text=clean_desc):
                    continue

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

# 7. Indeed (Direct Scraper via JobSpy)
def _scrape_indeed_sync(search_term: str, location: str, results_wanted: int = 25) -> List[Dict[str, Any]]:
    """Synchronous worker that scrapes live Indeed postings via JobSpy."""
    try:
        from jobspy import scrape_jobs
        df = scrape_jobs(
            site_name=["indeed"],
            search_term=search_term,
            location=location,
            results_wanted=results_wanted,
            country_indeed="USA",
        )
        if df is None or df.empty:
            return []

        jobs_list = []
        for _, row in df.iterrows():
            title = str(row.get("title") or "").strip()
            company = str(row.get("company") or "").strip()
            loc = str(row.get("location") or "USA").strip()
            url = str(row.get("job_url") or "").strip()
            if not title or not url or title.lower() == "nan" or url.lower() == "nan":
                continue

            desc = clean_html(str(row.get("description") or ""))
            min_sal = float(row.get("min_amount")) if row.get("min_amount") is not None and str(row.get("min_amount")) != "nan" else None
            max_sal = float(row.get("max_amount")) if row.get("max_amount") is not None and str(row.get("max_amount")) != "nan" else None
            is_remote = bool(row.get("is_remote", False)) or "remote" in loc.lower()

            jobs_list.append({
                "title": title,
                "company": company or "Indeed Employer",
                "location": loc,
                "workplace_type": "remote" if is_remote else "hybrid",
                "url": url,
                "salary_min": min_sal,
                "salary_max": max_sal,
                "salary_currency": str(row.get("currency") or "USD") if str(row.get("currency")) != "nan" else "USD",
                "tags": ["indeed", "direct-hire"],
                "description": desc,
                "source": "indeed",
            })
        return jobs_list
    except Exception as e:
        logger.warning(f"Error in Indeed JobSpy scraper: {e}")
        return []

async def fetch_indeed_jobs(query: Optional[str] = None, us_only: bool = True) -> List[Dict[str, Any]]:
    """Fetch live US listings directly from Indeed."""
    search_term = query.strip() if query and query.strip() else "Software Developer"
    location = "United States" if us_only else "Remote"
    try:
        raw_jobs = await asyncio.to_thread(_scrape_indeed_sync, search_term, location, 25)
        filtered = []
        for j in raw_jobs:
            if us_only and not is_us_eligible(location=j["location"], title=j["title"], text=j["description"]):
                continue
            filtered.append(j)
        return filtered
    except Exception as e:
        logger.warning(f"Error fetching Indeed jobs: {e}")
        return []

# 8. Adzuna API (US Jobs across Indeed, ZipRecruiter, etc.)
async def fetch_adzuna_jobs(
    query: Optional[str] = None,
    app_id: Optional[str] = None,
    app_key: Optional[str] = None,
    us_only: bool = True
) -> List[Dict[str, Any]]:
    """Fetch live US jobs across Indeed, ZipRecruiter & major boards via Adzuna API."""
    app_id = app_id or os.getenv("ADZUNA_APP_ID")
    app_key = app_key or os.getenv("ADZUNA_APP_KEY")

    if not app_id or not app_key:
        logger.debug("Adzuna API ID and Key not provided.")
        return []

    search_query = query or "software developer"
    url = "https://api.adzuna.com/v1/api/jobs/us/search/1"
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
                    loc_display = item.get("location", {}).get("display_name", "United States")
                    salary_min = float(item.get("salary_min", 0)) if item.get("salary_min") else None
                    salary_max = float(item.get("salary_max", 0)) if item.get("salary_max") else None
                    desc = clean_html(item.get("description", ""))
                    apply_url = item.get("redirect_url", "")
                    category = item.get("category", {}).get("label", "IT Jobs")
                    is_remote = "remote" in title.lower() or "remote" in desc.lower() or "remote" in loc_display.lower()

                    if us_only and not is_us_eligible(location=loc_display, title=title, text=desc):
                        continue

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

# Aggregated Search with Source Filtering & US-Only Enforcement
async def search_aggregated_jobs(
    query: Optional[str] = None,
    source: Optional[str] = None,
    adzuna_app_id: Optional[str] = None,
    adzuna_app_key: Optional[str] = None,
    us_only: bool = True
) -> List[Dict[str, Any]]:
    """Aggregates listings concurrently across all supported boards with US filtering."""

    tasks = []
    source_lower = (source or "all").lower()

    if source_lower in ("all", "indeed"):
        tasks.append(fetch_indeed_jobs(query, us_only=us_only))
    if source_lower in ("all", "arbeitnow"):
        tasks.append(fetch_arbeitnow_jobs(query, us_only=us_only))
    if source_lower in ("all", "jobicy"):
        tasks.append(fetch_jobicy_jobs(query, us_only=us_only))
    if source_lower in ("all", "weworkremotely"):
        tasks.append(fetch_weworkremotely_jobs(query, us_only=us_only))
    if source_lower in ("all", "himalayas"):
        tasks.append(fetch_himalayas_jobs(query, us_only=us_only))
    if source_lower in ("all", "hackernews"):
        tasks.append(fetch_hackernews_jobs(query, us_only=us_only))
    if source_lower in ("all", "remoteok"):
        tasks.append(fetch_remoteok_jobs(query, us_only=us_only))
    if source_lower in ("all", "adzuna"):
        tasks.append(fetch_adzuna_jobs(query, adzuna_app_id, adzuna_app_key, us_only=us_only))

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

