import pytest
from app.services.matcher import extract_tech_keywords, analyze_job_fit
from app.services.ai_generator import generate_offline_template
from app.services.job_extractor import extract_salary_range

def test_extract_tech_keywords():
    sample_text = """
    We are seeking a Senior Python Engineer who has extensive experience with
    FastAPI, PostgreSQL, Docker, and React. Experience with AWS and CI/CD pipelines
    is a huge plus.
    """
    found = extract_tech_keywords(sample_text)
    assert "python" in found
    assert "fastapi" in found
    assert "postgresql" in found
    assert "docker" in found
    assert "react" in found
    assert "aws" in found

def test_analyze_job_fit():
    job_text = "Required: Python, React, PostgreSQL, Docker, AWS"
    candidate_skills = ["Python", "React", "PostgreSQL", "Docker", "AWS", "Git"]

    fit = analyze_job_fit(job_text, candidate_skills)
    assert fit["score"] >= 80
    assert "python" in fit["matched_skills"]
    assert "react" in fit["matched_skills"]
    assert len(fit["missing_skills"]) == 0

def test_analyze_job_fit_partial():
    job_text = "Looking for Go, Kubernetes, Kafka, and Terraform."
    candidate_skills = ["Python", "React"]

    fit = analyze_job_fit(job_text, candidate_skills)
    assert fit["score"] <= 40
    assert "kubernetes" in fit["missing_skills"]
    assert "kafka" in fit["missing_skills"]

def test_salary_extraction():
    text1 = "Base salary is $130,000 - $160,000 per year plus equity."
    min_sal, max_sal = extract_salary_range(text1)
    assert min_sal == 130000.0
    assert max_sal == 160000.0

    text2 = "Compensation: $140k to $180k USD"
    min_sal2, max_sal2 = extract_salary_range(text2)
    assert min_sal2 == 140000.0
    assert max_sal2 == 180000.0

def test_generate_offline_template():
    job_data = {
        "title": "Lead Backend Engineer",
        "company": "Acme Cloud",
    }
    profile_data = {
        "full_name": "Justin Kilpatrick",
        "email": "justin@example.com",
        "title": "Senior Engineer",
        "summary": "Building high-performance distributed systems.",
    }
    letter = generate_offline_template(
        "cover_letter",
        job_data,
        profile_data,
        ["python", "fastapi", "docker"]
    )
    assert "Acme Cloud" in letter
    assert "Justin Kilpatrick" in letter
    assert "Lead Backend Engineer" in letter
