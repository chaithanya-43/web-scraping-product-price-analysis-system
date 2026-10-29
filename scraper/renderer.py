"""Optional browser fallback for public pages with client-rendered content."""
import logging
from urllib.parse import urlparse

from scraper.fetcher import check_analysis_deadline, fetch_render_resource, validate_public_url

logger = logging.getLogger(__name__)


def render_page(url: str) -> str | None:
    """Render a page through the same polite fetch policy used for static HTML.

    Browser traffic is intercepted: every HTTP resource is validated, checked
    against robots.txt, streamed under a size cap, and paced by hostname.
    """
    url = validate_public_url(url)
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.debug("Playwright is not installed; JavaScript fallback is unavailable")
        return None

    failure = []
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
        except Exception as exc:
            logger.debug("Chromium is unavailable for JavaScript fallback: %s", exc)
            return None
        try:
            context = browser.new_context(user_agent="PriceAnalyzerBot/1.0")

            def proxy_resource(route):
                try:
                    check_analysis_deadline()
                    parsed = urlparse(route.request.url)
                    if parsed.scheme not in {"http", "https"}:
                        route.abort()
                        return
                    status, headers, body = fetch_render_resource(route.request.url)
                    route.fulfill(status=status, headers=headers, body=body)
                except Exception as exc:
                    failure.append(str(exc))
                    try:
                        route.abort()
                    except Exception:
                        pass

            context.route("**/*", proxy_resource)
            page = context.new_page()
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=25_000)
                page.wait_for_timeout(1_200)
                check_analysis_deadline()
                html = page.content()
            except Exception as exc:
                check_analysis_deadline()
                logger.debug("JavaScript rendering could not complete: %s", exc)
                return None
            lowered = html[:20000].lower()
            if any(marker in lowered for marker in ("captcha", "verify you are human", "unusual traffic", "access denied")):
                raise RuntimeError("The site presented an access challenge; JavaScript rendering stopped.")
            if failure:
                logger.debug("One or more JavaScript page resources were blocked: %s", failure[0])
            return html
        finally:
            browser.close()
