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
