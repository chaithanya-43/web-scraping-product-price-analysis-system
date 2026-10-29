from urllib.parse import urlparse


SUPPORTED_SOURCES = {
    "books.toscrape.com": "books_to_scrape",
    "testingurl.dev": "testingurl"
}


def detect_source(url):
    """
    Identify which supported scraper should be used
    for the supplied URL.
    """

    parsed_url = urlparse(url)
    hostname = parsed_url.netloc.lower()

    if hostname.startswith("www."):
        hostname = hostname[4:]

    for domain, source_name in SUPPORTED_SOURCES.items():
        if hostname == domain or hostname.endswith("." + domain):
            return source_name

    return None
