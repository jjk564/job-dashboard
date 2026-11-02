import os
import re
import json
import random
import asyncio
import logging
from urllib.parse import urlparse, parse_qs
import httpx
from bs4 import BeautifulSoup
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

# Coherent browser header profiles for anti-bot evasion (no bot User-Agent strings)
BROWSER_PROFILES: List[Dict[str, str]] = [
    {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
    },
    {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"macOS"',
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
    },
    {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0",
        "Sec-Ch-Ua": '"Microsoft Edge";v="123", "Not:A-Brand";v="8", "Chromium";v="123"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
    },
]

HEADERS = BROWSER_PROFILES[0]

# Domains where TLS fingerprint impersonation (curl_cffi) should be used first
TLS_STRICT_DOMAINS = (
    "linkedin.com",
    "ashbyhq.com",
    "indeed.com",
    "glassdoor.com",
    "ziprecruiter.com",
    "myworkdayjobs.com",
)


def get_stealth_headers(url: str = "", referer: Optional[str] = None, json_api: bool = False) -> Dict[str, str]:
    """Returns a coherent browser header dictionary with optional Referer and JSON Accept override."""
    profile = dict(random.choice(BROWSER_PROFILES))
    if json_api:
        profile["Accept"] = "application/json, text/plain, */*"
        profile["Sec-Fetch-Dest"] = "empty"
        profile["Sec-Fetch-Mode"] = "cors"
        profile["Sec-Fetch-Site"] = "same-origin"
        profile.pop("Upgrade-Insecure-Requests", None)
        profile.pop("Sec-Fetch-User", None)
    if referer:
        profile["Referer"] = referer
    elif url:
        try:
            parsed = urlparse(url)
            if parsed.scheme and parsed.netloc:
                profile["Referer"] = f"{parsed.scheme}://{parsed.netloc}/"
        except Exception:
            pass
    return profile


def get_configured_proxy() -> Optional[str]:
    """Reads optional residential/ISP proxy URL or rotates from SCRAPER_PROXY_POOL."""
    pool = os.getenv("SCRAPER_PROXY_POOL", "").strip()
    if pool:
        candidates = [p.strip() for p in pool.split(",") if p.strip()]
        if candidates:
            return random.choice(candidates)
    single = os.getenv("SCRAPER_PROXY_URL", "").strip()
    return single if single else None


def _looks_like_waf_challenge(html: str, status_code: int) -> bool:
    if status_code in (403, 429, 503):
        return True
    head = (html or "")[:2500].lower()
    return any(
        marker in head
        for marker in (
            "just a moment...",
            "cf-browser-verification",
            "challenge-platform",
            "attention required! | cloudflare",
            "verify you are human",
            "access denied",
        )
    )


async def stealth_fetch_text(
    url: str,
    timeout: float = 15.0,
    referer: Optional[str] = None,
    json_api: bool = False,
) -> tuple[int, str]:
    """
    Fetches a URL using realistic browser headers and automatic curl_cffi Chrome TLS
    impersonation for strict anti-bot domains or WAF challenge fallback.
    """
    headers = get_stealth_headers(url, referer=referer, json_api=json_api)
    proxy = get_configured_proxy()
    url_lower = url.lower()
    prefer_tls_impersonation = any(d in url_lower for d in TLS_STRICT_DOMAINS)

    async def _fetch_via_curl_cffi() -> tuple[int, str]:
        from curl_cffi.requests import AsyncSession
        session_kwargs: Dict[str, Any] = {
            "impersonate": "chrome124",
            "timeout": timeout,
            "headers": headers,
        }
        if proxy:
            session_kwargs["proxies"] = {"http": proxy, "https": proxy}
        async with AsyncSession(**session_kwargs) as session:
            resp = await session.get(url, allow_redirects=True)
            return resp.status_code, resp.text

    if prefer_tls_impersonation:
        try:
            status, text = await _fetch_via_curl_cffi()
            if status == 200 and not _looks_like_waf_challenge(text, status):
                return status, text
        except Exception as e:
            logger.debug(f"curl_cffi primary fetch failed for {url}: {e}")

    # Standard async httpx path
    try:
        client_kwargs: Dict[str, Any] = {
            "timeout": timeout,
            "follow_redirects": True,
            "headers": headers,
        }
        if proxy:
            client_kwargs["proxy"] = proxy
        async with httpx.AsyncClient(**client_kwargs) as client:
            resp = await client.get(url)
            status = resp.status_code
            text = resp.text
            if not _looks_like_waf_challenge(text, status):
                return status, text
    except Exception as e:
        logger.debug(f"httpx fetch failed for {url}, falling back to curl_cffi: {e}")

    # Fallback to curl_cffi TLS impersonation if httpx hit a WAF challenge or network error
    status, text = await _fetch_via_curl_cffi()
    return status, text


def clean_html_text(html_content: str) -> str:
    """Removes script, style tags and extracts clean text."""
    if not html_content:
        return ""
    soup = BeautifulSoup(html_content, "html.parser")
    for script_or_style in soup(["script", "style", "noscript", "nav", "footer", "header"]):
        script_or_style.decompose()
    text = soup.get_text(separator="\n")
    lines = [line.strip() for line in text.splitlines()]
    return "\n".join(chunk for chunk in lines if chunk)


def extract_salary_range(text: str) -> tuple[Optional[float], Optional[float]]:
    """Tries to find salary and hourly compensation figures in text/description."""
    if not text:
        return None, None

    # 1. Hourly range pattern: e.g. $25 - $35/hr, $25.00 to $40.00 per hour, $30 - 45 / hr
    hourly_range_pattern = r"\$([0-9]+(?:\.[0-9]{2})?)\s*(?:-|to|–|—)\s*\$?([0-9]+(?:\.[0-9]{2})?)\s*(?:\/|\s*(?:per|an)\s*)?(?:hr|hour)\b"
    m_hr = re.search(hourly_range_pattern, text, re.IGNORECASE)
    if m_hr:
        try:
            h_min = float(m_hr.group(1)) * 2080
            h_max = float(m_hr.group(2)) * 2080
            return h_min, h_max
        except Exception:
            pass

    # Single hourly rate: e.g. $35/hr, $40 per hour
    single_hr_pattern = r"\$([0-9]+(?:\.[0-9]{2})?)\s*(?:\/|\s*(?:per|an)\s*)(?:hr|hour)\b"
    m_shr = re.search(single_hr_pattern, text, re.IGNORECASE)
    if m_shr:
        try:
            val = float(m_shr.group(1)) * 2080
            return val, val
        except Exception:
            pass

    # 2. Standard annual range: e.g. $120,000 - $160,000 or $120k - $160k
    range_pattern = r"\$((?:\d{2,3}k)|[0-9]{2,3}(?:,[0-9]{3})*)\s*(?:-|to|–|—)\s*\$?((?:\d{2,3}k)|[0-9]{2,3}(?:,[0-9]{3})*)"
    match = re.search(range_pattern, text, re.IGNORECASE)
    if match:
        def parse_val(v: str) -> float:
            v = v.lower().replace(",", "")
            if "k" in v:
                return float(v.replace("k", "")) * 1000
            val = float(v)
            if val < 200:
                return val * 2080
            return val
        try:
            val_min = parse_val(match.group(1))
            val_max = parse_val(match.group(2))
            if val_min > 0 and val_max >= val_min:
                return val_min, val_max
        except Exception:
            pass

    # 3. Single annual figure: e.g. $85,000/year or $90k/yr
    single_pattern = r"\$((?:\d{2,3}k)|[0-9]{2,3}(?:,[0-9]{3})*)\s*(?:\/|\s*(?:per|a)\s*)?(?:year|yr|annually)\b"
    m_single = re.search(single_pattern, text, re.IGNORECASE)
    if m_single:
        def parse_val(v: str) -> float:
            v = v.lower().replace(",", "")
            if "k" in v:
                return float(v.replace("k", "")) * 1000
            val = float(v)
            if val < 200:
                return val * 2080
            return val
        try:
            val = parse_val(m_single.group(1))
            return val, val
        except Exception:
            pass

    # 4. Phrase-based salary: e.g. "base salary of $130,000"
    phrase_pattern = r"(?:base\s+salary|base\s+pay|target\s+salary|salary\s+range)[\s:]+\$((?:\d{2,3}k)|[0-9]{2,3}(?:,[0-9]{3})*)"
    m_phrase = re.search(phrase_pattern, text, re.IGNORECASE)
    if m_phrase:
        def parse_val(v: str) -> float:
            v = v.lower().replace(",", "")
            if "k" in v:
                return float(v.replace("k", "")) * 1000
            val = float(v)
            if val < 200:
                return val * 2080
            return val
        try:
            val = parse_val(m_phrase.group(1))
            return val, val
        except Exception:
            pass

    return None, None


def extract_json_ld_job_posting(soup: BeautifulSoup) -> Optional[Dict[str, Any]]:
    """
    Extracts structured Schema.org JobPosting metadata from <script type="application/ld+json">
    blocks if present on the page (used by Workday, iCIMS, SmartRecruiters, Eightfold, etc.).
    """
    for script in soup.find_all("script", type="application/ld+json"):
        raw = script.string or script.get_text()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except Exception:
            continue

        candidates = []
        if isinstance(data, dict):
            if data.get("@type") == "JobPosting":
                candidates.append(data)
            elif isinstance(data.get("@graph"), list):
                candidates.extend(x for x in data["@graph"] if isinstance(x, dict) and x.get("@type") == "JobPosting")
        elif isinstance(data, list):
            candidates.extend(x for x in data if isinstance(x, dict) and x.get("@type") == "JobPosting")

        for jp in candidates:
            title = (jp.get("title") or "").strip()
            if not title:
                continue
            org = jp.get("hiringOrganization")
            company = ""
            if isinstance(org, dict):
                company = (org.get("name") or "").strip()
            elif isinstance(org, str):
                company = org.strip()

            # Location parsing
            loc_str = ""
            job_loc = jp.get("jobLocation")
            if isinstance(job_loc, list) and job_loc:
                job_loc = job_loc[0]
            if isinstance(job_loc, dict):
                addr = job_loc.get("address")
                if isinstance(addr, dict):
                    parts = [
                        addr.get("addressLocality", ""),
                        addr.get("addressRegion", ""),
                        addr.get("addressCountry", ""),
                    ]
                    loc_str = ", ".join(str(p).strip() for p in parts if p)

            loc_type = str(jp.get("jobLocationType") or "").upper()
            is_remote = "TELECOMMUTE" in loc_type or "remote" in loc_str.lower() or "remote" in title.lower()
            if not loc_str:
                loc_str = "Remote" if is_remote else "United States"

            desc_html = jp.get("description") or ""
            desc = clean_html_text(desc_html) if "<" in desc_html else desc_html.strip()

            sal_min, sal_max = None, None
            base_sal = jp.get("baseSalary")
            if isinstance(base_sal, dict):
                val_obj = base_sal.get("value")
                if isinstance(val_obj, dict):
                    try:
                        if val_obj.get("minValue"):
                            sal_min = float(val_obj["minValue"])
                        if val_obj.get("maxValue"):
                            sal_max = float(val_obj["maxValue"])
                        if sal_min and sal_min < 200:
                            sal_min *= 2080
                        if sal_max and sal_max < 200:
                            sal_max *= 2080
                    except Exception:
                        pass

            if sal_min is None and sal_max is None and desc:
                sal_min, sal_max = extract_salary_range(desc)

            return {
                "title": title,
                "company": company or "Company",
                "location": loc_str,
                "workplace_type": "remote" if is_remote else "hybrid",
                "salary_min": sal_min,
                "salary_max": sal_max,
                "description": desc[:8000],
            }
    return None


async def _try_greenhouse_api(url: str) -> Optional[Dict[str, Any]]:
    """
    Attempts to resolve a Greenhouse job URL directly via the public boards-api JSON endpoint
    to bypass HTML layout changes and WAF blocks.
    """
    parsed = urlparse(url)
    path_parts = [p for p in parsed.path.split("/") if p]
    slug = None
    job_id = None

    # Pattern 1: boards.greenhouse.io/{slug}/jobs/{job_id}
    if "greenhouse.io" in parsed.netloc and len(path_parts) >= 3 and path_parts[1] == "jobs":
        slug = path_parts[0]
        job_id = path_parts[2]
    # Pattern 2: ?gh_jid={job_id} on company domain or greenhouse
    qs = parse_qs(parsed.query)
    if not job_id and "gh_jid" in qs:
        job_id = qs["gh_jid"][0]
        if not slug and path_parts:
            slug = path_parts[0]

    if not slug or not job_id or not re.match(r"^\d+$", str(job_id)):
        return None

    api_url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs/{job_id}"
    try:
        status, text = await stealth_fetch_text(api_url, timeout=10.0, json_api=True)
        if status != 200:
            return None
        data = json.loads(text)
        title = (data.get("title") or "").strip()
        if not title:
            return None
        loc = ((data.get("location") or {}).get("name") or "Remote").strip()
        content_html = data.get("content") or ""
        # Greenhouse API often HTML-escapes the content string
        if "&lt;" in content_html:
            import html as html_mod
            content_html = html_mod.unescape(content_html)
        desc = clean_html_text(content_html)
        sal_min, sal_max = extract_salary_range(desc)
        is_remote = "remote" in loc.lower() or "remote" in title.lower()
        return {
            "title": title,
            "company": slug.replace("-", " ").title(),
            "location": loc,
            "workplace_type": "remote" if is_remote else "hybrid",
            "url": url,
            "salary_min": sal_min,
            "salary_max": sal_max,
            "description": desc[:8000],
            "source": "greenhouse",
        }
    except Exception as e:
        logger.debug(f"Greenhouse direct API fallback failed for {url}: {e}")
        return None


async def _try_lever_api(url: str) -> Optional[Dict[str, Any]]:
    """
    Attempts to resolve a Lever job URL (jobs.lever.co/{slug}/{uuid}) via Lever's JSON API.
    """
    parsed = urlparse(url)
    path_parts = [p for p in parsed.path.split("/") if p]
    if "lever.co" not in parsed.netloc or len(path_parts) < 2:
        return None
    slug, job_uuid = path_parts[0], path_parts[1]
    if job_uuid in ("apply", "search"):
        return None

    api_url = f"https://api.lever.co/v0/postings/{slug}/{job_uuid}?mode=json"
    try:
        status, text = await stealth_fetch_text(api_url, timeout=10.0, json_api=True)
        if status != 200:
            return None
        data = json.loads(text)
        title = (data.get("text") or "").strip()
        if not title:
            return None
        cats = data.get("categories") or {}
        loc = (cats.get("location") or "Remote").strip()
        wp_raw = str(data.get("workplaceType") or "").lower()
        is_remote = wp_raw == "remote" or "remote" in loc.lower()

        desc_parts = [data.get("descriptionPlain") or clean_html_text(data.get("description") or "")]
        for lst in (data.get("lists") or []):
            if isinstance(lst, dict):
                heading = lst.get("text") or ""
                content = clean_html_text(lst.get("content") or "")
                if heading or content:
                    desc_parts.append(f"{heading}\n{content}".strip())
        if data.get("additionalPlain"):
            desc_parts.append(data["additionalPlain"])

        desc = "\n\n".join(p for p in desc_parts if p).strip()
        sal_min, sal_max = None, None
        sal_range = data.get("salaryRange")
        if isinstance(sal_range, dict):
            if sal_range.get("min"):
                sal_min = float(sal_range["min"])
            if sal_range.get("max"):
                sal_max = float(sal_range["max"])
        if sal_min is None and sal_max is None:
            sal_min, sal_max = extract_salary_range(desc)

        return {
            "title": title,
            "company": slug.replace("-", " ").title(),
            "location": loc,
            "workplace_type": "remote" if is_remote else ("onsite" if wp_raw == "onsite" else "hybrid"),
            "url": url,
            "salary_min": sal_min,
            "salary_max": sal_max,
            "description": desc[:8000],
            "source": "lever",
        }
    except Exception as e:
        logger.debug(f"Lever direct API fallback failed for {url}: {e}")
        return None


async def extract_ashby_job(url: str, html: str, soup: BeautifulSoup) -> Dict[str, Any]:
    """
    Extracts structured job posting details from Ashby URLs (jobs.ashbyhq.com/{slug}/{id})
    via Ashby's public posting API or embedded JSON-LD / window.__appData.
    """
    parsed = urlparse(url)
    path_parts = [p for p in parsed.path.split("/") if p]
    slug = path_parts[0] if path_parts else ""
    job_id = path_parts[1] if len(path_parts) > 1 else ""

    if slug and job_id:
        api_url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true"
        try:
            status, text = await stealth_fetch_text(api_url, timeout=10.0, json_api=True)
            if status == 200:
                board_data = json.loads(text)
                for j in (board_data.get("jobs") or []):
                    j_url = (j.get("jobUrl") or j.get("applyUrl") or "").lower()
                    if job_id.lower() in j_url or str(j.get("id", "")).lower() == job_id.lower():
                        title = (j.get("title") or "").strip()
                        loc = (j.get("location") or "Remote").strip()
                        is_remote = bool(j.get("isRemote")) or str(j.get("workplaceType") or "").lower() == "remote" or "remote" in loc.lower()
                        desc = (j.get("descriptionPlain") or clean_html_text(j.get("descriptionHtml") or "")).strip()
                        sal_min, sal_max = None, None
                        comp = j.get("compensation") or {}
                        for sc in (comp.get("summaryComponents") or []):
                            if sc.get("compensationType") == "Salary":
                                if sc.get("minValue"):
                                    sal_min = float(sc["minValue"])
                                if sc.get("maxValue"):
                                    sal_max = float(sc["maxValue"])
                                break
                        if sal_min is None and sal_max is None:
                            sal_min, sal_max = extract_salary_range(desc)
                        return {
                            "title": title or "Software Engineer",
                            "company": slug.replace("-", " ").title(),
                            "location": loc,
                            "workplace_type": "remote" if is_remote else "hybrid",
                            "url": url,
                            "salary_min": sal_min,
                            "salary_max": sal_max,
                            "description": desc[:8000],
                            "source": "ashby",
                        }
        except Exception as e:
            logger.debug(f"Ashby API lookup failed for {url}: {e}")

    ld_data = extract_json_ld_job_posting(soup)
    if ld_data:
        return {**ld_data, "url": url, "source": "ashby"}

    app_data_match = re.search(r"window\.__appData\s*=\s*(\{.*?\});?\s*</script>", html, re.S)
    if app_data_match:
        try:
            app_data = json.loads(app_data_match.group(1))
            posting = app_data.get("posting") or {}
            if posting and isinstance(posting, dict):
                title = (posting.get("title") or "").strip()
                loc = (posting.get("locationName") or posting.get("location") or "Remote").strip()
                wp_raw = str(posting.get("workplaceType") or "").lower()
                is_remote = wp_raw == "remote" or "remote" in loc.lower()
                desc = (posting.get("descriptionPlain") or clean_html_text(posting.get("descriptionHtml") or "")).strip()
                sal_min, sal_max = extract_salary_range(desc)
                return {
                    "title": title or "Software Engineer",
                    "company": slug.replace("-", " ").title() if slug else "Unknown Company",
                    "location": loc,
                    "workplace_type": "remote" if is_remote else "hybrid",
                    "url": url,
                    "salary_min": sal_min,
                    "salary_max": sal_max,
                    "description": desc[:8000],
                    "source": "ashby",
                }
        except Exception as e:
            logger.debug(f"Ashby window.__appData parse error: {e}")

    gen = await extract_generic_job(url, html, soup)
    gen["source"] = "ashby"
    return gen


async def extract_linkedin_guest_job(url: str) -> Optional[Dict[str, Any]]:
    """
    Extracts a LinkedIn job posting using LinkedIn's unauthenticated public Guest API
    (/jobs-guest/jobs/api/jobPosting/{id}) so zero login cookies (li_at) are ever required.
    """
    m = re.search(r"(?:jobs/view/|(?:currentJobId|jobPosting)=?/?)(?:[\w-]+-)?(\d{7,12})\b", url)
    if not m:
        return None
    job_id = m.group(1)
    guest_url = f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"
    try:
        status, html = await stealth_fetch_text(
            guest_url,
            timeout=12.0,
            referer="https://www.linkedin.com/jobs/search/",
        )
        if status != 200 or not html.strip():
            return None
        soup = BeautifulSoup(html, "html.parser")
        title_el = soup.find("h2", class_=re.compile(r"top-card-layout__title", re.I)) or soup.find("h2") or soup.find("h1")
        company_el = soup.find("a", class_=re.compile(r"topcard__org-name-link", re.I)) or soup.find("span", class_=re.compile(r"topcard__flavor", re.I))
        loc_el = soup.find("span", class_=re.compile(r"topcard__flavor--bullet", re.I))
        desc_el = soup.find("div", class_=re.compile(r"show-more-less-html__markup|description__text", re.I)) or soup.body

        title = title_el.get_text(strip=True) if title_el else "Software Engineer"
        company = company_el.get_text(strip=True) if company_el else "LinkedIn Employer"
        location = loc_el.get_text(strip=True) if loc_el else "United States"
        desc = clean_html_text(str(desc_el)) if desc_el else ""
        sal_min, sal_max = extract_salary_range(desc)
        is_remote = "remote" in location.lower() or "remote" in title.lower() or "remote" in desc[:400].lower()

        return {
            "title": title,
            "company": company,
            "location": location,
            "workplace_type": "remote" if is_remote else "hybrid",
            "url": url,
            "salary_min": sal_min,
            "salary_max": sal_max,
            "description": desc[:8000],
            "source": "linkedin",
        }
    except Exception as e:
        logger.debug(f"LinkedIn guest extraction failed for {url}: {e}")
        return None


async def extract_greenhouse_job(url: str, html: str, soup: BeautifulSoup) -> Dict[str, Any]:
    ld_data = extract_json_ld_job_posting(soup)
    if ld_data and ld_data.get("description"):
        return {**ld_data, "url": url, "source": "greenhouse"}

    title_el = soup.find("h1", class_="app-title") or soup.find("h1")
    company_el = soup.find("span", class_="company-name") or soup.find(class_="company")
    location_el = soup.find("div", class_="location") or soup.find(class_="location")

    title = title_el.get_text(strip=True) if title_el else ""
    company = company_el.get_text(strip=True) if company_el else ""
    location = location_el.get_text(strip=True) if location_el else "Remote"

    content_el = soup.find("div", id="content") or soup.find(class_="job-description") or soup.body
    desc = clean_html_text(str(content_el)) if content_el else ""

    salary_min, salary_max = extract_salary_range(desc)

    return {
        "title": title or "Software Engineer",
        "company": company or "Company",
        "location": location,
        "workplace_type": "remote" if "remote" in location.lower() or "remote" in desc.lower() else "hybrid",
        "url": url,
        "salary_min": salary_min,
        "salary_max": salary_max,
        "description": desc,
        "source": "greenhouse",
    }


async def extract_lever_job(url: str, html: str, soup: BeautifulSoup) -> Dict[str, Any]:
    title_el = soup.find("h2") or soup.find("h1")
    company_el = soup.find("title")
    location_el = soup.find("span", class_="location") or soup.find(class_="sort-by-time")

    title = title_el.get_text(strip=True) if title_el else ""
    company = ""
    if company_el:
        comp_text = company_el.get_text(strip=True)
        if "-" in comp_text:
            company = comp_text.split("-")[-1].strip()

    location = location_el.get_text(strip=True) if location_el else "Remote"
    content_el = soup.find("div", class_="content") or soup.body
    desc = clean_html_text(str(content_el)) if content_el else ""
    salary_min, salary_max = extract_salary_range(desc)

    return {
        "title": title or "Software Engineer",
        "company": company or "Company",
        "location": location,
        "workplace_type": "remote" if "remote" in location.lower() or "remote" in desc.lower() else "hybrid",
        "url": url,
        "salary_min": salary_min,
        "salary_max": salary_max,
        "description": desc,
        "source": "lever",
    }


async def extract_generic_job(url: str, html: str, soup: BeautifulSoup) -> Dict[str, Any]:
    # 1. Try Schema.org JobPosting JSON-LD first (highest fidelity on Workday, iCIMS, etc.)
    ld_data = extract_json_ld_job_posting(soup)
    if ld_data and ld_data.get("description"):
        return {**ld_data, "url": url, "source": "url_import"}

    # 2. Try OpenGraph tags
    og_title = soup.find("meta", property="og:title")
    og_desc = soup.find("meta", property="og:description")
    og_site_name = soup.find("meta", property="og:site_name")

    title = og_title["content"].strip() if og_title and og_title.get("content") else ""
    if not title:
        h1 = soup.find("h1")
        title = h1.get_text(strip=True) if h1 else (soup.title.get_text(strip=True) if soup.title else "Job Posting")

    company = og_site_name["content"].strip() if og_site_name and og_site_name.get("content") else ""
    if not company:
        if " at " in title:
            parts = title.split(" at ")
            title = parts[0].strip()
            company = parts[1].strip()
        elif " - " in title:
            parts = title.split(" - ")
            title = parts[0].strip()
            company = parts[1].strip()

    main_el = soup.find("main") or soup.find("article") or soup.find(class_=re.compile(r"job|posting|detail|description", re.I)) or soup.body
    desc = clean_html_text(str(main_el)) if main_el else ""
    if not desc and og_desc and og_desc.get("content"):
        desc = og_desc["content"]

    salary_min, salary_max = extract_salary_range(desc)
    is_remote = "remote" in title.lower() or "remote" in desc[:500].lower()

    return {
        "title": title,
        "company": company or "Company",
        "location": "Remote" if is_remote else "Onsite",
        "workplace_type": "remote" if is_remote else "hybrid",
        "url": url,
        "salary_min": salary_min,
        "salary_max": salary_max,
        "description": desc[:8000],
        "source": "url_import",
    }


async def extract_job_from_url(url: str) -> Dict[str, Any]:
    """
    Extracts structured job details from a URL using direct ATS APIs first (Greenhouse, Lever,
    Ashby, LinkedIn Guest API), falling back to stealth TLS-impersonated HTML + JSON-LD extraction.
    """
    url_lower = url.lower()

    # Fast-path 1: Direct unauthenticated ATS / Guest APIs (zero bot friction)
    if "linkedin.com" in url_lower:
        li_job = await extract_linkedin_guest_job(url)
        if li_job and li_job.get("description"):
            return li_job

    if "greenhouse.io" in url_lower or "gh_jid=" in url_lower:
        gh_job = await _try_greenhouse_api(url)
        if gh_job and gh_job.get("description"):
            return gh_job

    if "lever.co" in url_lower:
        lv_job = await _try_lever_api(url)
        if lv_job and lv_job.get("description"):
            return lv_job

    # Fetch HTML via stealth fetcher (httpx + curl_cffi Chrome TLS impersonation fallback)
    status, html = await stealth_fetch_text(url, timeout=15.0)
    if status >= 400 and not html:
        raise ValueError(f"HTTP {status} fetching job URL: {url}")

    soup = BeautifulSoup(html, "html.parser")

    if "greenhouse.io" in url_lower:
        return await extract_greenhouse_job(url, html, soup)
    elif "lever.co" in url_lower:
        return await extract_lever_job(url, html, soup)
    elif "ashbyhq.com" in url_lower:
        return await extract_ashby_job(url, html, soup)
    else:
        return await extract_generic_job(url, html, soup)
