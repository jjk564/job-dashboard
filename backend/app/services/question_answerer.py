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
) -> Dict[str, str]:
    """
    Writes tailored resume and cover letter files (.pdf, .md, .txt) to disk under
    backend/generated_packets/job_{job_id}/ so browser automation can upload them.
    """
    safe_company = re.sub(r"[^a-zA-Z0-9_-]+", "_", (company or "Company").strip())[:30].strip("_") or "Company"
    job_dir = PACKETS_DIR / f"job_{job_id}_{safe_company}"
    job_dir.mkdir(parents=True, exist_ok=True)

    resume_pdf_path = job_dir / "Tailored_Resume.pdf"
    resume_md_path = job_dir / "Tailored_Resume.md"
    resume_txt_path = job_dir / "Tailored_Resume.txt"

    cover_pdf_path = job_dir / "Tailored_Cover_Letter.pdf"
    cover_md_path = job_dir / "Tailored_Cover_Letter.md"
    cover_txt_path = job_dir / "Tailored_Cover_Letter.txt"

    resume_md_path.write_text(resume_markdown or "", encoding="utf-8")
    resume_txt_path.write_text(_clean_markdown_to_plain(resume_markdown or ""), encoding="utf-8")
    resume_pdf_path.write_bytes(render_text_to_minimal_pdf(f"Resume - {job_title}", resume_markdown or ""))

    cover_md_path.write_text(cover_letter_markdown or "", encoding="utf-8")
    cover_txt_path.write_text(_clean_markdown_to_plain(cover_letter_markdown or ""), encoding="utf-8")
    cover_pdf_path.write_bytes(render_text_to_minimal_pdf(f"Cover Letter - {company}", cover_letter_markdown or ""))

    return {
        "directory": str(job_dir),
        "resume_pdf": str(resume_pdf_path),
        "resume_md": str(resume_md_path),
        "resume_txt": str(resume_txt_path),
        "cover_letter_pdf": str(cover_pdf_path),
        "cover_letter_md": str(cover_md_path),
        "cover_letter_txt": str(cover_txt_path),
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
    if q in ("name", "full name", "your name", "legal name", "candidate name") or "full legal name" in q:
        return {
            "question": q_raw,
            "answer": full_name,
            "category": "contact",
            "confidence": "high" if full_name else "manual_needed",
        }
    if "preferred name" in q or "pronoun" in q:
        ans = first_name if "preferred name" in q else "Prefer not to say"
        opt = _match_option(options, [ans, "prefer not", "decline"])
        return {
            "question": q_raw,
            "answer": opt or ans,
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
    if any(k in q for k in ("sponsorship", "visa", "h-1b", "h1b", "opt", "cpt", "immigration")):
        desired = "Yes" if needs_sponsorship else "No"
        opt = _match_option(options, [desired, "no", "do not require", "not require"] if not needs_sponsorship else ["yes", "require"])
        return {
            "question": q_raw,
            "answer": opt or desired,
            "category": "work_authorization",
            "confidence": "high",
        }
    if any(k in q for k in ("authorized to work", "legally authorized", "work authorization", "right to work", "eligible to work")):
        opt = _match_option(options, ["yes", "authorized", "citizen", "permanent"])
        return {
            "question": q_raw,
            "answer": opt or ("Yes" if options is not None or "?" in q_raw else work_auth),
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
        loc_val = location or "United States"
        opt = _match_option(options, [loc_val, "remote", "united states"])
        return {
            "question": q_raw,
            "answer": opt or loc_val,
            "category": "location",
            "confidence": "high" if location else "medium",
        }

    # 5. Compensation & Salary Expectations
    if any(k in q for k in ("salary", "compensation", "pay expectation", "desired pay", "hourly rate", "annual base")):
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
                sal_ans = "$110,000 - $145,000 (flexible based on total compensation)"
        if field_type == "number":
            nums = re.findall(r"\d+", sal_ans.replace(",", ""))
            num_val = nums[0] if nums else "120000"
            return {"question": q_raw, "answer": num_val, "category": "compensation", "confidence": "high"}
        return {
            "question": q_raw,
            "answer": sal_ans,
            "category": "compensation",
            "confidence": "high",
        }

    # 6. Notice Period / Start Date / Availability
    if any(k in q for k in ("notice period", "when can you start", "start date", "earliest start", "availability", "available to start")):
        opt = _match_option(options, [notice_period, "2 weeks", "two weeks", "immediately", "immediate", "1-2 weeks"])
        return {
            "question": q_raw,
            "answer": opt or notice_period,
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

    # 8. Education / Degree / University
    if any(k in q for k in ("highest level of education", "degree", "education level", "bachelor", "university", "college")):
        opt = _match_option(options, ["bachelor", "b.s.", "bs", "4-year", "college", "yes"])
        return {
            "question": q_raw,
            "answer": opt or "Bachelor's Degree in Computer Science / Information Technology",
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
            "answer": "Independent / Software Engineering",
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

    # 11. Previously employed / Applied before / Government / Non-compete
    if any(k in q for k in ("previously worked at", "ever worked for", "former employee", "applied before", "non-compete", "restrictive covenant", "government official", "related to anyone")):
        opt = _match_option(options, ["no", "never", "none"])
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

    # 12. EEO / Voluntary Self-Identification (Gender, Ethnicity, Veteran, Disability)
    if any(k in q for k in ("gender", "race", "hispanic", "latino", "ethnicity", "veteran", "disability", "sexual orientation", "self-identify", "demographic")):
        opt = _match_option(
            options,
            [
                "decline to self-identify",
                "i do not wish to answer",
                "prefer not to say",
                "prefer not to answer",
                "decline",
                "choose not to disclose",
            ],
        )
        return {
            "question": q_raw,
            "answer": opt or "Decline to self-identify",
            "category": "eeo",
            "confidence": "high",
        }

    # 13. Privacy Policy / Terms & Certification Checkboxes
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
