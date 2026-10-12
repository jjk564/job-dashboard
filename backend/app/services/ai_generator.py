import logging
import httpx
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

def generate_offline_template(
    doc_type: str,
    job_data: Dict[str, Any],
    profile_data: Dict[str, Any],
    matched_skills: list[str],
    tone: str = "professional"
) -> str:
    """Generates high-quality documents without external API calls."""
    candidate_name = profile_data.get("full_name") or "Candidate"
    candidate_email = profile_data.get("email") or "candidate@email.com"
    candidate_phone = profile_data.get("phone") or ""
    candidate_location = profile_data.get("location") or "Remote"
    candidate_title = profile_data.get("title") or "Software Engineer"
    candidate_summary = profile_data.get("summary") or "Experienced engineer committed to building scalable, reliable applications."
    
    company = job_data.get("company") or "the Team"
    job_title = job_data.get("title") or "Software Engineer"
    skills_highlight = ", ".join(matched_skills[:4]) if matched_skills else "modern software engineering practices"

    if doc_type == "cover_letter":
        return f"""# Cover Letter

**{candidate_name}**  
{candidate_location} | {candidate_email} {f'| {candidate_phone}' if candidate_phone else ''}  
{profile_data.get('linkedin_url', '')}  

---

**Dear Hiring Team at {company},**

I am writing to express my enthusiastic interest in the **{job_title}** position. With my background in {candidate_title} and a strong track record of engineering impact, I was immediately drawn to {company}'s mission and technical challenges.

Throughout my experience, I have developed deep expertise working with **{skills_highlight}**. {candidate_summary} I take pride in architecting resilient systems, writing maintainable code, and collaborating closely with cross-functional teams to solve critical business problems.

Specific strengths I bring to the {job_title} role include:
- **Core Technology Mastery**: Extensive hands-on experience leveraging {skills_highlight} to deliver production-grade features.
- **Problem Solving & Architecture**: Designing maintainable, scalable solutions with an emphasis on performance, automated testing, and developer velocity.
- **Ownership & Collaboration**: Driving projects from concept through deployment while maintaining clear communication across teams.

I am eager to bring my problem-solving mindset and technical leadership to {company}. Thank you very much for your time and consideration—I look forward to discussing how my experience aligns with your team's upcoming goals.

Sincerely,  
**{candidate_name}**
"""

    elif doc_type == "resume_bullets":
        skills_str = ", ".join(matched_skills[:5]) if matched_skills else "Python, TypeScript, and modern cloud architecture"
        return f"""# Tailored Resume Highlights for {job_title} at {company}

### Targeted Summary Statement
{candidate_title} with proven expertise in **{skills_str}**. Adept at designing scalable distributed systems, boosting system reliability, and shipping high-value features in fast-paced environments.

### Recommended Targeted Bullet Points
- Architected and delivered core platform services utilizing **{skills_highlight}**, resulting in improved throughput and reduced latency.
- Spearheaded adoption of best engineering practices, automated testing, and CI/CD pipelines across the technical stack.
- Collaborated across product and engineering teams to translate ambiguous requirements into maintainable, performant software solutions.
- Championed code quality, modular architecture, and documentation to accelerate developer onboarding and project velocity.

### Keywords to Ensure on Resume:
{", ".join(f"`{s}`" for s in matched_skills)}
"""

    elif doc_type == "pitch":
        return f"""# Elevator Pitch & Networking Note

**Subject**: {candidate_name} — Quick note regarding {job_title} at {company}

Hi {job_data.get('contact_person') or 'there'},

I noticed {company} is looking for a **{job_title}**, and given my background in {candidate_title} with focus on **{skills_highlight}**, I wanted to reach out directly.

{candidate_summary} I would love to learn more about the team's technical priorities and share how my experience could help accelerate your roadmap.

Best regards,  
{candidate_name}  
{candidate_email}
"""

    return f"Document type '{doc_type}' generated for {job_title} at {company}."

async def generate_ai_document(
    doc_type: str,
    job_data: Dict[str, Any],
    profile_data: Dict[str, Any],
    matched_skills: list[str],
    tone: str = "professional",
    custom_instructions: Optional[str] = None,
    provider: str = "template",
    api_key: Optional[str] = None,
) -> tuple[str, str]:
    """Generates document via template or LLM API (Gemini, OpenAI, Ollama)."""

    # 1. Fallback / default to fast local template
    if provider == "template" or not provider:
        content = generate_offline_template(doc_type, job_data, profile_data, matched_skills, tone)
        return content, "template"

    # 2. Ollama local model
    if provider == "ollama":
        try:
            prompt = f"""You are an expert career coach and technical resume writer.
Generate a {doc_type.replace('_', ' ')} in Markdown.
Tone: {tone}
Job Title: {job_data.get('title')}
Company: {job_data.get('company')}
Job Description: {job_data.get('description', '')[:2000]}
Candidate Profile:
Name: {profile_data.get('full_name')}
Title: {profile_data.get('title')}
Summary: {profile_data.get('summary')}
Matched Skills: {', '.join(matched_skills)}
Custom Instructions: {custom_instructions or 'None'}
"""
            async with httpx.AsyncClient(timeout=30.0) as client:
                res = await client.post(
                    "http://localhost:11434/api/generate",
                    json={"model": "llama3", "prompt": prompt, "stream": False}
                )
                if res.status_code == 200:
                    return res.json().get("response", ""), "ollama"
        except Exception as e:
            logger.warning(f"Ollama generation failed: {e}. Falling back to template.")

    # 3. Gemini API
    if provider == "gemini" and api_key:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
            prompt_text = f"""You are an elite career coach and ATS optimization expert. Write a tailored {doc_type} in Markdown.
Target Role: {job_data.get('title')} at {job_data.get('company')}
Tone: {tone}
Candidate: {profile_data.get('full_name')} ({profile_data.get('title')})
Profile Summary: {profile_data.get('summary')}
Key Matched Skills: {', '.join(matched_skills)}
Job Description: {job_data.get('description', '')[:2500]}
Additional Notes: {custom_instructions or ''}
Return clean, polished Markdown."""
            async with httpx.AsyncClient(timeout=20.0) as client:
                res = await client.post(
                    url,
                    json={"contents": [{"parts": [{"text": prompt_text}]}]}
                )
                if res.status_code == 200:
                    data = res.json()
                    generated = data["candidates"][0]["content"]["parts"][0]["text"]
                    return generated, "gemini"
        except Exception as e:
            logger.warning(f"Gemini API failed: {e}. Falling back to template.")

    # 4. OpenAI API
    if provider == "openai" and api_key:
        try:
            url = "https://api.openai.com/v1/chat/completions"
            headers = {"Authorization": f"Bearer {api_key}"}
            prompt_text = f"""Write a tailored {doc_type} in Markdown.
Target Role: {job_data.get('title')} at {job_data.get('company')}
Tone: {tone}
Candidate: {profile_data.get('full_name')} ({profile_data.get('title')})
Profile Summary: {profile_data.get('summary')}
Key Matched Skills: {', '.join(matched_skills)}
Job Description: {job_data.get('description', '')[:2500]}
Additional Notes: {custom_instructions or ''}"""
            async with httpx.AsyncClient(timeout=20.0) as client:
                res = await client.post(
                    url,
                    headers=headers,
                    json={
                        "model": "gpt-4o-mini",
                        "messages": [{"role": "user", "content": prompt_text}],
                        "temperature": 0.7,
                    }
                )
                if res.status_code == 200:
                    data = res.json()
                    generated = data["choices"][0]["message"]["content"]
                    return generated, "openai"
        except Exception as e:
            logger.warning(f"OpenAI API failed: {e}. Falling back to template.")

    # Fallback
    content = generate_offline_template(doc_type, job_data, profile_data, matched_skills, tone)
    return content, "template (fallback)"
