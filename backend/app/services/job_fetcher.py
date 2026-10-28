import logging
import asyncio
import os
import re
import xml.etree.ElementTree as ET
from typing import List, Dict, Any, Optional
import httpx
from bs4 import BeautifulSoup
from .location_matcher import is_job_in_range, is_job_pure_remote
from .job_extractor import extract_salary_range

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

_US_STATE_CODES = {
    "al", "ak", "az", "ar", "ca", "co", "ct", "de", "fl", "ga",
    "hi", "id", "il", "in", "ia", "ks", "ky", "la", "me", "md",
    "ma", "mi", "mn", "ms", "mo", "mt", "ne", "nv", "nh", "nj",
    "nm", "ny", "nc", "nd", "oh", "ok", "or", "pa", "ri", "sc",
    "sd", "tn", "tx", "ut", "vt", "va", "wa", "wv", "wi", "wy", "dc"
}

def _has_us_indicator(loc_str: str) -> bool:
    """Checks if a location string explicitly indicates a US state, country, or global-remote open to US."""
    loc_lower = (loc_str or "").lower()
    if any(u in loc_lower for u in [
        "united states", "usa", "u.s.", "us remote", "remote in usa", "remote - us",
        "remote (us", "north america", "worldwide", "global", "americas", "anywhere"
    ]):
        return True
    # Check for ", XX" two-letter US state code (e.g. "San Francisco, CA" or "Austin, TX")
    for m in re.finditer(r',\s*([a-z]{2})\b', loc_lower):
        if m.group(1) in _US_STATE_CODES:
            return True
    return False

def _matches_target_location(
    job_location: str,
    target_location: Optional[str],
    is_remote: bool,
    include_remote: bool = True,
    radius: Optional[int] = 50,
    workplace_type: str = "",
    title: str = ""
) -> bool:
    """Filters listings with distance radius matching and ensures hybrid/onsite jobs outside target range are excluded."""
    return is_job_in_range(
        job_location=job_location,
        target_location=target_location,
        radius_miles=radius,
        workplace_type=workplace_type,
        is_remote=is_remote,
        include_remote=include_remote,
        title=title
    )

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
        if marker in full_header or marker in (text or "")[:400].lower():
            return False

    # 2. Check structured location restrictions (e.g. Himalayas, SimplifyJobs)
    if location_list is not None and len(location_list) > 0:
        locs_lower = [str(l).lower() for l in location_list]
        has_us = any(_has_us_indicator(l) for l in locs_lower)
        if not has_us:
            return False

    # 3. Check location string for explicit foreign exclusivity
    explicit_foreign_regions = [
        "europe only", "eu only", "uk only", "emea only", "apac only", "latam only",
        "remote in uk", "remote - uk", "united kingdom", ", uk", "(uk)",
        "canada", "toronto", "vancouver", "montreal", "waterloo", "ottawa", "calgary",
        "germany", "deutschland", "berlin", "munich", "frankfurt", "london", "bristol",
        "slough", "cambridge, uk", "manchester, uk", "edinburgh", "belfast",
        "ireland", "dublin", "paris", "france", "madrid", "barcelona", "spain",
        "tokyo", "japan", "singapore", "brazil", "brasil", "são paulo", "portugal", "lisbon",
        "india", "bangalore", "bengaluru", "mumbai", "hyderabad", "pune", "chennai", "gurugram", "noida",
        "sydney", "melbourne", "australia", "new south wales", ", aus",
        "netherlands", "amsterdam", "poland", "warsaw", "krakow", "wroclaw",
        "israel", "tel aviv", "yokneam", "haifa", "romania", "bucharest",
        "mexico", "mexico city", "guadalajara", "monterrey", "argentina", "buenos aires",
        "colombia", "bogota", "chile", "santiago", "korea", "seoul", "taiwan", "taipei",
        "china", "beijing", "shanghai", "shenzhen", "hong kong", "switzerland", "zurich",
        "sweden", "stockholm", "austria", "vienna", "belgium", "brussels", "italy", "milan",
        "czech", "prague", "hungary", "budapest", "uae", "dubai", "philippines", "manila",
    ]
    for region in explicit_foreign_regions:
        if region in loc_lower:
            # If it doesn't also explicitly state a US state or US / Worldwide / Americas / Anywhere, reject
            if not _has_us_indicator(loc_lower):
                return False

    # Check word-boundary 'uk' so 'Luke' or 'Duke' is not rejected, but 'London, UK' or 'UK Remote' is
    if re.search(r'\buk\b', loc_lower) and not _has_us_indicator(loc_lower):
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
    # Tier 2 / Level 2 support and technician roles are early-career (1-2 years) and should not be treated as high-level senior
    is_early_support_tier = bool(
        re.search(r'\b(support|help\s*desk|technician|service\s*desk|desktop)\b', t) and
        re.search(r'\b(?:tier|level)?\s*(?:ii|2)\b', t)
    )
    if not is_early_support_tier:
        if re.search(r'\b(iii|iv|v|vi)\b', t):
            return True
        if re.search(
            r'\b(?:engineer|developer|programmer|analyst|specialist|scientist|technician|level|tier|swe|sde)\s*(?:-\s*)?(?:3|4|5|6)\b',
            t
        ):
            return True
    else:
        if re.search(r'\b(?:tier|level)\s*(?:iii|3|4|5)\b', t):
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
    if (salary_min and salary_min >= 160000) or (salary_max and salary_max >= 185000):
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

    # Entry-level compensation band signal when job title is clearly a technical, IT, or software role
    is_tech_title = bool(
        re.search(r'\b(developer|engineer|programmer|software|web|frontend|front-end|backend|back-end|full[\s-]stack|data|analyst|qa|devops|cloud|cyber|security|it|systems|network|ai|ml|support|technician|administrator|helpdesk|desktop)\b', (title or "").lower())
    )
    if is_tech_title:
        if salary_max and 40000 <= salary_max <= 95000:
            return True
        if salary_min and 40000 <= salary_min <= 85000 and (not salary_max or salary_max <= 105000):
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

    # Word boundary match for short tokens (<= 4 chars, e.g. ui, ai, ml, go, jr, sr, c++, sql, aws, it, soc, noc)
    if len(t) <= 4:
        if re.search(r'(?:\b|(?<=\s))' + re.escape(t) + r'(?:\b|(?=\s))', full_text):
            return True
    else:
        if t in full_text:
            return True
        # Basic plural/singular stem matching (e.g. "solutions" -> "solution", "cloud" -> "clouds")
        if t.endswith('s') and t[:-1] in full_text:
            return True
        if not t.endswith('s') and (t + 's') in full_text:
            return True

    synonym_groups = [
        {
            "solutions engineer", "solutionsengineer", "solution engineer", "solutions consultant",
            "solution consultant", "technical solutions engineer", "technical solutions consultant",
            "sales engineer", "presales engineer", "pre-sales engineer", "customer solutions engineer",
            "solutions specialist", "solution architect", "solutions architect"
        },
        {"developer", "engineer", "dev", "programmer", "software", "coder", "architect", "engineering", "development"},
        {"senior", "sr", "lead", "principal", "staff"},
        {"frontend", "front-end", "ui", "react", "vue", "angular", "javascript", "typescript"},
        {"backend", "back-end", "api", "server", "django", "fastapi", "nodejs", "node.js"},
        {"fullstack", "full-stack", "full stack"},
        {"devops", "sre", "infrastructure", "cloud", "aws", "kubernetes", "docker", "platform"},
        {"data", "machine learning", "ml", "ai", "data engineer", "data scientist", "analytics", "analyst", "etl"},
        {"remote", "wfh", "work from home", "anywhere", "telecommute"},
        {"it support", "itsupport", "technical support", "tech support", "help desk", "helpdesk", "desktop support", "desktopsupport", "field technician", "it technician", "support specialist", "endpoint support", "service desk"},
        {"sysadmin", "systems administrator", "system administrator", "systems admin", "system admin", "endpoint administrator", "it administrator", "windows administrator"},
        {"network", "network technician", "network administrator", "network specialist", "noc technician", "noc", "network engineer", "networking"},
        {"cybersecurity", "cyber security", "soc analyst", "soc", "security analyst", "information security", "infosec", "threat analyst"},
        {"hardware technician", "repair technician", "service technician", "pcb", "diagnostic technician"},
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
    normalized_q = re.sub(r'\bit[\s-]+support\b', 'itsupport', normalized_q)
    normalized_q = re.sub(r'\btech(?:nical)?[\s-]+support\b', 'itsupport', normalized_q)
    normalized_q = re.sub(r'\bhelp[\s-]+desk\b', 'helpdesk', normalized_q)
    normalized_q = re.sub(r'\bdesktop[\s-]+support\b', 'desktopsupport', normalized_q)
    normalized_q = re.sub(r'\bsystems?[\s-]+admin(?:istrator)?\b', 'sysadmin', normalized_q)
    normalized_q = re.sub(r'\bnetwork[\s-]+(?:technician|admin(?:istrator)?|engineer)\b', 'network', normalized_q)
    normalized_q = re.sub(r'\bcyber[\s-]+security\b', 'cybersecurity', normalized_q)
    normalized_q = re.sub(r'\bsoc[\s-]+analyst\b', 'soc', normalized_q)
    normalized_q = re.sub(r'\bsolutions?[\s-]+engineers?\b', 'solutionsengineer', normalized_q)
    normalized_q = re.sub(r'\bsolutions?[\s-]+consultants?\b', 'solutionsengineer', normalized_q)
    normalized_q = re.sub(r'\bsales[\s-]+engineers?\b', 'solutionsengineer', normalized_q)
    normalized_q = re.sub(r'\bpre[\s-]?sales[\s-]+engineers?\b', 'solutionsengineer', normalized_q)
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

            t1 = asyncio.to_thread(_scrape_indeed_sync, q1, loc_str, is_remote_query, 45, distance_val)
            t2 = asyncio.to_thread(_scrape_indeed_sync, q2, loc_str, is_remote_query, 45, distance_val)
            t3 = asyncio.to_thread(_scrape_indeed_sync, q3, loc_str, is_remote_query, 35, distance_val)
            res = await asyncio.gather(t1, t2, t3, return_exceptions=True)
            raw_jobs = []
            for r in res:
                if isinstance(r, list):
                    raw_jobs.extend(r)
        else:
            # Include a concurrent entry-level batch so general searches also surface entry-level opportunities
            t1 = asyncio.to_thread(_scrape_indeed_sync, search_term, loc_str, is_remote_query, 50, distance_val)
            t2 = asyncio.to_thread(_scrape_indeed_sync, f'"entry level" {search_term}', loc_str, is_remote_query, 30, distance_val)
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
            t1 = asyncio.to_thread(_scrape_ziprecruiter_sync, search_term, us_only, is_remote_query, 3, location, radius)
            t2 = asyncio.to_thread(_scrape_ziprecruiter_sync, f"entry level {search_term}", us_only, is_remote_query, 2, location, radius)
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
    radius: Optional[int] = None,
    min_salary: Optional[float] = None
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
        "results_per_page": 100,
        "what": search_query,
        "content-type": "application/json",
    }
    if min_salary and min_salary > 0:
        params["salary_min"] = int(min_salary)
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

# 10. LinkedIn & Glassdoor (Direct Scrapers via JobSpy)
def _scrape_jobspy_board_sync(
    site_name: str,
    search_term: str,
    location: str,
    is_remote: bool = False,
    results_wanted: int = 30,
    distance: Optional[int] = None
) -> List[Dict[str, Any]]:
    """Synchronous worker that scrapes LinkedIn or Glassdoor via JobSpy with location & radius distance."""
    try:
        from jobspy import scrape_jobs
        scrape_kwargs: Dict[str, Any] = {
            "site_name": [site_name],
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

        clean_q = re.sub(r"\b(remote|wfh|work from home)\b", "", search_term, flags=re.I).strip()
        q_tokens = [tok.lower() for tok in re.split(r'\W+', clean_q) if len(tok) > 1]

        jobs_list = []
        for _, row in df.iterrows():
            title = str(row.get("title") or "").strip()
            company = str(row.get("company") or "").strip()
            loc = str(row.get("location") or "USA").strip()
            url = str(row.get("job_url") or "").strip()
            if not title or not url or title.lower() == "nan" or url.lower() == "nan":
                continue
            if company.lower() == "nan" or not company:
                company = f"{site_name.capitalize()} Employer"
            if loc.lower() == "nan" or not loc:
                loc = "Remote" if is_remote else "USA"

            raw_desc = str(row.get("description") or "").strip()
            desc = clean_html(raw_desc) if raw_desc and raw_desc.lower() != "nan" else ""

            min_sal = float(row.get("min_amount")) if row.get("min_amount") is not None and str(row.get("min_amount")) != "nan" else None
            max_sal = float(row.get("max_amount")) if row.get("max_amount") is not None and str(row.get("max_amount")) != "nan" else None
            if min_sal and min_sal < 200:
                min_sal = round(min_sal * 2080, 2)
            if max_sal and max_sal < 200:
                max_sal = round(max_sal * 2080, 2)

            job_is_remote = bool(row.get("is_remote", False)) or "remote" in loc.lower() or is_remote
            tags = [site_name, "direct-hire"]
            if job_is_remote:
                tags.append("remote")

            if not _is_senior_or_mid_title(title):
                for tok in q_tokens:
                    if tok not in tags:
                        tags.append(tok)
                if not desc:
                    desc = f"{title} ({loc}) at {company}. Matched search criteria: {clean_q}. Full listing available on {site_name.capitalize()}."
            elif not desc:
                desc = f"{title} ({loc}) at {company}. Full listing available on {site_name.capitalize()}."

            jobs_list.append({
                "title": title,
                "company": company,
                "location": "Remote" if job_is_remote and loc in ("", "USA") else loc,
                "workplace_type": "remote" if job_is_remote else "hybrid",
                "url": url,
                "salary_min": min_sal,
                "salary_max": max_sal,
                "salary_currency": str(row.get("currency") or "USD") if str(row.get("currency")) != "nan" else "USD",
                "tags": tags,
                "description": desc,
                "source": site_name,
            })
        return jobs_list
    except Exception as e:
        logger.warning(f"Error in {site_name} JobSpy scraper: {e}")
        return []

async def _fetch_jobspy_board_jobs(
    site_name: str,
    query: Optional[str] = None,
    us_only: bool = True,
    location: Optional[str] = None,
    radius: Optional[int] = None
) -> List[Dict[str, Any]]:
    """Generic async wrapper for LinkedIn and Glassdoor JobSpy scrapers with entry-level query expansion."""
    q_lower = (query or "").lower().strip()
    is_remote_query = any(w in q_lower for w in ("remote", "wfh", "work from home"))
    is_junior_query = any(w in q_lower for w in ("junior", "jr", "entry", "entry-level", "associate", "intern", "new grad"))

    clean_term = re.sub(r"\b(remote|wfh|work from home)\b", "", q_lower, flags=re.I).strip()
    clean_term = re.sub(r"[/,()+-]", " ", clean_term)
    clean_term = " ".join(clean_term.split())
    search_term = clean_term if clean_term else "Software Engineer"

    core_term = re.sub(
        r"\b(junior|jr|entry\s+level|entry|associate|new\s+grad|early\s+career|intern|internship|level)\b",
        "",
        clean_term,
        flags=re.I
    )
    core_term = " ".join(core_term.split()).strip() or "software engineer"

    target_loc = location.strip() if location and location.strip() else None
    if is_remote_query:
        loc_str = "United States"
    elif target_loc:
        loc_str = target_loc
    else:
        loc_str = "United States" if us_only else "Remote"

    distance_val = radius if (target_loc and radius) else (50 if target_loc else None)

    try:
        if is_junior_query:
            q1 = f"entry level {core_term}"
            q2 = f"junior {core_term}"
            t1 = asyncio.to_thread(_scrape_jobspy_board_sync, site_name, q1, loc_str, is_remote_query, 35, distance_val)
            t2 = asyncio.to_thread(_scrape_jobspy_board_sync, site_name, q2, loc_str, is_remote_query, 35, distance_val)
            res = await asyncio.gather(t1, t2, return_exceptions=True)
        else:
            t1 = asyncio.to_thread(_scrape_jobspy_board_sync, site_name, search_term, loc_str, is_remote_query, 45, distance_val)
            t2 = asyncio.to_thread(_scrape_jobspy_board_sync, site_name, f"associate {search_term}", loc_str, is_remote_query, 25, distance_val)
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
        logger.warning(f"Error fetching {site_name} jobs: {e}")
        return []

async def fetch_linkedin_jobs(
    query: Optional[str] = None,
    us_only: bool = True,
    location: Optional[str] = None,
    radius: Optional[int] = None
) -> List[Dict[str, Any]]:
    """Fetch live US listings from LinkedIn via JobSpy."""
    return await _fetch_jobspy_board_jobs("linkedin", query=query, us_only=us_only, location=location, radius=radius)

async def fetch_glassdoor_jobs(
    query: Optional[str] = None,
    us_only: bool = True,
    location: Optional[str] = None,
    radius: Optional[int] = None
) -> List[Dict[str, Any]]:
    """Fetch live US listings with salary data from Glassdoor via JobSpy."""
    return await _fetch_jobspy_board_jobs("glassdoor", query=query, us_only=us_only, location=location, radius=radius)


# 11. The Muse Public API (Zero-Auth JSON API with Native Experience Level & Tech Categories)
async def fetch_themuse_jobs(
    query: Optional[str] = None,
    us_only: bool = True,
    location: Optional[str] = None,
    include_remote: bool = True
) -> List[Dict[str, Any]]:
    """Fetch curated tech & engineering listings from The Muse public API."""
    q_lower = (query or "").lower().strip()
    is_junior_q = any(w in q_lower for w in ("junior", "jr", "entry", "entry-level", "associate", "intern", "new grad", "early career"))
    is_senior_q = any(w in q_lower for w in ("senior", "sr", "staff", "principal", "lead"))

    base_url = "https://www.themuse.com/api/public/jobs"
    categories = ["Software Engineering", "Data and Analytics", "IT", "Computer and IT"]

    params_list = []
    if is_junior_q:
        for lvl in ("Entry Level", "Internship"):
            params_list.append([("category", c) for c in categories] + [("level", lvl), ("page", "1")])
    elif is_senior_q:
        params_list.append([("category", c) for c in categories] + [("level", "Senior Level"), ("page", "1")])
    else:
        params_list.append([("category", c) for c in categories] + [("page", "1")])
        params_list.append([("category", c) for c in categories] + [("level", "Entry Level"), ("page", "1")])

    results = []
    seen = set()
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            responses = await asyncio.gather(
                *[client.get(base_url, params=p, headers=HEADERS) for p in params_list],
                return_exceptions=True
            )
            for resp in responses:
                if isinstance(resp, Exception) or resp.status_code != 200:
                    continue
                items = resp.json().get("results", [])
                for item in items:
                    title = (item.get("name") or "").strip()
                    company = (item.get("company", {}) or {}).get("name", "The Muse Employer").strip()
                    if not title:
                        continue
                    key = f"{title.lower()}|{company.lower()}"
                    if key in seen:
                        continue

                    locs = [l.get("name", "") for l in (item.get("locations") or []) if l.get("name")]
                    loc_str = ", ".join(locs) if locs else "United States"
                    is_remote = any("remote" in l.lower() or "flexible" in l.lower() for l in locs) or "remote" in title.lower()

                    levels = [lv.get("name", "") for lv in (item.get("levels") or []) if lv.get("name")]
                    cats = [ct.get("name", "") for ct in (item.get("categories") or []) if ct.get("name")]
                    tags = ["themuse"] + [lv.lower() for lv in levels] + [ct.lower() for ct in cats[:2]]
                    if is_remote:
                        tags.append("remote")

                    desc = clean_html(item.get("contents", ""))
                    if levels:
                        desc = f"Experience Level: {', '.join(levels)}. {desc}"

                    apply_url = (item.get("refs", {}) or {}).get("landing_page", "")
                    if not apply_url:
                        continue

                    if us_only and not is_us_eligible(location=loc_str, title=title, text=desc, location_list=locs if locs else None):
                        continue
                    if not _matches_target_location(loc_str, location, is_remote, include_remote):
                        continue
                    if not matches_query(query, title, company, tags, desc, location=loc_str, workplace_type="remote" if is_remote else "hybrid"):
                        continue

                    seen.add(key)
                    results.append({
                        "title": title,
                        "company": company,
                        "location": "Remote (USA)" if is_remote and "flexible" in loc_str.lower() else loc_str,
                        "workplace_type": "remote" if is_remote else "hybrid",
                        "url": apply_url,
                        "salary_min": None,
                        "salary_max": None,
                        "salary_currency": "USD",
                        "tags": tags[:6],
                        "description": desc[:6000],
                        "source": "themuse",
                    })
                    if len(results) >= 60:
                        break
    except Exception as e:
        logger.warning(f"Error fetching The Muse jobs: {e}")
    return results


# 12. SimplifyJobs Curated Entry-Level / New-Grad & Internship GitHub Feeds
_SIMPLIFY_CACHE: Dict[str, Any] = {"timestamp": 0.0, "newgrad": [], "internship": []}

async def fetch_simplify_jobs(
    query: Optional[str] = None,
    us_only: bool = True,
    location: Optional[str] = None,
    include_remote: bool = True
) -> List[Dict[str, Any]]:
    """Fetch curated active US Entry-Level, New-Grad & Internship tech roles from SimplifyJobs GitHub JSON feeds."""
    import time
    now = time.time()
    newgrad_url = "https://raw.githubusercontent.com/SimplifyJobs/New-Grad-Positions/dev/.github/scripts/listings.json"
    intern_url = "https://raw.githubusercontent.com/SimplifyJobs/Summer2026-Internships/dev/.github/scripts/listings.json"

    q_lower = (query or "").lower().strip()
    want_internships = any(w in q_lower for w in ("intern", "internship", "co-op"))

    try:
        if now - _SIMPLIFY_CACHE["timestamp"] > 300 or not _SIMPLIFY_CACHE["newgrad"]:
            async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
                r_ng, r_in = await asyncio.gather(
                    client.get(newgrad_url, headers=HEADERS),
                    client.get(intern_url, headers=HEADERS),
                    return_exceptions=True
                )
                if not isinstance(r_ng, Exception) and r_ng.status_code == 200:
                    ng_data = [x for x in r_ng.json() if isinstance(x, dict) and x.get("active") and x.get("is_visible", True)]
                    ng_data.sort(key=lambda x: x.get("date_posted", 0), reverse=True)
                    _SIMPLIFY_CACHE["newgrad"] = ng_data
                if not isinstance(r_in, Exception) and r_in.status_code == 200:
                    in_data = [x for x in r_in.json() if isinstance(x, dict) and x.get("active") and x.get("is_visible", True)]
                    in_data.sort(key=lambda x: x.get("date_posted", 0), reverse=True)
                    _SIMPLIFY_CACHE["internship"] = in_data
                if _SIMPLIFY_CACHE["newgrad"] or _SIMPLIFY_CACHE["internship"]:
                    _SIMPLIFY_CACHE["timestamp"] = now

        pool = list(_SIMPLIFY_CACHE["newgrad"])
        if want_internships:
            pool = list(_SIMPLIFY_CACHE["internship"]) + pool
        else:
            pool = pool + list(_SIMPLIFY_CACHE["internship"][:150])

        results = []
        seen = set()
        for item in pool:
            title = (item.get("title") or "").strip()
            company = (item.get("company_name") or "").strip()
            apply_url = (item.get("url") or "").strip()
            if not title or not company or not apply_url:
                continue

            key = f"{title.lower()}|{company.lower()}"
            if key in seen:
                continue

            locs = [str(l).strip() for l in (item.get("locations") or []) if l]
            loc_str = ", ".join(locs) if locs else "United States"
            is_remote = any("remote" in l.lower() for l in locs) or "remote" in title.lower()

            category = (item.get("category") or "Software").strip()
            sponsorship = (item.get("sponsorship") or "").strip()
            degrees = [str(d) for d in (item.get("degrees") or []) if d]

            tags = ["simplify", "new-grad", "entry-level", category.lower()]
            if is_remote:
                tags.append("remote")

            desc = (
                f"Entry-Level / New Grad {title} ({category} Engineering / Tech) at {company} in {loc_str}. "
                f"Target degrees: {', '.join(degrees) if degrees else 'BS/MS'}. "
                f"{f'Sponsorship: {sponsorship}. ' if sponsorship else ''}"
                f"Curated active early-career software & tech opening via SimplifyJobs."
            )

            if us_only and not is_us_eligible(location=loc_str, title=title, text=desc, location_list=locs if locs else None):
                continue
            if not _matches_target_location(loc_str, location, is_remote, include_remote):
                continue
            if not matches_query(query, title, company, tags, desc, location=loc_str, workplace_type="remote" if is_remote else "hybrid"):
                continue

            seen.add(key)
            results.append({
                "title": title,
                "company": company,
                "location": loc_str,
                "workplace_type": "remote" if is_remote else "hybrid",
                "url": apply_url,
                "salary_min": None,
                "salary_max": None,
                "salary_currency": "USD",
                "tags": tags,
                "description": desc,
                "source": "simplify",
            })
            if len(results) >= 80:
                break
        return results
    except Exception as e:
        logger.warning(f"Error fetching SimplifyJobs feed: {e}")
        return []


# 13. Direct Multi-Company ATS Boards (Greenhouse, Ashby, Lever for 25+ Top Tech Companies)
GREENHOUSE_COMPANIES = [
    ("anthropic", "Anthropic"),
    ("stripe", "Stripe"),
    ("cloudflare", "Cloudflare"),
    ("databricks", "Databricks"),
    ("vercel", "Vercel"),
    ("coinbase", "Coinbase"),
    ("discord", "Discord"),
    ("reddit", "Reddit"),
    ("robinhood", "Robinhood"),
    ("pinterest", "Pinterest"),
    ("figma", "Figma"),
    ("airbnb", "Airbnb"),
    ("gitlab", "GitLab"),
    ("duolingo", "Duolingo"),
    ("twilio", "Twilio"),
    ("scaleai", "Scale AI"),
]

ASHBY_COMPANIES = [
    ("openai", "OpenAI"),
    ("ramp", "Ramp"),
    ("linear", "Linear"),
    ("notion", "Notion"),
    ("plaid", "Plaid"),
    ("supabase", "Supabase"),
    ("posthog", "PostHog"),
]

LEVER_COMPANIES = [
    ("palantir", "Palantir"),
    ("zoox", "Zoox"),
]

_COMPANY_BOARDS_CACHE: Dict[str, Any] = {"timestamp": 0.0, "jobs": []}

async def _fetch_single_greenhouse_board(client: httpx.AsyncClient, slug: str, company_name: str) -> List[Dict[str, Any]]:
    url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
    out = []
    try:
        resp = await client.get(url)
        if resp.status_code == 200:
            for j in resp.json().get("jobs", []):
                title = (j.get("title") or "").strip()
                loc = (j.get("location", {}) or {}).get("name", "United States") or "United States"
                apply_url = (j.get("absolute_url") or "").strip()
                if not title or not apply_url:
                    continue
                depts = [d.get("name", "") for d in (j.get("departments") or []) if isinstance(d, dict) and d.get("name")]
                is_remote = "remote" in loc.lower() or "remote" in title.lower() or "anywhere" in loc.lower()
                tags = ["company_boards", "greenhouse", slug] + [d.lower() for d in depts[:2]]
                if is_remote:
                    tags.append("remote")
                desc = f"{title} at {company_name} ({loc}). Department: {', '.join(depts) if depts else 'Engineering & Tech'}."
                out.append({
                    "title": title,
                    "company": company_name,
                    "location": loc,
                    "workplace_type": "remote" if is_remote else "hybrid",
                    "url": apply_url,
                    "salary_min": None,
                    "salary_max": None,
                    "salary_currency": "USD",
                    "tags": tags[:6],
                    "description": desc,
                    "source": "company_boards",
                })
    except Exception as e:
        logger.debug(f"Greenhouse board {slug} error: {e}")
    return out

async def _fetch_single_ashby_board(client: httpx.AsyncClient, slug: str, company_name: str) -> List[Dict[str, Any]]:
    url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true"
    out = []
    try:
        resp = await client.get(url)
        if resp.status_code == 200:
            for j in resp.json().get("jobs", []):
                if not j.get("isListed", True):
                    continue
                title = (j.get("title") or "").strip()
                loc = (j.get("location") or "United States").strip()
                apply_url = (j.get("jobUrl") or j.get("applyUrl") or "").strip()
                if not title or not apply_url:
                    continue
                dept = (j.get("department") or "").strip()
                team = (j.get("team") or "").strip()
                is_remote = bool(j.get("isRemote")) or str(j.get("workplaceType") or "").lower() == "remote" or "remote" in loc.lower()

                sal_min = None
                sal_max = None
                comp = j.get("compensation") or {}
                for sc in (comp.get("summaryComponents") or []):
                    if sc.get("compensationType") == "Salary":
                        if sc.get("minValue"):
                            sal_min = float(sc["minValue"])
                        if sc.get("maxValue"):
                            sal_max = float(sc["maxValue"])
                        break

                tags = ["company_boards", "ashby", slug]
                if dept:
                    tags.append(dept.lower())
                if is_remote:
                    tags.append("remote")

                plain = (j.get("descriptionPlain") or "").strip()
                desc = plain[:4000] if plain else f"{title} at {company_name} ({loc}). {dept} {team}."

                out.append({
                    "title": title,
                    "company": company_name,
                    "location": loc,
                    "workplace_type": "remote" if is_remote else "hybrid",
                    "url": apply_url,
                    "salary_min": sal_min,
                    "salary_max": sal_max,
                    "salary_currency": "USD",
                    "tags": tags[:6],
                    "description": desc,
                    "source": "company_boards",
                })
    except Exception as e:
        logger.debug(f"Ashby board {slug} error: {e}")
    return out

async def _fetch_single_lever_board(client: httpx.AsyncClient, slug: str, company_name: str) -> List[Dict[str, Any]]:
    url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
    out = []
    try:
        resp = await client.get(url)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list):
                for j in data:
                    title = (j.get("text") or "").strip()
                    cats = j.get("categories") or {}
                    loc = (cats.get("location") or "United States").strip()
                    team = (cats.get("team") or "").strip()
                    apply_url = (j.get("hostedUrl") or j.get("applyUrl") or "").strip()
                    if not title or not apply_url:
                        continue
                    is_remote = str(j.get("workplaceType") or "").lower() == "remote" or "remote" in loc.lower()
                    tags = ["company_boards", "lever", slug]
                    if team:
                        tags.append(team.lower())
                    if is_remote:
                        tags.append("remote")
                    plain = (j.get("descriptionPlain") or "").strip()
                    desc = plain[:4000] if plain else f"{title} at {company_name} ({loc}). {team}."
                    out.append({
                        "title": title,
                        "company": company_name,
                        "location": loc,
                        "workplace_type": "remote" if is_remote else "hybrid",
                        "url": apply_url,
                        "salary_min": None,
                        "salary_max": None,
                        "salary_currency": "USD",
                        "tags": tags[:6],
                        "description": desc,
                        "source": "company_boards",
                    })
    except Exception as e:
        logger.debug(f"Lever board {slug} error: {e}")
    return out

async def fetch_company_boards_jobs(
    query: Optional[str] = None,
    us_only: bool = True,
    location: Optional[str] = None,
    include_remote: bool = True
) -> List[Dict[str, Any]]:
    """Fetch jobs directly from 25+ top tech companies' Greenhouse, Ashby, and Lever ATS boards."""
    import time
    now = time.time()
    headers = {"Accept-Encoding": "gzip, deflate", "User-Agent": HEADERS["User-Agent"]}

    try:
        if now - _COMPANY_BOARDS_CACHE["timestamp"] > 300 or not _COMPANY_BOARDS_CACHE["jobs"]:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True, headers=headers) as client:
                board_tasks = (
                    [_fetch_single_greenhouse_board(client, s, n) for s, n in GREENHOUSE_COMPANIES]
                    + [_fetch_single_ashby_board(client, s, n) for s, n in ASHBY_COMPANIES]
                    + [_fetch_single_lever_board(client, s, n) for s, n in LEVER_COMPANIES]
                )
                board_results = await asyncio.gather(*board_tasks, return_exceptions=True)
                all_board_jobs = []
                for br in board_results:
                    if isinstance(br, list):
                        all_board_jobs.extend(br)
                if all_board_jobs:
                    _COMPANY_BOARDS_CACHE["jobs"] = all_board_jobs
                    _COMPANY_BOARDS_CACHE["timestamp"] = now

        q_lower = (query or "").lower().strip()
        all_company_names = [n.lower() for _, n in GREENHOUSE_COMPANIES + ASHBY_COMPANIES + LEVER_COMPANIES]
        is_specific_company_q = any(c in q_lower for c in all_company_names)
        max_per_company = 60 if is_specific_company_q else 8

        company_counts: Dict[str, int] = {}
        results = []

        for j in _COMPANY_BOARDS_CACHE["jobs"]:
            comp = j["company"]
            if company_counts.get(comp, 0) >= max_per_company:
                continue
            if us_only and not is_us_eligible(location=j["location"], title=j["title"], text=j["description"]):
                continue
            is_rem = j["workplace_type"] == "remote" or "remote" in j["location"].lower()
            if not _matches_target_location(j["location"], location, is_rem, include_remote):
                continue
            if not matches_query(
                query, j["title"], comp, j["tags"], j["description"],
                location=j["location"], workplace_type=j["workplace_type"],
                salary_min=j.get("salary_min"), salary_max=j.get("salary_max")
            ):
                continue

            company_counts[comp] = company_counts.get(comp, 0) + 1
            results.append(j)
            if len(results) >= 120:
                break

        return results
    except Exception as e:
        logger.warning(f"Error fetching company boards jobs: {e}")
        return []


# 14. Direct Big Tech Career Portals (Google, Microsoft, Amazon, Apple, Netflix, NVIDIA, Salesforce)
def _clean_bigtech_query(query: Optional[str], company_name: str) -> str:
    """Strips the company's own name and 'remote' from the search term sent to a single-company portal."""
    q = (query or "").lower().strip()
    q = re.sub(r"\b" + re.escape(company_name.lower()) + r"\b", "", q, flags=re.I)
    q = re.sub(r"\b(remote|wfh|work from home)\b", "", q, flags=re.I)
    q = re.sub(r"[/,()+-]", " ", q)
    q = " ".join(q.split()).strip()
    return q if q else "software engineer"

async def _fetch_amazon_careers(client: httpx.AsyncClient, query: Optional[str], us_only: bool, location: Optional[str]) -> List[Dict[str, Any]]:
    search_q = _clean_bigtech_query(query, "amazon")
    loc_q = location.strip() if location and location.strip() else "United States"
    url = "https://www.amazon.jobs/en/search.json"
    params = {"base_query": search_q, "loc_query": loc_q, "result_limit": 25}
    out = []
    try:
        resp = await client.get(url, params=params)
        if resp.status_code == 200:
            for j in resp.json().get("jobs", []):
                if us_only and j.get("country_code") not in ("USA", "US", None):
                    continue
                title = (j.get("title") or "").strip()
                loc = (j.get("normalized_location") or j.get("location") or "United States").strip()
                path = (j.get("job_path") or "").strip()
                if not title or not path:
                    continue
                apply_url = f"https://www.amazon.jobs{path}" if path.startswith("/") else path
                desc_parts = [
                    clean_html(j.get("description_short") or ""),
                    clean_html(j.get("basic_qualifications") or ""),
                    clean_html(j.get("preferred_qualifications") or ""),
                ]
                desc = " ".join(p for p in desc_parts if p).strip()
                is_remote = "remote" in loc.lower() or "virtual" in loc.lower() or "remote" in title.lower()
                tags = ["bigtech", "amazon", "direct-hire"]
                if j.get("university_job") or j.get("is_intern"):
                    tags.append("entry-level")
                if is_remote:
                    tags.append("remote")
                out.append({
                    "title": title,
                    "company": "Amazon",
                    "location": loc,
                    "workplace_type": "remote" if is_remote else "hybrid",
                    "url": apply_url,
                    "salary_min": None,
                    "salary_max": None,
                    "salary_currency": "USD",
                    "tags": tags,
                    "description": desc or f"{title} at Amazon ({loc}).",
                    "source": "bigtech",
                })
    except Exception as e:
        logger.debug(f"Amazon careers error: {e}")
    return out

async def _fetch_microsoft_careers(query: Optional[str], us_only: bool, location: Optional[str]) -> List[Dict[str, Any]]:
    search_q = _clean_bigtech_query(query, "microsoft")
    loc_q = location.strip() if location and location.strip() else ("United States" if us_only else "")
    out = []
    try:
        ms_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Referer": "https://apply.careers.microsoft.com/careers",
            "Accept-Encoding": "gzip, deflate",
        }
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True, headers=ms_headers) as client:
            await client.get("https://apply.careers.microsoft.com/careers")
            resp = await client.get(
                "https://apply.careers.microsoft.com/api/pcsx/search",
                params={"domain": "microsoft.com", "query": search_q, "location": loc_q, "start": 0}
            )
            if resp.status_code == 200:
                positions = (resp.json().get("data") or {}).get("positions") or []
                for p in positions:
                    title = (p.get("name") or "").strip()
                    locs = p.get("standardizedLocations") or p.get("locations") or ["Redmond, WA, US"]
                    loc = ", ".join(str(l) for l in locs[:2] if l)
                    pos_url = (p.get("positionUrl") or "").strip()
                    if not title or not pos_url:
                        continue
                    apply_url = f"https://apply.careers.microsoft.com{pos_url}" if pos_url.startswith("/") else pos_url
                    work_opt = str(p.get("workLocationOption") or "").lower()
                    is_remote = work_opt == "remote" or "remote" in loc.lower() or "remote" in title.lower()
                    dept = (p.get("department") or "Software Engineering").strip()
                    tags = ["bigtech", "microsoft", dept.lower()]
                    if is_remote:
                        tags.append("remote")
                    out.append({
                        "title": title,
                        "company": "Microsoft",
                        "location": loc,
                        "workplace_type": "remote" if is_remote else ("onsite" if work_opt == "onsite" else "hybrid"),
                        "url": apply_url,
                        "salary_min": None,
                        "salary_max": None,
                        "salary_currency": "USD",
                        "tags": tags,
                        "description": f"{title} ({dept}) at Microsoft in {loc}. Matched search: {search_q}.",
                        "source": "bigtech",
                    })
    except Exception as e:
        logger.debug(f"Microsoft careers error: {e}")
    return out

async def _fetch_google_careers(client: httpx.AsyncClient, query: Optional[str], us_only: bool, location: Optional[str]) -> List[Dict[str, Any]]:
    search_q = _clean_bigtech_query(query, "google")
    loc_q = location.strip() if location and location.strip() else ("United States" if us_only else "")
    params: List[ Any ] = [("q", search_q)]
    if loc_q:
        params.append(("location", loc_q))
    q_lower = (query or "").lower()
    if any(w in q_lower for w in ("junior", "jr", "entry", "new grad", "associate", "early")):
        params.append(("target_level", "EARLY"))
        params.append(("target_level", "INTERN_AND_APPRENTICE"))

    out = []
    try:
        resp = await client.get("https://www.google.com/about/careers/applications/jobs/results/", params=params)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            for li in soup.find_all("li"):
                a = li.find("a", href=re.compile(r"^jobs/results/\d+"))
                if not a:
                    continue
                h3 = li.find("h3")
                title = h3.get_text(strip=True) if h3 else ""
                if not title:
                    continue
                href = a["href"]
                apply_url = f"https://www.google.com/about/careers/applications/{href}"
                card_text = li.get_text(" | ", strip=True)
                loc_match = re.search(r"place\s*\|\s*([^|]+)", card_text)
                loc = loc_match.group(1).strip() if loc_match else (loc_q or "United States")
                lvl_match = re.search(r"bar_chart\s*\|\s*([^|]+)", card_text)
                lvl = lvl_match.group(1).strip() if lvl_match else ""
                is_remote = "remote" in loc.lower() or "remote" in title.lower()
                tags = ["bigtech", "google", "direct-hire"]
                if lvl:
                    tags.append(lvl.lower())
                if is_remote:
                    tags.append("remote")
                out.append({
                    "title": title,
                    "company": "Google",
                    "location": loc,
                    "workplace_type": "remote" if is_remote else "hybrid",
                    "url": apply_url,
                    "salary_min": None,
                    "salary_max": None,
                    "salary_currency": "USD",
                    "tags": tags,
                    "description": f"{title} at Google ({loc}). Level: {lvl or 'Engineering'}. {card_text[:600]}",
                    "source": "bigtech",
                })
    except Exception as e:
        logger.debug(f"Google careers error: {e}")
    return out

async def _fetch_apple_careers(client: httpx.AsyncClient, query: Optional[str], us_only: bool) -> List[Dict[str, Any]]:
    search_q = _clean_bigtech_query(query, "apple")
    url = "https://jobs.apple.com/en-us/search"
    params = {"search": search_q, "sort": "relevance", "location": "united-states-USA"}
    out = []
    seen_urls = set()
    try:
        resp = await client.get(url, params=params)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            for a in soup.find_all("a", href=re.compile(r"^/en-us/details/\d+")):
                title = a.get_text(strip=True)
                if not title or title.lower() == "see full role description":
                    continue
                href = a["href"]
                apply_url = f"https://jobs.apple.com{href}"
                if apply_url in seen_urls:
                    continue
                seen_urls.add(apply_url)
                parent = a.find_parent("li") or a.find_parent("div") or a.find_parent("tr")
                card_text = parent.get_text(" | ", strip=True) if parent else ""
                loc_match = re.search(r"Location\s*\|\s*([^|]+)", card_text)
                loc = f"{loc_match.group(1).strip()}, USA" if loc_match else "Cupertino, CA, USA"
                is_remote = "remote" in loc.lower() or "home office" in loc.lower() or "remote" in title.lower()
                tags = ["bigtech", "apple", "direct-hire"]
                if is_remote:
                    tags.append("remote")
                out.append({
                    "title": title,
                    "company": "Apple",
                    "location": loc,
                    "workplace_type": "remote" if is_remote else "hybrid",
                    "url": apply_url,
                    "salary_min": None,
                    "salary_max": None,
                    "salary_currency": "USD",
                    "tags": tags,
                    "description": f"{title} at Apple ({loc}). Matched search: {search_q}. {card_text[:400]}",
                    "source": "bigtech",
                })
                if len(out) >= 20:
                    break
    except Exception as e:
        logger.debug(f"Apple careers error: {e}")
    return out

async def _fetch_netflix_careers(client: httpx.AsyncClient, query: Optional[str], us_only: bool, location: Optional[str]) -> List[Dict[str, Any]]:
    search_q = _clean_bigtech_query(query, "netflix")
    url = "https://explore.jobs.netflix.net/api/apply/v2/jobs"
    params = {"domain": "netflix.com", "start": 0, "num": 20, "query": search_q}
    if location and location.strip():
        params["location"] = location.strip()
    out = []
    try:
        resp = await client.get(url, params=params)
        if resp.status_code == 200:
            for p in resp.json().get("positions", []):
                title = (p.get("name") or "").strip()
                loc = (p.get("location") or "Los Gatos, CA, USA").strip()
                apply_url = (p.get("canonicalPositionUrl") or "").strip()
                if not title or not apply_url:
                    continue
                desc = clean_html(p.get("job_description") or "")
                work_opt = str(p.get("work_location_option") or "").lower()
                is_remote = work_opt == "remote" or "remote" in loc.lower() or "remote" in title.lower()
                dept = (p.get("department") or "Engineering").strip()
                tags = ["bigtech", "netflix", dept.lower()]
                if is_remote:
                    tags.append("remote")
                out.append({
                    "title": title,
                    "company": "Netflix",
                    "location": loc,
                    "workplace_type": "remote" if is_remote else "hybrid",
                    "url": apply_url,
                    "salary_min": None,
                    "salary_max": None,
                    "salary_currency": "USD",
                    "tags": tags,
                    "description": desc[:4000] if desc else f"{title} at Netflix ({loc}).",
                    "source": "bigtech",
                })
    except Exception as e:
        logger.debug(f"Netflix careers error: {e}")
    return out

async def _fetch_workday_careers(
    client: httpx.AsyncClient,
    company_name: str,
    api_url: str,
    public_base_url: str,
    query: Optional[str]
) -> List[Dict[str, Any]]:
    search_q = _clean_bigtech_query(query, company_name)
    out = []
    try:
        resp = await client.post(
            api_url,
            json={"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": search_q}
        )
        if resp.status_code == 200:
            for p in resp.json().get("jobPostings", []):
                title = (p.get("title") or "").strip()
                loc = (p.get("locationsText") or "United States").strip()
                ext_path = (p.get("externalPath") or "").strip()
                if not title or not ext_path:
                    continue
                apply_url = f"{public_base_url}{ext_path}"
                is_remote = "remote" in loc.lower() or "remote" in title.lower()
                tags = ["bigtech", company_name.lower(), "workday"]
                if is_remote:
                    tags.append("remote")
                out.append({
                    "title": title,
                    "company": company_name,
                    "location": loc,
                    "workplace_type": "remote" if is_remote else "hybrid",
                    "url": apply_url,
                    "salary_min": None,
                    "salary_max": None,
                    "salary_currency": "USD",
                    "tags": tags,
                    "description": f"{title} at {company_name} ({loc}). Matched search: {search_q}.",
                    "source": "bigtech",
                })
    except Exception as e:
        logger.debug(f"Workday {company_name} error: {e}")
    return out

async def fetch_bigtech_jobs(
    query: Optional[str] = None,
    us_only: bool = True,
    location: Optional[str] = None,
    include_remote: bool = True
) -> List[Dict[str, Any]]:
    """Fetch live roles directly from Google, Microsoft, Amazon, Apple, Netflix, NVIDIA, and Salesforce career portals."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept-Encoding": "gzip, deflate",
    }
    try:
        async with httpx.AsyncClient(timeout=11.0, follow_redirects=True, headers=headers) as client:
            tasks = [
                _fetch_amazon_careers(client, query, us_only, location),
                _fetch_microsoft_careers(query, us_only, location),
                _fetch_google_careers(client, query, us_only, location),
                _fetch_apple_careers(client, query, us_only),
                _fetch_netflix_careers(client, query, us_only, location),
                _fetch_workday_careers(
                    client,
                    "NVIDIA",
                    "https://nvidia.wd5.myworkdayjobs.com/wday/cxs/nvidia/NVIDIAExternalCareerSite/jobs",
                    "https://nvidia.wd5.myworkdayjobs.com/en-US/NVIDIAExternalCareerSite",
                    query
                ),
                _fetch_workday_careers(
                    client,
                    "Salesforce",
                    "https://salesforce.wd12.myworkdayjobs.com/wday/cxs/salesforce/External_Career_Site/jobs",
                    "https://salesforce.wd12.myworkdayjobs.com/en-US/External_Career_Site",
                    query
                ),
            ]
            res_lists = await asyncio.gather(*tasks, return_exceptions=True)

        raw_jobs = []
        for r in res_lists:
            if isinstance(r, list):
                raw_jobs.extend(r)

        filtered = []
        seen = set()
        for j in raw_jobs:
            key = f"{j['title'].lower().strip()}|{j['company'].lower().strip()}"
            if key in seen:
                continue
            if us_only and not is_us_eligible(location=j["location"], title=j["title"], text=j["description"]):
                continue
            is_rem = j["workplace_type"] == "remote" or "remote" in j["location"].lower()
            if not _matches_target_location(j["location"], location, is_rem, include_remote):
                continue
            if not matches_query(
                query, j["title"], j["company"], j["tags"], j["description"],
                location=j["location"], workplace_type=j["workplace_type"],
                salary_min=j.get("salary_min"), salary_max=j.get("salary_max")
            ):
                continue
            seen.add(key)
            filtered.append(j)
        return filtered
    except Exception as e:
        logger.warning(f"Error fetching Big Tech jobs: {e}")
        return []


# Aggregated Search with Source Filtering, US-Only, and Location Radius Support
async def search_aggregated_jobs(
    query: Optional[str] = None,
    source: Optional[str] = None,
    adzuna_app_id: Optional[str] = None,
    adzuna_app_key: Optional[str] = None,
    us_only: bool = True,
    location: Optional[str] = None,
    radius: Optional[int] = None,
    include_remote: bool = True,
    min_salary: Optional[float] = None,
    include_undisclosed_salary: bool = True
) -> List[Dict[str, Any]]:
    """Aggregates listings concurrently across all supported boards with US, salary, and location/radius filtering."""

    tasks = []
    source_lower = (source or "all").lower()

    if source_lower in ("all", "bigtech"):
        tasks.append(fetch_bigtech_jobs(query, us_only=us_only, location=location, include_remote=include_remote))
    if source_lower in ("all", "company_boards"):
        tasks.append(fetch_company_boards_jobs(query, us_only=us_only, location=location, include_remote=include_remote))
    if source_lower in ("all", "simplify"):
        tasks.append(fetch_simplify_jobs(query, us_only=us_only, location=location, include_remote=include_remote))
    if source_lower in ("all", "indeed"):
        tasks.append(fetch_indeed_jobs(query, us_only=us_only, location=location, radius=radius))
    if source_lower in ("all", "linkedin"):
        tasks.append(fetch_linkedin_jobs(query, us_only=us_only, location=location, radius=radius))
    if source_lower in ("all", "glassdoor"):
        tasks.append(fetch_glassdoor_jobs(query, us_only=us_only, location=location, radius=radius))
    if source_lower in ("all", "ziprecruiter"):
        tasks.append(fetch_ziprecruiter_jobs(query, us_only=us_only, location=location, radius=radius))
    if source_lower in ("all", "themuse"):
        tasks.append(fetch_themuse_jobs(query, us_only=us_only, location=location, include_remote=include_remote))
    if source_lower in ("all", "adzuna"):
        tasks.append(fetch_adzuna_jobs(query, adzuna_app_id, adzuna_app_key, us_only=us_only, location=location, radius=radius, min_salary=min_salary))

    # Remote / global boards: include if include_remote is True, or if user hasn't specified a strict local location, or if explicitly selected
    should_fetch_remote_boards = include_remote or not location or source_lower != "all"

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

    # If location is provided, enforce location and radius filtering across all aggregated sources:
    # 1. Pure remote positions are kept if include_remote is True, and excluded if include_remote is False.
    # 2. Hybrid and Onsite positions (which expect physical office presence) MUST be within radius of location.
    if location and location.strip():
        combined = [
            j for j in combined
            if is_job_in_range(
                job_location=j.get("location", ""),
                target_location=location,
                radius_miles=radius,
                workplace_type=j.get("workplace_type", ""),
                is_remote=j.get("workplace_type") == "remote" or "remote" in (j.get("location") or "").lower(),
                include_remote=include_remote,
                title=j.get("title", "")
            )
        ]

    # Backfill salary from description for any listings missing salary
    for j in combined:
        if j.get("salary_min") is None and j.get("salary_max") is None and j.get("description"):
            s_min, s_max = extract_salary_range(j["description"])
            if s_min is not None or s_max is not None:
                j["salary_min"] = s_min
                j["salary_max"] = s_max

    # Enforce minimum compensation filter if requested
    if min_salary and min_salary > 0:
        def meets_salary(job: Dict[str, Any]) -> bool:
            s_min = job.get("salary_min")
            s_max = job.get("salary_max")
            if s_max is not None:
                return s_max >= min_salary
            if s_min is not None:
                return s_min >= min_salary
            return include_undisclosed_salary

        combined = [j for j in combined if meets_salary(j)]

    # Deduplicate by title + company
    seen = set()
    unique_jobs = []
    for j in combined:
        key = f"{j['title'].lower().strip()}|{j['company'].lower().strip()}"
        if key not in seen:
            seen.add(key)
            unique_jobs.append(j)

    return unique_jobs


