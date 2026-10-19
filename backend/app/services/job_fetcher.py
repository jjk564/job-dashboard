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

def _has_explicit_junior_title(title: str) -> bool:
    t = (title or "").lower()
    if re.search(
        r'\b(junior|jr\.?|entry[\s-]level|new\s+grad(?:uate)?|recent\s+grad(?:uate)?|fresh\s+grad(?:uate)?|'
        r'early[\s-]career|apprentice|apprenticeship|intern|internship|trainee|rotational|campus|'
        r'university\s+grad(?:uate)?|college\s+grad(?:uate)?)\b',
        t
    ):
        return True
    if re.search(r'\bassociate\b', t) and not re.search(
        r'\b(director|vp|vice\s+president|partner|principal|counsel|dean|professor|budtender|retail|store|warehouse|cashier)\b', t
    ):
        if re.search(
            r'\b(developer|engineer|engineering|programmer|software|web|frontend|backend|full[\s-]stack|data|analyst|qa|devops|cloud|cyber|security|it|systems|tech|technology|technical|application|support|scientist|consultant|designer|product)\b',
            t
        ):
            return True
    if re.search(
        r'\b(software\s+engineer|developer|engineer|analyst|programmer|specialist|technician|'
        r'administrator|consultant|scientist|designer|qa|sdet|devops|support|swe|sde)\s*(?:-\s*)?(?:i|1)\b',
        t
    ) or re.search(r'\b(?:level|tier)\s*(?:i|1)\b', t):
        return True
    return False


def _is_senior_or_mid_title(title: str) -> bool:
    t = (title or "").lower()
    if re.search(
        r'\b(staff|senior|sr\.?|principal|lead|tech\s+lead|team\s+lead|manager|director|vp|'
        r'vice\s+president|head\s+of|architect|distinguished|fellow|chief|cto|cio)\b',
        t
    ):
        if not re.search(r'\b(junior|jr\.?|entry[\s-]level|intern|apprentice)\b', t):
            return True
    if re.search(r'\b(mid[\s-]level|intermediate)\b', t):
        if not re.search(r'\b(junior|jr\.?|entry[\s-]level|early)\b', t):
            return True
    if _has_explicit_junior_title(t):
        return False
    if re.search(r'\b(ii|iii|iv|v|vi)\b', t):
        return True
    if re.search(
        r'\b(?:engineer|developer|programmer|analyst|specialist|scientist|technician|level|tier|swe|sde)\s*(?:-\s*)?(?:2|3|4|5|6)\b',
        t
    ):
        return True
    return False


def _requires_4plus_years(description: str) -> bool:
    if not description:
        return False
    desc_lower = description.lower()
    # Strip company history / legacy blurbs and age requirements before checking candidate experience
    cleaned = re.sub(
        r'\b(?:must\s+be\s+|at\s+least\s+)?\d{2}\s*(?:years?|yrs?)\s+of\s+age\b',
        '', desc_lower
    )
    cleaned = re.sub(
        r'\b(?:company|team|organization|firm|business|industry|leader|legacy|history|combined)\s+'
        r'(?:with|of|for|celebrating|bringing)\s+(?:more\s+than\s+|over\s+)?\d+\+?\s*(?:years?|yrs?)\b',
        '', cleaned
    )
    cleaned = re.sub(
        r'\b(?:more\s+than|over)\s+(?:1[5-9]|[2-9]\d)\s*\+?\s*(?:years?|yrs?)\s+(?:of\s+)?(?:experience|exp)?\b',
        '', cleaned
    )

    # Check if there is an explicit entry-level range like 0-4, 1-4, 2-4, 0 to 3, 1 to 4 years
    has_entry_range = bool(
        re.search(r'\b[0-2]\s*(?:to|-|–|—)\s*[1-4]\s*(?:years?|yrs?)\b', cleaned)
    )

    # Require actual experience keywords so "4 years vesting" or "10 years ago" never triggers
    if re.search(
        r'\b(?:(?:minimum|at\s+least|over|requires?)\s+(?:of\s+)?)?([4-9]|1[0-5])\s*\+?\s*(?:(?:to|-|–|—)\s*\d+\s*)?'
        r'(?:years?|yrs?)\s+(?:of\s+)?(?:[\w/-]+\s+){0,3}?(?:experience|exp|hands-on|background|development|engineering|programming)\b',
        cleaned
    ):
        if not has_entry_range:
            return True

    if re.search(r'\b(4-6|4-7|5-7|5-8|6-8|6-10|7-10|8-10|8-12|10-15)\s*(?:years?|yrs?)\b', cleaned):
        return True
    return False


def _has_junior_signals(
    title: str,
    description: str,
    salary_min: Optional[float] = None,
    salary_max: Optional[float] = None
) -> bool:
    if _is_senior_or_mid_title(title):
        return False
    if _has_explicit_junior_title(title):
        return True
    if _requires_4plus_years(description):
        return False
    if (salary_min and salary_min >= 120000) or (salary_max and salary_max >= 145000):
        return False

    desc_lower = (description or "").lower()
    # Remove mentorship false-positives and "graduate degree"
    clean_text = re.sub(
        r'\b(?:mentor|mentoring|mentors|lead|leading|leads|coach|coaching|coaches|supervise|supervising|guide|guiding)\s+'
        r'(?:and\s+\w+\s+)?(?:to\s+)?(?:junior|entry|intern|early[\s-]career)\b',
        '', desc_lower
    )
    clean_text = re.sub(r'\bgraduate\s+degree\b', '', clean_text)

    if (
        re.search(
            r'\b(junior|jr\.?|entry[\s-]level|entrylevel|new\s+grad(?:uate)?|recent\s+grad(?:uate)?|'
            r'fresh\s+grad(?:uate)?|early[\s-]career|earlycareer|apprentice|apprenticeship|'
            r'internship|trainee|campus\s+hire|rotational\s+program|university\s+grad(?:uate)?|'
            r'college\s+grad(?:uate)?|bootcamp)\b',
            clean_text
        ) or
        re.search(
            r'\b(software\s+engineer|developer|engineer|analyst|programmer|specialist|technician)\s+(?:i|1)\b',
            clean_text
        ) or
        re.search(r'\b(?:level|tier)\s+(?:i|1)\b', clean_text) or
        re.search(r'\b[0-2]\s*(?:to|-|–|—)\s*[1-3]\s*(?:years?|yrs?)\b', clean_text) or
        re.search(
            r'\b[0-2]\s*\+?\s*(?:years?|yrs?)\s+(?:of\s+)?(?:[\w/-]+\s+){0,2}?(?:experience|exp|hands-on|development|engineering)\b',
            clean_text
        ) or
        re.search(r'\b(?:minimum|at\s+least|up\s+to|under|less\s+than)\s+(?:of\s+)?[1-2]\s*(?:years?|yrs?)\b', clean_text) or
        "no experience required" in clean_text or
        "no prior experience" in clean_text or
        "on-the-job training" in clean_text or
        "on-job-training" in clean_text
    ):
        return True

    # Entry-level compensation band signal when job title is clearly a technical/software role
    is_tech_title = bool(
        re.search(r'\b(developer|engineer|programmer|software|web|frontend|front-end|backend|back-end|full[\s-]stack|data|analyst|qa|devops|cloud|cyber|security|it|systems|network|ai|ml)\b', (title or "").lower())
    )
    if is_tech_title:
        if salary_max and 45000 <= salary_max <= 95000:
            return True
        if salary_min and 45000 <= salary_min <= 85000 and (not salary_max or salary_max <= 105000):
            return True

    return False


def _term_matches(term: str, full_text: str, title: str = "", description: str = "") -> bool:
    t = term.lower().strip()
    if not t:
        return True

    junior_group = {
        "junior", "jr", "entry", "entry-level", "entrylevel", "associate",
        "newgrad", "graduate", "apprentice", "intern", "internship", "trainee", "earlycareer"
    }
    if t in junior_group:
        return _has_junior_signals(title, description or full_text)

    # Word boundary match for short tokens (<= 4 chars, e.g. ui, ai, ml, go, jr, sr, c++, sql, aws)
    if len(t) <= 4:
        if re.search(r'(?:\b|(?<=\s))' + re.escape(t) + r'(?:\b|(?=\s))', full_text):
            return True
    else:
        if t in full_text:
            return True

    synonym_groups = [
        {"developer", "engineer", "dev", "programmer", "software", "coder", "architect", "engineering", "development"},
        {"senior", "sr", "lead", "principal", "staff"},
        {"frontend", "front-end", "ui", "react", "vue", "angular", "javascript", "typescript"},
        {"backend", "back-end", "api", "server", "django", "fastapi", "nodejs", "node.js"},
        {"fullstack", "full-stack", "full stack"},
        {"devops", "sre", "infrastructure", "cloud", "aws", "kubernetes", "docker", "platform"},
        {"data", "machine learning", "ml", "ai", "data engineer", "data scientist", "analytics", "analyst"},
        {"remote", "wfh", "work from home", "anywhere", "telecommute"},
    ]
    for group in synonym_groups:
        if t in group:
            for syn in group:
                if len(syn) <= 4:
                    if re.search(r'\b' + re.escape(syn) + r'\b', full_text):
                        return True
                else:
                    if syn in full_text:
                        return True
    return False


def matches_query(
    query: Optional[str],
    title: str,
    company: str,
    tags: List[Any],
    description: str,
    location: str = "",
    workplace_type: str = "",
    salary_min: Optional[float] = None,
    salary_max: Optional[float] = None
) -> bool:
    """
    Smart multi-keyword and synonym matching across title, company, tags, description, and workplace type.
    When multiple keywords are queried (e.g. 'python remote' or 'junior react developer'),
    every keyword or concept cluster is evaluated flexibly.
    """
    if not query:
        return True
    q = query.lower().strip()
    if not q:
        return True

    tag_str = " ".join(str(t) for t in tags)
    full_text = f"{title} {company} {location} {workplace_type} {tag_str} {description}".lower()

    is_junior_q = any(
        k in q for k in (
            "junior", "jr", "entry", "entry-level", "entrylevel",
            "associate", "new grad", "newgrad", "early career", "earlycareer", "intern"
        )
    )
    if is_junior_q:
        if not _has_junior_signals(title, f"{tag_str} {description}", salary_min=salary_min, salary_max=salary_max):
            return False

    # Direct exact substring match (only if not a junior query or already passed junior signal check)
    if q in full_text:
        return True

    # Normalize composite phrases BEFORE splitting punctuation/whitespace
    normalized_q = q
    normalized_q = re.sub(r'\bentry[\s-]+level\b', 'entrylevel', normalized_q)
    normalized_q = re.sub(r'\bnew\s+grad(?:uate)?\b', 'newgrad', normalized_q)
    normalized_q = re.sub(r'\brecent\s+grad(?:uate)?\b', 'newgrad', normalized_q)
    normalized_q = re.sub(r'\bearly[\s-]+career\b', 'earlycareer', normalized_q)
    normalized_q = re.sub(r'\bmid[\s-]+level\b', 'midlevel', normalized_q)
    normalized_q = re.sub(r'\bfull[\s-]+stack\b', 'fullstack', normalized_q)
    normalized_q = re.sub(r'\bfront[\s-]+end\b', 'frontend', normalized_q)
    normalized_q = re.sub(r'\bback[\s-]+end\b', 'backend', normalized_q)
    normalized_q = re.sub(r'\bwork\s+from\s+home\b', 'remote', normalized_q)
    normalized_q = re.sub(r'[/,()"+-]', ' ', normalized_q)

    stop_words = {"and", "or", "the", "for", "with", "in", "level", "role", "position", "job", "jobs"}
    terms = [t for t in normalized_q.split() if len(t) > 1 and t not in stop_words]
    if not terms:
        return True

    loc_wp_lower = f"{location} {workplace_type} {tag_str}".lower()
    is_remote_job = "remote" in loc_wp_lower or "wfh" in loc_wp_lower or "anywhere" in loc_wp_lower

    for term in terms:
        if term in ("remote", "wfh", "telecommute") and is_remote_job:
            continue
        if not _term_matches(term, full_text, title=title, description=f"{tag_str} {description}"):
            return False
    return True



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

                    if not matches_query(query, title, company, tags, description, location=location, workplace_type="remote"):
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
                    if len(results) >= 60:
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

                    if not matches_query(query, title, company, tags, description, location=location, workplace_type="remote" if is_remote else "hybrid"):
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
                    if len(results) >= 60:
                        break
    except Exception as e:
        logger.warning(f"Error fetching Arbeitnow jobs: {e}")
    return results

# 3. Jobicy
async def fetch_jobicy_jobs(query: Optional[str] = None, us_only: bool = True) -> List[Dict[str, Any]]:
    """Fetch jobs from Jobicy public API."""
    url = "https://jobicy.com/api/v2/remote-jobs?count=100&tag=dev&geo=usa" if us_only else "https://jobicy.com/api/v2/remote-jobs?count=100&tag=dev"
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

                    if not matches_query(query, title, company, tags, description, location=location, workplace_type="remote"):
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
                    if len(results) >= 60:
                        break
    except Exception as e:
        logger.warning(f"Error fetching Jobicy jobs: {e}")
    return results


# 4. We Work Remotely (RSS Feeds)
async def fetch_weworkremotely_jobs(query: Optional[str] = None, us_only: bool = True) -> List[Dict[str, Any]]:
    """Fetch top tech roles from We Work Remotely official RSS feeds concurrently."""
    feeds = [
        "https://weworkremotely.com/categories/remote-programming-jobs.rss",
        "https://weworkremotely.com/categories/remote-full-stack-programming-jobs.rss",
        "https://weworkremotely.com/categories/remote-front-end-programming-jobs.rss",
        "https://weworkremotely.com/categories/remote-back-end-programming-jobs.rss",
        "https://weworkremotely.com/categories/remote-devops-sysadmin-jobs.rss",
    ]
    results = []
    seen = set()
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            responses = await asyncio.gather(
                *[client.get(feed_url, headers=HEADERS) for feed_url in feeds],
                return_exceptions=True
            )
            for resp in responses:
                if isinstance(resp, Exception) or resp.status_code != 200:
                    continue
                try:
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

                        key = f"{title.lower()}|{company.lower()}"
                        if key in seen:
                            continue

                        location = "Remote (USA/Global)"

                        # US filter
                        if us_only and not is_us_eligible(location=location, title=title, text=desc):
                            continue

                        if not matches_query(query, title, company, ["remote", "weworkremotely"], desc, location=location, workplace_type="remote"):
                            continue

                        seen.add(key)
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
                    logger.debug(f"Feed parse error: {inner_e}")
    except Exception as e:
        logger.warning(f"Error fetching We Work Remotely jobs: {e}")
    return results

# 5. Himalayas (Public API) - Filtered to US Only
async def fetch_himalayas_jobs(query: Optional[str] = None, us_only: bool = True) -> List[Dict[str, Any]]:
    """Fetch remote opportunities from Himalayas public API (filtered for US eligibility)."""
    results = []
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            offsets = (0, 20, 40, 60)
            responses = await asyncio.gather(
                *[client.get(f"https://himalayas.app/jobs/api?limit=20&offset={offset}", headers=HEADERS) for offset in offsets],
                return_exceptions=True
            )
            for resp in responses:
                if isinstance(resp, Exception) or resp.status_code != 200:
                    continue
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

                    if not matches_query(query, title, company, categories, description, location=location, workplace_type="remote", salary_min=salary_min, salary_max=salary_max):
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
            q_lower = (query or "").lower().strip()
            is_junior_q = any(w in q_lower for w in ("junior", "jr", "entry", "entry-level", "associate", "intern", "new grad", "grad"))

            # Fetch a broad set of comments so synonym matching (intern, new grad, entry-level, junior) can evaluate all posts
            requests_to_make = [
                client.get("https://hn.algolia.com/api/v1/search", params={"tags": f"comment,story_{story_id}", "hitsPerPage": 150})
            ]
            if is_junior_q:
                for kw in ("intern", "grad", "junior"):
                    requests_to_make.append(
                        client.get("https://hn.algolia.com/api/v1/search", params={"tags": f"comment,story_{story_id}", "hitsPerPage": 50, "query": kw})
                    )
            elif query:
                requests_to_make.append(
                    client.get("https://hn.algolia.com/api/v1/search", params={"tags": f"comment,story_{story_id}", "hitsPerPage": 60, "query": query})
                )

            responses = await asyncio.gather(*requests_to_make, return_exceptions=True)
            comments = []
            seen_cids = set()
            for r in responses:
                if isinstance(r, Exception) or r.status_code != 200:
                    continue
                for hit in r.json().get("hits", []):
                    cid = hit.get("objectID")
                    if cid and cid not in seen_cids:
                        seen_cids.add(cid)
                        comments.append(hit)

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

                if not matches_query(query, title, company, ["hacker-news", "startup", "direct-hire"], clean_desc, location=location, workplace_type="remote" if is_remote else "hybrid"):
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
def _scrape_indeed_sync(
    search_term: str,
    location: str,
    is_remote: bool = False,
    results_wanted: int = 40,
    distance: Optional[int] = None
) -> List[Dict[str, Any]]:
    """Synchronous worker that scrapes live Indeed postings via JobSpy with location & radius distance."""
    try:
        from jobspy import scrape_jobs
        scrape_kwargs = {
            "site_name": ["indeed"],
            "search_term": search_term,
            "location": location,
            "is_remote": is_remote,
            "results_wanted": results_wanted,
            "country_indeed": "USA",
        }
        if distance is not None:
            scrape_kwargs["distance"] = distance

        df = scrape_jobs(**scrape_kwargs)
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
            # Convert hourly wages (< $200) to approximate annual salary so salary filters work consistently
            if min_sal and min_sal < 200:
                min_sal = round(min_sal * 2080, 2)
            if max_sal and max_sal < 200:
                max_sal = round(max_sal * 2080, 2)
            job_is_remote = bool(row.get("is_remote", False)) or "remote" in loc.lower() or is_remote

            tags = ["indeed", "direct-hire"]
            if job_is_remote:
                tags.append("remote")

            jobs_list.append({
                "title": title,
                "company": company or "Indeed Employer",
                "location": "Remote" if job_is_remote and loc in ("", "USA") else loc,
                "workplace_type": "remote" if job_is_remote else "hybrid",
                "url": url,
                "salary_min": min_sal,
                "salary_max": max_sal,
                "salary_currency": str(row.get("currency") or "USD") if str(row.get("currency")) != "nan" else "USD",
                "tags": tags,
                "description": desc,
                "source": "indeed",
            })
        return jobs_list
    except Exception as e:
        logger.warning(f"Error in Indeed JobSpy scraper: {e}")
        return []

async def fetch_indeed_jobs(
    query: Optional[str] = None,
    us_only: bool = True,
    location: Optional[str] = None,
    radius: Optional[int] = None
) -> List[Dict[str, Any]]:
    """Fetch live US listings directly from Indeed with entry-level synonym expansion and location/radius filtering."""
    q_lower = (query or "").lower().strip()
    is_remote_query = any(w in q_lower for w in ("remote", "wfh", "work from home"))
    is_junior_query = any(w in q_lower for w in ("junior", "jr", "entry", "entry-level", "associate", "intern", "new grad"))

    # Clean query for search_term: remove the word 'remote' so Indeed gets the pure job title
    clean_term = re.sub(r"\b(remote|wfh|work from home)\b", "", q_lower, flags=re.I).strip()
    clean_term = re.sub(r"[/,()+-]", " ", clean_term)
    clean_term = " ".join(clean_term.split())
    search_term = clean_term if clean_term else "Software Developer"

    # Strip junior tokens to isolate the core role/tech discipline
    core_term = re.sub(
        r"\b(junior|jr|entry\s+level|entry|associate|new\s+grad|early\s+career|intern|internship|level)\b",
        "",
        clean_term,
        flags=re.I
    )
    core_term = " ".join(core_term.split()).strip()
    if not core_term:
        core_term = "software developer"

    # User-specified target location
    target_loc = location.strip() if location and location.strip() else None
    if is_remote_query:
        loc_str = "Remote"
    elif target_loc:
        loc_str = target_loc
    else:
        loc_str = "United States" if us_only else "Remote"

    distance_val = radius if (target_loc and radius) else (50 if target_loc else None)

    try:
        if is_junior_query:
            # Quoted "entry level" and targeted junior/associate queries dramatically boost genuine entry-level results on Indeed
            if core_term.lower() in ("developer", "software developer", "software engineer", "engineer"):
                q1 = '"entry level" software developer'
                q2 = 'junior software engineer'
                q3 = 'associate software engineer'
            else:
                q1 = f'"entry level" {core_term}'
                q2 = f'junior {core_term}'
                q3 = f'associate {core_term}'

            t1 = asyncio.to_thread(_scrape_indeed_sync, q1, loc_str, is_remote_query, 35, distance_val)
            t2 = asyncio.to_thread(_scrape_indeed_sync, q2, loc_str, is_remote_query, 35, distance_val)
            t3 = asyncio.to_thread(_scrape_indeed_sync, q3, loc_str, is_remote_query, 25, distance_val)
            res = await asyncio.gather(t1, t2, t3, return_exceptions=True)
            raw_jobs = []
            for r in res:
                if isinstance(r, list):
                    raw_jobs.extend(r)
        else:
            # Include a concurrent entry-level batch so general searches also surface entry-level opportunities
            t1 = asyncio.to_thread(_scrape_indeed_sync, search_term, loc_str, is_remote_query, 35, distance_val)
            t2 = asyncio.to_thread(_scrape_indeed_sync, f'"entry level" {search_term}', loc_str, is_remote_query, 20, distance_val)
            res = await asyncio.gather(t1, t2, return_exceptions=True)
            raw_jobs = []
            for r in res:
                if isinstance(r, list):
                    raw_jobs.extend(r)

        filtered = []
        seen = set()
        for j in raw_jobs:
            key = f"{j['title'].lower().strip()}|{j['company'].lower().strip()}"
            if key in seen:
                continue
            seen.add(key)
            if us_only and not is_us_eligible(location=j["location"], title=j["title"], text=j["description"]):
                continue
            if not matches_query(
                query, j["title"], j["company"], j["tags"], j["description"],
                location=j["location"], workplace_type=j["workplace_type"],
                salary_min=j.get("salary_min"), salary_max=j.get("salary_max")
            ):
                continue
            filtered.append(j)
        return filtered
    except Exception as e:
        logger.warning(f"Error fetching Indeed jobs: {e}")
        return []

# 8. ZipRecruiter (Direct Live Scraper via curl_cffi)
def _scrape_ziprecruiter_sync(
    search_term: str,
    us_only: bool = True,
    is_remote: bool = False,
    max_pages: int = 2,
    location: Optional[str] = None,
    radius: Optional[int] = None
) -> List[Dict[str, Any]]:
    """Synchronous worker that scrapes live ZipRecruiter postings across multiple pages via curl_cffi with location & radius filtering."""
    try:
        from curl_cffi import requests as cffi_requests
        s = cffi_requests.Session(impersonate="safari")
        search_q = search_term or "software developer"

        # Remove the word 'remote' so ZipRecruiter doesn't search for 'remote' in job title text
        clean_q = re.sub(r"\b(remote|wfh|work from home)\b", "", search_q, flags=re.I)
        clean_q = re.sub(r"[/,()+-]", " ", clean_q)
        clean_q = " ".join(clean_q.split())
        if not clean_q:
            clean_q = "software developer"

        encoded_q = "+".join(clean_q.split())
        target_loc = location.strip() if location and location.strip() else None
        if is_remote:
            loc_param = "Remote"
        elif target_loc:
            loc_param = "+".join(target_loc.split())
        else:
            loc_param = "United+States" if us_only else "Remote"

        radius_query = f"&radius={radius}" if (target_loc and radius) else ""

        jobs_list = []
        seen_keys = set()

        for page in range(1, max_pages + 1):
            url = f"https://www.ziprecruiter.com/jobs-search?search={encoded_q}&location={loc_param}{radius_query}&page={page}"
            r = s.get(url, timeout=12)
            if r.status_code != 200:
                break

            soup = BeautifulSoup(r.text, "html.parser")

            # Parse canonical direct job URLs from Schema.org ItemList script tag
            url_map = {}
            for sc in soup.find_all("script"):
                txt = sc.text or ""
                if "schema.org" in txt and "ItemList" in txt:
                    try:
                        import json
                        data = json.loads(txt)
                        for it in data.get("itemListElement", []):
                            name = it.get("name", "").strip()
                            u = it.get("url", "").strip()
                            if name and u:
                                url_map[name.lower()] = u
                    except Exception:
                        pass

            # Extract rich shortDescription & canonical URLs from embedded Next.js jobCards payload
            short_desc_map: Dict[str, str] = {}
            try:
                unescaped = r.text.replace('\\"', '"').replace('\\\\', '\\')
                card_matches = re.findall(
                    r'"listingKey":"[^"]+","title":"([^"]+)".*?"shortDescription":"([^"]*)".*?"rawCanonicalZipJobPageUrl":"([^"]*)"',
                    unescaped
                )
                for c_title, c_desc, c_url in card_matches:
                    t_key = c_title.strip().lower()
                    if c_desc:
                        short_desc_map[t_key] = clean_html(c_desc)
                    if c_url and t_key not in url_map:
                        url_map[t_key] = f"https://www.ziprecruiter.com{c_url}" if c_url.startswith("/") else c_url
            except Exception:
                pass

            articles = soup.find_all("article")
            if not articles:
                break

            for art in articles:
                h2 = art.find("h2")
                if not h2:
                    continue
                title = h2.text.strip()

                # Resolve direct job posting link
                link = url_map.get(title.lower(), "")
                if not link:
                    for a in art.find_all("a"):
                        href = a.get("href", "")
                        if "/Job/" in href or "jid=" in href:
                            link = href if href.startswith("http") else f"https://www.ziprecruiter.com{href}"
                            break
                if not link:
                    link_el = h2.find("a") or art.find("a")
                    link = link_el["href"] if link_el and "href" in link_el.attrs else ""
                    if link.startswith("/"):
                        link = f"https://www.ziprecruiter.com{link}"

                co_link = art.find("a", href=re.compile(r"/co/")) or art.find("a", {"data-testid": "job-card-company"})
                company = co_link.text.strip() if co_link else "ZipRecruiter Employer"

                loc_link = art.find("a", href=re.compile(r"location=")) or art.find("a", {"data-testid": "job-card-location"})
                job_loc = loc_link.text.strip() if loc_link else ("Remote" if is_remote else (target_loc or "USA"))

                card_is_remote = is_remote or "remote" in job_loc.lower() or "remote" in title.lower()
                salary_min = None
                salary_max = None
                tags = ["ziprecruiter", "direct-hire"]
                if card_is_remote:
                    tags.append("remote")

                for p in art.find_all(["p", "span"]):
                    t = p.text.strip()
                    if "remote" in t.lower():
                        card_is_remote = True
                        if "remote" not in tags:
                            tags.append("remote")
                    if t.startswith("$"):
                        is_hourly = "/hr" in t.lower() or "per hour" in t.lower() or "an hour" in t.lower()
                        m = re.findall(r"\$([0-9,]+(?:\.[0-9]+)?)(k)?", t, re.IGNORECASE)
                        if m:
                            nums = [float(n[0].replace(",", "")) * (1000 if n[1] else 1) for n in m]
                            if is_hourly or (nums and max(nums) < 200):
                                nums = [round(v * 2080, 2) for v in nums]
                            salary_min = min(nums)
                            salary_max = max(nums)
                    if t in ["Full-time", "Part-time", "Contract"]:
                        tags.append(t.lower())

                desc_loc = "Remote" if card_is_remote else job_loc
                key = f"{title.lower()}|{company.lower()}"
                if key in seen_keys:
                    continue
                seen_keys.add(key)

                snippet = short_desc_map.get(title.lower(), "")
                # If the role is not a senior/mid-level title, preserve the ZipRecruiter full-text search query context
                # so listings whose tech stack or entry-level keywords appear deeper in the posting body are retained
                if not _is_senior_or_mid_title(title):
                    q_tokens = [tok.lower() for tok in clean_q.split() if len(tok) > 1]
                    for tok in q_tokens:
                        if tok not in tags:
                            tags.append(tok)
                    context_note = f"Matched search criteria: {clean_q}."
                else:
                    context_note = ""

                full_desc = f"{title} ({desc_loc}) at {company}. {snippet} {context_note} Full listing available on ZipRecruiter.".strip()

                jobs_list.append({
                    "title": title,
                    "company": company,
                    "location": desc_loc,
                    "workplace_type": "remote" if card_is_remote else "hybrid",
                    "url": link,
                    "salary_min": salary_min,
                    "salary_max": salary_max,
                    "salary_currency": "USD",
                    "tags": tags,
                    "description": full_desc,
                    "source": "ziprecruiter",
                })
                if len(jobs_list) >= 80:
                    break

            if len(jobs_list) >= 80:
                break

        return jobs_list
    except Exception as e:
        logger.warning(f"Error scraping ZipRecruiter: {e}")
        return []

async def fetch_ziprecruiter_jobs(
    query: Optional[str] = None,
    us_only: bool = True,
    location: Optional[str] = None,
    radius: Optional[int] = None
) -> List[Dict[str, Any]]:
    """Fetch live US listings directly from ZipRecruiter with multi-query & multi-page expansion and location/radius filtering."""
    q_lower = (query or "").lower().strip()
    is_remote_query = any(w in q_lower for w in ("remote", "wfh", "work from home"))
    is_junior_query = any(w in q_lower for w in ("junior", "jr", "entry", "entry-level", "associate", "intern", "new grad"))

    clean_term = re.sub(r"\b(remote|wfh|work from home)\b", "", q_lower, flags=re.I).strip()
    clean_term = re.sub(r"[/,()+-]", " ", clean_term)
    clean_term = " ".join(clean_term.split())

    core_term = re.sub(
        r"\b(junior|jr|entry\s+level|entry|associate|new\s+grad|early\s+career|intern|internship|level)\b",
        "",
        clean_term,
        flags=re.I
    )
    core_term = " ".join(core_term.split()).strip()
    if not core_term:
        core_term = "software developer"

    try:
        if is_junior_query:
            if core_term.lower() in ("developer", "software developer", "software engineer", "engineer"):
                q1 = "junior software developer"
                q2 = "entry level software engineer"
                q3 = "associate software engineer"
            else:
                q1 = f"junior {core_term}"
                q2 = f"entry level {core_term}"
                q3 = f"associate {core_term}"

            t1 = asyncio.to_thread(_scrape_ziprecruiter_sync, q1, us_only, is_remote_query, 2, location, radius)
            t2 = asyncio.to_thread(_scrape_ziprecruiter_sync, q2, us_only, is_remote_query, 2, location, radius)
            t3 = asyncio.to_thread(_scrape_ziprecruiter_sync, q3, us_only, is_remote_query, 1, location, radius)
            res = await asyncio.gather(t1, t2, t3, return_exceptions=True)
            raw_jobs = []
            for r in res:
                if isinstance(r, list):
                    raw_jobs.extend(r)
        else:
            search_term = clean_term if clean_term else "Software Developer"
            t1 = asyncio.to_thread(_scrape_ziprecruiter_sync, search_term, us_only, is_remote_query, 2, location, radius)
            t2 = asyncio.to_thread(_scrape_ziprecruiter_sync, f"entry level {search_term}", us_only, is_remote_query, 1, location, radius)
            res = await asyncio.gather(t1, t2, return_exceptions=True)
            raw_jobs = []
            for r in res:
                if isinstance(r, list):
                    raw_jobs.extend(r)

        filtered = []
        seen = set()
        for j in raw_jobs:
            key = f"{j['title'].lower().strip()}|{j['company'].lower().strip()}"
            if key in seen:
                continue
            seen.add(key)
            if us_only and not is_us_eligible(location=j["location"], title=j["title"], text=j["description"]):
                continue
            if not matches_query(
                query, j["title"], j["company"], j["tags"], j["description"],
                location=j["location"], workplace_type=j["workplace_type"],
                salary_min=j.get("salary_min"), salary_max=j.get("salary_max")
            ):
                continue
            filtered.append(j)
        return filtered
    except Exception as e:
        logger.warning(f"Error fetching ZipRecruiter jobs: {e}")
        return []

# 9. Adzuna API (US Jobs across Indeed, ZipRecruiter, etc.)
async def fetch_adzuna_jobs(
    query: Optional[str] = None,
    app_id: Optional[str] = None,
    app_key: Optional[str] = None,
    us_only: bool = True,
    location: Optional[str] = None,
    radius: Optional[int] = None
) -> List[Dict[str, Any]]:
    """Fetch live US jobs across Indeed, ZipRecruiter & major boards via Adzuna API with location & radius distance."""
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
        "results_per_page": 50,
        "what": search_query,
        "content-type": "application/json",
    }
    if location and location.strip():
        params["where"] = location.strip()
        if radius:
            params["distance"] = radius

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

                    if not matches_query(query, title, company, ["adzuna", "indeed-aggregated", category.lower()], desc, location=loc_display, workplace_type="remote" if is_remote else "hybrid"):
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

# Aggregated Search with Source Filtering, US-Only, and Location Radius Support
async def search_aggregated_jobs(
    query: Optional[str] = None,
    source: Optional[str] = None,
    adzuna_app_id: Optional[str] = None,
    adzuna_app_key: Optional[str] = None,
    us_only: bool = True,
    location: Optional[str] = None,
    radius: Optional[int] = None,
    include_remote: bool = True
) -> List[Dict[str, Any]]:
    """Aggregates listings concurrently across all supported boards with US & location/radius filtering."""

    tasks = []
    source_lower = (source or "all").lower()

    if source_lower in ("all", "indeed"):
        tasks.append(fetch_indeed_jobs(query, us_only=us_only, location=location, radius=radius))
    if source_lower in ("all", "ziprecruiter"):
        tasks.append(fetch_ziprecruiter_jobs(query, us_only=us_only, location=location, radius=radius))
    if source_lower in ("all", "adzuna"):
        tasks.append(fetch_adzuna_jobs(query, adzuna_app_id, adzuna_app_key, us_only=us_only, location=location, radius=radius))

    # Remote / global boards: only include if include_remote is True, or if user hasn't specified a strict local location
    should_fetch_remote_boards = include_remote or not location

    if should_fetch_remote_boards:
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

    results_lists = await asyncio.gather(*tasks, return_exceptions=True)

    combined = []
    for r in results_lists:
        if isinstance(r, list):
            combined.extend(r)
        elif isinstance(r, Exception):
            logger.warning(f"Error during parallel job fetch: {r}")

    # If location is provided and user unchecked include_remote, filter out purely remote positions
    if location and not include_remote:
        combined = [
            j for j in combined
            if j.get("workplace_type") != "remote" and "remote" not in (j.get("location") or "").lower()
        ]

    # Deduplicate by title + company
    seen = set()
    unique_jobs = []
    for j in combined:
        key = f"{j['title'].lower().strip()}|{j['company'].lower().strip()}"
        if key not in seen:
            seen.add(key)
            unique_jobs.append(j)

    return unique_jobs

