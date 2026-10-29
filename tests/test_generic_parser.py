import json

from scraper.parsers.generic import parse_products


def test_product_jsonld_with_graph_and_multiple_offers():
    data = {
        "@context": "https://schema.org",
        "@graph": [{
            "@type": "Product",
            "name": "Trail Pack",
            "url": "/gear/trail-pack",
            "category": ["Outdoor", "Packs"],
            "aggregateRating": {"ratingValue": "4.7"},
            "offers": [
                {"@type": "Offer", "price": "89.95", "priceCurrency": "USD", "availability": "https://schema.org/InStock"}
            ],
        }],
    }
    products = parse_products(
        f'<script type="application/ld+json">{json.dumps(data)}</script>',
        "https://shop.example.com/",
    )
    assert products == [{
        "product_name": "Trail Pack", "price": "89.95", "currency": "USD",
            "rating": "4.7", "availability": "InStock", "category": "Outdoor / Packs",
        "discount": None,
        "product_link": "https://shop.example.com/gear/trail-pack",
    }]


def test_itemlist_with_linked_products_and_listitem_urls():
    data = {
        "@type": "ItemList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "item": {"@type": "Product", "name": "Mug", "url": "/mug", "offers": {"price": "12", "priceCurrency": "EUR"}}},
            {"position": 2, "name": "Tea tin", "url": "/tea"},
        ],
    }
    products = parse_products(
        f'<script type="application/ld+json">{json.dumps(data)}</script>',
        "https://shop.example.com/catalog/",
    )
    assert [product["product_name"] for product in products] == ["Mug", "Tea tin"]
    assert products[0]["price"] == "12"
    assert products[0]["currency"] == "EUR"
    assert products[1]["product_link"] == "https://shop.example.com/tea"


def test_meta_and_html_detail_page_fallbacks():
    meta = parse_products('<meta property="og:title" content="Canvas Bag"><meta property="product:price:amount" content="24.50">', "https://shop.example.com/bag")
    assert meta[0]["product_name"] == "Canvas Bag"
    assert meta[0]["price"] == "24.50"
    html = parse_products('<main><h1>Wool Hat</h1><span class="price">£18.00</span></main>', "https://shop.example.com/hat")
    assert html[0]["product_name"] == "Wool Hat"
    assert html[0]["price"] == "18.00"
    assert html[0]["currency"] == "GBP"


def test_prices_support_common_thousands_and_decimal_separators():
    html = '''<script type="application/ld+json">
    {"@type":"Product","name":"Camera","offers":{"price":"1.299,99","priceCurrency":"EUR"}}
    </script>'''
    assert parse_products(html, "https://shop.example/camera")[0]["price"] == "1299.99"


def test_itemlist_product_is_enriched_from_same_site_detail_page(monkeypatch):
    import scraper.scraper as scraper_module

    listing = '''<script type="application/ld+json">{"@type":"ItemList","itemListElement":[
      {"@type":"ListItem","item":{"@type":"Product","name":"Desk Lamp","url":"/lamp"}}]}</script>'''
    detail = '''<script type="application/ld+json">{"@type":"Product","name":"Desk Lamp","offers":{"price":"35.00","priceCurrency":"USD"},"aggregateRating":{"ratingValue":"4.6"}}</script>'''
    monkeypatch.setattr(scraper_module, "validate_public_url", lambda url: url)
    monkeypatch.setattr(scraper_module, "fetch_page", lambda url: listing if url.endswith("category") else detail)
    products = scraper_module.scrape_products("https://shop.example/category")
    assert products[0]["price"] == "35.00"
    assert products[0]["currency"] == "USD"
    assert products[0]["rating"] == "4.6"


def test_detail_price_is_not_applied_to_a_different_variant(monkeypatch):
    import scraper.scraper as scraper_module

    listing = '''<script type="application/ld+json">{"@type":"ItemList","itemListElement":[
      {"@type":"ListItem","item":{"@type":"Product","name":"Apple iPhone 18 Pro Max (Black, 256 GB)","url":"/iphone"}}]}</script>'''
    detail = '''<script type="application/ld+json">{"@type":"Product","name":"Apple iPhone 18 Pro (Black, 256 GB)","offers":{"price":"164900","priceCurrency":"INR"}}</script>'''
    monkeypatch.setattr(scraper_module, "validate_public_url", lambda url: url)
    monkeypatch.setattr(scraper_module, "fetch_page", lambda url: listing if url.endswith("category") else detail)

    products = scraper_module.scrape_products("https://shop.example/category")

    assert products[0]["product_name"] == "Apple iPhone 18 Pro Max (Black, 256 GB)"
    assert products[0]["price"] is None


def test_optional_detail_enrichment_returns_collected_products_on_deadline(monkeypatch):
    import scraper.scraper as scraper_module

    listing = '''<script type="application/ld+json">{"@type":"ItemList","itemListElement":[
      {"@type":"ListItem","item":{"@type":"Product","name":"Desk Lamp","url":"/lamp"}}]}</script>'''

    def fetch(url):
        if url.endswith("category"):
            return listing
        raise scraper_module.AnalysisTimeout("Analysis timed out while contacting the website.")

    monkeypatch.setattr(scraper_module, "validate_public_url", lambda url: url)
    monkeypatch.setattr(scraper_module, "fetch_page", fetch)

    products = scraper_module.scrape_products("https://shop.example/category")

    assert len(products) == 1
    assert products[0]["product_name"] == "Desk Lamp"
    assert products[0]["price"] is None


def test_javascript_fallback_runs_when_static_html_has_no_products(monkeypatch):
    import scraper.scraper as scraper_module

    rendered = '''<script type="application/ld+json">
    {"@type":"Product","name":"Rendered kettle","offers":{"price":"42.00","priceCurrency":"USD"}}
    </script>'''
    calls = []
    monkeypatch.setattr(scraper_module, "validate_public_url", lambda url: url)
    monkeypatch.setattr(scraper_module, "fetch_page", lambda _url: "<html><body><div id='app'></div></body></html>")
    monkeypatch.setattr(scraper_module, "render_page", lambda url: calls.append(url) or rendered)

    products = scraper_module.scrape_products("https://shop.example/category")

    assert calls == ["https://shop.example/category"]
    assert products[0]["product_name"] == "Rendered kettle"
    assert products[0]["price"] == "42.00"



def test_requested_page_limit_stops_at_last_available_page(monkeypatch):
    import scraper.scraper as scraper_module

    def product(name, price, next_href=None):
        data = {"@type": "Product", "name": name,
                "offers": {"price": str(price), "priceCurrency": "USD"}}
        next_link = f'<a rel="next" href="{next_href}">Next</a>' if next_href else ""
        return f'<script type="application/ld+json">{json.dumps(data)}</script>' + next_link

    page_one = product("Page one kettle", 20, "?page=2")
    page_two = product("Page two kettle", 25)
    monkeypatch.setattr(scraper_module, "validate_public_url", lambda url: url)
    monkeypatch.setattr(scraper_module, "fetch_page", lambda url: page_one if "page=2" not in url else page_two)
    result = scraper_module.scrape_products("https://shop.example/search", pages=5)

    assert [item["product_name"] for item in result] == ["Page one kettle", "Page two kettle"]
    assert result.pages_scraped == 2
    assert result.pages_requested == 5
    assert result.page_product_counts == [1, 1]


def test_missing_later_page_returns_products_from_pages_already_scraped(monkeypatch):
    import scraper.scraper as scraper_module

    data = {"@type": "Product", "name": "Available kettle",
            "offers": {"price": "20", "priceCurrency": "USD"}}
    page_one = f'<script type="application/ld+json">{json.dumps(data)}</script><a rel="next" href="?page=2">Next</a>'

    def fetch(url):
        if "page=2" in url:
            raise RuntimeError("The website returned an HTTP error: 404 Not Found")
        return page_one

    monkeypatch.setattr(scraper_module, "validate_public_url", lambda url: url)
    monkeypatch.setattr(scraper_module, "fetch_page", fetch)
    result = scraper_module.scrape_products("https://shop.example/search", pages=4)

    assert len(result) == 1
    assert result[0]["product_name"] == "Available kettle"
    assert result.pages_scraped == 1
    assert result.pages_requested == 4



def test_detail_enrichment_continues_past_30_products(monkeypatch):
    import scraper.scraper as scraper_module

    items = [
        {"@type": "ListItem", "item": {
            "@type": "Product", "name": f"Catalog item {index}",
            "url": f"/product/{index}",
        }}
        for index in range(31)
    ]
    listing = '<script type="application/ld+json">' + json.dumps({
        "@type": "ItemList", "itemListElement": items,
    }) + '</script>'

    def fetch(url):
        if url.endswith("/category"):
            return listing
        index = url.rsplit("/", 1)[-1]
        product = {"@type": "Product", "name": f"Catalog item {index}",
                   "offers": {"price": str(10 + int(index)), "priceCurrency": "USD"}}
        return '<script type="application/ld+json">' + json.dumps(product) + '</script>'

    monkeypatch.setattr(scraper_module, "validate_public_url", lambda url: url)
    monkeypatch.setattr(scraper_module, "fetch_page", fetch)
    monkeypatch.setattr(scraper_module, "render_page", lambda _url: None)
    products = scraper_module.scrape_products("https://shop.example/category")

    assert len(products) == 31
    assert all(product["price"] is not None for product in products)
