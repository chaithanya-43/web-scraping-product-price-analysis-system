from bs4 import BeautifulSoup
from urllib.parse import urljoin


RATING_MAP = {
    "★☆☆☆☆": 1,
    "★★☆☆☆": 2,
    "★★★☆☆": 3,
    "★★★★☆": 4,
    "★★★★★": 5
}


def parse_products(
    html,
    base_url="https://testingurl.dev/"
):
    """
    Extract products from TestingURL.dev ecommerce pages.
    """

    soup = BeautifulSoup(html, "html.parser")

    products = []

    product_links = soup.select("a")

    for link_element in product_links:

        text = link_element.get_text(" ", strip=True)

        if "$" not in text:
            continue

        href = link_element.get("href")

        if not href:
            continue

        product_name = ""
        price = ""
        rating = None

        parts = text.split("$", 1)

        product_name = parts[0].strip()

        price_and_rating = parts[1].strip()

        price_parts = price_and_rating.split("·", 1)

        price = "$" + price_parts[0].strip()

        if len(price_parts) > 1:
            rating_text = price_parts[1].strip()

            rating = RATING_MAP.get(rating_text)

        product_link = urljoin(
            base_url,
            href
        )

        products.append({
            "product_name": product_name,
            "price": price,
            "rating": rating,
            "availability": "",
            "category": "Laptops",
            "product_link": product_link
        })

    return products