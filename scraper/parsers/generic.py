import logging
logger = logging.getLogger(__name__)

"""Generic extraction for Product and ItemList JSON-LD with HTML fallbacks."""

import json
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup


def _types(value):
    return value if isinstance(value, list) else [value]


def _is_type(data, wanted):
    return isinstance(data, dict) and any(
        isinstance(value, str)
        and value.rsplit("/", 1)[-1].lower() == wanted.lower()
        for value in _types(data.get("@type", []))
    )


def _walk(data):
    """Walk JSON-LD arrays and graph containers."""
    if isinstance(data, list):
        for entry in data:
            yield from _walk(entry)
    elif isinstance(data, dict):
        yield data
        for key in ("@graph", "mainEntity", "itemListElement"):
            if key in data:
                yield from _walk(data[key])
        if isinstance(data.get("item"), dict):
            yield from _walk(data["item"])


def _first(value):
    return value[0] if isinstance(value, list) and value else value


def _offer_details(offers):
    offer = _first(offers)

    if not isinstance(offer, dict):
        return None, None, "", None

    spec = _first(offer.get("priceSpecification"))
    if not isinstance(spec, dict):
        spec = {}

    price = offer.get("price", spec.get("price"))
    currency = offer.get("priceCurrency", spec.get("priceCurrency"))
    availability = offer.get("availability", "")

    if isinstance(availability, str):
        availability = availability.rsplit("/", 1)[-1]

    discount = offer.get("discountPercentage", offer.get("discount"))

    if discount is None:
        reference_price = offer.get(
            "highPrice",
            offer.get("listPrice", offer.get("priceBeforeDiscount")),
        )
        try:
            if (
                reference_price is not None
                and price is not None
                and float(reference_price) > float(price)
            ):
                discount = round(
                    (1 - float(price) / float(reference_price)) * 100,
                    2,
                )
        except (TypeError, ValueError):
            discount = None

    return price, currency, availability, discount


def _as_product(data, base_url):
    if not _is_type(data, "Product"):
        return None

    name = data.get("name") or ""
    if isinstance(name, dict):
        name = name.get("name", "")

    price, currency, availability, discount = _offer_details(
        data.get("offers")
    )

    if discount is None:
        discount = data.get("discountPercentage", data.get("discount"))

    aggregate = data.get("aggregateRating")
    rating = (
        aggregate.get("ratingValue")
        if isinstance(aggregate, dict)
        else None
    )

    url = data.get("url") or data.get("@id") or base_url
    category = data.get("category", "")

    if isinstance(category, list):
        category = " / ".join(str(part) for part in category)

    return {
        "product_name": str(name).strip(),
        "price": price,
        "currency": currency,
        "rating": rating,
        "availability": availability,
        "category": category if isinstance(category, str) else "",
        "discount": _normalize_discount(discount),
        "product_link": urljoin(base_url, str(url)),
    }


def _jsonld_products(soup, base_url):
    products = []
    seen = set()

    def add_product(product):
        if not product or not product.get("product_name"):
            return

        key = (
            product["product_name"].casefold(),
            product["product_link"],
        )

        if key not in seen:
            seen.add(key)
            products.append(product)

    for script in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(script.string or script.get_text())
        except (json.JSONDecodeError, TypeError):
            continue

        for node in _walk(data):
            if _is_type(node, "Product"):
                add_product(_as_product(node, base_url))

            elif _is_type(node, "ListItem"):
                nested = node.get("item")

                if isinstance(nested, dict) and _is_type(nested, "Product"):
                    add_product(_as_product(nested, base_url))

                elif isinstance(nested, (str, dict)):
                    item = nested if isinstance(nested, dict) else {}
                    name = item.get("name") or node.get("name")
                    link = (
                        item.get("url")
                        or item.get("@id")
                        or node.get("url")
                        or (nested if isinstance(nested, str) else None)
                    )

                    if name and link:
                        add_product({
                            "product_name": str(name).strip(),
                            "price": None,
                            "currency": None,
                            "rating": None,
                            "availability": "",
                            "category": "",
                            "product_link": urljoin(base_url, str(link)),
                        })

            elif _is_type(node, "ItemList"):
                entries = node.get("itemListElement", [])

                if not isinstance(entries, list):
                    continue

                for entry in entries:
                    if not isinstance(entry, dict):
                        continue

                    item = entry.get("item", entry)

                    if isinstance(item, dict) and _is_type(item, "Product"):
                        add_product(_as_product(item, base_url))
                        continue

                    item_dict = item if isinstance(item, dict) else {}
                    name = item_dict.get("name") or entry.get("name")
                    link = (
                        item_dict.get("url")
                        or item_dict.get("@id")
                        or entry.get("url")
                        or (item if isinstance(item, str) else None)
                    )

                    if name and link:
                        add_product({
                            "product_name": str(name).strip(),
                            "price": None,
                            "currency": None,
                            "rating": None,
                            "availability": "",
                            "category": "",
                            "product_link": urljoin(base_url, str(link)),
                        })

    return products


def _meta_product(soup, base_url):
    def meta(*keys):
        for key in keys:
            tag = (
                soup.find("meta", attrs={"property": key})
                or soup.find("meta", attrs={"name": key})
            )
            if tag and tag.get("content"):
                return tag["content"].strip()
        return ""

    name = meta("og:title", "twitter:title")
    price = meta("product:price:amount", "og:price:amount")

    if not name and not price:
        return None

    return {
        "product_name": name or (
            soup.title.get_text(strip=True) if soup.title else "Product"
        ),
        "price": price or None,
        "currency": meta(
            "product:price:currency", "og:price:currency"
        ) or None,
        "rating": meta("product:rating", "rating") or None,
        "availability": meta("product:availability", "og:availability"),
        "category": meta("product:category", "og:category"),
        "discount": _normalize_discount(
            meta("product:price:discount", "product:discount")
        ) or None,
        "product_link": urljoin(base_url, meta("og:url") or base_url),
    }


def _value(element):
    if not element:
        return ""

    for attr in ("content", "value", "data-price", "data-value"):
        if element.get(attr):
            return str(element[attr]).strip()

    return element.get_text(" ", strip=True)


def _select_text(root, selectors):
    for selector in selectors:
        result = _value(root.select_one(selector))
        if result:
            return result
    return ""


def _html_products(soup, base_url):
    """Extract products from common product cards and Flipkart cards."""

    selectors = (
        "[itemtype*=Product]",
        "[data-product]",
        ".product-card",
        ".product-item",
        ".product-tile",
        ".product",
        "article",
        "div._1AtVbE",
        "div[data-id]",
    )

    # Price selectors include common generic and Flipkart markup.
    price_selectors = (
        "[itemprop=price]",
        "[data-price]",
        ".price",
        ".product-price",
        ".sale-price",
        ".current-price",
        "._30jeq3",
        ".Nx9bqj",
        "[class*='price']",
    )

    for selector in selectors:
        products = []
        seen = set()

        for card in soup.select(selector):
            link = card.select_one("a[href]")

            name = _select_text(
                card,
                (
                    "[itemprop=name]",
                    ".product-title",
                    ".product-name",
                    "._4rR01T",
                    ".s1Q9rs",
                    "h2",
                    "h3",
                    "h4",
                ),
            )

            name = name or (
                link.get("title", "").strip() if link else ""
            )
            name = name or (
                link.get_text(" ", strip=True) if link else ""
            )

            if not name:
                continue

            price = _select_text(card, price_selectors)

            if len(products) < 3:
                logger.debug("\n===== CARD PRICE INSPECTION =====")
                logger.debug("Product:", name)
                logger.debug("Price found:", repr(price))
                logger.debug("Card classes:", card.get("class"))
                logger.debug("Card HTML:", str(card)[:2500])
                logger.debug("=================================\n")

            # Avoid returning nested card containers multiple times.
            href = link.get("href") if link else base_url
            product_link = urljoin(base_url, href)
            key = (name.casefold(), product_link)

            if key in seen:
                continue
            seen.add(key)

            discount = _select_text(
                card,
                (
                    "[itemprop=discount]",
                    ".discount-percent",
                    ".discount",
                    ".save-percent",
                ),
            )

            rating = _select_text(
                card,
                (
                    "[itemprop=ratingValue]",
                    ".rating",
                    ".product-rating",
                    ".stars",
                ),
            )

            availability = _select_text(
                card,
                (
                    "[itemprop=availability]",
                    ".availability",
                    ".stock",
                    ".in-stock",
                ),
            )

            products.append({
                "product_name": name,
                "price": _normalize_price(price) if price else None,
                "currency": _currency(price),
                "rating": rating or None,
                "availability": availability,
                "category": "",
                "discount": _normalize_discount(discount) or None,
                "product_link": product_link,
            })

        if products:
            return products

    # Product-detail fallback.
    name = _select_text(
        soup,
        ("[itemprop=name]", "h1", ".product-title", ".product-name"),
    )
    price = _select_text(soup, price_selectors)

    if name and price:
        return [{
            "product_name": name,
            "price": _normalize_price(price),
            "currency": _currency(price),
            "rating": _select_text(
                soup, ("[itemprop=ratingValue]", ".rating")
            ) or None,
            "availability": _select_text(
                soup, ("[itemprop=availability]", ".availability")
            ),
            "category": "",
            "discount": None,
            "product_link": base_url,
        }]

    return []


def _currency(value):
    value = str(value or "")

    for token, currency in (
        ("₹", "INR"),
        ("Rs", "INR"),
        ("£", "GBP"),
        ("€", "EUR"),
        ("$", "USD"),
    ):
        if token in value:
            return currency

    return None


def _normalize_price(value):
    if value is None:
        return None

    match = re.search(r"-?\d[\d,.]*", str(value))
    if not match:
        return value

    number = match.group(0)

    if "." in number and "," in number:
        decimal = "." if number.rfind(".") > number.rfind(",") else ","
        thousands = "," if decimal == "." else "."
        number = number.replace(thousands, "").replace(decimal, ".")

    elif "," in number:
        tail = number.rsplit(",", 1)[1]
        number = number.replace(
            ",",
            "." if len(tail) in (1, 2) else "",
        )

    return number


def _normalize_discount(value):
    if value is None or value == "":
        return None

    match = re.search(r"\d+(?:[.,]\d+)?", str(value))
    if not match:
        return None

    try:
        return float(match.group(0).replace(",", "."))
    except ValueError:
        return None


def parse_products(html, base_url=""):
    """Extract structured data first, then metadata and HTML cards."""

    soup = BeautifulSoup(html or "", "html.parser")

    products = _jsonld_products(soup, base_url)

    if not products:
        product = _meta_product(soup, base_url)
        products = [product] if product else _html_products(soup, base_url)

    for product in products:
        if not product.get("currency"):
            product["currency"] = _currency(product.get("price"))

        product["price"] = _normalize_price(product.get("price"))
        product["product_link"] = urljoin(
            base_url,
            product.get("product_link") or base_url,
        )

    return products
