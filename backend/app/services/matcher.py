import re
from typing import List, Dict, Any, Set

COMMON_TECH_SKILLS = [
    # Languages & Scripting
    "python", "javascript", "typescript", "golang", "java", "c++", "c#", "ruby", "rust", "php", "swift", "kotlin", "sql", "bash", "powershell", "html", "css",
    # Frontend
    "react", "vue", "angular", "svelte", "next.js", "nextjs", "nuxt", "tailwind", "tailwindcss", "redux", "graphql", "webpack", "vite", "sass", "bootstrap",
    # Backend & Frameworks
    "node.js", "nodejs", "fastapi", "django", "flask", "express", "spring", "spring boot", "ruby on rails", "rails", "asp.net", "laravel", "nest.js",
    # Databases & Caching
    "postgresql", "postgres", "mysql", "mongodb", "sqlite", "redis", "elasticsearch", "dynamodb", "cassandra", "supabase", "firebase",
    # Cloud & DevOps & Infra
    "aws", "amazon web services", "azure", "gcp", "google cloud", "docker", "kubernetes", "k8s", "terraform", "ansible", "ci/cd", "github actions", "gitlab", "jenkins", "linux", "nginx", "helm", "git", "github",
    # Enterprise IT & Identity & Platforms
    "active directory", "azure ad", "entra id", "microsoft 365", "m365", "exchange", "microsoft teams", "servicenow", "microsoft dynamics 365", "dynamics 365", "iam", "access control", "sso", "okta",
    # Operating Systems & Endpoint Administration
    "windows 10", "windows 11", "windows server", "macos", "ubuntu", "debian", "endpoint administration", "endpoint management", "desktop support", "help desk", "technical support", "it support", "ticketing",
    # Networking & Protocols
    "tcp/ip", "dns", "dhcp", "vpn", "lan/wan", "lan", "wan", "wi-fi", "wifi", "subnetting", "firewalls", "firewall", "routing", "routers", "switches", "network administration", "network troubleshooting", "networking",
    # Cybersecurity & Operations
    "cybersecurity", "incident response", "log analysis", "siem", "soc", "vulnerability management", "cve", "nvd", "threat analysis", "information security",
    # Hardware & Diagnostics
    "hardware diagnostics", "root-cause analysis", "pcb", "firmware", "microcontroller", "endpoint imaging",
    # Architecture & Practices
    "microservices", "rest", "restful", "api", "grpc", "event-driven", "kafka", "rabbitmq", "distributed systems", "system design", "agile", "scrum", "tdd", "unit testing", "automation", "workflow automation",
    # AI & Data & ETL
    "machine learning", "deep learning", "nlp", "llm", "pytorch", "tensorflow", "pandas", "numpy", "scikit-learn", "data engineering", "spark", "airflow", "data processing", "data pipelines", "data analysis", "etl"
]

# Strict Golang pattern to avoid false positives on the English verb 'go'
GOLANG_PATTERN = re.compile(
    r"\b(?:golang|go\s*lang(?:uage)?)\b|"
    r"\bgo\s+(?:developer|engineer|dev|code|programming|backend)\b|"
    r"\b(?:built|written|implemented|develop(?:ed)?|experience|coding|proficient|fluency|programming|looking for|seeking)\s+(?:in|with|for)?\s*go\b|"
    r"(?:\bpython|\bjava|\bc\+\+|\brust|\bc#|\bkubernetes|\bdocker|\btypescript|\breact|\bkafka|\baws)[,\s/]+go\b|"
    r"\bgo[,\s/]+(?:python|java|rust|c\+\+|c#|kubernetes|docker|typescript|react|kafka|aws)\b",
    re.IGNORECASE
)

# Canonical synonym mapping to prevent minor phrasing mismatches
SKILL_SYNONYMS = {
    "golang": "go",
    "go": "go",
    "postgres": "postgresql",
    "postgresql": "postgresql",
    "nodejs": "node.js",
    "node": "node.js",
    "node.js": "node.js",
    "reactjs": "react",
    "react.js": "react",
    "react": "react",
    "nextjs": "next.js",
    "next.js": "next.js",
    "k8s": "kubernetes",
    "kubernetes": "kubernetes",
    "amazon web services": "aws",
    "aws": "aws",
    "google cloud": "gcp",
    "gcp": "gcp",
    "rest": "rest",
    "restful": "rest",
    "rest api": "rest",
    "rest apis": "rest",
    "api": "rest",
    "apis": "rest",
    "github": "git",
    "git": "git",
    "github actions": "github actions",
    "tailwindcss": "tailwind",
    "tailwind": "tailwind",
    "workflow automation": "automation",
    "automation": "automation",
    "data processing": "data processing",
    "data pipelines": "data processing",
    "data pipeline": "data processing",
    "data analysis": "data processing",
    "data engineering": "data processing",
    "etl": "etl",
    # Enterprise & Identity
    "microsoft 365": "m365",
    "office 365": "m365",
    "o365": "m365",
    "azure ad": "active directory",
    "entra id": "active directory",
    "azure active directory": "active directory",
    "microsoft dynamics": "dynamics 365",
    "microsoft dynamics 365": "dynamics 365",
    # IT Support & Admin
    "helpdesk": "help desk",
    "desktop support": "it support",
    "technical support": "it support",
    "sysadmin": "systems administration",
    "system administration": "systems administration",
    "systems administrator": "systems administration",
    "endpoint administration": "endpoint administration",
    "endpoint management": "endpoint administration",
    # Networking
    "wifi": "wi-fi",
    "firewall": "firewalls",
    "lan": "networking",
    "wan": "networking",
    "lan/wan": "networking",
    "tcp/ip": "networking",
    "network troubleshooting": "networking",
    # Security
    "cve": "vulnerability management",
    "nvd": "vulnerability management",
    "information security": "cybersecurity",
}

# Real-world implied competencies (e.g. Pandas implies data processing and data analysis)
IMPLIED_SKILLS = {
    "pandas": {"data processing", "data analysis", "etl"},
    "scikit-learn": {"machine learning", "data analysis"},
    "pytorch": {"machine learning", "deep learning"},
    "tensorflow": {"machine learning", "deep learning"},
    "fastapi": {"rest", "api"},
    "django": {"rest", "api"},
    "flask": {"rest", "api"},
    "express": {"rest", "api"},
    "power automate": {"automation", "workflow automation"},
    "active directory": {"access control", "windows server", "iam"},
    "m365": {"active directory", "it support", "endpoint administration"},
    "servicenow": {"ticketing", "it support", "incident response"},
    "dynamics 365": {"ticketing", "it support", "sla"},
    "wi-fi": {"networking"},
    "dns": {"networking"},
    "dhcp": {"networking"},
    "vpn": {"networking", "cybersecurity"},
    "firewalls": {"networking", "cybersecurity"},
    "siem": {"log analysis", "incident response", "cybersecurity"},
    "soc": {"incident response", "cybersecurity", "log analysis"},
    "auth.log": {"log analysis", "linux"},
}

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
            canonical = SKILL_SYNONYMS.get(skill, skill)
            found.add(canonical)
    if GOLANG_PATTERN.search(text_lower):
        found.add("go")
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
    candidate_set = set()
    for s in candidate_skills:
        if not s:
            continue
        s_norm = s.lower().strip()
        canonical = SKILL_SYNONYMS.get(s_norm, s_norm)
        candidate_set.add(canonical)

    if profile_text:
        profile_skills = extract_tech_keywords(profile_text)
        candidate_set.update(profile_skills)

    # Expand candidate set with implied skills (e.g. Pandas -> data processing)
    implied = set()
    for s in list(candidate_set):
        if s in IMPLIED_SKILLS:
            for imp in IMPLIED_SKILLS[s]:
                implied.add(SKILL_SYNONYMS.get(imp, imp))
    candidate_set.update(implied)

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
