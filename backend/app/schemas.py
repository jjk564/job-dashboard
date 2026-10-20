from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field

# Skill Schemas
class SkillBase(BaseModel):
    name: str
    category: str = "general"
    proficiency: str = "intermediate"

class SkillCreate(SkillBase):
    pass

class SkillResponse(SkillBase):
    id: int

    class Config:
        from_attributes = True

# Activity Schemas
class ActivityCreate(BaseModel):
    activity_type: str  # status_change, note, interview, email, follow_up
    title: str
    details: Optional[str] = None

class ActivityResponse(BaseModel):
    id: int
    job_id: int
    activity_type: str
    title: str
    details: Optional[str] = None
    created_at: Optional[str] = None

    class Config:
        from_attributes = True

# Document Schemas
class TailoredDocCreate(BaseModel):
    doc_type: str = "cover_letter"
    content: str

class TailoredDocResponse(BaseModel):
    id: int
    job_id: int
    doc_type: str
    content: str
    created_at: Optional[str] = None

    class Config:
        from_attributes = True

# Job Schemas
class JobBase(BaseModel):
    title: str
    company: str
    location: Optional[str] = "Remote"
    workplace_type: Optional[str] = "remote"
    url: Optional[str] = None
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    salary_currency: Optional[str] = "USD"
    description: Optional[str] = None
    requirements: Optional[str] = None
    source: Optional[str] = "manual"
    status: Optional[str] = "TO_APPLY"
    priority: Optional[str] = "medium"
    notes: Optional[str] = None
    deadline: Optional[datetime] = None
    is_expired: Optional[bool] = False
    expired_at: Optional[datetime] = None
    expired_reason: Optional[str] = None
    contact_person: Optional[str] = None
    contact_email: Optional[str] = None

class JobCreate(JobBase):
    pass

class JobUpdate(BaseModel):
    title: Optional[str] = None
    company: Optional[str] = None
    location: Optional[str] = None
    workplace_type: Optional[str] = None
    url: Optional[str] = None
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    salary_currency: Optional[str] = None
    description: Optional[str] = None
    requirements: Optional[str] = None
    source: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    fit_score: Optional[int] = None
    fit_breakdown: Optional[Dict[str, Any]] = None
    notes: Optional[str] = None
    applied_at: Optional[datetime] = None
    deadline: Optional[datetime] = None
    is_expired: Optional[bool] = None
    expired_at: Optional[datetime] = None
    expired_reason: Optional[str] = None
    contact_person: Optional[str] = None
    contact_email: Optional[str] = None

class JobResponse(BaseModel):
    id: int
    title: str
    company: str
    location: Optional[str] = None
    workplace_type: Optional[str] = None
    url: Optional[str] = None
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    salary_currency: Optional[str] = "USD"
    description: Optional[str] = None
    requirements: Optional[str] = None
    source: Optional[str] = None
    status: str
    priority: str
    fit_score: Optional[int] = None
    fit_breakdown: Optional[Dict[str, Any]] = None
    notes: Optional[str] = None
    applied_at: Optional[str] = None
    deadline: Optional[str] = None
    is_expired: Optional[bool] = False
    expired_at: Optional[str] = None
    expired_reason: Optional[str] = None
    contact_person: Optional[str] = None
    contact_email: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    activities: Optional[List[ActivityResponse]] = []
    tailored_documents: Optional[List[TailoredDocResponse]] = []

    class Config:
        from_attributes = True

# Profile Schemas
class ProfileBase(BaseModel):
    full_name: Optional[str] = ""
    email: Optional[str] = ""
    phone: Optional[str] = ""
    location: Optional[str] = ""
    title: Optional[str] = ""
    summary: Optional[str] = ""
    linkedin_url: Optional[str] = ""
    github_url: Optional[str] = ""
    portfolio_url: Optional[str] = ""
    work_authorization: Optional[str] = "Authorized to work in the US without sponsorship"
    desired_salary: Optional[str] = ""
    notice_period: Optional[str] = "Immediate / 2 weeks"
    master_resume_text: Optional[str] = ""

class ProfileUpdate(ProfileBase):
    pass

class ProfileResponse(ProfileBase):
    id: int
    updated_at: Optional[str] = None

    class Config:
        from_attributes = True

# URL Import Schema
class URLImportRequest(BaseModel):
    url: str

class URLImportResponse(BaseModel):
    title: str
    company: str
    location: Optional[str] = "Remote"
    workplace_type: Optional[str] = "remote"
    url: str
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    description: str
    requirements: Optional[str] = None
    source: str = "url_import"

# Match & Tailor Schemas
class MatchAnalysisResponse(BaseModel):
    score: int
    matched_skills: List[str]
    missing_skills: List[str]
    detected_requirements: List[str]
    summary: str

class GenerateDocumentRequest(BaseModel):
    doc_type: str = "cover_letter"  # cover_letter, resume_bullets, pitch
    tone: Optional[str] = "professional"  # professional, confident, concise
    custom_instructions: Optional[str] = None
    provider: Optional[str] = "template"  # template, gemini, openai, ollama
    api_key: Optional[str] = None

class GenerateDocumentResponse(BaseModel):
    doc_type: str
    content: str
    provider_used: str

class AutofillPayloadResponse(BaseModel):
    first_name: str
    last_name: str
    full_name: str
    email: str
    phone: str
    location: str
    linkedin_url: str
    github_url: str
    portfolio_url: str
    work_authorization: str
    desired_salary: str
    notice_period: str
    summary: str
    cover_letter_snippet: str
