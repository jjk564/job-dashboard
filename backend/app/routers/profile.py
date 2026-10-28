from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from ..database import get_db
from ..models import Profile, Skill
from ..schemas import ProfileUpdate, ProfileResponse, SkillCreate, SkillResponse

router = APIRouter(prefix="/api/profile", tags=["Profile"])

DEFAULT_SKILLS = [
    # Software & Backend
    ("Python", "languages", "expert"),
    ("SQL", "languages", "expert"),
    ("Go", "languages", "intermediate"),
    ("Bash", "languages", "expert"),
    ("REST APIs", "architecture", "expert"),
    ("SQLite3", "databases", "expert"),
    ("Git & GitHub Actions", "tools", "expert"),
    ("Data Pipelines / ETL", "architecture", "expert"),
    # IT Support, SysAdmin & Networking
    ("Active Directory", "enterprise_it", "intermediate"),
    ("Microsoft 365 (Admin Center)", "enterprise_it", "expert"),
    ("Windows 10/11 & Windows Server", "operating_systems", "expert"),
    ("Linux (Ubuntu/Debian)", "operating_systems", "expert"),
    ("Networking (TCP/IP, DNS, DHCP, VPN)", "networking", "expert"),
    ("ServiceNow & Dynamics 365 CRM", "enterprise_it", "intermediate"),
    ("Cybersecurity & Log Analysis", "security", "intermediate"),
    ("Hardware & Diagnostic Triage", "hardware", "expert"),
]

async def get_or_create_profile(db: AsyncSession) -> Profile:
    res = await db.execute(select(Profile).limit(1))
    profile = res.scalars().first()
    if not profile:
        profile = Profile(
            full_name="",
            email="",
            phone="",
            location="",
            title="Software Engineer",
            summary="Experienced software engineer with expertise in full-stack development, distributed systems, and modern cloud technologies.",
            linkedin_url="",
            github_url="",
            portfolio_url="",
            work_authorization="Authorized to work in the US without sponsorship",
            desired_salary="",
            notice_period="Immediate / 2 weeks",
            master_resume_text="Software Engineer with experience across full stack web development, APIs, databases, and modern software development practices."
        )
        db.add(profile)
        await db.commit()
        await db.refresh(profile)

        # Seed initial skills if empty
        s_res = await db.execute(select(Skill).limit(1))
        if not s_res.scalars().first():
            for name, cat, prof in DEFAULT_SKILLS:
                db.add(Skill(name=name, category=cat, proficiency=prof))
            await db.commit()

    return profile

@router.get("", response_model=ProfileResponse)
async def get_profile(db: AsyncSession = Depends(get_db)):
    profile = await get_or_create_profile(db)
    return profile.to_dict()

@router.put("", response_model=ProfileResponse)
async def update_profile(profile_in: ProfileUpdate, db: AsyncSession = Depends(get_db)):
    profile = await get_or_create_profile(db)
    for k, v in profile_in.model_dump(exclude_unset=True).items():
        setattr(profile, k, v)
    await db.commit()
    await db.refresh(profile)
    return profile.to_dict()

@router.get("/skills", response_model=List[SkillResponse])
async def list_skills(db: AsyncSession = Depends(get_db)):
    await get_or_create_profile(db)
    res = await db.execute(select(Skill).order_by(Skill.category, Skill.name))
    skills = res.scalars().all()
    return [s.to_dict() for s in skills]

@router.post("/skills", response_model=SkillResponse)
async def add_skill(skill_in: SkillCreate, db: AsyncSession = Depends(get_db)):
    # Check if exists
    res = await db.execute(select(Skill).where(Skill.name.ilike(skill_in.name.strip())))
    existing = res.scalars().first()
    if existing:
        existing.proficiency = skill_in.proficiency
        existing.category = skill_in.category
        await db.commit()
        await db.refresh(existing)
        return existing.to_dict()

    skill = Skill(
        name=skill_in.name.strip(),
        category=skill_in.category,
        proficiency=skill_in.proficiency
    )
    db.add(skill)
    await db.commit()
    await db.refresh(skill)
    return skill.to_dict()

@router.delete("/skills/{skill_id}")
async def delete_skill(skill_id: int, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Skill).where(Skill.id == skill_id))
    skill = res.scalars().first()
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    await db.delete(skill)
    await db.commit()
    return {"success": True, "message": "Skill removed"}
