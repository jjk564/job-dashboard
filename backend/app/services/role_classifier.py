"""
Orthogonal Role Classification & Profile Scoring Engine.

Infers two orthogonal seniority/track axes from job titles & descriptions:
  - track: 'ic' | 'manager' | 'unknown' (Does this role have direct reports?)
  - level: Position on its track's ladder:
      IC ladder:      junior | mid | senior | staff | principal | fellow
      Manager ladder: manager | senior_manager | director | vp | cxo
  - discipline: 'eng' | 'adjacent' | 'unknown'

Combines hadoku-jobplatform's orthogonal track/level distance scoring with
JobPulse's synonym & implied-competency skill ontology.
"""

import re
from typing import Optional, List, Dict, Any
from .matcher import analyze_job_fit, SKILL_SYNONYMS, extract_tech_keywords

IC_LEVELS = ("junior", "mid", "senior", "staff", "principal", "fellow")
MANAGER_LEVELS = ("manager", "senior_manager", "director", "vp", "cxo")
ALL_LEVELS = IC_LEVELS + MANAGER_LEVELS

ENG_TITLE_RE = re.compile(
    r"\b(?:engineer(?:ing)?|developer|swe|sde|sre|devops|architect|scientist|"
    r"researcher|programmer|technician|sysadmin|administrator|cybersecurity|security|network)\b",
    re.IGNORECASE,
)

ADJACENT_TITLE_RE = re.compile(
    r"|".join([
        r"\b(?:technical\s+)?(?:product|program|project)\s+(?:manager|owner|lead|director)\b",
        r"\btpm\b",
        r"\b(?:product\s+|ux\s+|ui\s+|visual\s+)?designer\b|\bux\b|\bdesign\s+(?:lead|director)\b",
        r"\b(?:marketing|sales|account\s+(?:executive|manager)|partnerships?|business\s+development)\b",
        r"\b(?:recruiter|talent|people\s+ops|human\s+resources|counsel|legal|"
        r"accountant|controller|customer\s+(?:success|support)|community)\b",
        r"\b(?:business|financial|data)\s+analyst\b",
    ]),
    re.IGNORECASE,
)

# Titles that contain 'Manager' or 'Director' in the title head but are IC roles (no direct reports)
IC_QUALIFIED_TITLE_RE = re.compile(
    r"|".join([
        r"\b(?:product|program|project|technical program|account|community|"
        r"partner(?:ship)?|marketing|category|brand|portfolio|delivery|release|"
        r"customer success|social media|content)\s+manager\b",
        r"\b(?:account|partner|client|non[\s-]?executive)\s+director\b",
    ]),
    re.IGNORECASE,
)

CXO_AS_CONTEXT_RE = re.compile(
    r"\b(?:office of|to the|reporting to|support(?:ing)? the)\b",
    re.IGNORECASE,
)

MANAGER_TITLE_RULES = [
    (re.compile(r"\bc[teiofps]o\b|\bchief\b(?! of staff)", re.IGNORECASE), "cxo"),
    (re.compile(r"\b(?:[se]?vp|vice president)\b", re.IGNORECASE), "vp"),
    (re.compile(r"\bhead of\b", re.IGNORECASE), "vp"),
    (re.compile(r"\b(?:senior|sr\.?|group)\s+director\b", re.IGNORECASE), "vp"),
    (re.compile(r"\bdirector\b", re.IGNORECASE), "director"),
    (re.compile(r"\b(?:senior|sr\.?|group)\s+(?:engineering\s+)?manager\b", re.IGNORECASE), "senior_manager"),
    (re.compile(r"\bmanager\b", re.IGNORECASE), "manager"),
    (re.compile(r"\bsupervisor\b", re.IGNORECASE), "manager"),
]

IC_LEVEL_RULES = [
    (re.compile(r"\b(?:distinguished|fellow)\b", re.IGNORECASE), "fellow"),
    (re.compile(r"\bprincipal\b", re.IGNORECASE), "principal"),
    (re.compile(r"(?<!of )(?<!technical )\bstaff\b", re.IGNORECASE), "staff"),
    (re.compile(r"\b(?:senior|sr\.?)\b", re.IGNORECASE), "senior"),
    (
        re.compile(
            r"\b(?:junior|jr\.?|intern|internship|new\s+grad|graduate|entry[\s-]level|apprentice)\b",
            re.IGNORECASE,
        ),
        "junior",
    ),
    (re.compile(r"\bassociate\b", re.IGNORECASE), "junior"),
    (re.compile(r"\b(?:ii|iii)\b", re.IGNORECASE), "mid"),
    (re.compile(r"\bi\b$", re.IGNORECASE), "junior"),
]

AMBIGUOUS_TITLE_RE = re.compile(r"\b(?:lead|leader|leadership)\b", re.IGNORECASE)
TECH_LEAD_RE = re.compile(r"\b(?:tech|technical)\s+lead\b", re.IGNORECASE)

REPORTS_SIGNALS_RE = [
    re.compile(r"\bdirect reports?\b", re.IGNORECASE),
    re.compile(r"\bpeople manage(?:r|ment)\b", re.IGNORECASE),
    re.compile(r"\bmanag(?:e|ing) a team of\b", re.IGNORECASE),
    re.compile(r"\breport(?:s|ing) (?:in)?to you\b", re.IGNORECASE),
    re.compile(r"\bperformance reviews?\b", re.IGNORECASE),
    re.compile(r"\bmanage the (?:career|growth|performance)\b", re.IGNORECASE),
    re.compile(r"\bhiring plan\b", re.IGNORECASE),
    re.compile(r"\bheadcount\b", re.IGNORECASE),
]


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def _title_head(title: str) -> str:
    """Extracts the primary role clause before any comma or spaced dash."""
    match = re.search(r"\s[-–—]\s|,", title)
    return title[: match.start()].strip() if match and match.start() > 0 else title


def _ic_level_from(title: str) -> Optional[str]:
    for pattern, level in IC_LEVEL_RULES:
        if pattern.search(title):
            return level
    return None


def classify_discipline(title: str) -> str:
    t = _normalize(title)
    if not t:
        return "unknown"
    if ENG_TITLE_RE.search(t):
        return "eng"
    if ADJACENT_TITLE_RE.search(t):
        return "adjacent"
    return "unknown"


def classify_role(title: str, description: str = "") -> Dict[str, Optional[str]]:
    """
    Infers (track, level, discipline) for a job posting.
    Returns:
      {
        "track": "ic" | "manager" | "unknown",
        "level": str | None,
        "discipline": "eng" | "adjacent" | "unknown"
      }
    """
    t = _normalize(title)
    if not t:
        return {"track": "unknown", "level": None, "discipline": "unknown"}

    discipline = classify_discipline(t)
    head = _title_head(t)

    # 1. Explicit people-management title in the head (unless IC-qualified like Product Manager)
    if not IC_QUALIFIED_TITLE_RE.search(head):
        for pattern, level in MANAGER_TITLE_RULES:
            if not pattern.search(head):
                continue
            if level == "cxo" and CXO_AS_CONTEXT_RE.search(head):
                break
            return {"track": "manager", "level": level, "discipline": discipline}

    # 2. IC level from full title
    ic_level = _ic_level_from(t)

    # 3. Ambiguous "lead" titles fall back to probing description body for direct-reports signals
    if AMBIGUOUS_TITLE_RE.search(head) and not TECH_LEAD_RE.search(head):
        body = _normalize(description)
        if any(sig.search(body) for sig in REPORTS_SIGNALS_RE):
            return {"track": "manager", "level": "manager", "discipline": discipline}

    return {"track": "ic", "level": ic_level, "discipline": discipline}


def level_track(level: str) -> str:
    return "ic" if level in IC_LEVELS else "manager"


def level_rank(level: str) -> int:
    if level in IC_LEVELS:
        return IC_LEVELS.index(level)
    if level in MANAGER_LEVELS:
        return MANAGER_LEVELS.index(level)
    return -1


def match_level_score(job_level: Optional[str], profile_levels: List[str]) -> float:
    """
    Grades level match by ladder distance (0.0 to 1.0):
      - Profile has no level constraints -> 1.0 (neutral/full pass)
      - Job has no detected level -> 0.65 (neutral signal, not penalized as a mismatch)
      - Exact rung match -> 1.0
      - 1 rung away on the same track -> 0.7
      - Further away or different track -> 0.2
    """
    if not profile_levels:
        return 1.0
    if not job_level:
        return 0.65
    if job_level in profile_levels:
        return 1.0

    job_trk = level_track(job_level)
    job_rnk = level_rank(job_level)
    best = 0.2
    for target in profile_levels:
        if level_track(target) == job_trk:
            dist = abs(job_rnk - level_rank(target))
            if dist == 1:
                best = max(best, 0.7)
    return best


def match_remote_score(job_workplace: Optional[str], remote_pref: str) -> float:
    """Grades workplace type against profile preference."""
    pref = (remote_pref or "any").lower()
    if pref in ("any", "all", ""):
        return 1.0
    wp = (job_workplace or "unknown").lower()
    if wp == "unknown":
        return 0.6
    if wp == pref:
        return 1.0
    if pref == "hybrid" and wp == "remote":
        return 0.85
    if pref == "remote" and wp == "hybrid":
        return 0.5
    return 0.2


def score_job_for_search_profile(
    title: str,
    description: str,
    company: str,
    workplace_type: Optional[str],
    role_track: Optional[str],
    role_level: Optional[str],
    profile_keywords: List[str],
    profile_levels: List[str],
    profile_remote_pref: str = "any",
    profile_companies: Optional[List[str]] = None,
    candidate_skills: Optional[List[str]] = None,
    master_resume_text: str = "",
) -> Dict[str, Any]:
    """
    Computes a unified multi-signal score (0-100) for a job against a SearchProfile,
    blending:
      - keyword_match (0.40): Synonym & implied-competency skill match against description
      - title_match   (0.30): Profile keywords / target role alignment in title
      - level_match   (0.15): Orthogonal seniority ladder distance
      - remote_match  (0.15): Workplace preference alignment
    """
    if not role_track and not role_level:
        classified = classify_role(title, description)
        role_track = classified["track"]
        role_level = classified["level"]

    combined_skills = list(profile_keywords or [])
    if candidate_skills:
        for s in candidate_skills:
            if s not in combined_skills:
                combined_skills.append(s)

    base_fit = analyze_job_fit(
        job_text=f"{title} {description or ''}",
        candidate_skills=combined_skills,
        profile_text=master_resume_text,
    )
    keyword_signal = base_fit["score"] / 100.0

    # Title match signal
    if profile_keywords:
        title_lower = (title or "").lower()
        title_extracted = extract_tech_keywords(title)
        hits = 0
        for kw in profile_keywords:
            kw_norm = kw.lower().strip()
            canonical = SKILL_SYNONYMS.get(kw_norm, kw_norm)
            if kw_norm in title_lower or canonical in title_extracted:
                hits += 1
        title_signal = min(1.0, (hits / max(1, min(len(profile_keywords), 3))) * 0.85 + 0.15) if hits > 0 else 0.45
    else:
        title_signal = keyword_signal

    level_signal = match_level_score(role_level, profile_levels or [])
    remote_signal = match_remote_score(workplace_type, profile_remote_pref)

    weighted = (
        0.40 * keyword_signal
        + 0.30 * title_signal
        + 0.15 * level_signal
        + 0.15 * remote_signal
    )

    # Boost if company is in target_companies
    if profile_companies and company:
        comp_lower = company.lower().strip()
        if any(tc.lower().strip() in comp_lower or comp_lower in tc.lower().strip() for tc in profile_companies if tc):
            weighted = min(0.99, weighted + 0.08)

    final_score = max(10, min(99, int(round(weighted * 100))))

    return {
        "score": final_score,
        "matched_skills": base_fit["matched_skills"],
        "missing_skills": base_fit["missing_skills"],
        "detected_requirements": base_fit["detected_requirements"],
        "role_track": role_track,
        "role_level": role_level,
        "score_breakdown": {
            "keyword_match": round(keyword_signal, 2),
            "title_match": round(title_signal, 2),
            "level_match": round(level_signal, 2),
            "remote_match": round(remote_signal, 2),
        },
        "summary": base_fit["summary"],
    }
