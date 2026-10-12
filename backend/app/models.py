import json
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from .database import Base

class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    company = Column(String(255), nullable=False)
    location = Column(String(255), nullable=True, default="Remote")
    workplace_type = Column(String(50), default="remote")  # remote, hybrid, onsite
    url = Column(String(1024), nullable=True)
    salary_min = Column(Float, nullable=True)
    salary_max = Column(Float, nullable=True)
    salary_currency = Column(String(10), default="USD")
    description = Column(Text, nullable=True)
    requirements = Column(Text, nullable=True)
    source = Column(String(100), default="manual")
    status = Column(String(50), default="WISHLIST")  # WISHLIST, TO_APPLY, APPLIED, INTERVIEWING, OFFER, REJECTED, ARCHIVED
    priority = Column(String(20), default="medium")  # low, medium, high
    fit_score = Column(Integer, nullable=True)
    fit_breakdown = Column(Text, nullable=True)  # JSON {matched: [], missing: [], score: int}
    notes = Column(Text, nullable=True)
    applied_at = Column(DateTime, nullable=True)
    deadline = Column(DateTime, nullable=True)
    contact_person = Column(String(255), nullable=True)
    contact_email = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    activities = relationship("ApplicationActivity", back_populates="job", cascade="all, delete-orphan", lazy="selectin")
    tailored_documents = relationship("TailoredDocument", back_populates="job", cascade="all, delete-orphan", lazy="selectin")

    def to_dict(self):
        breakdown = None
        if self.fit_breakdown:
            try:
                breakdown = json.loads(self.fit_breakdown)
            except Exception:
                breakdown = None

        return {
            "id": self.id,
            "title": self.title,
            "company": self.company,
            "location": self.location,
            "workplace_type": self.workplace_type,
            "url": self.url,
            "salary_min": self.salary_min,
            "salary_max": self.salary_max,
            "salary_currency": self.salary_currency,
            "description": self.description,
            "requirements": self.requirements,
            "source": self.source,
            "status": self.status,
            "priority": self.priority,
            "fit_score": self.fit_score,
            "fit_breakdown": breakdown,
            "notes": self.notes,
            "applied_at": self.applied_at.isoformat() if self.applied_at else None,
            "deadline": self.deadline.isoformat() if self.deadline else None,
            "contact_person": self.contact_person,
            "contact_email": self.contact_email,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

class Profile(Base):
    __tablename__ = "profiles"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String(255), default="")
    email = Column(String(255), default="")
    phone = Column(String(50), default="")
    location = Column(String(255), default="")
    title = Column(String(255), default="")
    summary = Column(Text, default="")
    linkedin_url = Column(String(500), default="")
    github_url = Column(String(500), default="")
    portfolio_url = Column(String(500), default="")
    work_authorization = Column(String(255), default="Authorized to work in the US without sponsorship")
    desired_salary = Column(String(100), default="")
    notice_period = Column(String(100), default="Immediate / 2 weeks")
    master_resume_text = Column(Text, default="")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "full_name": self.full_name,
            "email": self.email,
            "phone": self.phone,
            "location": self.location,
            "title": self.title,
            "summary": self.summary,
            "linkedin_url": self.linkedin_url,
            "github_url": self.github_url,
            "portfolio_url": self.portfolio_url,
            "work_authorization": self.work_authorization,
            "desired_salary": self.desired_salary,
            "notice_period": self.notice_period,
            "master_resume_text": self.master_resume_text,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

class Skill(Base):
    __tablename__ = "skills"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, unique=True)
    category = Column(String(100), default="general")  # languages, frameworks, databases, cloud_devops, tools, soft_skills
    proficiency = Column(String(50), default="intermediate")  # beginner, intermediate, expert

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "proficiency": self.proficiency,
        }

class ApplicationActivity(Base):
    __tablename__ = "application_activities"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=False, index=True)
    activity_type = Column(String(50), nullable=False)  # status_change, note, interview, email, follow_up
    title = Column(String(255), nullable=False)
    details = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    job = relationship("Job", back_populates="activities")

    def to_dict(self):
        return {
            "id": self.id,
            "job_id": self.job_id,
            "activity_type": self.activity_type,
            "title": self.title,
            "details": self.details,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

class TailoredDocument(Base):
    __tablename__ = "tailored_documents"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=False, index=True)
    doc_type = Column(String(50), default="cover_letter")  # cover_letter, resume_bullet_points, pitch
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    job = relationship("Job", back_populates="tailored_documents")

    def to_dict(self):
        return {
            "id": self.id,
            "job_id": self.job_id,
            "doc_type": self.doc_type,
            "content": self.content,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
