from bs4 import BeautifulSoup


RATING_MAP = {
    "One": 1,
    "Two": 2,
    "Three": 3,
    "Four": 4,
    "Five": 5
}


def parse_products(html, base_url="https://books.toscrape.com/"):
    """
    Extract multiple products from a Books to Scrape page.
    """

    soup = BeautifulSoup(html, "html.parser")

    products = []

    product_cards = soup.select("article.product_pod")

    for card in product_cards:

        name_element = card.select_one("h3 a")
        name = name_element.get("title", "").strip() if name_element else ""

        price_element = card.select_one("p.price_color")
        price = price_element.get_text(strip=True) if price_element else ""

        availability_element = card.select_one("p.instock.availability")
        availability = (
            availability_element.get_text(" ", strip=True)
            if availability_element
            else ""
        )

        rating_element = card.select_one("p.star-rating")

        rating = None

        if rating_element:
            rating_classes = rating_element.get("class", [])

            for rating_name, rating_value in RATING_MAP.items():
                if rating_name in rating_classes:
                    rating = rating_value
                    break

        if name_element and name_element.get("href"):
            link = name_element["href"]

            if link.startswith("http"):
                product_link = link
            else:
                product_link = base_url.rstrip("/") + "/" + link.lstrip("/")
        else:
            product_link = ""

        products.append({
            "product_name": name,
            "price": price,
            "rating": rating,
            "availability": availability,
            "category": "Books",
            "product_link": product_link
        })

    return products
