"""
Unified client for the Hadoku ecosystem services:
1. Hadoku Vault Credential Loader (.devvault.local.json / HADOKU_USER_KEY / HADOKU_SERVICE_KEY)
2. Hadoku Resume Service (https://hadoku.me/resume/api/*)
   - /tailored-resume, /cover-letter, /application-extras, /variants, /resume.pdf
   - Local ResumeBlock chunker compatible with @wolffm/resume-bot blocks.json schema
3. Hadoku Scraper & JobPlatform Workers (https://scraper.hadoku.me/api/v1/jobboards/* & https://hadoku.me/jobplatform/api/*)
   - /probe, /match, /targets, /search, and /jobplatform/api/jobs corpus sync
"""
import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

HADOKU_BASE_URL = os.environ.get("HADOKU_BASE_URL", "https://hadoku.me").rstrip("/")
RESUME_API_BASE = os.environ.get("HADOKU_RESUME_API_URL", f"{HADOKU_BASE_URL}/resume/api").rstrip("/")
JOBPLATFORM_API_BASE = os.environ.get("HADOKU_JOBPLATFORM_API_URL", f"{HADOKU_BASE_URL}/jobplatform/api").rstrip("/")
SCRAPER_API_BASE = os.environ.get("HADOKU_SCRAPER_API_URL", "https://scraper.hadoku.me").rstrip("/")

# Repo root where `npx @hadoku/dev-vault login` writes `.devvault.local.json`
REPO_ROOT = Path(__file__).resolve().parents[3]
DEVVAULT_LOCAL_PATH = REPO_ROOT / ".devvault.local.json"


def get_hadoku_user_key(explicit_key: Optional[str] = None) -> Optional[str]:
    """
    Resolves the Hadoku service/friend credential in priority order:
    1. Explicitly supplied key (e.g., from request header/body)
    2. Environment variable (HADOKU_USER_KEY or HADOKU_SERVICE_KEY)
    3. Local `.devvault.local.json` minted by `npx @hadoku/dev-vault login`
    Never logs the key value.
    """
    if explicit_key and explicit_key.strip():
        return explicit_key.strip()

    env_key = os.environ.get("HADOKU_USER_KEY") or os.environ.get("HADOKU_SERVICE_KEY")
    if env_key and env_key.strip():
        return env_key.strip()

    try:
        if DEVVAULT_LOCAL_PATH.exists():
            data = json.loads(DEVVAULT_LOCAL_PATH.read_text(encoding="utf-8"))
            key = data.get("key")
            if isinstance(key, str) and key.strip():
                return key.strip()
    except Exception as e:
        logger.debug(f"Could not read .devvault.local.json: {e}")

    return None


def _auth_headers(explicit_key: Optional[str] = None) -> Dict[str, str]:
    key = get_hadoku_user_key(explicit_key)
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if key:
        headers["X-User-Key"] = key
    return headers


# ============================================================================
# 1. Hadoku Resume Service Client (/resume/api/*)
# ============================================================================

async def check_hadoku_services_health(explicit_key: Optional[str] = None) -> Dict[str, Any]:
    """Checks connectivity and auth status across resume-api, jobplatform-worker, and scraper.hadoku.me."""
    key = get_hadoku_user_key(explicit_key)
    headers = _auth_headers(explicit_key)
    status_report: Dict[str, Any] = {
        "vault_key_configured": bool(key),
        "vault_key_source": (
            "env"
            if (os.environ.get("HADOKU_USER_KEY") or os.environ.get("HADOKU_SERVICE_KEY"))
            else (".devvault.local.json" if DEVVAULT_LOCAL_PATH.exists() and key else "none")
        ),
        "resume_api": {"online": False, "status": None},
        "jobplatform_api": {"online": False, "status": None},
        "scraper_api": {"online": False, "active_targets": 0},
    }

    async with httpx.AsyncClient(timeout=8.0) as client:
        try:
            r_res = await client.get(f"{RESUME_API_BASE}/health", headers=headers)
            status_report["resume_api"] = {
                "online": r_res.status_code == 200,
                "status": r_res.status_code,
            }
        except Exception as e:
            status_report["resume_api"]["error"] = str(e)

        try:
            r_jp = await client.get(f"{JOBPLATFORM_API_BASE}/health", headers=headers)
            status_report["jobplatform_api"] = {
                "online": r_jp.status_code == 200,
                "status": r_jp.status_code,
            }
        except Exception as e:
            status_report["jobplatform_api"]["error"] = str(e)

        if key:
            try:
                r_sc = await client.get(
                    f"{SCRAPER_API_BASE}/api/v1/jobboards/targets?active_only=true",
                    headers=headers,
                )
                if r_sc.status_code == 200:
                    body = r_sc.json()
                    count = (body.get("data") or {}).get("count", 0)
                    status_report["scraper_api"] = {
                        "online": True,
                        "status": 200,
                        "active_targets": count,
                    }
                else:
                    status_report["scraper_api"] = {
                        "online": False,
                        "status": r_sc.status_code,
                        "active_targets": 0,
                    }
            except Exception as e:
                status_report["scraper_api"]["error"] = str(e)

    return status_report


async def generate_hadoku_tailored_resume(
    job_title: str,
    company: str,
    description: str,
    profile_type: Optional[str] = None,
    tailor: bool = True,
    explicit_key: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Calls POST https://hadoku.me/resume/api/tailored-resume
    Returns { "resume_markdown": str, "blocks_used": List[str], "cached": bool }
    """
    key = get_hadoku_user_key(explicit_key)
    if not key:
        return None

    payload: Dict[str, Any] = {
        "job_title": job_title,
        "company": company,
        "description": description or f"{job_title} at {company}",
        "tailor": tailor,
    }
    if profile_type:
        payload["profile_type"] = profile_type

    async with httpx.AsyncClient(timeout=45.0) as client:
        res = await client.post(
            f"{RESUME_API_BASE}/tailored-resume",
            headers=_auth_headers(key),
            json=payload,
        )
        if res.status_code == 200:
            return res.json()
        logger.warning(f"hadoku-resume /tailored-resume returned {res.status_code}: {res.text[:250]}")
        return None


async def generate_hadoku_cover_letter(
    job_title: str,
    company: str,
    description: str,
    tone: str = "conversational",
    explicit_key: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Calls POST https://hadoku.me/resume/api/cover-letter
    Returns { "cover_letter_markdown": str, "cached": bool }
    """
    key = get_hadoku_user_key(explicit_key)
    if not key:
        return None

    mapped_tone = "formal" if tone in ("formal", "professional") else "conversational"
    payload = {
        "job_title": job_title,
        "company": company,
        "description": description or f"{job_title} at {company}",
        "tone": mapped_tone,
    }

    async with httpx.AsyncClient(timeout=40.0) as client:
        res = await client.post(
            f"{RESUME_API_BASE}/cover-letter",
            headers=_auth_headers(key),
            json=payload,
        )
        if res.status_code == 200:
            return res.json()
        logger.warning(f"hadoku-resume /cover-letter returned {res.status_code}: {res.text[:250]}")
        return None


async def generate_hadoku_application_extras(
    job_title: str,
    company: str,
    description: str,
    resume_markdown: str,
    job_location: Optional[str] = None,
    workplace_type: Optional[str] = None,
    explicit_key: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Calls POST https://hadoku.me/resume/api/application-extras
    Returns {
      "cover_letter_markdown", "intro_email", "why_hook",
      "screening_answers": [{"q", "a"}], "salary_line",
      "linkedin_note", "talking_points": [str],
      "standard_fields", "contact", "cached"
    }
    """
    key = get_hadoku_user_key(explicit_key)
    if not key:
        return None

    payload: Dict[str, Any] = {
        "job_title": job_title,
        "company": company,
        "description": description or f"{job_title} at {company}",
        "resume_markdown": resume_markdown,
    }
    if job_location:
        payload["job_location"] = job_location
    if workplace_type:
        payload["workplace_type"] = workplace_type

    async with httpx.AsyncClient(timeout=45.0) as client:
        res = await client.post(
            f"{RESUME_API_BASE}/application-extras",
            headers=_auth_headers(key),
            json=payload,
        )
        if res.status_code == 200:
            return res.json()
        logger.warning(f"hadoku-resume /application-extras returned {res.status_code}: {res.text[:250]}")
        return None


async def mint_hadoku_resume_variant(
    label: str,
    markdown: str,
    cover_letter_markdown: Optional[str] = None,
    company: Optional[str] = None,
    job_title: Optional[str] = None,
    ttl_days: int = 365,
    explicit_key: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Calls POST https://hadoku.me/resume/api/variants to mint a shareable packet link
    (https://hadoku.me/resume?v={slug}) and server-rendered PDF (https://hadoku.me/resume/api/resume.pdf?v={slug}).
    """
    key = get_hadoku_user_key(explicit_key)
    if not key:
        return None

    payload: Dict[str, Any] = {
        "label": label,
        "markdown": markdown,
        "ttl_days": ttl_days,
    }
    if cover_letter_markdown:
        payload["cover_letter_markdown"] = cover_letter_markdown
    if company:
        payload["company"] = company
    if job_title:
        payload["job_title"] = job_title

    async with httpx.AsyncClient(timeout=25.0) as client:
        res = await client.post(
            f"{RESUME_API_BASE}/variants",
            headers=_auth_headers(key),
            json=payload,
        )
        if res.status_code in (200, 201):
            data = res.json()
            slug = data.get("slug")
            if slug:
                return {
                    "slug": slug,
                    "label": data.get("label", label),
                    "created_at": data.get("created_at"),
                    "url": f"{HADOKU_BASE_URL}/resume?v={slug}",
                    "pdf_url": f"{RESUME_API_BASE}/resume.pdf?v={slug}",
                    "json_url": f"{RESUME_API_BASE}/resume?v={slug}",
                }
        logger.warning(f"hadoku-resume /variants returned {res.status_code}: {res.text[:250]}")
        return None


# ============================================================================
# 2. Local Resume Chunker (hadoku-resume-bot `ResumeBlock` format)
# ============================================================================

def chunk_resume_into_blocks(
    master_resume_text: str,
    full_name: str = "Candidate",
    title: str = "Software Engineer",
    summary: str = "",
    email: str = "",
    phone: str = "",
    location: str = "",
    linkedin_url: str = "",
    github_url: str = "",
    skills: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Separates a candidate's master resume + profile into structured `ResumeBlock`
    chunks matching `@wolffm/resume-bot` (`hadoku-resume-bot/src/builder/api.ts`):
      { id, type: 'header'|'summary'|'experience'|'project'|'skills'|'education', tags: [], title, content, priority }
    """
    blocks: List[Dict[str, Any]] = []

    # 1. Header block (always included)
    contact_parts = [p for p in [location, email, phone, linkedin_url, github_url] if p and p.strip()]
    header_md = f"# {full_name}\n**{title}**"
    if contact_parts:
        header_md += "\n" + " | ".join(contact_parts)
    blocks.append({
        "id": "header-main",
        "type": "header",
        "tags": ["always", "section:header"],
        "title": f"{full_name} Header",
        "content": header_md,
        "priority": 100,
    })

    # 2. Summary block
    if summary and summary.strip():
        blocks.append({
            "id": "summary-primary",
            "type": "summary",
            "tags": ["section:summary", "variant:summary"],
            "title": f"{title} Summary",
            "content": summary.strip(),
            "priority": 90,
        })

    # 3. Parse sections from master_resume_text
    raw_text = (master_resume_text or "").strip()
    if raw_text:
        sections = re.split(r"\n(?=#{1,3}\s+|[A-Z][A-Z\s/&]{3,}:?\n)", raw_text)
        idx = 1
        for sec in sections:
            sec_clean = sec.strip()
            if not sec_clean or len(sec_clean) < 15:
                continue
            lines = sec_clean.splitlines()
            heading = re.sub(r"^#{1,4}\s*", "", lines[0]).strip().rstrip(":")
            body = "\n".join(lines[1:]).strip() if len(lines) > 1 else sec_clean

            h_low = heading.lower()
            if any(k in h_low for k in ("educat", "universit", "degree", "b.s", "m.s", "bachelor", "master")):
                b_type = "education"
                section_tag = "section:education"
                prio = 60
            elif any(k in h_low for k in ("project", "portfolio", "open source", "built")):
                b_type = "project"
                section_tag = "section:projects"
                prio = 80
            elif any(k in h_low for k in ("skill", "technolog", "stack", "certificat", "tool")):
                b_type = "skills"
                section_tag = "section:skills"
                prio = 70
            elif any(k in h_low for k in ("summar", "profile", "objective", "about")):
                b_type = "summary"
                section_tag = "section:summary"
                prio = 88
            else:
                b_type = "experience"
                section_tag = "section:experience-primary"
                prio = 85

            # Extract lowercase tech tags from content
            detected_tags = [section_tag]
            if b_type == "project":
                detected_tags.append("tier:1")
            for kw in ("python", "sql", "go", "typescript", "javascript", "react", "aws", "docker", "linux", "active directory", "servicenow", "fastapi"):
                if kw in sec_clean.lower():
                    detected_tags.append(kw.replace(" ", "-"))

            slug_id = re.sub(r"[^a-z0-9]+", "-", heading.lower()).strip("-")[:28] or f"block-{idx}"
            blocks.append({
                "id": f"{b_type}-{slug_id}-{idx}",
                "type": b_type,
                "tags": detected_tags,
                "title": heading[:80] if heading else f"{b_type.title()} #{idx}",
                "content": body if body else sec_clean,
                "priority": prio,
            })
            idx += 1

    # 4. Skills block if skills list is provided
    if skills:
        blocks.append({
            "id": "skills-core",
            "type": "skills",
            "tags": ["always", "section:skills"],
            "title": "Core Technical Skills",
            "content": "**Skills & Technologies:** " + ", ".join(skills),
            "priority": 75,
        })

    return blocks


def assemble_local_tailored_resume(
    blocks: List[Dict[str, Any]],
    job_title: str,
    company: str,
    job_description: str,
    matched_skills: Optional[List[str]] = None,
) -> str:
    """
    Selects and orders the most relevant ResumeBlocks for a target job posting
    when generating a customized resume from local candidate blocks.
    """
    jd_lower = f"{job_title} {company} {job_description}".lower()
    jd_words = set(re.findall(r"[a-z0-9+#.-]{2,}", jd_lower))

    def score_block(b: Dict[str, Any]) -> float:
        if "always" in b.get("tags", []):
            return 1000.0 + b.get("priority", 50)
        text_words = set(re.findall(r"[a-z0-9+#.-]{2,}", f"{b.get('title', '')} {b.get('content', '')}".lower()))
        overlap = len(jd_words.intersection(text_words))
        return float(b.get("priority", 50)) + (overlap * 4.5)

    scored = sorted(blocks, key=score_block, reverse=True)
    headers = [b for b in scored if b["type"] == "header"]
    summaries = [b for b in scored if b["type"] == "summary"][:1]
    experiences = [b for b in scored if b["type"] == "experience"][:4]
    projects = [b for b in scored if b["type"] == "project"][:4]
    skill_blocks = [b for b in scored if b["type"] == "skills"][:2]
    education = [b for b in scored if b["type"] == "education"][:2]

    parts: List[str] = []
    for h in headers:
        parts.append(h["content"])
    if summaries:
        parts.append(f"## Targeted Summary ({job_title} @ {company})\n" + summaries[0]["content"])
    if skill_blocks:
        parts.append("## Technical Skills\n" + "\n\n".join(b["content"] for b in skill_blocks))
    if experiences:
        parts.append("## Professional Experience\n" + "\n\n".join(f"### {b['title']}\n{b['content']}" for b in experiences))
    if projects:
        parts.append("## Selected Projects\n" + "\n\n".join(f"### {b['title']}\n{b['content']}" for b in projects))
    if education:
        parts.append("## Education\n" + "\n\n".join(f"### {b['title']}\n{b['content']}" for b in education))

    return "\n\n---\n\n".join(parts)


# ============================================================================
# 3. Hadoku Scraper & JobPlatform Client (scraper.hadoku.me & hadoku.me/jobplatform/api)
# ============================================================================

async def match_companies_on_scraper(
    names: List[str],
    providers: Optional[List[str]] = None,
    explicit_key: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Calls POST https://scraper.hadoku.me/api/v1/jobboards/match
    Given company names (e.g., ["Stripe", "Linear"]), returns the best matched ATS board:
      [{ query, matched, ats, slug, company_name, n_jobs, sample_titles, domain }]
    """
    key = get_hadoku_user_key(explicit_key)
    if not key or not names:
        return []

    payload: Dict[str, Any] = {"names": names}
    if providers:
        payload["providers"] = providers

    async with httpx.AsyncClient(timeout=20.0) as client:
        res = await client.post(
            f"{SCRAPER_API_BASE}/api/v1/jobboards/match",
            headers=_auth_headers(key),
            json=payload,
        )
        if res.status_code == 200:
            body = res.json()
            return (body.get("data") or {}).get("results", [])
        logger.warning(f"scraper /match returned {res.status_code}: {res.text[:250]}")
        return []


async def probe_slugs_on_scraper(
    slugs: List[str],
    providers: Optional[List[str]] = None,
    explicit_key: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Calls POST https://scraper.hadoku.me/api/v1/jobboards/probe
    Probes explicit slugs against Greenhouse, Ashby, and Lever.
    """
    key = get_hadoku_user_key(explicit_key)
    if not key or not slugs:
        return []

    payload: Dict[str, Any] = {"slugs": slugs}
    if providers:
        payload["providers"] = providers

    async with httpx.AsyncClient(timeout=20.0) as client:
        res = await client.post(
            f"{SCRAPER_API_BASE}/api/v1/jobboards/probe",
            headers=_auth_headers(key),
            json=payload,
        )
        if res.status_code == 200:
            body = res.json()
            return (body.get("data") or {}).get("results", [])
        logger.warning(f"scraper /probe returned {res.status_code}: {res.text[:250]}")
        return []


async def list_scraper_targets(
    active_only: bool = True,
    ats: Optional[str] = None,
    explicit_key: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Calls GET https://scraper.hadoku.me/api/v1/jobboards/targets
    Returns { count: int, targets: List[Dict] }
    """
    key = get_hadoku_user_key(explicit_key)
    if not key:
        return {"count": 0, "targets": []}

    params: Dict[str, Any] = {"active_only": str(active_only).lower()}
    if ats:
        params["ats"] = ats

    async with httpx.AsyncClient(timeout=15.0) as client:
        res = await client.get(
            f"{SCRAPER_API_BASE}/api/v1/jobboards/targets",
            headers=_auth_headers(key),
            params=params,
        )
        if res.status_code == 200:
            body = res.json()
            return body.get("data") or {"count": 0, "targets": []}
        return {"count": 0, "targets": []}


async def trigger_scraper_run(explicit_key: Optional[str] = None) -> Dict[str, Any]:
    """
    Calls POST https://scraper.hadoku.me/api/v1/jobboards/search (fire-and-forget 202).
    """
    key = get_hadoku_user_key(explicit_key)
    if not key:
        return {"triggered": False, "error": "No Hadoku vault key configured (.devvault.local.json missing)"}

    async with httpx.AsyncClient(timeout=15.0) as client:
        res = await client.post(
            f"{SCRAPER_API_BASE}/api/v1/jobboards/search",
            headers=_auth_headers(key),
            json={},
        )
        return {
            "triggered": res.status_code in (200, 202),
            "status_code": res.status_code,
            "response": res.json() if res.headers.get("content-type", "").startswith("application/json") else res.text[:200],
        }


async def fetch_hadoku_jobplatform_jobs(
    limit: int = 100,
    page: int = 1,
    workplace: Optional[str] = None,
    min_salary: Optional[int] = None,
    sort: str = "date",
    profile_id: Optional[str] = None,
    explicit_key: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Fetches scraped postings from https://hadoku.me/jobplatform/api/jobs (populated by hadoku-scrape
    across 200+ Greenhouse, Ashby, Lever, RemoteOK, Remotive, and Muse targets).
    Supports profile_id filtering/scoring (e.g., Early Career & Junior Tech profile).
    """
    headers = _auth_headers(explicit_key)
    params: Dict[str, Any] = {
        "limit": min(max(1, limit), 100),
        "page": max(1, page),
        "sort": sort,
    }
    if profile_id:
        params["profile_id"] = profile_id
    if workplace in ("remote", "hybrid", "onsite"):
        params["workplace"] = workplace
    if min_salary and min_salary > 0:
        params["min_salary"] = int(min_salary)

    async with httpx.AsyncClient(timeout=15.0) as client:
        res = await client.get(
            f"{JOBPLATFORM_API_BASE}/jobs",
            headers=headers,
            params=params,
        )
        if res.status_code == 200:
            body = res.json()
            return (body.get("data") or {}).get("jobs", [])
        logger.debug(f"hadoku jobplatform /jobs returned {res.status_code}")
        return []
