import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from ..database import get_db
from ..models import Job, Profile, Skill, TailoredDocument
from ..schemas import (
    MatchAnalysisResponse,
    GenerateDocumentRequest,
    GenerateDocumentResponse,
    AutofillPayloadResponse,
)
from ..services.matcher import analyze_job_fit
from ..services.ai_generator import generate_ai_document
from ..services.browser_assistant import launch_assisted_application

router = APIRouter(prefix="/api/assistant", tags=["Assistant"])

@router.post("/{job_id}/match", response_model=MatchAnalysisResponse)
async def analyze_job_match(job_id: int, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Job).where(Job.id == job_id))
    job = res.scalars().first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    p_res = await db.execute(select(Profile).limit(1))
    profile = p_res.scalars().first()
    s_res = await db.execute(select(Skill))
    skills = [s.name for s in s_res.scalars().all()]

    job_text = f"{job.title} {job.description or ''} {job.requirements or ''}"
    profile_text = f"{profile.summary if profile else ''} {profile.master_resume_text if profile else ''}"

    analysis = analyze_job_fit(job_text, skills, profile_text)

    # Persist score to job
    job.fit_score = analysis["score"]
    job.fit_breakdown = json.dumps(analysis)
    await db.commit()
    await db.refresh(job)

    return analysis

@router.post("/{job_id}/generate", response_model=GenerateDocumentResponse)
async def generate_document(
    job_id: int,
    req: GenerateDocumentRequest,
    db: AsyncSession = Depends(get_db)
):
    res = await db.execute(select(Job).where(Job.id == job_id))
    job = res.scalars().first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    p_res = await db.execute(select(Profile).limit(1))
    profile = p_res.scalars().first()
    profile_dict = profile.to_dict() if profile else {}

    # Extract matched skills
    matched_skills = []
    if job.fit_breakdown:
        try:
            b = json.loads(job.fit_breakdown)
            matched_skills = b.get("matched_skills", [])
        except Exception:
            pass

    # Default to hadoku-resume when .devvault.local.json is active and no explicit provider was forced
    from ..services.hadoku_client import (
        get_hadoku_user_key,
        generate_hadoku_tailored_resume,
        generate_hadoku_cover_letter,
        generate_hadoku_application_extras,
        mint_hadoku_resume_variant,
    )
    effective_provider = req.provider or ("hadoku" if get_hadoku_user_key(req.api_key) else "template")
    if effective_provider == "template" and get_hadoku_user_key(req.api_key):
        effective_provider = "hadoku"

    content, provider_used = await generate_ai_document(
        doc_type=req.doc_type,
        job_data=job.to_dict(),
        profile_data=profile_dict,
        matched_skills=matched_skills,
        tone=req.tone or "professional",
        custom_instructions=req.custom_instructions,
        provider=effective_provider,
        api_key=req.api_key,
    )

    # Save to database
    doc = TailoredDocument(
        job_id=job.id,
        doc_type=req.doc_type,
        content=content
    )
    db.add(doc)
    await db.commit()

    return {
        "doc_type": req.doc_type,
        "content": content,
        "provider_used": provider_used,
    }


@router.post("/{job_id}/application-kit")
async def generate_job_application_kit(job_id: int, db: AsyncSession = Depends(get_db)):
    """
    Calls Hadoku Resume Service (/resume/api/application-extras) to produce the structured
    non-resume application kit: why_hook, intro_email, linkedin_note, salary_line,
    talking_points, screening_answers, and cover_letter_markdown.
    """
    from ..services.hadoku_client import (
        get_hadoku_user_key,
        generate_hadoku_tailored_resume,
        generate_hadoku_application_extras,
    )
    from ..services.ai_generator import generate_offline_template

    res = await db.execute(select(Job).where(Job.id == job_id))
    job = res.scalars().first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    p_res = await db.execute(select(Profile).limit(1))
    profile = p_res.scalars().first()
    profile_dict = profile.to_dict() if profile else {}

    matched_skills = []
    if job.fit_breakdown:
        try:
            matched_skills = json.loads(job.fit_breakdown).get("matched_skills", [])
        except Exception:
            pass

    if get_hadoku_user_key():
        tailored = await generate_hadoku_tailored_resume(
            job_title=job.title,
            company=job.company,
            description=job.description or f"{job.title} at {job.company}",
            tailor=True,
        )
        resume_md = (
            (tailored or {}).get("resume_markdown")
            or (profile.master_resume_text if profile else "")
            or generate_offline_template("tailored_resume", job.to_dict(), profile_dict, matched_skills)
        )
        extras = await generate_hadoku_application_extras(
            job_title=job.title,
            company=job.company,
            description=job.description or f"{job.title} at {job.company}",
            resume_markdown=resume_md,
            job_location=job.location,
            workplace_type=job.workplace_type,
        )
        if extras:
            return {
                "provider_used": "hadoku-resume",
                "why_hook": extras.get("why_hook", ""),
                "intro_email": extras.get("intro_email", ""),
                "linkedin_note": extras.get("linkedin_note", ""),
                "salary_line": extras.get("salary_line", ""),
                "talking_points": extras.get("talking_points", []),
                "screening_answers": extras.get("screening_answers", []),
                "cover_letter_markdown": extras.get("cover_letter_markdown", ""),
                "standard_fields": extras.get("standard_fields", ""),
            }

    # Local fallback if offline
    skills_str = ", ".join(matched_skills[:4]) if matched_skills else "Python, TypeScript, and modern systems"
    return {
        "provider_used": "local-fallback",
        "why_hook": f"I am excited by {job.company}'s work and the chance to bring my expertise in {skills_str} to the {job.title} team.",
        "intro_email": f"Hi Hiring Team,\n\nI recently applied for the {job.title} role at {job.company}. With hands-on experience in {skills_str}, I'd love to share how I can contribute to your roadmap.",
        "linkedin_note": f"Hi! I just applied for the {job.title} role at {job.company}. Given my background in {skills_str}, I'd love to connect!",
        "salary_line": profile_dict.get("desired_salary") or "Competitive / Open to discussion based on total compensation",
        "talking_points": [
            f"Proven delivery using {skills_str} in production environments.",
            f"Direct alignment with {job.company}'s {job.title} requirements.",
            "Strong track record of cross-functional ownership and automated testing.",
        ],
        "screening_answers": [
            {"q": "Why are you interested in this role?", "a": f"The {job.title} position at {job.company} aligns closely with my background in {skills_str}."},
            {"q": "Do you require visa sponsorship?", "a": profile_dict.get("work_authorization") or "Authorized to work in the US without sponsorship."},
            {"q": "What is your availability / notice period?", "a": profile_dict.get("notice_period") or "2 weeks notice; available to start promptly."},
        ],
        "cover_letter_markdown": generate_offline_template("cover_letter", job.to_dict(), profile_dict, matched_skills),
        "standard_fields": "",
    }


@router.post("/{job_id}/mint-packet")
async def mint_job_resume_packet(job_id: int, db: AsyncSession = Depends(get_db)):
    """
    Generates a tailored resume + cover letter for the job and mints a shareable
    Hadoku Resume Variant Packet (`https://hadoku.me/resume?v={slug}` + PDF download).
    """
    from ..services.hadoku_client import (
        get_hadoku_user_key,
        generate_hadoku_tailored_resume,
        generate_hadoku_cover_letter,
        mint_hadoku_resume_variant,
    )
    from ..services.ai_generator import generate_offline_template
    from ..models import ApplicationActivity

    res = await db.execute(select(Job).where(Job.id == job_id))
    job = res.scalars().first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if not get_hadoku_user_key():
        raise HTTPException(
            status_code=400,
            detail="No Hadoku vault credential found (.devvault.local.json). Run `npx @hadoku/dev-vault login` first.",
        )

    p_res = await db.execute(select(Profile).limit(1))
    profile = p_res.scalars().first()
    profile_dict = profile.to_dict() if profile else {}

    matched_skills = []
    if job.fit_breakdown:
        try:
            matched_skills = json.loads(job.fit_breakdown).get("matched_skills", [])
        except Exception:
            pass

    tailored = await generate_hadoku_tailored_resume(
        job_title=job.title,
        company=job.company,
        description=job.description or f"{job.title} at {job.company}",
        tailor=True,
    )
    resume_md = (
        (tailored or {}).get("resume_markdown")
        or generate_offline_template("tailored_resume", job.to_dict(), profile_dict, matched_skills)
    )

    cl_res = await generate_hadoku_cover_letter(
        job_title=job.title,
        company=job.company,
        description=job.description or f"{job.title} at {job.company}",
    )
    cover_md = (cl_res or {}).get("cover_letter_markdown")

    minted = await mint_hadoku_resume_variant(
        label=f"{job.company} - {job.title}",
        markdown=resume_md,
        cover_letter_markdown=cover_md,
        company=job.company,
        job_title=job.title,
        ttl_days=365,
    )
    if not minted:
        raise HTTPException(status_code=502, detail="Failed to mint packet variant on hadoku.me/resume/api/variants")

    # Save packet record in TailoredDocument and ApplicationActivity
    packet_summary = (
        f"# Minted Hadoku Application Packet\n"
        f"- **Packet Link:** {minted['url']}\n"
        f"- **Server PDF Download:** {minted['pdf_url']}\n"
        f"- **Variant Slug:** `{minted['slug']}`\n\n"
        f"---\n\n{resume_md}"
    )
    db.add(TailoredDocument(job_id=job.id, doc_type="packet", content=packet_summary))
    db.add(
        ApplicationActivity(
            job_id=job.id,
            activity_type="packet_minted",
            title=f"Minted Hadoku Packet ({minted['slug']})",
            details=f"Shareable URL: {minted['url']} | PDF: {minted['pdf_url']}",
        )
    )
    await db.commit()

    return minted

@router.get("/{job_id}/autofill-payload", response_model=AutofillPayloadResponse)
async def get_autofill_payload(job_id: int, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Job).where(Job.id == job_id))
    job = res.scalars().first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    p_res = await db.execute(select(Profile).limit(1))
    profile = p_res.scalars().first()
    if not profile:
        raise HTTPException(status_code=400, detail="Profile not configured")

    name_parts = (profile.full_name or "").split()
    first_name = name_parts[0] if name_parts else ""
    last_name = " ".join(name_parts[1:]) if len(name_parts) > 1 else ""

    # Check for latest cover letter
    doc_res = await db.execute(
        select(TailoredDocument)
        .where(TailoredDocument.job_id == job_id, TailoredDocument.doc_type == "cover_letter")
        .order_by(TailoredDocument.created_at.desc())
        .limit(1)
    )
    doc = doc_res.scalars().first()
    cover_snippet = doc.content if doc else f"I am excited to apply for the {job.title} role at {job.company}."

    return {
        "first_name": first_name,
        "last_name": last_name,
        "full_name": profile.full_name or "",
        "email": profile.email or "",
        "phone": profile.phone or "",
        "location": profile.location or "",
        "linkedin_url": profile.linkedin_url or "",
        "github_url": profile.github_url or "",
        "portfolio_url": profile.portfolio_url or "",
        "work_authorization": profile.work_authorization or "",
        "desired_salary": profile.desired_salary or "",
        "notice_period": profile.notice_period or "",
        "summary": profile.summary or "",
        "cover_letter_snippet": cover_snippet,
    }

@router.post("/{job_id}/launch-browser")
async def trigger_browser_assistant(job_id: int, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Job).where(Job.id == job_id))
    job = res.scalars().first()
    if not job or not job.url:
        raise HTTPException(status_code=400, detail="Job or job URL not found")

    p_res = await db.execute(select(Profile).limit(1))
    profile = p_res.scalars().first()
    profile_dict = profile.to_dict() if profile else {}

    result = await launch_assisted_application(job.url, profile_dict)
    return result
