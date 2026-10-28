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

def test_golang_prose_does_not_match_english_go():
    text = "Conducting rigorous evaluations that go beyond benchmarks and help products go live."
    found = extract_tech_keywords(text)
    assert "go" not in found
    assert "golang" not in found

def test_pandas_implies_data_processing():
    job_text = "Seeking engineer to build data processing pipelines in Python."
    candidate_skills = ["Python", "Pandas"]
    fit = analyze_job_fit(job_text, candidate_skills)
    assert fit["score"] >= 80
    assert "data processing" in fit["matched_skills"]

def test_salary_extraction():
    text1 = "Base salary is $130,000 - $160,000 per year plus equity."
    min_sal, max_sal = extract_salary_range(text1)
    assert min_sal == 130000.0
    assert max_sal == 160000.0

    text2 = "Compensation: $140k to $180k USD"
    min_sal2, max_sal2 = extract_salary_range(text2)
    assert min_sal2 == 140000.0
    assert max_sal2 == 180000.0

    # Hourly rate extraction (converted to annual at 2080 hrs/yr)
    text3 = "Pay: $30 - $45 per hour depending on experience."
    min_sal3, max_sal3 = extract_salary_range(text3)
    assert min_sal3 == 30.0 * 2080
    assert max_sal3 == 45.0 * 2080

    text4 = "Rate: $35/hr"
    min_sal4, max_sal4 = extract_salary_range(text4)
    assert min_sal4 == 35.0 * 2080
    assert max_sal4 == 35.0 * 2080

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


def test_new_board_helpers_and_us_location_filtering():
    from app.services.job_fetcher import (
        is_us_eligible,
        _has_us_indicator,
        _matches_target_location,
        _clean_bigtech_query,
    )

    # US state code and indicator checks
    assert _has_us_indicator("San Francisco, CA")
    assert _has_us_indicator("Austin, TX")
    assert _has_us_indicator("Remote in USA")
    assert not _has_us_indicator("Bristol, UK")
    assert not _has_us_indicator("Toronto, ON, Canada")

    # SimplifyJobs / multi-location list US filtering
    assert is_us_eligible("Jupiter, FL", "Software Engineer", "", location_list=["Jupiter, FL"])
    assert not is_us_eligible("Bristol, UK", "Graduate Software Engineer", "", location_list=["Bristol, UK"])
    assert not is_us_eligible("Israel, Yokneam", "Software Engineer", "")

    # Target location filtering for boards without native radius
    assert _matches_target_location("Austin, TX", "Austin, TX", is_remote=False, include_remote=True)
    assert _matches_target_location("Remote, USA", "Austin, TX", is_remote=True, include_remote=True)
    assert not _matches_target_location("Remote, USA", "Austin, TX", is_remote=True, include_remote=False)
    assert not _matches_target_location("Boston, MA", "Austin, TX", is_remote=False, include_remote=True)
    # Hybrid listings outside target range must be filtered out even when include_remote=True
    assert not _matches_target_location("Hybrid - Seattle, WA", "Austin, TX", is_remote=False, include_remote=True, workplace_type="hybrid")
    assert not _matches_target_location("San Francisco, CA (Hybrid)", "Austin, TX", is_remote=False, include_remote=True, workplace_type="hybrid")
    # Hybrid listings within local commute radius are allowed
    assert _matches_target_location("Round Rock, TX", "Austin, TX", is_remote=False, include_remote=True, radius=25, workplace_type="hybrid")
    # Out of radius in same state (Dallas is ~180mi from Austin)
    assert not _matches_target_location("Dallas, TX", "Austin, TX", is_remote=False, include_remote=True, radius=25, workplace_type="hybrid")

    # Single-company portal query cleaning
    assert _clean_bigtech_query("Google", "Google") == "software engineer"
    assert _clean_bigtech_query("Microsoft backend python", "Microsoft") == "backend python"
    assert _clean_bigtech_query("Amazon it support", "Amazon") == "it support"

def test_it_support_and_sysadmin_matching():
    from app.services.job_fetcher import matches_query, _term_matches, _has_junior_signals
    from app.services.matcher import extract_tech_keywords, analyze_job_fit

    # 1. Matches IT Support, Help Desk, Desktop Support synonym queries
    assert matches_query("it support", "Help Desk Technician", "Acme Health", [], "Troubleshoot Windows 10/11 and Active Directory")
    assert matches_query("sysadmin", "Systems Administrator", "City Hospital", [], "Administer Windows Server and M365")
    assert matches_query("network", "NOC Technician", "Telecom Corp", [], "Monitor TCP/IP, DNS, DHCP, and VPN routing")
    assert matches_query("cybersecurity", "SOC Analyst Tier 1", "Cyber Defense", [], "Review auth.log and investigate incidents")

    # 2. Junior signals for IT Support Tier 1 & 2
    assert _has_junior_signals("IT Support Specialist Tier 1", "Provide first-line endpoint support.")
    assert _has_junior_signals("Desktop Support Technician I", "1 year of experience with Geek Squad or MSP.")

    # 3. Matcher extraction for Resume 2 IT competencies
    text = "Requirements: Active Directory, Microsoft 365, ServiceNow, Windows Server, TCP/IP, and VPN."
    extracted = extract_tech_keywords(text)
    assert "active directory" in extracted
    assert "m365" in extracted
    assert "servicenow" in extracted
    assert "windows server" in extracted
    assert "networking" in extracted  # via TCP/IP / VPN

    # 4. Job fit analysis with IT skills
    candidate_skills = ["Active Directory", "Microsoft 365", "Windows Server", "ServiceNow", "TCP/IP", "VPN"]
    fit = analyze_job_fit(text, candidate_skills)
    assert fit["score"] >= 80
    assert "active directory" in fit["matched_skills"]
    assert "m365" in fit["matched_skills"]

@pytest.mark.asyncio
async def test_check_job_expiration_deadline():
    from datetime import datetime, timedelta
    from app.services.expiration_checker import check_job_expiration

    # Past deadline
    past = datetime.utcnow() - timedelta(days=2)
    is_exp, reason = await check_job_expiration(None, deadline=past)
    assert is_exp is True
    assert "deadline passed" in reason.lower()

    # Future deadline with no URL
    future = datetime.utcnow() + timedelta(days=10)
    is_exp2, reason2 = await check_job_expiration(None, deadline=future)
    assert is_exp2 is False
    assert reason2 is None

@pytest.mark.asyncio
async def test_check_job_expiration_invalid_url():
    from app.services.expiration_checker import check_job_expiration
    is_exp, reason = await check_job_expiration("not-a-valid-url")
    assert is_exp is False
    assert reason is None



