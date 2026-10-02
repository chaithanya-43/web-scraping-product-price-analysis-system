from scraper.fetcher import fetch_page
from scraper.parser import parse_product


def scrape_product(url):
    """
    Fetch a webpage and extract product information.
    """

    html = fetch_page(url)

    product = parse_product(html)

    product["product_link"] = url

    return product