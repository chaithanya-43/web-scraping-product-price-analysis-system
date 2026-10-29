import logging
logger = logging.getLogger(__name__)

from datetime import datetime, timezone
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from scraper.fetcher import (
    AnalysisTimeout,
    bounded_analysis,
    check_analysis_deadline,
    fetch_page,
    validate_public_url,
)
from scraper.parser import parse_products
from scraper.renderer import render_page
from scraper.parsers.generic import (
    parse_products as parse_generic_products,
)
from scraper.parsers.testingurl import (
    parse_products as parse_testingurl_products,
)
from scraper.sources import detect_source

MAX_DETAIL_ENRICHMENTS = 160


class ScrapeResult(list):
    """Collected products plus page counts for graceful partial analyses."""

    def __init__(self, products, pages_scraped, pages_requested, page_product_counts=None):
        super().__init__(products)
        self.pages_scraped = pages_scraped
        self.pages_requested = pages_requested
        self.page_product_counts = list(page_product_counts or [])


def add_metadata(products, website_name):
    """Add common metadata to scraped products."""

    scraped_at = datetime.now(timezone.utc).isoformat()

    for product in products:
        product["website_name"] = website_name

        if "discount" not in product:
            product["discount"] = None

        if "currency" not in product:
            price = str(product.get("price", ""))

            if "₹" in price or "Rs" in price or "INR" in price:
                product["currency"] = "INR"
            elif "£" in price or "Â£" in price:
                product["currency"] = "GBP"
            elif "$" in price:
                product["currency"] = "USD"
            elif "€" in price:
                product["currency"] = "EUR"
            else:
                product["currency"] = None

        product["last_updated"] = scraped_at

    return products


def find_next_page(html, current_url):
    """Find the next-page URL on Books to Scrape."""

    soup = BeautifulSoup(html, "html.parser")
    next_link = soup.select_one("li.next a")

    if not next_link or not next_link.get("href"):
        return None

    return urljoin(current_url, next_link["href"])


def find_generic_next_page(html, current_url):
    """Find common next-page links, including Flipkart's Next link."""

    soup = BeautifulSoup(html, "html.parser")
    current_host = urlparse(current_url).netloc

    selectors = [
        'a[rel="next"]',
        'link[rel="next"]',
        'a[aria-label="Next"]',
        'a[aria-label="Next page"]',
        'a[title="Next"]',
        "a.next",
        "a.next-page",
        "a.pagination-next",
        'a[class*="next"]',
    ]

    for selector in selectors:
        for link in soup.select(selector):
            href = link.get("href")

            if not href:
                continue

            next_url = urljoin(current_url, href)

            if (
                urlparse(next_url).netloc == current_host
                and next_url != current_url
            ):
                return next_url

    # Fallback for pagination links identified by visible text.
    for link in soup.select("a[href]"):
        text = link.get_text(" ", strip=True).lower()
        label = " ".join((link.get("aria-label", ""), link.get("title", ""))).lower()

        if not (text.startswith("next") or label.startswith("next") or text in ("›", "→")):
            continue

        next_url = urljoin(current_url, link["href"])

        if (
            urlparse(next_url).netloc == current_host
            and next_url != current_url
        ):
            return next_url

    return None


def debug_prices(products, label, limit=10):
    """Print sample product prices to diagnose extraction problems."""

    logger.debug(f"\n===== {label}: PRICE DEBUG =====")
    logger.debug(f"Products received: {len(products)}")

    for index, product in enumerate(products[:limit], start=1):
        logger.debug(
            f"[PRICE DEBUG {index}] "
            f"Name={product.get('product_name')!r} | "
            f"Price={product.get('price')!r} | "
            f"Currency={product.get('currency')!r} | "
            f"Link={product.get('product_link')!r}"
        )

    missing = sum(
        1 for product in products
        if product.get("price") is None
        or str(product.get("price")).strip() == ""
    )

    logger.debug(f"Products with missing prices: {missing}")
    logger.debug(f"Products with a price value: {len(products) - missing}")
    logger.debug("================================\n")


def _product_identity(value):
    """Normalize punctuation and spacing while preserving every variant token."""
    return re.sub(r"[^a-z0-9]", "", str(value or "").casefold())


@bounded_analysis
def scrape_products(url, pages=1):
    """Scrape a supported or generically extractable website."""

    if not isinstance(pages, int) or isinstance(pages, bool):
        raise ValueError("pages must be an integer.")

    if pages < 1:
        raise ValueError("pages must be at least 1.")

    if pages > 20:
        raise ValueError("A maximum of 20 pages can be analyzed at once.")

    url = validate_public_url(url)
    source = detect_source(url)

    if source == "books_to_scrape":
        return add_metadata(
            scrape_books_to_scrape(url, pages),
            "Books to Scrape",
        )

    if source == "testingurl":
        return add_metadata(
            scrape_testingurl(url, pages),
            "TestingURL.dev",
        )

    return scrape_generic(url, pages)


def scrape_books_to_scrape(url, pages=1):
    """Scrape Books to Scrape using its existing pagination."""

    all_products = []
    current_url = url
    visited = set()
    pages_scraped = 0
    page_product_counts = []

    for page_number in range(1, pages + 1):
        if current_url in visited:
            break

        visited.add(current_url)
        try:
            check_analysis_deadline()
            html = fetch_page(current_url)
        except (AnalysisTimeout, ValueError, RuntimeError) as exc:
            if pages_scraped:
                logger.info("Stopping after %s of %s requested pages: %s", pages_scraped, pages, exc)
                break
            raise
        pages_scraped += 1

        logger.debug(f"[Books] Fetching page {page_number}: {current_url}")

        products = parse_products(html, base_url=current_url)

        debug_prices(products, f"Books page {page_number}")
        page_product_counts.append(len(products))
        all_products.extend(products)

        logger.debug(f"[Books] Products on page: {len(products)}")
        logger.debug(f"[Books] Total products: {len(all_products)}")

        if page_number == pages:
            break

        next_page = find_next_page(html, current_url)
        logger.debug(f"[Books] Next page URL: {next_page}")

        if not next_page:
            break

        current_url = next_page

    return ScrapeResult(all_products, pages_scraped, pages, page_product_counts)


def scrape_testingurl(url, pages=1):
    """Scrape TestingURL.dev."""

    all_products = []
    current_url = url
    visited = set()
    pages_scraped = 0
    page_product_counts = []

    for page_number in range(1, pages + 1):
        if current_url in visited:
            break

        visited.add(current_url)
        try:
            check_analysis_deadline()
            html = fetch_page(current_url)
        except (AnalysisTimeout, ValueError, RuntimeError) as exc:
            if pages_scraped:
                logger.info("Stopping after %s of %s requested pages: %s", pages_scraped, pages, exc)
                break
            raise
        pages_scraped += 1

        logger.debug(f"[TestingURL] Fetching page {page_number}: {current_url}")

        products = parse_testingurl_products(
            html,
            base_url=current_url,
        )

        if not products:
            products = parse_generic_products(
                html,
                base_url=current_url,
            )

        debug_prices(products, f"TestingURL page {page_number}")
        page_product_counts.append(len(products))
        all_products.extend(products)

        logger.debug(f"[TestingURL] Products on page: {len(products)}")
        logger.debug(f"[TestingURL] Total products: {len(all_products)}")

        if page_number == pages:
            break

        soup = BeautifulSoup(html, "html.parser")
        next_link = soup.select_one(
            'a[rel="next"], link[rel="next"]'
        )

        if not next_link or not next_link.get("href"):
            logger.debug("[TestingURL] No next-page link found.")
            break

        next_url = urljoin(current_url, next_link["href"])

        if next_url in visited:
            break

        current_url = next_url

    return ScrapeResult(all_products, pages_scraped, pages, page_product_counts)


def scrape_generic(url, pages=1):
    """Scrape generic pages using the generic product parser."""

    all_products = []
    current_url = validate_public_url(url)
    visited_pages = set()

    parsed_url = urlparse(url)
    website_name = parsed_url.netloc

    if website_name.startswith("www."):
        website_name = website_name[4:]

    source_host = parsed_url.hostname
    pages_scraped = 0
    page_product_counts = []

    # Fetch up to the requested number of pages. If a later page is gone or blocked,
    # keep the pages already collected and analyze those results.
    for page_number in range(1, pages + 1):
        if current_url in visited_pages:
            logger.debug("[Generic] Repeated page detected; stopping.")
            break

        visited_pages.add(current_url)

        logger.debug(f"[Generic] Fetching page {page_number}: {current_url}")
        try:
            check_analysis_deadline()
            html = fetch_page(current_url)
        except (AnalysisTimeout, ValueError, RuntimeError) as exc:
            if pages_scraped:
                logger.info("Stopping after %s of %s requested pages: %s", pages_scraped, pages, exc)
                break
            raise
        pages_scraped += 1
        pagination_html = html
        logger.debug(f"[Generic] HTML length: {len(html)}")

        products = parse_generic_products(
            html,
            base_url=current_url,
        )

        if page_number == 1 and (not products or not any(product.get("price") is not None for product in products)):
            try:
                rendered_html = render_page(current_url)
            except (AnalysisTimeout, ValueError, RuntimeError) as exc:
                logger.debug("JavaScript fallback stopped: %s", exc)
                rendered_html = None
            if rendered_html:
                rendered_products = parse_generic_products(rendered_html, base_url=current_url)
                if rendered_products and any(product.get("price") is not None for product in rendered_products):
                    products = rendered_products
                    pagination_html = rendered_html
                    logger.debug("JavaScript fallback recovered %s product rows", len(products))

        logger.debug(f"[Generic] Products found on page: {len(products)}")
        debug_prices(products, f"Generic page {page_number}")
        page_product_counts.append(len(products))
        all_products.extend(products)

        logger.debug(f"[Generic] Total products so far: {len(all_products)}")

        if page_number == pages:
            break

        next_page = find_generic_next_page(pagination_html, current_url)
        logger.debug(f"[Generic] Next page URL: {next_page}")

        if not next_page:
            logger.debug("[Generic] No recognizable next-page link. Stopping.")
            break

        current_url = validate_public_url(next_page)

    # Enrich products that have no price.
    # This limit does not limit the total number of products collected.
    enriched = 0
    visited_products = set()

    for product in all_products:
        try:
            check_analysis_deadline()
        except AnalysisTimeout as exc:
            logger.debug(f"[Generic] Detail enrichment stopped at the analysis deadline: {exc}")
            break

        link = product.get("product_link")

        if not link or link in visited_products:
            continue

        if product.get("price") is not None:
            continue

        if enriched >= MAX_DETAIL_ENRICHMENTS:
            logger.debug("[Generic] Detail enrichment limit reached.")
            break

        if urlparse(link).hostname != source_host:
            continue

        visited_products.add(link)

        try:
            detail_html = fetch_page(link)
        except AnalysisTimeout as exc:
            logger.debug(f"[Generic] Detail enrichment stopped at the analysis deadline: {exc}")
            break
        except (ValueError, RuntimeError) as exc:
            logger.debug(f"[Generic] Detail page skipped: {exc}")
            continue

        detail_products = parse_generic_products(
            detail_html,
            base_url=link,
        )

        if not detail_products:
            logger.debug(f"[Generic] No product data found on detail page: {link}")
            continue

        detail = detail_products[0]

        if _product_identity(product.get("product_name")) != _product_identity(
            detail.get("product_name")
        ):
            logger.debug(
                "[Generic] Detail page skipped because its product/variant "
                f"does not exactly match the listing: "
                f"{product.get('product_name')!r} != "
                f"{detail.get('product_name')!r}"
            )
            continue

        for field in (
            "price",
            "currency",
            "rating",
            "availability",
            "category",
        ):
            if not product.get(field) and detail.get(field):
                product[field] = detail[field]

        if product.get("price") is not None:
            logger.debug(
                f"[Generic] Detail price recovered: "
                f"{product.get('product_name')!r} -> "
                f"{product.get('price')!r}"
            )

        enriched += 1

    debug_prices(all_products, "Generic after detail enrichment")

    logger.debug(f"[Generic] Final product count: {len(all_products)}")

    return add_metadata(ScrapeResult(all_products, pages_scraped, pages, page_product_counts), website_name)
