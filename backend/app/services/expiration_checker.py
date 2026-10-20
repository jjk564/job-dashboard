import logging
from datetime import datetime
from typing import Tuple, Optional
import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

COMMON_EXPIRED_PHRASES = [
    "this job has expired",
    "this job is no longer available",
    "this posting has expired",
    "job posting has expired",
    "no longer accepting applications",
    "this position is closed",
    "position has been filled",
    "the position you are looking for is closed",
    "this position has been closed",
    "job is closed",
    "this role has been filled",
    "this role is no longer available",
    "this job posting is no longer active",
    "this vacancy has expired",
    "this listing is inactive",
    "job no longer available",
    "posting has expired",
    "posting is closed",
    "applications are now closed",
    "application deadline has passed",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
}

async def check_job_expiration(
    url: Optional[str],
    deadline: Optional[datetime] = None
) -> Tuple[bool, Optional[str]]:
    """
    Checks if a job posting has expired based on application deadline or live webpage inspection.
    Returns: (is_expired: bool, reason: Optional[str])
    """
    # 1. Deadline check
    if deadline:
        now = datetime.utcnow()
        deadline_naive = deadline.replace(tzinfo=None) if deadline.tzinfo else deadline
        if deadline_naive < now:
            return True, f"Application deadline passed on {deadline.strftime('%b %d, %Y')}"

    # 2. URL check
    if not url or not url.startswith(("http://", "https://")):
        return False, None

    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True, headers=HEADERS) as client:
            resp = await client.get(url)

            # Hard 404 or 410 Gone
            if resp.status_code in (404, 410):
                return True, f"Posting link unavailable (HTTP {resp.status_code})"

            # If platform bot protection blocked the check (401, 403, 429), don't falsely expire
            if resp.status_code in (401, 403, 429):
                logger.info("Bot challenge or rate limit (%s) for %s", resp.status_code, url)
                return False, None

            # Check if redirected to a generic search / landing page
            orig_lower = url.lower()
            final_lower = str(resp.url).lower()
            if "indeed.com/viewjob" in orig_lower and "indeed.com/viewjob" not in final_lower:
                return True, "Redirected from job posting to search page"

            if "ziprecruiter.com/c/" in orig_lower and "/job/" not in final_lower and "/c/" not in final_lower:
                return True, "Redirected from job posting"

            # Parse visible text
            soup = BeautifulSoup(resp.text, "html.parser")
            for tag in soup(["script", "style", "noscript", "header", "footer", "nav"]):
                tag.decompose()

            text = " ".join(soup.get_text(" ").split()).lower()
            for phrase in COMMON_EXPIRED_PHRASES:
                if phrase in text:
                    return True, f"Posting closed: '{phrase.title()}'"

            return False, None

    except httpx.ConnectError:
        return True, "Posting host domain is unreachable"
    except Exception as e:
        logger.warning("Error checking expiration for %s: %s", url, e)
        return False, None
