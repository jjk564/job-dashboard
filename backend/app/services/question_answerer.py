"""
Intelligent Application Question Answering & Document Export Engine for JobPulse Autopilot.

1. Answers standard and custom ATS screening questions (Greenhouse, Lever, Ashby, Workable, generic forms)
   using the candidate's Profile, Skills inventory, Master Resume, Job details, and Application Kit.
2. Assigns confidence scores ('high', 'medium', 'manual_needed') so Autopilot knows whether an application
   can be safely auto-submitted or should be routed to the 'Need to Apply' (TO_APPLY) stage.
3. Exports tailored resumes and cover letters to valid local .pdf, .txt, and .md files for ATS file upload fields.
"""
import os
import re
import logging
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parents[2]
PACKETS_DIR = BASE_DIR / "generated_packets"


def _clean_markdown_to_plain(md_text: str) -> str:
    """Strips markdown syntax into clean plain text for PDF rendering and plain-text form fields."""
    if not md_text:
        return ""
    text = re.sub(r"^#{1,6}\s*", "", md_text, flags=re.MULTILINE)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"^---+\s*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def render_text_to_minimal_pdf(title: str, markdown_text: str) -> bytes:
    """
    Renders markdown/plain text into a valid, standard single-or-multi-line PDF 1.4 document
    using built-in Helvetica font with zero external binary dependencies.
    """
    plain = _clean_markdown_to_plain(markdown_text)
    raw_lines = plain.splitlines()
    wrapped_lines: List[str] = []
    for line in raw_lines:
        line_ascii = line.encode("latin-1", errors="replace").decode("latin-1")
        if len(line_ascii) <= 88:
            wrapped_lines.append(line_ascii)
        else:
            words = line_ascii.split(" ")
            curr = ""
            for w in words:
                if len(curr) + len(w) + 1 <= 88:
                    curr = f"{curr} {w}".strip()
                else:
                    if curr:
                        wrapped_lines.append(curr)
                    curr = w
            if curr:
                wrapped_lines.append(curr)

    # Fit up to 52 lines per page
    lines_per_page = 52
    pages_lines = [
        wrapped_lines[i : i + lines_per_page]
        for i in range(0, max(1, len(wrapped_lines)), lines_per_page)
    ]

    def _esc_pdf(s: str) -> str:
        return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    objects: List[bytes] = []

    # Object 1: Catalog
    objects.append(b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")

    # Object 2: Pages placeholder (filled after creating page objects)
    num_pages = len(pages_lines)
    first_page_obj_id = 4
    page_kids = " ".join(f"{first_page_obj_id + i * 2} 0 R" for i in range(num_pages))
    objects.append(
        f"2 0 obj\n<< /Type /Pages /Kids [{page_kids}] /Count {num_pages} >>\nendobj\n".encode("latin-1")
    )

    # Object 3: Font
    objects.append(
        b"3 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
    )

    for idx, p_lines in enumerate(pages_lines):
        page_obj_id = first_page_obj_id + idx * 2
        content_obj_id = page_obj_id + 1

        stream_cmds = ["BT", "/F1 10 Tf", "50 750 Td", "13 TL"]
        for line in p_lines:
            stream_cmds.append(f"({_esc_pdf(line)}) Tj T*")
        stream_cmds.append("ET")
        stream_bytes = "\n".join(stream_cmds).encode("latin-1")

        page_obj = (
            f"{page_obj_id} 0 obj\n"
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_obj_id} 0 R >>\n"
            f"endobj\n"
        ).encode("latin-1")
        content_obj = (
            f"{content_obj_id} 0 obj\n<< /Length {len(stream_bytes)} >>\nstream\n".encode("latin-1")
            + stream_bytes
            + b"\nendstream\nendobj\n"
        )
        objects.append(page_obj)
        objects.append(content_obj)

    # Assemble PDF with xref table
    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objects:
        offsets.append(len(out))
        out.extend(obj)

    xref_pos = len(out)
    out.extend(f"xref\n0 {len(offsets)}\n".encode("latin-1"))
    out.extend(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        out.extend(f"{off:010d} 00000 n \n".encode("latin-1"))

    out.extend(
        f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode("latin-1")
    )
    return bytes(out)


def export_application_files(
    job_id: int,
    company: str,
    job_title: str,
    resume_markdown: str,
    cover_letter_markdown: str,
    candidate_name: Optional[str] = "Justin Kilpatrick",
) -> Dict[str, str]:
    """
    Writes tailored resume and cover letter files (.pdf, .md, .txt) to disk under
    backend/generated_packets/job_{job_id}/ with professional candidate naming
    (e.g., Justin_Kilpatrick_Resume.pdf) and backwards-compatible legacy aliases.
    """
    safe_company = re.sub(r"[^a-zA-Z0-9_-]+", "_", (company or "Company").strip())[:30].strip("_") or "Company"
    job_dir = PACKETS_DIR / f"job_{job_id}_{safe_company}"
    job_dir.mkdir(parents=True, exist_ok=True)

    raw_name = (candidate_name or "Justin Kilpatrick").strip()
    safe_name = re.sub(r"[^\w\s-]", "", raw_name).strip()
    name_slug = "_".join(safe_name.split()) if safe_name else "Justin_Kilpatrick"

    primary_resume_pdf = job_dir / f"{name_slug}_Resume.pdf"
    primary_resume_md = job_dir / f"{name_slug}_Resume.md"
    primary_resume_txt = job_dir / f"{name_slug}_Resume.txt"

    primary_cover_pdf = job_dir / f"{name_slug}_Cover_Letter.pdf"
    primary_cover_md = job_dir / f"{name_slug}_Cover_Letter.md"
    primary_cover_txt = job_dir / f"{name_slug}_Cover_Letter.txt"

    legacy_resume_pdf = job_dir / "Tailored_Resume.pdf"
    legacy_resume_md = job_dir / "Tailored_Resume.md"
    legacy_resume_txt = job_dir / "Tailored_Resume.txt"

    legacy_cover_pdf = job_dir / "Tailored_Cover_Letter.pdf"
    legacy_cover_md = job_dir / "Tailored_Cover_Letter.md"
    legacy_cover_txt = job_dir / "Tailored_Cover_Letter.txt"

    resume_txt_content = _clean_markdown_to_plain(resume_markdown or "")
    resume_pdf_bytes = render_text_to_minimal_pdf(f"Resume - {job_title}", resume_markdown or "")

    cover_txt_content = _clean_markdown_to_plain(cover_letter_markdown or "")
    cover_pdf_bytes = render_text_to_minimal_pdf(f"Cover Letter - {company}", cover_letter_markdown or "")

    primary_md = resume_markdown or ""
    primary_resume_md.write_text(primary_md, encoding="utf-8")
    primary_resume_txt.write_text(resume_txt_content, encoding="utf-8")
    primary_resume_pdf.write_bytes(resume_pdf_bytes)

    primary_cover_md.write_text(cover_letter_markdown or "", encoding="utf-8")
    primary_cover_txt.write_text(cover_txt_content, encoding="utf-8")
    primary_cover_pdf.write_bytes(cover_pdf_bytes)

    # Legacy aliases so existing references or tests never fail
    legacy_resume_md.write_text(primary_md, encoding="utf-8")
    legacy_resume_txt.write_text(resume_txt_content, encoding="utf-8")
    legacy_resume_pdf.write_bytes(resume_pdf_bytes)

    legacy_cover_md.write_text(cover_letter_markdown or "", encoding="utf-8")
    legacy_cover_txt.write_text(cover_txt_content, encoding="utf-8")
    legacy_cover_pdf.write_bytes(cover_pdf_bytes)

    return {
        "directory": str(job_dir),
        "resume_pdf": str(primary_resume_pdf),
        "resume_md": str(primary_resume_md),
        "resume_txt": str(primary_resume_txt),
        "cover_letter_pdf": str(primary_cover_pdf),
        "cover_letter_md": str(primary_cover_md),
        "cover_letter_txt": str(primary_cover_txt),
        "legacy_resume_pdf": str(legacy_resume_pdf),
        "legacy_cover_letter_pdf": str(legacy_cover_pdf),
    }


def _match_option(options: Optional[List[str]], preferred_patterns: List[str]) -> Optional[str]:
    """Finds the best matching dropdown/radio option from a list of available options."""
    if not options:
        return None
    cleaned = [o.strip() for o in options if o and o.strip() and not o.strip().lower().startswith(("select", "choose", "--"))]
    if not cleaned:
        return None

    # Pass 1: Exact matches (case-insensitive)
    for pat in preferred_patterns:
        pat_low = pat.lower().strip()
        for opt in cleaned:
            if pat_low == opt.lower().strip():
                return opt

    # Pass 2: Whole-word boundary matches or multi-word substring matches
    for pat in preferred_patterns:
        pat_low = pat.lower().strip()
        for opt in cleaned:
            opt_low = opt.lower().strip()
            # If pattern contains multiple words, allow substring match
            if " " in pat_low:
                if pat_low in opt_low or opt_low in pat_low:
                    return opt
            else:
                # Single word: match strictly with word boundaries so "no" doesn't match "latino"
                if re.search(r"\b" + re.escape(pat_low) + r"\b", opt_low):
                    return opt

    return None


_US_STATE_FULL_TO_ABBR = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR", "california": "CA",
    "colorado": "CO", "connecticut": "CT", "delaware": "DE", "florida": "FL", "georgia": "GA",
    "hawaii": "HI", "idaho": "ID", "illinois": "IL", "indiana": "IN", "iowa": "IA",
    "kansas": "KS", "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS", "missouri": "MO",
    "montana": "MT", "nebraska": "NE", "nevada": "NV", "new hampshire": "NH", "new jersey": "NJ",
    "new mexico": "NM", "new york": "NY", "north carolina": "NC", "north dakota": "ND", "ohio": "OH",
    "oklahoma": "OK", "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT", "vermont": "VT",
    "virginia": "VA", "washington": "WA", "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY",
    "district of columbia": "DC",
}
_US_ABBR_TO_FULL = {v.lower(): k.title() for k, v in _US_STATE_FULL_TO_ABBR.items()}


def _parse_profile_location_parts(location: str) -> Tuple[str, str, str, str]:
    """
    Splits a profile location like 'Boston, Massachusetts (Remote)' or 'Austin, TX'
    into (clean_full, city, state_full, state_abbr).
    """
    clean_loc = re.sub(r"[\(\[\{].*?[\)\]\}]", "", location or "").split("-")[0].strip()
    if not clean_loc or clean_loc.lower() in ("remote", "united states", "us", "usa"):
        return ("Boston, MA", "Boston", "Massachusetts", "MA")
    parts = [p.strip() for p in clean_loc.split(",") if p.strip()]
    city = parts[0] if parts else "Boston"
    state_full = ""
    state_abbr = ""
    if len(parts) >= 2:
        raw_st = parts[1].strip()
        raw_st_low = raw_st.lower()
        if raw_st_low in _US_STATE_FULL_TO_ABBR:
            state_full = raw_st.title()
            state_abbr = _US_STATE_FULL_TO_ABBR[raw_st_low]
        elif raw_st_low in _US_ABBR_TO_FULL:
            state_abbr = raw_st.upper()
            state_full = _US_ABBR_TO_FULL[raw_st_low]
        else:
            state_full = raw_st
            state_abbr = raw_st
    clean_display = f"{city}, {state_abbr}" if state_abbr else clean_loc
    return (clean_display, city, state_full, state_abbr)


_ROLE_TITLE_WORDS = {
    "engineer", "developer", "technician", "agent", "analyst", "manager",
    "specialist", "coordinator", "intern", "director", "architect", "consultant",
    "administrator", "lead", "associate", "representative", "assistant", "scientist",
    "support", "service", "field", "software", "product", "project", "systems",
}


def _extract_current_company(profile_data: Dict[str, Any]) -> str:
    """Determines the candidate's current/most-recent employer from profile or master resume."""
    direct = (profile_data.get("current_company") or profile_data.get("company") or "").strip()
    if direct:
        return direct
    resume = (profile_data.get("master_resume_text") or "").strip()
    if resume:
        lines = [ln.strip() for ln in resume.splitlines() if ln.strip()]
        # 1. Look right below PROFESSIONAL EXPERIENCE / WORK EXPERIENCE for "Company | City, ST"
        in_exp = False
        for ln in lines:
            up = ln.upper().strip("#* :")
            if up in ("EXPERIENCE", "WORK EXPERIENCE", "PROFESSIONAL EXPERIENCE", "EMPLOYMENT", "EMPLOYMENT HISTORY"):
                in_exp = True
                continue
            if in_exp and up in ("EDUCATION", "PROJECTS", "TECHNICAL PROJECTS", "SKILLS", "CERTIFICATIONS"):
                break
            if in_exp and any(sep in ln for sep in ("|", "—", "–")):
                left = re.split(r"\s*(?:\||—|–)\s*", ln, maxsplit=1)[0].strip("#* ").strip()
                left_words = {w.lower() for w in re.findall(r"[A-Za-z]+", left)}
                if left and 2 <= len(left) <= 45 and not (left_words & _ROLE_TITLE_WORDS):
                    return left
        # 2. Fallback scan for lines with company | City, ST format anywhere
        for ln in lines:
            m = re.match(r"^(?:#{1,4}\s*)?(?:\*\*)?([A-Z][A-Za-z0-9 .&-]{1,40})(?:\*\*)?\s*(?:\||—|–)\s*[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?,\s*[A-Z]{2}\b", ln)
            if m:
                cand = m.group(1).strip()
                cand_words = {w.lower() for w in re.findall(r"[A-Za-z]+", cand)}
                if not (cand_words & _ROLE_TITLE_WORDS):
                    return cand
        if "hyperice" in resume.lower():
            return "Hyperice"
    return "Hyperice"


def answer_single_question(
    question_text: str,
    job_data: Dict[str, Any],
    profile_data: Dict[str, Any],
    candidate_skills: Optional[List[Any]] = None,
    app_kit: Optional[Dict[str, Any]] = None,
    options: Optional[List[str]] = None,
    field_type: str = "text",
    required: bool = True,
) -> Dict[str, Any]:
    """
    Evaluates a single application form question or field label and returns:
      {
        "question": str,
        "answer": str,
        "category": str,
        "confidence": "high" | "medium" | "manual_needed"
      }
    """
    q_raw = (question_text or "").strip()
    # Normalize identifier-style fallback labels like "first-name-input", "firstName", "last_name"
    # Note: only split camelCase when starting with lowercase (e.g. firstName, confirmEmail) so
    # capitalized brand names like "LinkedIn", "GitHub", "GitLab" are never split.
    q_clean = q_raw
    if q_clean and " " not in q_clean:
        has_delim = any(ch in q_clean for ch in ("-", "_"))
        is_lower_camel = bool(re.match(r"^[a-z]+[A-Z]", q_clean))
        if has_delim or is_lower_camel:
            q_clean = re.sub(r"\be-mail\b", "email", q_clean, flags=re.IGNORECASE)
            q_clean = re.sub(r"\bh-1b\b", "h1b", q_clean, flags=re.IGNORECASE)
            if is_lower_camel:
                q_clean = re.sub(r"([a-z])([A-Z])", r"\1 \2", q_clean)
            if has_delim:
                q_clean = re.sub(r"[-_]+", " ", q_clean)
    q = " ".join(q_clean.lower().split())
    # Strip leading/trailing ATS badge noise like "* Address 1", "(required)", "(optional)", "required", "optional", "*", ":"
    q = re.sub(r"\s*\((?:required|optional)\)\s*", " ", q)
    q = re.sub(r"[\s*:]+(?:required|optional)\s*$", "", q)
    q = re.sub(r"^[\s*:]+|[\s*:]+$", "", q).strip()
    ftype = (field_type or "text").lower().strip()

    full_name = (profile_data.get("full_name") or "").strip()
    name_parts = full_name.split()
    first_name = name_parts[0] if name_parts else ""
    last_name = " ".join(name_parts[1:]) if len(name_parts) > 1 else ""
    email = (profile_data.get("email") or "").strip()
    phone = (profile_data.get("phone") or "").strip()
    location = (profile_data.get("location") or "Remote, US").strip()
    clean_location, city_only, state_full, state_abbr = _parse_profile_location_parts(location)
    title = (profile_data.get("title") or "Software Engineer").strip()
    current_company = _extract_current_company(profile_data)
    summary = (profile_data.get("summary") or "").strip()
    linkedin = (profile_data.get("linkedin_url") or "").strip()
    github = (profile_data.get("github_url") or "").strip()
    portfolio = (profile_data.get("portfolio_url") or github or linkedin).strip()
    work_auth = (profile_data.get("work_authorization") or "Authorized to work in the US without sponsorship").strip()
    desired_salary = (profile_data.get("desired_salary") or "").strip()
    notice_period = (profile_data.get("notice_period") or "Immediate / 2 weeks").strip()
    master_resume = (profile_data.get("master_resume_text") or "").strip()

    company = (job_data.get("company") or "the company").strip()
    job_title = (job_data.get("title") or title).strip()

    # Skill names and proficiency map
    skill_map: Dict[str, str] = {}
    if candidate_skills:
        for s in candidate_skills:
            if isinstance(s, dict):
                skill_map[s.get("name", "").lower()] = s.get("proficiency", "intermediate")
            elif hasattr(s, "name"):
                skill_map[getattr(s, "name", "").lower()] = getattr(s, "proficiency", "intermediate")
            elif isinstance(s, str):
                skill_map[s.lower()] = "intermediate"

    matched_skills = []
    fb = job_data.get("fit_breakdown")
    if isinstance(fb, dict):
        matched_skills = fb.get("matched_skills") or []
    if not matched_skills and skill_map:
        matched_skills = list(skill_map.keys())[:5]
    skills_str = ", ".join(matched_skills[:4]) if matched_skills else "Python, TypeScript, SQL, and modern systems"

    # Helper to determine if options look like a Yes/No choice
    is_yes_no_options = bool(
        options
        and len(options) <= 4
        and any(re.search(r"\byes\b", o.lower()) for o in options)
        and any(re.search(r"\bno\b", o.lower()) for o in options)
    )

    # 0. Consent / SMS / Email Communication Opt-In / Privacy Policy / Certification
    # Evaluated BEFORE contact/email/OPT rules so "receive email updates" or "opt out" never triggers email/visa rules!
    if any(k in q for k in (
        "text message", "text messages", "sms opt", "sms updates", "receive text message",
        "receive text", "text messaging", "email updates", "receive emails", "contact you via email",
        "contact you by email", "job alerts", "future opportunities", "talent network",
    )):
        opt = _match_option(options, ["yes - i consent to receiving text messages", "yes - i consent", "i consent", "yes", "true", "agree", "accept"])
        return {
            "question": q_raw,
            "answer": opt or "Yes",
            "category": "consent",
            "confidence": "high",
        }
    if any(k in q for k in (
        "privacy policy", "privacy notice", "acknowledge", "certify that", "consent to",
        "terms and conditions", "terms of service", "agree to", "data processing",
        "gdpr", "candidate privacy", "i confirm that", "true and accurate",
    )):
        opt = _match_option(options, ["yes", "i agree", "i acknowledge", "i consent", "accept", "agree", "confirm"])
        return {
            "question": q_raw,
            "answer": opt or "Yes",
            "category": "consent",
            "confidence": "high",
        }

    # 1. Referral & "How did you hear about us?" (evaluated BEFORE LinkedIn/Website/Email/Name rules!)
    if any(k in q for k in (
        "refer you", "referred you", "referral name", "who referred", "were you referred",
        "employee referral", "referred by an employee", "referrer",
    )):
        if is_yes_no_options:
            opt = _match_option(options, ["no", "none", "neither"])
            return {"question": q_raw, "answer": opt or "No", "category": "referral", "confidence": "high"}
        opt = _match_option(options, ["no", "none", "n/a", "neither", "not applicable"])
        return {
            "question": q_raw,
            "answer": opt or "N/A",
            "category": "referral",
            "confidence": "high",
        }

    if any(k in q for k in (
        "how did you hear", "how did you learn about", "how did you first learn", "first learn about",
        "how did you find", "where did you see", "where did you hear", "where did you find",
        "where did you learn", "referred by", "application source", "job source",
    )) or (q in ("source", "referral source", "lead source") and "open source" not in q):
        src = job_data.get("source") or "Company Career Board"
        preferred = ["job board", "company website", "career page", "careers page", "linkedin", "indeed", "online job board", "other"]
        if src.lower() in ("linkedin", "indeed", "glassdoor", "ziprecruiter"):
            preferred.insert(0, src.lower())
        opt = _match_option(options, preferred)
        return {
            "question": q_raw,
            "answer": opt or (f"{src.title()}" if src.lower() in ("linkedin", "indeed", "glassdoor", "ziprecruiter") else "Company Career Page"),
            "category": "referral",
            "confidence": "high",
        }

    # 2. Standard Contact / Identity Fields
    if any(k in q for k in ("first name", "given name", "firstname")) and not any(x in q for x in ("refer", "manager", "supervisor", "emergency")):
        return {
            "question": q_raw,
            "answer": first_name,
            "category": "contact",
            "confidence": "high" if first_name else "manual_needed",
        }
    if any(k in q for k in ("last name", "family name", "surname", "lastname")) and not any(x in q for x in ("refer", "manager", "supervisor", "emergency")):
        return {
            "question": q_raw,
            "answer": last_name or first_name,
            "category": "contact",
            "confidence": "high" if (last_name or first_name) else "manual_needed",
        }
    if any(k in q for k in ("middle name", "middle initial")):
        return {
            "question": q_raw,
            "answer": "",
            "category": "contact",
            "confidence": "high",
        }
    if (
        q in ("name", "full name", "your name", "legal name", "candidate name", "applicant name")
        or any(k in q for k in ("legal name", "full name", "your full name", "candidate's name", "signature"))
    ) and not any(x in q for x in ("refer", "company", "employer", "school", "university", "manager", "supervisor", "emergency")):
        return {
            "question": q_raw,
            "answer": full_name,
            "category": "contact",
            "confidence": "high" if full_name else "manual_needed",
        }
    if "preferred name" in q or "nickname" in q:
        return {
            "question": q_raw,
            "answer": first_name or full_name,
            "category": "contact",
            "confidence": "high",
        }
    if "pronoun" in q:
        opt = _match_option(options, ["he/him/his", "he/him", "he / him", "he"])
        return {
            "question": q_raw,
            "answer": opt or "He/him/his",
            "category": "contact",
            "confidence": "high",
        }
    if "email" in q and not any(x in q for x in ("refer", "manager", "supervisor", "emergency", "receive", "consent", "subscribe", "alert")):
        return {
            "question": q_raw,
            "answer": email,
            "category": "contact",
            "confidence": "high" if email else "manual_needed",
        }
    if (
        re.match(
            r"^(?:name\s+)?(?:prefix|salutation|suffix|middle(?:\s+(?:name|initial))?|former\s+name|maiden\s+name|previous\s+name|other\s+name)\b",
            q,
        )
        or any(k in q for k in (
            "phone extension", "phone ext", "extension number",
            "secondary phone", "alternate phone", "other phone", "additional phone", "second phone",
        ))
    ):
        return {
            "question": q_raw,
            "answer": "",
            "category": "contact",
            "confidence": "high" if not required else "manual_needed",
        }
    if any(k in q for k in ("phone type", "phone device type", "device type", "type of phone", "number type")):
        opt = _match_option(options, ["mobile", "cell", "cellular", "personal", "home"])
        return {
            "question": q_raw,
            "answer": opt or "Mobile",
            "category": "contact",
            "confidence": "high",
        }
    if ("country code" in q or "dial code" in q or "calling code" in q) or ("country" in q and "phone" in q):
        opt = _match_option(options, ["united states (+1)", "united states +1", "+1", "us +1", "united states", "usa"])
        return {
            "question": q_raw,
            "answer": opt or "+1",
            "category": "contact",
            "confidence": "high",
        }
    if any(k in q for k in ("phone", "mobile", "telephone", "cell")) and not any(x in q for x in ("refer", "manager", "supervisor", "emergency", "extension", "ext", "type")):
        return {
            "question": q_raw,
            "answer": phone,
            "category": "contact",
            "confidence": "high" if phone else "manual_needed",
        }

    # 3. Links & Profiles (avoid matching open-ended questions that merely mention a platform)
    if "linkedin" in q and (len(q) <= 80 or any(w in q for w in ("url", "link", "profile", "account", "page"))):
        return {
            "question": q_raw,
            "answer": linkedin,
            "category": "links",
            "confidence": "high" if linkedin else ("medium" if not required else "manual_needed"),
        }
    if any(k in q for k in ("github", "gitlab", "bitbucket")) and (len(q) <= 85 or any(w in q for w in ("url", "link", "profile", "handle", "username", "repo"))):
        return {
            "question": q_raw,
            "answer": github,
            "category": "links",
            "confidence": "high" if github else ("medium" if not required else "manual_needed"),
        }
    if any(k in q for k in ("twitter", "x url", "x profile", "x handle", "dribbble", "behance", "instagram", "facebook", "stackoverflow", "stack overflow", "kaggle")):
        return {
            "question": q_raw,
            "answer": "",
            "category": "links",
            "confidence": "high" if not required else "manual_needed",
        }
    if any(k in q for k in ("portfolio", "personal website", "personal site", "other website", "other url", "website url", "blog")) or q in ("website", "url", "portfolio"):
        return {
            "question": q_raw,
            "answer": portfolio,
            "category": "links",
            "confidence": "high" if portfolio else "medium",
        }

    # 4. Work Authorization & Visa Sponsorship (evaluated before country/location so 'authorized to work in the United States' matches work auth)
    needs_sponsorship = "require sponsorship" in work_auth.lower() and "without" not in work_auth.lower()

    if any(k in q for k in ("export control", "export controls", "itar", "u.s. export", "us export", "u.s. person under", "us person under", "eligible under u.s. law to receive information")):
        opt = _match_option(options, ["yes", "u.s. citizen", "us citizen", "u.s. person", "authorized", "permanent resident"])
        return {
            "question": q_raw,
            "answer": opt or "Yes",
            "category": "work_authorization",
            "confidence": "high",
        }

    # 4a. Positive "...without sponsorship" phrasing (e.g. "Are you eligible to work without required sponsorship?")
    is_work_without_sponsorship_q = (
        "without" in q
        and any(k in q for k in ("sponsorship", "visa"))
        and any(k in q for k in ("work", "employ", "eligible", "authorized", "able"))
    )
    if is_work_without_sponsorship_q:
        desired_auth = "No" if needs_sponsorship else "Yes"
        opt = _match_option(
            options,
            ["yes", "authorized", "u.s. citizen", "us citizen", "citizen", "permanent resident"]
            if desired_auth == "Yes"
            else ["no", "require sponsorship"],
        )
        return {
            "question": q_raw,
            "answer": opt or (desired_auth if options is not None or "?" in q_raw or ftype in ("select", "combobox", "radio") else work_auth),
            "category": "work_authorization",
            "confidence": "high",
        }

    # 4b. Questions asking if candidate requires sponsorship — MUST run BEFORE generic "work authorization" check,
    #     because sponsorship helper text frequently mentions "current work authorization" / OPT / CPT!
    has_negated_sponsorship = any(
        neg in q for neg in ("not require sponsorship", "no sponsorship", "don't require sponsorship", "do not require sponsorship")
    )
    if not has_negated_sponsorship and any(k in q for k in (
        "require sponsorship", "need sponsorship", "require visa", "require immigration",
        "sponsorship for employment", "sponsorship now or in the future",
        "sponsorship in the future", "in the future require sponsorship",
        "will you in the future require", "will you now or in the future require",
        "require any visa",
    )):
        desired = "Yes" if needs_sponsorship else "No"
        opt = _match_option(options, [desired, "no", "do not require", "not require"] if not needs_sponsorship else ["yes", "require"])
        return {
            "question": q_raw,
            "answer": opt or desired,
            "category": "work_authorization",
            "confidence": "high",
        }

    # 4c. Questions asking if the candidate is legally authorized/eligible to work
    if any(k in q for k in (
        "authorized to work", "legally authorized", "work authorization",
        "right to work", "eligible to work", "legally eligible",
        "legally permitted to work", "permitted to work",
    )):
        opt = _match_option(options, ["yes", "authorized", "u.s. citizen", "us citizen", "citizen", "permanent resident"])
        return {
            "question": q_raw,
            "answer": opt or ("Yes" if options is not None or "?" in q_raw or ftype in ("select", "combobox", "radio") else work_auth),
            "category": "work_authorization",
            "confidence": "high",
        }

    if any(k in q for k in ("sponsorship", "visa", "h-1b", "h1b", "cpt", "immigration")) or (re.search(r"\bopt\b", q) and not re.search(r"\bopt[- ](out|in)\b", q)):
        desired = "Yes" if needs_sponsorship else "No"
        opt = _match_option(options, [desired, "no", "do not require", "not require"] if not needs_sponsorship else ["yes", "require"])
        return {
            "question": q_raw,
            "answer": opt or desired,
            "category": "work_authorization",
            "confidence": "high",
        }

    if any(k in q for k in ("security clearance", "active clearance", "ts/sci", "secret clearance")):
        has_clearance = "clearance" in master_resume.lower() or "clearance" in summary.lower()
        ans = "Yes" if has_clearance else "No"
        opt = _match_option(options, [ans, "none", "no"])
        return {
            "question": q_raw,
            "answer": opt or ans,
            "category": "work_authorization",
            "confidence": "high" if has_clearance else "medium",
        }

    # 5. Location / Relocation / Country / City / State / Postal / Street
    if any(k in q for k in (
        "relocat", "willing to move", "commute to", "work on-site", "work onsite",
        "work in the office", "days a week", "in-office", "in office", "residing in",
        "hybrid schedule", "workplace arrangement", "work arrangement", "remote / hybrid",
    )):
        wp = (job_data.get("workplace_type") or "remote").lower()
        opt = _match_option(options, ["yes", "open", "willing"])
        return {
            "question": q_raw,
            "answer": opt or ("Yes" if wp in ("remote", "hybrid") or options is not None or "?" in q_raw else "Yes, open to relocation / hybrid schedule"),
            "category": "location",
            "confidence": "high",
        }

    # Separate Zip / Postal Code field (never paste location or essay if unknown)
    if re.search(r"\b(?:zip|postal)(?:\s*/\s*(?:zip|postal))?\s*code\b|\bzipcode\b|^zip$|^postal$|^zip\s*/\s*postal$|^postal\s*/\s*zip$", q):
        zip_val = (profile_data.get("zip_code") or profile_data.get("postal_code") or "").strip()
        return {
            "question": q_raw,
            "answer": zip_val,
            "category": "location",
            "confidence": "high" if zip_val else "manual_needed",
        }

    # Optional Address Line 2 / Apt / Suite (skip silently if not required)
    if re.search(r"\baddress\s*(?:line\s*)?2\b|\b(?:apt|apartment|suite|unit|bldg)\b", q):
        addr2_val = (profile_data.get("address_line_2") or "").strip()
        return {
            "question": q_raw,
            "answer": addr2_val,
            "category": "location",
            "confidence": "high" if (addr2_val or not required) else "manual_needed",
        }

    # Separate Street / Mailing Address field (strict — avoids "address a problem" or "address gaps")
    if re.search(r"\b(?:street|mailing|home|residential|physical|current)\s+address\b|^address(?:\s*(?:line\s*)?1)?$|^address\s*(?:line\s*)?1\b", q):
        addr_val = (profile_data.get("street_address") or "").strip()
        return {
            "question": q_raw,
            "answer": addr_val,
            "category": "location",
            "confidence": "high" if addr_val else "manual_needed",
        }

    # Separate State / Province field (strict — NEVER matches "please state your..." or "decline to state"!)
    if (
        q in (
            "state", "state/province", "state / province", "state/province/region",
            "state / province / region", "province", "state of residence", "us state",
            "state or province", "home state", "current state", "region/state",
        )
        or re.search(r"\b(?:which|what)\s+(?:u\.?s\.?\s+)?state\b|\bstate\s*/\s*province\b|\bstate\s+of\s+residence\b|\bstate\s+or\s+province\b", q)
    ):
        opt = _match_option(options, [state_full, state_abbr, "massachusetts", "ma"])
        return {
            "question": q_raw,
            "answer": opt or state_full or state_abbr or "Massachusetts",
            "category": "location",
            "confidence": "high",
        }

    # Separate City field
    if q in ("city", "city/town", "city / town", "town", "town/city", "current city", "home city", "city of residence") or re.search(r"\b(?:which|what)\s+city\b", q):
        opt = _match_option(options, [city_only, clean_location, "boston"])
        return {
            "question": q_raw,
            "answer": opt or city_only or "Boston",
            "category": "location",
            "confidence": "high",
        }

    if any(k in q for k in ("country", "united states", "reside in the us", "based in the us", "located in the us")):
        opt = _match_option(options, ["united states of america", "united states", "usa", "u.s.", "us", "yes"])
        is_yn_q = any(k in q for k in ("reside in", "based in", "located in", "are you in", "do you live in"))
        return {
            "question": q_raw,
            "answer": opt or ("Yes" if is_yn_q else "United States"),
            "category": "location",
            "confidence": "high",
        }

    if any(k in q for k in (
        "city, state", "city/state", "current location", "location",
        "place of residence", "residence", "where are you based",
        "where do you live", "where you live", "where are you located",
        "time zone", "timezone",
    )):
        if "time zone" in q or "timezone" in q:
            opt = _match_option(options, ["eastern", "est", "edt", "et", "utc-5", "america/new_york"])
            return {"question": q_raw, "answer": opt or "Eastern Time (ET)", "category": "location", "confidence": "high"}
        loc_val = clean_location or "Boston, MA"
        opt = _match_option(options, [loc_val, city_only, state_full, state_abbr, "boston", "massachusetts", "remote", "united states"])
        return {
            "question": q_raw,
            "answer": opt or loc_val,
            "category": "location",
            "confidence": "high" if location else "medium",
        }

    # Remote Connectivity / High-Speed Internet / Equipment Requirements
    if any(k in q for k in (
        "internet connection", "high-speed internet", "download and", "upload speeds",
        "mbps", "working remotely?", "meet this requirement while working remotely",
        "reliable high-speed", "vpn access", "home office",
    )):
        opt = _match_option(options, ["yes", "meet requirement", "agree", "i am able"])
        return {
            "question": q_raw,
            "answer": opt or "Yes",
            "category": "remote_requirements",
            "confidence": "high",
        }

    # 6. Compensation & Salary Expectations
    if any(k in q for k in ("salary expectations align", "align with the posted salary", "within the posted salary", "posted salary range", "salary expectations within", "comfortable with the salary", "comfortable with the compensation")):
        opt = _match_option(options, ["yes", "align", "agree"])
        return {
            "question": q_raw,
            "answer": opt or "Yes",
            "category": "compensation",
            "confidence": "high",
        }

    if any(k in q for k in ("salary", "compensation", "pay expectation", "desired pay", "hourly rate", "annual base", "expected pay", "base pay")):
        if is_yes_no_options:
            opt_yn = _match_option(options, ["yes", "acceptable", "agree"])
            if opt_yn:
                return {"question": q_raw, "answer": opt_yn, "category": "compensation", "confidence": "high"}

        sal_ans = desired_salary
        if not sal_ans:
            s_min = job_data.get("salary_min")
            s_max = job_data.get("salary_max")
            if s_min and s_max:
                sal_ans = f"${int(s_min):,} - ${int(s_max):,}"
            elif s_min:
                sal_ans = f"${int(s_min):,}"
            elif app_kit and app_kit.get("salary_line"):
                sal_ans = app_kit["salary_line"]
            else:
                sal_ans = "$70,000"
        if ftype == "number" or "hourly" in q:
            nums = [int(n) for n in re.findall(r"\d+", sal_ans.replace(",", "")) if int(n) >= 1000]
            if "hourly" in q:
                hr_val = str(round((nums[0] if nums else 70000) / 2080))
                return {"question": q_raw, "answer": hr_val if ftype == "number" else f"${hr_val}/hr", "category": "compensation", "confidence": "high"}
            num_val = str(nums[0]) if nums else "70000"
            return {"question": q_raw, "answer": num_val, "category": "compensation", "confidence": "high"}
        return {
            "question": q_raw,
            "answer": sal_ans,
            "category": "compensation",
            "confidence": "high",
        }

    # 7. Notice Period / Start Date / Availability
    if any(k in q for k in ("notice period", "when can you start", "start date", "earliest start", "availability", "available to start", "available for", "date available")):
        if ftype == "date":
            iso_date = (date.today() + timedelta(days=14)).isoformat()
            return {"question": q_raw, "answer": iso_date, "category": "availability", "confidence": "high"}
        opt = _match_option(options, ["yes", notice_period, "2 weeks", "two weeks", "immediately", "immediate", "1-2 weeks", "less than 2 weeks"])
        return {
            "question": q_raw,
            "answer": opt or ("Yes" if "available for" in q or is_yes_no_options else notice_period),
            "category": "availability",
            "confidence": "high",
        }

    if ftype == "date" and any(k in q for k in ("today", "date signed", "signature date", "current date")):
        return {"question": q_raw, "answer": date.today().isoformat(), "category": "compliance", "confidence": "high"}

    # 8. Years of Experience
    if any(k in q for k in ("years of experience", "how many years", "years working with", "years of professional", "years have you", "experience level")):
        years = "3"
        for sk_name, prof in skill_map.items():
            if sk_name and len(sk_name) >= 2 and re.search(r"\b" + re.escape(sk_name) + r"\b", q):
                years = "5" if prof == "expert" else ("3" if prof == "intermediate" else "1")
                break
        if is_yes_no_options:
            opt_yn = _match_option(options, ["yes"])
            return {"question": q_raw, "answer": opt_yn or "Yes", "category": "experience", "confidence": "high"}
        opt = _match_option(options, [f"{years}", f"{years} years", "3-5", "2-4", "1-3", "3+", "2+", "entry", "junior"])
        ans = opt or (years if ftype == "number" else f"{years}+ years")
        return {
            "question": q_raw,
            "answer": ans,
            "category": "experience",
            "confidence": "high",
        }

    # 9. Education / Degree / University / School / Discipline / Graduation Date
    if any(k in q for k in ("high school", "ged", "high-school")):
        opt = _match_option(options, ["yes", "completed", "graduated"])
        return {"question": q_raw, "answer": opt or "Yes", "category": "education", "confidence": "high"}

    if q in ("school", "university", "college", "school name", "university name", "institution") or (
        any(k in q for k in ("school", "university", "institution")) and not is_yes_no_options and "do you have" not in q
    ):
        opt = _match_option(options, ["university of massachusetts lowell", "umass lowell", "university of massachusetts", "other"])
        return {
            "question": q_raw,
            "answer": opt or "University of Massachusetts Lowell",
            "category": "education",
            "confidence": "high",
        }
    if q in ("discipline", "major", "field of study", "area of study") or any(k in q for k in ("discipline", "field of study", "area of study", "major")):
        opt = _match_option(options, ["computer science", "mathematics", "math", "information technology", "software engineering", "engineering", "other"])
        return {
            "question": q_raw,
            "answer": opt or "Mathematics & Computer Science",
            "category": "education",
            "confidence": "high",
        }
    if any(k in q for k in ("graduation date", "grad date", "when did you graduate", "expected graduation", "date of graduation")):
        if ftype == "date":
            return {"question": q_raw, "answer": "2024-05-15", "category": "education", "confidence": "high"}
        opt = _match_option(options, ["may 2024", "2024", "may 2025", "2025", "graduated", "already graduated"])
        return {
            "question": q_raw,
            "answer": opt or "May 2024",
            "category": "education",
            "confidence": "high",
        }
    if any(k in q for k in ("gpa", "grade point average", "cumulative gpa", "overall gpa")):
        opt = _match_option(options, ["3.5", "3.5 - 4.0", "3.0 - 3.5", "3.5+", "3.0+", "n/a", "na"])
        return {
            "question": q_raw,
            "answer": opt or "3.5",
            "category": "education",
            "confidence": "high",
        }
    if any(k in q for k in ("end date month", "graduation month", "start date month")):
        opt = _match_option(options, ["may", "05", "june", "september"])
        return {
            "question": q_raw,
            "answer": opt or "May",
            "category": "education",
            "confidence": "high",
        }
    if any(k in q for k in ("end date year", "graduation year", "year of graduation", "start date year")):
        opt = _match_option(options, ["2024", "2025", "2026"])
        return {
            "question": q_raw,
            "answer": opt or "2024",
            "category": "education",
            "confidence": "high",
        }
    if any(k in q for k in ("highest level of education", "degree", "education level", "bachelor", "college")):
        if is_yes_no_options or q.startswith(("do you have", "have you completed", "have you earned", "have you obtained")):
            opt = _match_option(options, ["yes"])
            return {"question": q_raw, "answer": opt or "Yes", "category": "education", "confidence": "high"}
        opt = _match_option(options, ["bachelor's degree", "bachelor", "b.s.", "b.a.", "bs", "ba", "4-year", "college", "yes"])
        return {
            "question": q_raw,
            "answer": opt or "Bachelor's Degree",
            "category": "education",
            "confidence": "high",
        }

    # 10. Current Company / Current Title
    if any(k in q for k in (
        "current title", "current job title", "most recent title", "current role",
        "headline", "position title", "role title", "job title",
    )) or q in ("title", "position"):
        return {
            "question": q_raw,
            "answer": title,
            "category": "experience",
            "confidence": "high",
        }
    if any(k in q for k in (
        "current company", "current employer", "most recent employer", "most recent company",
        "company name", "employer name", "organization name", "business name",
        "name of employer", "name of company",
    )) or q in ("company", "employer", "organization"):
        return {
            "question": q_raw,
            "answer": current_company,
            "category": "experience",
            "confidence": "high",
        }

    # 11. Essential Job Functions (ADA) / Previously employed / Applied before / Government / Non-compete / Accommodations
    # MUST be evaluated BEFORE the general "accommodation" rule so "Can you perform the essential functions
    # with or without reasonable accommodation?" answers "Yes" (NOT "No"!).
    if any(k in q for k in (
        "essential functions", "essential duties", "essential job functions",
        "essential requirements of the", "independently perform",
        "perform the duties of the position", "perform the duties of this",
        "perform the job functions", "perform the tasks",
    )):
        opt = _match_option(options, ["yes", "i am able", "able", "agree"])
        return {
            "question": q_raw,
            "answer": opt or "Yes",
            "category": "compliance",
            "confidence": "high",
        }

    if any(k in q for k in ("accommodation", "accessible", "interview process more accessible", "accessible and inclusive")):
        opt = _match_option(options, ["i do not require accommodations", "no accommodations needed", "no", "none", "not require"])
        return {
            "question": q_raw,
            "answer": opt or "I do not require accommodations",
            "category": "accommodations",
            "confidence": "high",
        }
    if any(k in q for k in (
        "previously worked", "ever worked for", "ever worked at", "ever been employed",
        "previously employed", "previously been employed", "been employed at", "been employed by",
        "former employee", "applied before", "previously applied", "non-compete", "noncompete",
        "non-disclosure", "non-solicit", "restrictive covenant", "government official",
        "related to anyone", "family member working", "relative working", "conflict of interest",
        "affiliated with", "worked for us",
    )):
        opt = _match_option(options, ["no", "never", "none", "n/a", "neither"])
        return {
            "question": q_raw,
            "answer": opt or "No",
            "category": "compliance",
            "confidence": "high",
        }
    if any(k in q for k in ("at least 18", "18 years of age", "18 years old", "legal age")):
        opt = _match_option(options, ["yes"])
        return {
            "question": q_raw,
            "answer": opt or "Yes",
            "category": "compliance",
            "confidence": "high",
        }

    # Background Check / Drug Screening / Criminal History
    if any(k in q for k in ("background check", "background screening", "drug test", "drug screen", "substance test", "pre-employment background")):
        opt = _match_option(options, ["yes", "i agree", "willing", "consent", "accept"])
        return {
            "question": q_raw,
            "answer": opt or "Yes",
            "category": "background_check",
            "confidence": "high",
        }
    if any(k in q for k in ("convicted of a felony", "criminal conviction", "criminal history")):
        opt = _match_option(options, ["no", "decline", "prefer not"])
        return {
            "question": q_raw,
            "answer": opt or "No",
            "category": "background_check",
            "confidence": "high",
        }

    # 12. EEO / Voluntary Self-Identification (Gender, Race, Ethnicity, Veteran, Disability)
    if (re.search(r"\b(?:gender|sex)\b", q)) and "sexual orientation" not in q:
        opt = _match_option(options, ["male", "man", "cisgender male", "he/him", "he/him/his", "decline to self-identify", "prefer not to say"])
        return {
            "question": q_raw,
            "answer": opt or "Male",
            "category": "eeo",
            "confidence": "high",
        }

    # Race / Ethnicity (evaluated before standalone Hispanic check so options containing Latino don't hijack Race)
    if any(k in q for k in ("race", "ethnicity", "ethnic origin", "racial", "demographic")):
        opt = _match_option(
            options,
            [
                "white (not hispanic or latino)", "white", "caucasian",
                "decline to self-identify", "decline to state", "i do not wish to answer", "prefer not to say", "decline",
                "choose not to disclose",
            ],
        )
        return {
            "question": q_raw,
            "answer": opt or "White (Not Hispanic or Latino)",
            "category": "eeo",
            "confidence": "high",
        }

    # Hispanic / Latino ethnicity check (standalone question)
    if any(k in q for k in ("hispanic", "latino", "latinx")):
        opt = _match_option(
            options,
            [
                "no", "not hispanic", "not hispanic or latino", "no, i am not", "no, not hispanic",
                "decline to self-identify", "decline to state", "i do not wish to answer", "prefer not to say",
            ],
        )
        return {
            "question": q_raw,
            "answer": opt or "No",
            "category": "eeo",
            "confidence": "high",
        }

    # Veteran Status
    if any(k in q for k in ("veteran", "military")):
        opt = _match_option(
            options,
            [
                "i am not a protected veteran", "no, i am not a protected veteran", "not a protected veteran",
                "not a veteran", "i am not a veteran", "no",
                "decline to self-identify", "i do not wish to answer", "prefer not to say",
            ],
        )
        return {
            "question": q_raw,
            "answer": opt or "I am not a protected veteran",
            "category": "eeo",
            "confidence": "high",
        }

    # Disability Status
    if any(k in q for k in ("disability", "handicap", "impairment")):
        opt = _match_option(
            options,
            [
                "no, i do not have a disability", "no, i don't have a disability",
                "no, i do not have a disability and have not had one in the past",
                "i do not have a disability", "no disability", "no",
                "i do not wish to answer", "i don't wish to answer", "decline to self-identify", "prefer not to say",
            ],
        )
        return {
            "question": q_raw,
            "answer": opt or "No, I do not have a disability",
            "category": "eeo",
            "confidence": "high",
        }

    if any(k in q for k in ("sexual orientation", "lgbtq", "transgender")):
        opt = _match_option(
            options,
            [
                "no", "heterosexual", "straight",
                "decline to self-identify", "i do not wish to answer", "prefer not to say",
            ],
        )
        return {
            "question": q_raw,
            "answer": opt or "Decline to self-identify",
            "category": "eeo",
            "confidence": "high",
        }

    # 13. Motivation / Why This Company / Why This Role / Cover Letter / Summary
    if any(k in q for k in ("passionate about testing", "passionate about qa", "quality assurance", "passion for qa", "passion for testing", "testing and qa", "why qa", "why testing")):
        qa_ans = (
            "I am passionate about Testing and QA because robust quality engineering is what transforms complex software into reliable, trustworthy systems. "
            "I thrive on designing thorough test strategies, isolating edge cases early, and writing automated tests in Python and modern frameworks to ensure "
            "end-users experience seamless, defect-free products. Combining my hardware diagnostic precision with software quality methodologies gives me a natural "
            "drive for uncovering root causes and continuously elevating software reliability."
        )
        return {
            "question": q_raw,
            "answer": qa_ans,
            "category": "motivation",
            "confidence": "high",
        }

    if any(k in q for k in (
        "not obvious from your resume", "isn't obvious from your resume", "not on your resume",
        "share about yourself", "tell us something about yourself", "outside of your resume", "more about yourself",
    )):
        share_ans = (
            "Outside of my resume bullets, I have an innate curiosity for reverse-engineering complex systems and removing friction through automated tooling. "
            "Whether I am experimenting with local AI workflows, optimizing developer pipelines, or diagnosing intricate hardware-software interfaces, I bring "
            "a disciplined diagnostic mindset, strong technical empathy, and genuine enthusiasm for collaborative team problem-solving."
        )
        return {
            "question": q_raw,
            "answer": share_ans,
            "category": "about_me",
            "confidence": "high",
        }

    if any(k in q for k in ("why do you want", "why are you interested", "what excites you", "why this role", f"why {company.lower()}", "what draws you", "passionate about", "passion for")):
        why_ans = (
            (app_kit or {}).get("why_hook")
            or f"I am drawn to {company}'s technical mission and the opportunity to contribute to the {job_title} role using my hands-on experience in {skills_str}. {summary}".strip()
        )
        return {
            "question": q_raw,
            "answer": why_ans,
            "category": "motivation",
            "confidence": "high",
        }

    if any(k in q for k in (
        "cover letter", "additional information", "anything else",
        "note to hiring", "message to hiring", "message to the hiring",
        "hiring manager", "hiring team", "about your interest",
        "interest working", "interest in working",
    )) or (
        ftype == "textarea" and any(k in q for k in ("professional summary", "profile summary", "summary"))
    ):
        cl_ans = (
            (app_kit or {}).get("why_hook")
            or f"Thank you for considering my application for {job_title} at {company}. With strong experience in {skills_str}, I am excited to help deliver reliable, high-impact solutions for your team."
        )
        return {
            "question": q_raw,
            "answer": cl_ans,
            "category": "cover_letter",
            "confidence": "high",
        }

    # 14. Technical Project / Experience Open-Ended Prompts (only for textareas or explicit prompt questions, NOT Yes/No radios)
    if any(k in q for k in (
        "describe a project", "technical project", "relevant project", "project or system",
        "challenging problem", "technical challenge", "tell us about", "proud of", "have you built",
    )):
        proj_ans = (
            f"In my work as a {title}, I architected and delivered production systems leveraging {skills_str}—"
            f"focusing on reliability, automated testing, and clean API design. {summary}".strip()
        )
        return {
            "question": q_raw,
            "answer": proj_ans,
            "category": "technical_open_ended",
            "confidence": "high",
        }

    if "experience with" in q:
        if is_yes_no_options:
            # Check if any candidate skill matches the question
            has_skill = any(sk and len(sk) >= 2 and re.search(r"\b" + re.escape(sk) + r"\b", q) for sk in skill_map.keys())
            if has_skill:
                opt = _match_option(options, ["yes"])
                return {"question": q_raw, "answer": opt or "Yes", "category": "experience", "confidence": "high"}
            # Unknown skill Yes/No: don't guess!
            return {"question": q_raw, "answer": "", "category": "custom", "confidence": "manual_needed"}
        if ftype == "textarea":
            proj_ans = (
                f"In my work as a {title}, I have hands-on experience leveraging {skills_str} to design, test, "
                f"and ship reliable production software. {summary}".strip()
            )
            return {"question": q_raw, "answer": proj_ans, "category": "technical_open_ended", "confidence": "medium"}

    # 15. Specific Cultural / Ranking / Short Stints Custom Prompts
    if any(k in q for k in ("coffee", "wi-fi", "wifi")) and any(k in q for k in ("coworkers", "snacks", "being right")):
        ranking_ans = (
            "1. Wi-Fi: High-speed, reliable connectivity is foundational for remote engineering, team collaboration, and shipping code.\n"
            "2. Good coworkers: A supportive, communicative team drives collective problem-solving, code quality, and engineering velocity.\n"
            "3. Coffee: Essential fuel for sustained focus during deep engineering sessions.\n"
            "4. Snacks: Great productivity booster for long problem-solving stretches.\n"
            "5. Being right: Delivering the right technical solution for the team and product matters far more than individual ego."
        )
        return {
            "question": q_raw,
            "answer": ranking_ans,
            "category": "culture_fit",
            "confidence": "high",
        }

    if any(k in q for k in ("short stints", "gaps in your resume", "gap in employment", "clarify about your previous experience", "taken a break to travel")):
        gaps_ans = (
            "I have a continuous record of technical growth and hands-on engineering experience across hardware diagnostics, "
            "systems administration, and full-stack software development with no unexplained employment gaps."
        )
        return {
            "question": q_raw,
            "answer": gaps_ans,
            "category": "experience_clarification",
            "confidence": "high",
        }

    # 16. Check pre-drafted screening_answers from Hadoku application_kit
    if app_kit and app_kit.get("screening_answers"):
        for item in app_kit["screening_answers"]:
            kit_q = (item.get("q") or "").lower()
            kit_a = (item.get("a") or "").strip()
            if kit_q and kit_a and (kit_q in q or q in kit_q):
                return {
                    "question": q_raw,
                    "answer": kit_a,
                    "category": "screening",
                    "confidence": "high",
                }

    # 17. Unrecognized custom question: NEVER paste generic essays into short inputs or pick options[0] blindly!
    if options is not None or ftype in ("select", "combobox", "radio", "checkbox", "number", "date", "tel", "email", "url"):
        return {
            "question": q_raw,
            "answer": "",
            "category": "custom",
            "confidence": "manual_needed",
        }

    # For unrecognized short single-line text inputs, leave empty and flag manual_needed so we never put wrong info in a box!
    if ftype != "textarea":
        return {
            "question": q_raw,
            "answer": "",
            "category": "custom",
            "confidence": "manual_needed",
        }

    # For unrecognized open-ended textareas, provide a draft in Q&A bank but mark manual_needed so autofill flags it cleanly
    fallback_ans = (
        f"As a {title} with experience in {skills_str}, I have consistently delivered scalable, well-tested solutions "
        f"that align with {company}'s requirements for the {job_title} position."
    )
    return {
        "question": q_raw,
        "answer": fallback_ans,
        "category": "custom",
        "confidence": "manual_needed",
    }


def extract_custom_questions_from_description(description: str) -> List[str]:
    """
    Scans a job description for embedded application questions (e.g. 'In your application, please answer...').
    """
    if not description:
        return []
    questions: List[str] = []
    for line in description.splitlines():
        clean = line.strip().lstrip("-*•0123456789.) ").strip()
        if 15 <= len(clean) <= 180 and clean.endswith("?"):
            low = clean.lower()
            if any(w in low for w in ("you", "your", "experience", "why", "how", "what", "describe", "tell us", "have you", "are you", "do you")):
                if clean not in questions:
                    questions.append(clean)
    return questions[:6]


def generate_comprehensive_qa_bundle(
    job_data: Dict[str, Any],
    profile_data: Dict[str, Any],
    candidate_skills: Optional[List[Any]] = None,
    app_kit: Optional[Dict[str, Any]] = None,
    extra_questions: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Generates a complete bank of tailored answers for standard ATS screening questions
    plus any role-specific questions extracted from the job description or live ATS form.
    """
    company = job_data.get("company") or "this company"
    job_title = job_data.get("title") or "this role"

    standard_questions = [
        f"Why are you interested in the {job_title} role at {company}?",
        "Are you legally authorized to work in the United States?",
        "Will you now or in the future require visa sponsorship for employment?",
        "What are your salary / compensation expectations?",
        "What is your notice period / earliest available start date?",
        "Describe a relevant technical project or system you built and your impact.",
        "How many years of relevant technical experience do you have?",
        "Are you open to the workplace arrangement (Remote / Hybrid / Onsite) for this role?",
        "LinkedIn Profile URL",
        "GitHub / Code Repository URL",
        "Portfolio / Personal Website URL",
    ]

    desc_questions = extract_custom_questions_from_description(job_data.get("description") or "")
    standard_set = {q.strip().lower() for q in standard_questions}
    all_questions: List[str] = []
    seen = set()

    for q in standard_questions + desc_questions + (extra_questions or []):
        q_norm = q.strip().lower()
        if q_norm and q_norm not in seen:
            seen.add(q_norm)
            all_questions.append(q.strip())

    # Include any additional screening Q&As from Hadoku application_kit
    if app_kit and isinstance(app_kit.get("screening_answers"), list):
        for item in app_kit["screening_answers"]:
            kq = (item.get("q") or "").strip()
            if kq and kq.lower() not in seen:
                seen.add(kq.lower())
                all_questions.append(kq)

    bundle: List[Dict[str, Any]] = []
    for q_text in all_questions:
        is_std = q_text.strip().lower() in standard_set
        ans_item = answer_single_question(
            question_text=q_text,
            job_data=job_data,
            profile_data=profile_dict if "profile_dict" in locals() else profile_data,
            candidate_skills=candidate_skills,
            app_kit=app_kit,
            required=is_std,
        )
        bundle.append(ans_item)

    return bundle
