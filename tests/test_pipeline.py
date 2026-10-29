import pandas as pd
import pytest

from scraper.fetcher import fetch_page
from scraper.parser import parse_products
from analysis.price_analysis import (
    clean_product_data,
    calculate_price_statistics
)


def test_invalid_url():
    with pytest.raises(ValueError):
        fetch_page("not-a-valid-url")


def test_parser_missing_fields():
    html = open(
        "tests/missing_fields.html",
        encoding="utf-8"
    ).read()

    products = parse_products(html)

    assert len(products) == 1
    assert products[0]["product_name"] == "Test Book"
    assert products[0]["price"] == ""
    assert products[0]["rating"] is None


def test_invalid_price_is_removed():
    html = open(
        "tests/invalid_price.html",
        encoding="utf-8"
    ).read()

    products = parse_products(html)
    df = clean_product_data(products)

    assert df.empty


def test_duplicate_products_removed():
    products = [
        {
            "product_name": "Book A",
            "price": "£20.00",
            "rating": 4,
            "availability": "In stock",
            "category": "Books",
            "product_link": "https://example.com/book-a"
        },
        {
            "product_name": "Book A",
            "price": "£20.00",
            "rating": 4,
            "availability": "In stock",
            "category": "Books",
            "product_link": "https://example.com/book-a"
        },
        {
            "product_name": "Book B",
            "price": "£30.00",
            "rating": 5,
            "availability": "In stock",
            "category": "Books",
            "product_link": "https://example.com/book-b"
        }
    ]

    df = clean_product_data(products)

    assert len(df) == 2
    assert list(df["product_name"]) == ["Book A", "Book B"]


def test_price_statistics():
    df = pd.DataFrame({
        "product_name": ["A", "B", "C"],
        "price": [10.0, 20.0, 30.0]
    })

    stats = calculate_price_statistics(df)

    assert stats["minimum_price"] == 10.0
    assert stats["maximum_price"] == 30.0
    assert stats["average_price"] == 20.0
    assert stats["price_difference"] == 20.0


def test_empty_price_statistics():
    df = pd.DataFrame({
        "product_name": [],
        "price": []
    })

    stats = calculate_price_statistics(df)

    assert stats["minimum_price"] is None
    assert stats["maximum_price"] is None
    assert stats["average_price"] is None
    assert stats["price_difference"] is None


def test_median_price():
    df = pd.DataFrame({
        "product_name": ["A", "B", "C"],
        "price": [10.0, 20.0, 30.0]
    })

    stats = calculate_price_statistics(df)

    assert stats["median_price"] == 20.0


def test_product_insights():
    from analysis.price_analysis import get_product_insights

    df = pd.DataFrame({
        "product_name": ["Cheap Book", "Best Book", "Expensive Book"],
        "price": [10.0, 25.0, 50.0],
        "rating": [2, 5, 4]
    })

    insights = get_product_insights(df)

    assert (
        insights["highest_rated_product"]["product_name"]
        == "Best Book"
    )

    assert (
        insights["lowest_priced_product"]["product_name"]
        == "Cheap Book"
    )

    assert (
        insights["most_expensive_product"]["product_name"]
        == "Expensive Book"
    )

def test_find_next_page():
    from scraper.scraper import find_next_page

    html = """
    <html>
    <body>
        <ul class="pager">
            <li class="next">
                <a href="page-2.html">next</a>
            </li>
        </ul>
    </body>
    </html>
    """

    result = find_next_page(
        html,
        "https://example.com/catalogue/page-1.html"
    )

    assert result == "https://example.com/catalogue/page-2.html"

def test_find_next_page_when_missing():
    from scraper.scraper import find_next_page

    html = """
    <html>
    <body>
        <ul class="pager">
        </ul>
    </body>
    </html>
    """

    result = find_next_page(
        html,
        "https://example.com/catalogue/page-1.html"
    )

    assert result is None


def test_books_product_links_resolve_relative_to_paginated_url():
    html = '''<article class="product_pod"><h3><a href="sample-book_1/index.html" title="Sample Book"></a></h3>
    <p class="price_color">£10.00</p><p class="star-rating Three"></p></article>'''
    products = parse_products(html, base_url="https://books.toscrape.com/catalogue/page-2.html")
    assert products[0]["product_link"] == "https://books.toscrape.com/catalogue/sample-book_1/index.html"



def test_cleaning_report_counts_duplicates_and_invalid_prices():
    products = [
        {"product_name": "Kettle", "price": "₹100", "product_link": "https://shop.example/kettle"},
        {"product_name": "Kettle", "price": "₹100", "product_link": "https://shop.example/kettle"},
        {"product_name": "Unknown price", "price": "not available", "product_link": "https://shop.example/unknown"},
        {"product_name": "Missing price", "price": None, "product_link": "https://shop.example/missing"},
    ]

    cleaned, report = clean_product_data(products, return_report=True)

    assert len(cleaned) == 1
    assert report == {
        "rows_received": 4,
        "duplicates_removed": 1,
        "invalid_prices_removed": 2,
        "valid_rows": 1,
    }
