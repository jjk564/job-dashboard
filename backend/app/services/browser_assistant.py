import logging
import asyncio
from typing import Dict, Any

logger = logging.getLogger(__name__)

async def launch_assisted_application(job_url: str, profile_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Launches a visible Chromium session with Playwright to pre-fill standard ATS form fields.
    Leaves the browser window open for user review.
    """
    if not job_url:
        return {"success": False, "message": "No application URL provided."}

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return {
            "success": False,
            "message": "Playwright is not installed. Please run 'pip install playwright && playwright install chromium'."
        }

    async def _runner():
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=False)
                context = await browser.new_context()
                page = await context.new_page()
                await page.goto(job_url, timeout=30000)

                # Wait for form elements
                await asyncio.sleep(2)

                full_name = profile_data.get("full_name", "")
                parts = full_name.split()
                first_name = parts[0] if parts else ""
                last_name = " ".join(parts[1:]) if len(parts) > 1 else ""
                email = profile_data.get("email", "")
                phone = profile_data.get("phone", "")
                linkedin = profile_data.get("linkedin_url", "")
                github = profile_data.get("github_url", "")
                portfolio = profile_data.get("portfolio_url", "")

                # Common selector maps
                field_mappings = [
                    ('input[name*="first_name" i], input[id*="first_name" i], input[autocomplete="given-name"]', first_name),
                    ('input[name*="last_name" i], input[id*="last_name" i], input[autocomplete="family-name"]', last_name),
                    ('input[name="name" i], input[id="name" i], input[autocomplete="name"]', full_name),
                    ('input[type="email"], input[name*="email" i], input[id*="email" i]', email),
                    ('input[type="tel"], input[name*="phone" i], input[id*="phone" i]', phone),
                    ('input[name*="linkedin" i], input[id*="linkedin" i], input[placeholder*="linkedin" i]', linkedin),
                    ('input[name*="github" i], input[id*="github" i], input[placeholder*="github" i]', github),
                    ('input[name*="website" i], input[id*="portfolio" i], input[placeholder*="portfolio" i]', portfolio),
                ]

                filled_count = 0
                for selector, val in field_mappings:
                    if val:
                        try:
                            loc = page.locator(selector).first
                            if await loc.count() > 0:
                                await loc.fill(val)
                                filled_count += 1
                        except Exception:
                            pass

                logger.info(f"Assisted application launched. Pre-filled {filled_count} fields.")
                # Keep browser open for user interaction for 5 minutes
                await asyncio.sleep(300)
                await browser.close()
        except Exception as e:
            logger.error(f"Playwright assistant error: {e}")

    # Launch in background so API returns immediately
    asyncio.create_task(_runner())

    return {
        "success": True,
        "message": f"Assisted browser session opened for {job_url}. Review and complete submission in the browser window."
    }
