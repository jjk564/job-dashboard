import re
import json
import logging
import httpx
from bs4 import BeautifulSoup
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

def clean_html_text(html_content: str) -> str:
    """Removes script, style tags and extracts clean text."""
    soup = BeautifulSoup(html_content, "html.parser")
    for script_or_style in soup(["script", "style", "noscript", "nav", "footer", "header"]):
        script_or_style.decompose()
    text = soup.get_text(separator="\n")
    # Clean up excessive newlines and whitespace
    lines = [line.strip() for line in text.splitlines()]
    return "\n".join(chunk for chunk in lines if chunk)

def extract_salary_range(text: str) -> tuple[Optional[float], Optional[float]]:
    """Tries to find salary numbers in description."""
    # Pattern e.g. $120,000 - $160,000 or $120k - $160k or $120,000 to $160,000
    pattern = r"\$([0-9]+(?:,[0-9]{3})*k?)\s*(?:-|to|–)\s*\$([0-9]+(?:,[0-9]{3})*k?)"
    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        def parse_val(v: str) -> float:
            v = v.lower().replace(",", "")
            if "k" in v:
                return float(v.replace("k", "")) * 1000
            return float(v)
        try:
            return parse_val(match.group(1)), parse_val(match.group(2))
        except Exception:
            pass
    return None, None

async def extract_greenhouse_job(url: str, html: str, soup: BeautifulSoup) -> Dict[str, Any]:
    # Check title
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
    # Try OpenGraph tags first
    og_title = soup.find("meta", property="og:title")
    og_desc = soup.find("meta", property="og:description")
    og_site_name = soup.find("meta", property="og:site_name")

    title = og_title["content"].strip() if og_title and og_title.get("content") else ""
    if not title:
        h1 = soup.find("h1")
        title = h1.get_text(strip=True) if h1 else (soup.title.get_text(strip=True) if soup.title else "Job Posting")

    company = og_site_name["content"].strip() if og_site_name and og_site_name.get("content") else ""
    if not company:
        # Check title like "Job Title at Company" or "Job Title - Company"
        if " at " in title:
            parts = title.split(" at ")
            title = parts[0].strip()
            company = parts[1].strip()
        elif " - " in title:
            parts = title.split(" - ")
            title = parts[0].strip()
            company = parts[1].strip()

    # Find main article content
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
        "description": desc[:8000],  # avoid excessively huge payloads
        "source": "url_import",
    }

async def extract_job_from_url(url: str) -> Dict[str, Any]:
    """Downloads webpage and extracts structured job details."""
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        resp = await client.get(url, headers=HEADERS)
        resp.raise_for_status()
        html = resp.text

    soup = BeautifulSoup(html, "html.parser")
    url_lower = url.lower()

    if "greenhouse.io" in url_lower:
        return await extract_greenhouse_job(url, html, soup)
    elif "lever.co" in url_lower:
        return await extract_lever_job(url, html, soup)
    else:
        return await extract_generic_job(url, html, soup)
