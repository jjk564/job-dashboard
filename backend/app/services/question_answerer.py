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
from pathlib import Path
from typing import Any, Dict, List, Optional

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
    for pat in preferred_patterns:
        pat_low = pat.lower()
        for opt in cleaned:
            if pat_low == opt.lower() or pat_low in opt.lower():
                return opt
    return None


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
    q = q_raw.lower()

    full_name = (profile_data.get("full_name") or "").strip()
    name_parts = full_name.split()
    first_name = name_parts[0] if name_parts else ""
    last_name = " ".join(name_parts[1:]) if len(name_parts) > 1 else ""
    email = (profile_data.get("email") or "").strip()
    phone = (profile_data.get("phone") or "").strip()
    location = (profile_data.get("location") or "Remote, US").strip()
    clean_location = re.sub(r"[\(\[\{].*?[\)\]\}]", "", location).split("-")[0].strip() or "Boston, MA"
    title = (profile_data.get("title") or "Software Engineer").strip()
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

    # 1. Standard Contact / Identity Fields
    if any(k in q for k in ("first name", "given name", "firstname")):
        return {
            "question": q_raw,
            "answer": first_name,
            "category": "contact",
            "confidence": "high" if first_name else "manual_needed",
        }
    if any(k in q for k in ("last name", "family name", "surname", "lastname")):
        return {
            "question": q_raw,
            "answer": last_name or first_name,
            "category": "contact",
            "confidence": "high" if (last_name or first_name) else "manual_needed",
        }
    if q in ("name", "full name", "your name", "legal name", "candidate name") or "legal name" in q:
        return {
            "question": q_raw,
            "answer": full_name,
            "category": "contact",
            "confidence": "high" if full_name else "manual_needed",
        }
    if "preferred name" in q:
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
    if "email" in q:
        return {
            "question": q_raw,
            "answer": email,
            "category": "contact",
            "confidence": "high" if email else "manual_needed",
        }
    if any(k in q for k in ("phone", "mobile", "telephone", "cell")):
        return {
            "question": q_raw,
            "answer": phone,
            "category": "contact",
            "confidence": "high" if phone else "manual_needed",
        }

    # 2. Links & Profiles
    if "linkedin" in q:
        return {
            "question": q_raw,
            "answer": linkedin,
            "category": "links",
            "confidence": "high" if linkedin else ("medium" if not required else "manual_needed"),
        }
    if "github" in q:
        return {
            "question": q_raw,
            "answer": github,
            "category": "links",
            "confidence": "high" if github else ("medium" if not required else "manual_needed"),
        }
    if any(k in q for k in ("portfolio", "personal website", "website", "blog", "other url")):
        return {
            "question": q_raw,
            "answer": portfolio,
            "category": "links",
            "confidence": "high" if portfolio else "medium",
        }

    # 3. Work Authorization & Visa Sponsorship (evaluated before country/location so 'authorized to work in the United States' matches work auth)
    needs_sponsorship = "require sponsorship" in work_auth.lower() and "without" not in work_auth.lower()

    if any(k in q for k in ("export control", "export controls", "itar", "u.s. export", "us export", "u.s. person under", "us person under", "eligible under u.s. law to receive information")):
        opt = _match_option(options, ["yes", "u.s. citizen", "us citizen", "u.s. person", "authorized", "permanent resident"])
        return {
            "question": q_raw,
            "answer": opt or "Yes",
            "category": "work_authorization",
            "confidence": "high",
        }

    # Check for SMS / text message agreement upfront so 'opt out' in SMS disclosures doesn't match visa OPT
    if any(k in q for k in ("text message", "text messages", "sms opt", "sms updates", "receive text message", "receive text", "text messaging")):
        opt = _match_option(options, ["yes - i consent to receiving text messages", "yes - i consent", "i consent", "yes", "true", "agree"])
        return {
            "question": q_raw,
            "answer": opt or "Yes - I consent to receiving text messages",
            "category": "consent",
            "confidence": "high",
        }

    # Questions asking if the candidate is legally authorized to work (e.g. "...without the need for visa sponsorship")
    if any(k in q for k in ("authorized to work", "legally authorized", "work authorization", "right to work", "eligible to work")):
        opt = _match_option(options, ["yes", "authorized", "citizen", "permanent resident", "u.s. citizen", "us citizen"])
        return {
            "question": q_raw,
            "answer": opt or ("Yes" if options is not None or "?" in q_raw else work_auth),
            "category": "work_authorization",
            "confidence": "high",
        }

    # Questions asking if candidate requires sponsorship
    if any(k in q for k in ("require sponsorship", "need sponsorship", "require visa", "sponsorship for employment", "sponsorship now or in the future", "will you now or in the future require", "require any visa")):
        desired = "Yes" if needs_sponsorship else "No"
        opt = _match_option(options, [desired, "no", "do not require", "not require"] if not needs_sponsorship else ["yes", "require"])
        return {
            "question": q_raw,
            "answer": opt or desired,
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

    # 4. Location / Address / Relocation / Remote / Workplace Arrangement
    if any(k in q for k in (
        "relocat", "willing to move", "commute to", "work on-site", "work onsite",
        "work in the office", "days a week", "in-office", "in office", "residing in",
        "hybrid schedule", "workplace arrangement", "work arrangement", "remote / hybrid"
    )):
        wp = (job_data.get("workplace_type") or "remote").lower()
        opt = _match_option(options, ["yes", "open", "willing"])
        return {
            "question": q_raw,
            "answer": opt or ("Yes" if wp in ("remote", "hybrid") else "Yes, open to relocation / hybrid schedule"),
            "category": "location",
            "confidence": "high",
        }
    if any(k in q for k in ("country", "united states", "reside in the us", "based in the us", "located in the us")):
        opt = _match_option(options, ["united states", "usa", "us", "yes"])
        return {
            "question": q_raw,
            "answer": opt or ("Yes" if "reside" in q or "based" in q or "located" in q else "United States"),
            "category": "location",
            "confidence": "high",
        }
    if any(k in q for k in ("city", "current location", "location", "where are you based", "where do you live", "address", "state")):
        loc_val = clean_location or "Boston, MA"
        opt = _match_option(options, [loc_val, "boston", "massachusetts", "remote", "united states"])
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
        "reliable high-speed", "vpn access", "home office"
    )):
        opt = _match_option(options, ["yes", "meet requirement", "agree", "i am able"])
        return {
            "question": q_raw,
            "answer": opt or "Yes",
            "category": "remote_requirements",
            "confidence": "high",
        }

    # 5. Compensation & Salary Expectations
    # Check for salary alignment first (e.g. "Do your salary expectations align with the posted salary range?")
    if any(k in q for k in ("salary expectations align", "align with the posted salary", "within the posted salary", "posted salary range", "salary expectations within")):
        opt = _match_option(options, ["yes", "align", "agree"])
        return {
            "question": q_raw,
            "answer": opt or "Yes",
            "category": "compensation",
            "confidence": "high",
        }

    if any(k in q for k in ("salary", "compensation", "pay expectation", "desired pay", "hourly rate", "annual base")):
        # If question is asking a Yes/No comfort question about salary
        opt_yn = _match_option(options, ["yes", "acceptable", "agree"])
        if opt_yn and options and len(options) <= 3 and any("yes" in o.lower() for o in options):
            return {
                "question": q_raw,
                "answer": opt_yn,
                "category": "compensation",
                "confidence": "high",
            }

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
        if field_type == "number":
            nums = re.findall(r"\d+", sal_ans.replace(",", ""))
            num_val = nums[0] if nums else "70000"
            return {"question": q_raw, "answer": num_val, "category": "compensation", "confidence": "high"}
        return {
            "question": q_raw,
            "answer": sal_ans,
            "category": "compensation",
            "confidence": "high",
        }

    # 6. Notice Period / Start Date / Availability
    if any(k in q for k in ("notice period", "when can you start", "start date", "earliest start", "availability", "available to start", "available for")):
        opt = _match_option(options, ["yes", notice_period, "2 weeks", "two weeks", "immediately", "immediate", "1-2 weeks"])
        return {
            "question": q_raw,
            "answer": opt or ("Yes" if "available for" in q else notice_period),
            "category": "availability",
            "confidence": "high",
        }

    # 7. Years of Experience
    if any(k in q for k in ("years of experience", "how many years", "years working with", "experience level")):
        # Check if a specific technology is mentioned
        years = "3"
        for sk_name, prof in skill_map.items():
            if sk_name and sk_name in q:
                years = "5" if prof == "expert" else ("3" if prof == "intermediate" else "1")
                break
        opt = _match_option(options, [f"{years}", "3-5", "2-4", "3+", "2+"])
        ans = opt or (years if field_type == "number" else f"{years}+ years")
        return {
            "question": q_raw,
            "answer": ans,
            "category": "experience",
            "confidence": "high",
        }

    # 8. Education / Degree / University / School / Discipline / Graduation Date
    if q in ("school", "university", "college") or "school" in q or "university" in q:
        opt = _match_option(options, ["university of massachusetts lowell", "umass lowell", "university of massachusetts", "other"])
        return {
            "question": q_raw,
            "answer": opt or "University of Massachusetts Lowell",
            "category": "education",
            "confidence": "high",
        }
    if q in ("discipline", "major", "field of study") or any(k in q for k in ("discipline", "field of study", "major")):
        opt = _match_option(options, ["computer science", "mathematics", "math", "information technology", "software engineering", "other"])
        return {
            "question": q_raw,
            "answer": opt or "Mathematics & Computer Science",
            "category": "education",
            "confidence": "high",
        }
    if any(k in q for k in ("graduation date", "grad date", "when did you graduate", "expected graduation", "date of graduation")):
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
        opt = _match_option(options, ["2025", "2026", "2024"])
        return {
            "question": q_raw,
            "answer": opt or "2025",
            "category": "education",
            "confidence": "high",
        }
    if any(k in q for k in ("highest level of education", "degree", "education level", "bachelor", "college")):
        opt = _match_option(options, ["bachelor", "b.a.", "b.s.", "bs", "ba", "4-year", "college", "yes"])
        return {
            "question": q_raw,
            "answer": opt or "Bachelor's Degree",
            "category": "education",
            "confidence": "high",
        }

    # 9. Current Company / Current Title
    if any(k in q for k in ("current title", "job title", "current role")):
        return {
            "question": q_raw,
            "answer": title,
            "category": "experience",
            "confidence": "high",
        }
    if any(k in q for k in ("current company", "current employer", "most recent employer")):
        return {
            "question": q_raw,
            "answer": "Hyperice",
            "category": "experience",
            "confidence": "high",
        }

    # 10. Referral / How did you hear about us?
    if any(k in q for k in ("how did you hear", "where did you see", "source", "referred by")):
        src = job_data.get("source") or "Company Career Board"
        opt = _match_option(options, ["company website", "career page", "job board", "linkedin", "other"])
        return {
            "question": q_raw,
            "answer": opt or f"Company Careers Board ({src})",
            "category": "referral",
            "confidence": "high",
        }

    # 11. Previously employed / Applied before / Government / Non-compete / Interview Accommodations
    if any(k in q for k in ("accommodation", "accessible", "interview process more accessible", "accessible and inclusive")):
        opt = _match_option(options, ["i do not require accommodations", "no accommodations needed", "no", "none", "not require"])
        return {
            "question": q_raw,
            "answer": opt or "I do not require accommodations",
            "category": "accommodations",
            "confidence": "high",
        }
    if any(k in q for k in ("previously worked", "ever worked for", "worked for", "former employee", "applied before", "non-compete", "restrictive covenant", "government official", "related to anyone", "history with", "affiliated with", "relationship with")):
        opt = _match_option(options, ["no", "never", "none", "n/a", "neither"])
        return {
            "question": q_raw,
            "answer": opt or "No",
            "category": "compliance",
            "confidence": "high",
        }
    if any(k in q for k in ("at least 18", "18 years of age", "legal age")):
        opt = _match_option(options, ["yes"])
        return {
            "question": q_raw,
            "answer": opt or "Yes",
            "category": "compliance",
            "confidence": "high",
        }

    # Background Check / Drug Screening / Criminal History
    if any(k in q for k in ("background check", "background screening", "drug test", "drug screen", "substance test", "criminal history", "pre-employment background")):
        opt = _match_option(options, ["yes", "i agree", "willing", "consent", "accept"])
        return {
            "question": q_raw,
            "answer": opt or "Yes",
            "category": "background_check",
            "confidence": "high",
        }

    # 12. EEO / Voluntary Self-Identification (Gender, Ethnicity, Race, Veteran, Disability)
    if any(k in q for k in ("gender", "sex")) and "sexual orientation" not in q:
        opt = _match_option(options, ["male", "man", "cisgender male", "he/him", "he/him/his"])
        return {
            "question": q_raw,
            "answer": opt or "Male",
            "category": "eeo",
            "confidence": "high",
        }

    # Hispanic / Latino ethnicity check
    if any(k in q for k in ("hispanic", "latino")):
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

    # Race / Ethnicity
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

    # Veteran Status
    if any(k in q for k in ("veteran", "military")):
        opt = _match_option(
            options,
            [
                "i am not a protected veteran", "not a veteran", "no", "not a protected veteran",
                "i am not a veteran", "decline to self-identify", "i do not wish to answer", "prefer not to say",
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
                "no, i do not have a disability", "no, i don't have a disability", "no",
                "i do not have a disability", "no disability",
                "i do not wish to answer", "decline to self-identify", "prefer not to say",
            ],
        )
        return {
            "question": q_raw,
            "answer": opt or "No, I do not have a disability",
            "category": "eeo",
            "confidence": "high",
        }

    if any(k in q for k in ("sexual orientation", "self-identify")):
        opt = _match_option(
            options,
            [
                "heterosexual", "straight",
                "decline to self-identify", "i do not wish to answer", "prefer not to say",
            ],
        )
        return {
            "question": q_raw,
            "answer": opt or "Decline to self-identify",
            "category": "eeo",
            "confidence": "high",
        }

    # 13. Privacy Policy / Terms & Certification Checkboxes / SMS Consent
    if any(k in q for k in ("text message", "text messages", "sms opt", "sms updates", "receive text message")):
        opt = _match_option(options, ["yes - i consent to receiving text messages", "yes - i consent", "i consent", "yes", "agree"])
        return {
            "question": q_raw,
            "answer": opt or "Yes - I consent to receiving text messages",
            "category": "consent",
            "confidence": "high",
        }
    if any(k in q for k in ("privacy policy", "acknowledge", "certify that", "consent to", "terms and conditions", "agree to")):
        opt = _match_option(options, ["yes", "i agree", "i acknowledge", "accept"])
        return {
            "question": q_raw,
            "answer": opt or "Yes",
            "category": "consent",
            "confidence": "high",
        }

    # 14. Motivation / Why This Company / Why This Role / Cover Letter / Summary
    if any(k in q for k in ("why do you want", "why are you interested", "what excites you", "why this role", f"why {company.lower()}", "what draws you")):
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

    if any(k in q for k in ("cover letter", "additional information", "anything else", "note to hiring", "summary")):
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

    # 15. Technical Project / Experience Open-Ended Prompts
    if any(k in q for k in ("describe a project", "challenging problem", "technical challenge", "tell us about", "experience with", "proud of", "built")):
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

    # 16. Specific Cultural / Ranking / Short Stints Custom Prompts
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

    # 17. Check pre-drafted screening_answers from Hadoku application_kit
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

    # 17. Unrecognized custom question: provide a grounded draft answer but flag confidence appropriately
    if options:
        # If there are explicit options we don't recognize and it's required, mark manual_needed
        return {
            "question": q_raw,
            "answer": options[0] if options else "",
            "category": "custom",
            "confidence": "manual_needed" if required else "medium",
        }

    fallback_ans = (
        f"As a {title} with experience in {skills_str}, I have consistently delivered scalable, well-tested solutions "
        f"that align with {company}'s requirements for the {job_title} position."
    )
    return {
        "question": q_raw,
        "answer": fallback_ans,
        "category": "custom",
        "confidence": "manual_needed" if required else "medium",
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
