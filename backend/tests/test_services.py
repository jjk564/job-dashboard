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

@pytest.mark.asyncio
async def test_search_aggregated_jobs_sources():
    from app.services.job_fetcher import search_aggregated_jobs, matches_query, is_us_eligible
    
    # Test keyword & synonym matching
    assert matches_query("developer", "Senior Software Engineer", "Acme", [], "Python FastAPI")
    assert matches_query("frontend", "React UI Developer", "Acme", [], "Building sleek web apps")
    assert matches_query("devops", "Site Reliability Engineer", "Acme", [], "Kubernetes AWS")
    assert not matches_query("accounting", "Software Engineer", "Acme", [], "Python code")

    # Test US eligibility filter
    assert is_us_eligible("Remote, USA", "Software Engineer", "US-based remote role")
    assert is_us_eligible("USA", "Developer", "Anywhere in the US")
    assert not is_us_eligible("Berlin, Germany", "Software Engineer (m/w/d)", "Festanstellung in Berlin")
    assert not is_us_eligible("London, UK", "Senior Backend Engineer", "Europe only role")

    # Test aggregated search with WWR
    jobs_wwr = await search_aggregated_jobs(query="engineer", source="weworkremotely")
    assert isinstance(jobs_wwr, list)
    if jobs_wwr:
        assert jobs_wwr[0]["source"] == "weworkremotely"


def test_entry_level_matching():
    from app.services.job_fetcher import matches_query

    # 1. 'entry level software engineer' should match Junior/Associate/Level-1 roles even without literal word 'level'
    assert matches_query(
        "entry level software engineer",
        "Associate, Software Engineering",
        "L3Harris",
        [],
        "Great role for recent college graduates in Python and C++."
    )
    assert matches_query(
        "entry level software engineer",
        "Software Engineer I",
        "Acme Corp",
        [],
        "0-2 years of experience building backend services."
    )
    assert matches_query(
        "junior developer",
        "Entry Level Application Developer",
        "XpressDocs",
        [],
        "We are a technology company with more than 20 years of experience helping clients. Must be 21 years of age."
    )

    # 2. Reject Senior / Mid-Level / 5+ years experience when querying junior/entry-level
    assert not matches_query(
        "junior developer",
        "Senior Software Engineer",
        "Acme",
        [],
        "We use internal tools and internet services."
    )
    assert not matches_query(
        "junior developer",
        "Mid-Level Automation Developer",
        "Acme",
        [],
        "Building automation scripts."
    )
    assert not matches_query(
        "junior developer",
        "Software Engineer",
        "Acme",
        [],
        "Requires 5+ years of software development experience."
    )

