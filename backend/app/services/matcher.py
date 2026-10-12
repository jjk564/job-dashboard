import re
from typing import List, Dict, Any, Set

COMMON_TECH_SKILLS = [
    # Languages
    "python", "javascript", "typescript", "golang", "go", "java", "c++", "c#", "ruby", "rust", "php", "swift", "kotlin", "sql", "bash", "html", "css",
    # Frontend
    "react", "vue", "angular", "svelte", "next.js", "nextjs", "nuxt", "tailwind", "tailwindcss", "redux", "graphql", "webpack", "vite", "sass", "bootstrap",
    # Backend & Frameworks
    "node.js", "nodejs", "fastapi", "django", "flask", "express", "spring", "spring boot", "ruby on rails", "rails", "asp.net", "laravel", "nest.js",
    # Databases & Caching
    "postgresql", "postgres", "mysql", "mongodb", "sqlite", "redis", "elasticsearch", "dynamodb", "cassandra", "supabase", "firebase",
    # Cloud & DevOps & Infra
    "aws", "amazon web services", "azure", "gcp", "google cloud", "docker", "kubernetes", "k8s", "terraform", "ansible", "ci/cd", "github actions", "gitlab", "jenkins", "linux", "nginx", "helm",
    # Architecture & Practices
    "microservices", "rest", "restful", "api", "grpc", "event-driven", "kafka", "rabbitmq", "distributed systems", "system design", "agile", "scrum", "tdd", "unit testing",
    # AI & Data
    "machine learning", "deep learning", "nlp", "llm", "pytorch", "tensorflow", "pandas", "numpy", "scikit-learn", "data engineering", "spark", "airflow"
]

def extract_tech_keywords(text: str) -> Set[str]:
    """Finds known technical keywords in any text block."""
    if not text:
        return set()
    text_lower = " " + text.lower() + " "
    found = set()
    for skill in COMMON_TECH_SKILLS:
        # Use regex to match word boundaries
        pattern = r"(?:\b|\s)" + re.escape(skill) + r"(?:\b|\s)"
        if re.search(pattern, text_lower):
            found.add(skill)
    return found

def analyze_job_fit(job_text: str, candidate_skills: List[str], profile_text: str = "") -> Dict[str, Any]:
    """
    Computes an ATS match score between a job description and candidate profile.
    Returns matched skills, missing skills, and percentage score.
    """
    if not job_text:
        return {
            "score": 75,
            "matched_skills": candidate_skills[:5],
            "missing_skills": [],
            "detected_requirements": [],
            "summary": "Job description is empty. Basic fit assumed.",
        }

    # Extract required skills from job
    job_reqs = extract_tech_keywords(job_text)

    # Candidate skills normalized
    candidate_set = {s.lower().strip() for s in candidate_skills if s}
    if profile_text:
        profile_skills = extract_tech_keywords(profile_text)
        candidate_set.update(profile_skills)

    if not job_reqs:
        # If no specific tech skills were isolated, fallback to word overlap
        return {
            "score": 70,
            "matched_skills": list(candidate_set)[:5],
            "missing_skills": [],
            "detected_requirements": [],
            "summary": "No specific technical stack detected. Good general profile match.",
        }

    matched = sorted(list(job_reqs.intersection(candidate_set)))
    missing = sorted(list(job_reqs.difference(candidate_set)))

    # Calculate match percentage
    match_ratio = len(matched) / len(job_reqs)
    score = int(round(match_ratio * 100))

    # Clamp score between 10 and 98 to keep it realistic
    score = max(10, min(98, score))

    if score >= 80:
        summary = f"Strong match! You meet {len(matched)} of {len(job_reqs)} core requirements."
    elif score >= 50:
        summary = f"Good match. You align on {len(matched)} key technologies, but {len(missing)} are missing."
    else:
        summary = f"Partial match. Job calls for {len(missing)} skills not listed in your profile."

    return {
        "score": score,
        "matched_skills": matched,
        "missing_skills": missing,
        "detected_requirements": sorted(list(job_reqs)),
        "summary": summary,
    }
